# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# encoding: utf-8

"""Rackspace Cloud Databases provider tasks."""

import logging

from celery import task

from checkmate.common import statsd
from checkmate.deployments import tasks
from checkmate import exceptions
from checkmate import middleware
from checkmate.providers import base
from checkmate.providers.rackspace.database import dbaas
from checkmate.providers.rackspace.database import provider
from checkmate import utils

LOG = logging.getLogger(__name__)


@task.task(base=base.RackspaceProviderTask, default_retry_delay=10,
           max_retries=2, provider=provider.Provider)
@statsd.collect
def create_configuration(context, name, db_type, db_version, config_params):
    """Create a database configuration entry."""
    return dbaas.create_configuration(context, name, db_type, db_version,
                                      config_params)


@task.task(base=base.RackspaceProviderTask, default_retry_delay=30,
           max_retries=120, acks_late=True, provider=provider.Provider)
@statsd.collect
def wait_on_status(context, instance=None, status='ACTIVE'):
    """Wait for instance status change to expected (ACTIVE by default).

    :param context: Context
    :param instance: Instance Information
    :param status: Status being waited for (expected)
    :return:
    """
    data = {}
    if isinstance(instance, dict) and not context.region:
        context.region = instance.get('region')
    try:
        if context.simulation:
            data['status'] = status
        else:
            details = dbaas.get_instance(context, instance.get('id'))
            data['status'] = details.get('instance', {}).get('status')
    except (StandardError, dbaas.CDBException) as exc:
        if status == 'DELETED' and str(exc).startswith('404 Not Found'):
            data['status'] = 'DELETED'
        else:
            data['status'] = 'ERROR'
            data['status-message'] = ('Error waiting on resource status %s' %
                                      status)
            data['error-message'] = exc.message
            wait_on_status.partial(data)
            raise

    if data['status'] == 'ERROR':
        data['status-message'] = 'Instance went into status ERROR'
        wait_on_status.partial(data)
        exc = exceptions.CheckmateException(
            data['status-message'],
            friendly_message=data['status-message'],
            options=exceptions.CAN_RESET)
        raise exc
    elif data['status'] in ['ACTIVE', 'DELETED']:
        data['status-message'] = ''
    else:
        data['status-message'] = ('DB instance in status %s. Waiting for '
                                  'status %s.' % (data['status'], status))
        wait_on_status.partial(data)
        msg = 'DB instance in status %s' % data['status']
        info = 'Database status is not %s' % status
        raise exceptions.CheckmateException(
            msg,
            friendly_message=info,
            options=exceptions.CAN_RESUME)
    return data


@task.task(base=base.RackspaceProviderTask, provider=provider.Provider)
@statsd.collect
def sync_resource_task(context, resource):
    """Task to handle syncing remote status with checkmate status."""
    if context.simulation:
        status = resource.get('status') or 'ACTIVE'
        results = {'status': status}
    else:
        instance = resource.get("instance") or {}
        instance_id = instance.get("id")
        try:
            if not instance_id:
                raise exceptions.CheckmateDoesNotExist("Instance is blank or "
                                                       "has no ID.")
            db_instance = dbaas.get_instance(context, instance_id)
            status = (db_instance.get('instance') or {}).get('status')
            LOG.info("Marking database instance %s as %s", instance_id,
                     status)
            results = {'status': status}
        except (dbaas.CDBException, exceptions.CheckmateDoesNotExist):
            LOG.info("Marking database instance %s as DELETED",
                     instance_id)
            results = {'status': 'DELETED'}
    return results


@task.task(base=base.RackspaceProviderTask, default_retry_delay=10,
           max_retries=2, provider=provider.Provider)
@statsd.collect
def create_instance(context, instance_name, desired_state, config_id=None,
                    replica_of=None):
    """Create a Cloud Database instance with options in desired_state."""
    try:
        instance = dbaas.create_instance(
            context, instance_name, desired_state.get('flavor'),
            size=desired_state.get('disk'),
            config_id=config_id,
            dstore_type=desired_state.get('datastore-type'),
            dstore_ver=desired_state.get('datastore-version'),
            databases=desired_state.get('databases'),
            users=desired_state.get('users'),
            replica_of=replica_of
        )
    except dbaas.CDBException as exc:
        raise exceptions.CheckmateException(
            str(exc), options=exceptions.CAN_RETRY)
    except Exception as exc:
        raise exceptions.CheckmateException(str(exc))

    create_instance.partial({'id': instance.get('id')})

    LOG.info("Created database instance %s (%s). Size %s, Flavor %s. "
             "Databases = %s", instance.get('name'), instance.get('id'),
             desired_state.get('disk'), desired_state.get('flavor'),
             desired_state.get('databases'))

    return instance


# pylint: disable=R0913
@task.task(base=base.RackspaceProviderTask, default_retry_delay=15,
           max_retries=40, provider=provider.Provider)
@statsd.collect
def create_database(context, name, character_set=None, collate=None,
                    instance_id=None, replica=False):
    """Create a database resource.

    This call also creates a server instance if it is not supplied.

    :param name: the database name
    :param region: where to create the database (ex. DFW or dallas)
    :param character_set: character set to use (see MySql and cloud databases
            documanetation)
    :param collate: collation to use (see MySql and cloud databases
            documanetation)
    :param instance_id: create the database on a specific instance id (if not
            supplied, the instance is created)
    """
    database = {'name': name}
    if character_set:
        database['character_set'] = character_set
    if collate:
        database['collate'] = collate
    databases = [database]

    if context.simulation:
        status = 'ACTIVE'
        instance = {
            'flavor': {'id': '1'},
            'hostname': 'srv2.rackdb.net',
            'port': 3306
        }
    else:
        instance = dbaas.get_instance(context, instance_id)
        instance = instance.get('instance') or {}
        status = instance.get('status')
        instance_id = instance.get('id')
        create_database.partial({'status': status})

        if status != "ACTIVE":
            raise exceptions.CheckmateException('Database instance is not '
                                                'active.',
                                                options=exceptions.CAN_RESUME)
        if not replica:  # No need to create db if it's a replica
            status = 'BUILD'
            try:
                dbaas.create_database(context, instance_id, databases)
            except dbaas.CDBException as exc:
                LOG.exception(exc)
                if str(exc).startswith('400'):
                    raise
                else:
                    raise exceptions.CheckmateException(
                        str(exc), options=exceptions.CAN_RESUME)
            except Exception as exc:
                raise exceptions.CheckmateException(str(exc))

    LOG.info('Created database %s on instance %s', name, instance_id)
    return {
        'host_instance': instance_id,
        'host_region': context.region,
        'name': name,
        'id': name,
        'status': status,
        'flavor': (instance.get('flavor') or {}).get('id'),
        'interfaces': {
            'mysql': {
                'host': instance.get('hostname'),
                'database_name': name,
                'port': instance.get('port', 3306)
            }
        }
    }


@task.task(base=base.RackspaceProviderTask, default_retry_delay=10,
           max_retries=2, provider=provider.Provider)
def add_user(context, instance_id, databases, username, password,
             replica=False):
    """Add a database user to an instance for one or more databases."""
    if context.simulation:
        status = 'ACTIVE'
        instance = {'hostname': 'srv0.rackdb.net'}
    else:
        try:
            instance = dbaas.get_instance(context, instance_id)
            instance = instance.get('instance') or {}
            status = instance.get('status')
        except dbaas.CDBException as exc:
            raise exceptions.CheckmateException(
                str(exc), friendly_message="Error in database provider",
                options=exceptions.CAN_RESUME)

        add_user.partial({'status': status})

        if status != "ACTIVE":
            raise exceptions.CheckmateException('Database instance is '
                                                'not active.',
                                                options=exceptions.CAN_RESUME)
        if not replica:  # No need to create user on replica db
            try:
                user_info = {'name': username, 'password': password}
                if databases:
                    user_info['databases'] = [{'name': n} for n in databases]
                dbaas.create_user(context, instance_id, user_info)
            except dbaas.CDBException as exc:
                raise exceptions.CheckmateException(
                    str(exc), options=exceptions.CAN_RESUME)
            except Exception as exc:
                raise exceptions.CheckmateException(
                    str(exc), options=exceptions.CAN_RESUME)

            LOG.info('Added user %s to %s on instance %s', username,
                     databases, instance_id)
    return {
        'username': username,
        'password': password,
        'status': 'ACTIVE',
        'interfaces': {
            'mysql': {
                'host': instance.get('hostname'),
                'database_name': databases[0],
                'username': username,
                'password': password,
            }
        }
    }


@task.task(base=base.RackspaceProviderTask, default_retry_delay=2,
           max_retries=60, provider=provider.Provider)
@statsd.collect
def delete_instance_task(context, deployment_id, resource, key):
    """Delete a database server instance, its databases and users."""
    utils.match_celery_logging(LOG)

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        dep_id = args[0].get('deployment_id')
        key = args[0].get('resource_key')
        if dep_id and key:
            ret = {
                'resources': {
                    key: {
                        'status': 'ERROR',
                        'status-message': (
                            'Unexpected error while deleting '
                            'database instance %s' % key
                        ),
                        'error-message': str(exc)
                    }
                }
            }
            tasks.resource_postback.delay(dep_id, ret)
        else:
            LOG.error("Missing deployment id and/or resource key in "
                      "delete_instance error callback.")

    delete_instance_task.on_failure = on_failure

    instance_id = (resource.get('instance') or {}).get('id')
    if not instance_id:
        msg = ("Instance ID is not available for Database server Instance, "
               "skipping delete_instance_task for resource %s in deployment "
               "%s" % (key, deployment_id))
        res = {'resources': {key: {'status': 'DELETED'}}}
        for hosted in resource.get('hosts', []):
            res['resources'][hosted] = {'status': 'DELETED'}
        LOG.info(msg)
        tasks.resource_postback.delay(deployment_id, res)
        return

    if isinstance(context, dict):
        context = middleware.RequestContext(**context)

    if context.simulation:
        results = {'resources': {key: {'status': 'DELETED'}}}
        for hosted in resource.get('hosts', []):
            results['resources'][hosted] = {
                'status': 'DELETED',
                'status-message': ''
            }
        # Send data back to deployment
        tasks.resource_postback.delay(deployment_id, results)
        return results

    res = {}
    try:
        dbaas.delete_instance(context, instance_id)
        LOG.info('Database instance %s deleted.', instance_id)
        res = {'resources': {key: {'status': 'DELETING'}}}
        for hosted in resource.get('hosts', []):
            res['resources'][hosted] = {
                'status': 'DELETED',
                'status-message': 'Host is being deleted'
            }
    except dbaas.CDBException as exc:
        if str(exc).startswith('404 Not Found'):  # already deleted
            res = {
                'resources': {
                    key: {
                        'status': 'DELETED',
                        'status-message': ''
                    }
                }
            }
            for hosted in resource.get('hosts', []):
                res['resources'][hosted] = {
                    'status': 'DELETED',
                    'status-message': ''
                }
        else:
            delete_instance_task.retry(exc=exc)
    except Exception as exc:
        # might be a service fluke, try again
        delete_instance_task.retry(exc=exc)
    tasks.resource_postback.delay(deployment_id, res)
    return res


@task.task(base=base.RackspaceProviderTask, default_retry_delay=2,
           max_retries=30, provider=provider.Provider)
@statsd.collect
def delete_database(context, deployment_id, resource, key):
    """Delete a database from an instance."""
    utils.match_celery_logging(LOG)

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        dep_id = args[0].get('deployment_id')
        key = args[0].get('resource_key')
        if dep_id and key:
            ret = {
                'resources': {
                    key: {
                        'status': 'ERROR',
                        'status-message': (
                            'Unexpected error while deleting '
                            'database %s' % key
                        ),
                        'error-message': str(exc)
                    }
                }
            }
            tasks.resource_postback.delay(dep_id, ret)
        else:
            LOG.error("Missing deployment id and/or resource key in "
                      "delete_database error callback.")

    delete_database.on_failure = on_failure

    instance = resource.get("instance")
    host_instance = resource.get("host_instance")
    if not (instance and host_instance):
        msg = ("Cannot find instance/host-instance for database to delete. "
               "Skipping delete_database call for resource %s in deployment "
               "%s - Instance Id: %s, Host Instance Id: %s" %
               (key, deployment_id, instance,
                host_instance))
        results = {
            'resources': {
                key: {
                    'status': 'DELETED',
                    'status-message': msg
                }
            }
        }
        LOG.info(msg)
        tasks.resource_postback.delay(deployment_id, results)
        return

    db_name = (resource.get('instance') or {}).get('name')
    instance_id = (resource.get('instance') or {}).get('host_instance')
    status = None
    try:
        result = dbaas.get_instance(context, instance_id)
        if 'instance' in result:
            status = result['instance'].get('status')
    except dbaas.CDBException as exc:
        if str(exc).startswith('404 Not Found'):
            status = 'DELETED'
        else:
            delete_database.retry(exc=exc)
    if status == 'DELETED':
        # instance is gone, so is the db
        return {
            'resources': {
                key: {
                    'status': 'DELETED',
                    'status-message': (
                        'Host %s was deleted' % resource.get('hosted_on')
                    )
                }
            }
        }
    elif status == 'BUILD':  # can't delete when instance in BUILD
        delete_database.retry(exc=exceptions.CheckmateException(
            "Waiting on instance to be out of BUILD status"))
    try:
        dbaas.delete_database(context, instance_id, db_name)
    except dbaas.CDBException as exc:
        delete_database.retry(exc=exc)
    LOG.info('Database %s deleted from instance %s', db_name, instance_id)
    ret = {'resources': {key: {'status': 'DELETED'}}}
    tasks.resource_postback.delay(deployment_id, ret)
    return ret


@task.task(base=base.RackspaceProviderTask, default_retry_delay=10,
           max_retries=10, provider=provider.Provider)
@statsd.collect
def delete_user(context, instance_id, username):
    """Delete a database user from an instance."""
    utils.match_celery_logging(LOG)

    dbaas.delete_user(context, instance_id, username)
    LOG.info('Deleted user %s from database instance %s', username,
             instance_id)


@task.task(base=base.RackspaceProviderTask, default_retry_delay=10,
           max_retries=10, provider=provider.Provider)
@statsd.collect
def delete_configuration(context, config_id, resource):
    """Delete database configuration referenced by config_id.

    Note: region is set to `None` when the database instance is deleted
    so we need to grab it from the resource. Of the two possibilies - one in
    'instance' and one in 'desired-state' - 'instance' seems the more
    appropriate choice, as indicated in the region assignment line below.
    """
    region = (
        (resource.get('instance') or {}).get('region') or
        (resource.get('desired-state') or {}).get('region')
    )
    if isinstance(context, dict):
        context['region'] = region or context.get('region')
        context = middleware.RequestContext(**context)
    utils.match_celery_logging(LOG)
    try:
        dbaas.delete_configuration(context, config_id)
        LOG.info('Deleted database configuration %s', config_id)
    except dbaas.CDBException as exc:
        if exc.message.startswith('404 Not Found'):  # pylint: disable=E1101
            LOG.info('Database configuration %s does not exist.', config_id)
        else:
            delete_configuration.retry(exc=exc)
