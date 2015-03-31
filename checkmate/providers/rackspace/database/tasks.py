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
from pyrax import exceptions as pyexc

from checkmate.common import statsd
from checkmate.deployments import tasks
from checkmate import exceptions
from checkmate.providers import base
from checkmate.providers.rackspace.database import dbaas
from checkmate.providers.rackspace.database import manager
from checkmate.providers.rackspace.database import provider
from checkmate import utils

LOG = logging.getLogger(__name__)


class DBAASContext(object):

    """Bare-bones context.

    Since the passed-in context was changed to a dict by
    `delete_resource_tasks`, DBAASContext is used to set the attributes
    expected by dbaas. This is temporary, as once the database
    provider refactor is complete all tasks will use a proper context.
    """

    def __init__(self, context, region=None):
        """Class initializer."""
        self.region = region or context.get('region')
        self.tenant = context.get('tenant')
        self.auth_token = context.get('auth_token')


@task.task(base=base.RackspaceProviderTask, default_retry_delay=10,
           max_retries=2, provider=provider.Provider)
@statsd.collect
def create_configuration(context, db_type, db_version, config_params):
    """Create a database configuration entry."""
    return dbaas.create_configuration(context, db_type, db_version,
                                      config_params)


# Disable pylint on api and callback as their passed in from ProviderTask
# pylint: disable=W0613
@task.task(base=base.RackspaceProviderTask, default_retry_delay=30,
           max_retries=120, acks_late=True, provider=provider.Provider)
@statsd.collect
def wait_on_build(context, instance=None, callback=None):
    """Wait on instance to be created, delete instance if it errors.

    :param context: Context
    :param instance: Instance Information
    :param api:
    :param callback:
    :return:
    """
    return manager.Manager.wait_on_build(context, instance["id"],
                                         wait_on_build.partial,
                                         simulate=context.simulation)


# Disable on api and callback.  Suppress num args
# pylint: disable=W0613
@task.task(base=base.RackspaceProviderTask, provider=provider.Provider)
@statsd.collect
def sync_resource_task(context, resource, api=None, callback=None):
    """Task to handle syncing remote status with checkmate status."""
    return manager.Manager.sync_resource(resource, sync_resource_task.api,
                                         context.simulation)


# Disable pylint on api and callback as their passed in from ProviderTask
# pylint: disable=W0613, R0913
@task.task(base=base.RackspaceProviderTask, default_retry_delay=10,
           max_retries=2, provider=provider.Provider)
@statsd.collect
def create_instance(context, instance_name, desired_state, callback=None,
                    config_id=None):
    """Create a Cloud Database instance with options in desired_state."""
    callback = callback or create_instance.partial
    return manager.Manager.create_instance(context,
                                           instance_name,
                                           desired_state,
                                           callback or create_instance.partial,
                                           config_id=config_id,
                                           simulate=context.simulation)


# pylint: disable=R0913
@task.task(base=base.RackspaceProviderTask, default_retry_delay=15,
           max_retries=40, provider=provider.Provider)
@statsd.collect
def create_database(context, name, region=None, character_set=None,
                    collate=None, instance_id=None, instance_attributes=None,
                    callback=None, api=None):
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
    :param instance_attributes: kwargs used to create the instance (used if
            instance_id not supplied)
    """
    return manager.Manager.create_database(name, instance_id,
                                           create_database.api,
                                           create_database.partial,
                                           context=context,
                                           character_set=character_set,
                                           collate=collate,
                                           instance_attrs=instance_attributes,
                                           simulate=context.simulation)


@task.task(base=base.RackspaceProviderTask, default_retry_delay=10,
           max_retries=2, provider=provider.Provider)
def add_user(context, instance_id, databases, username, password,
             api=None, callback=None):
    """Add a database user to an instance for one or more databases."""
    return manager.Manager.add_user(instance_id, databases, username, password,
                                    add_user.api, add_user.partial,
                                    context.simulation)


@task.task(default_retry_delay=2, max_retries=60)
@statsd.collect
def delete_instance_task(context, api=None):
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

    assert "deployment_id" in context, "No deployment id in context"
    assert 'resource_key' in context, 'No resource key in context'
    assert 'resource' in context, 'No resource defined in context'

    resource = context.get('resource')
    instance = resource.get('instance', {})
    region = instance.get('region') or context.get('region')

    assert 'region' in context, "No region defined in resource or context"
    resource_key = context.get("resource_key")
    deployment_id = context.get("deployment_id")
    instance_id = instance.get('id')
    if not instance_id:
        msg = ("Instance ID is not available for Database server Instance, "
               "skipping delete_instance_task for resource %s in deployment "
               "%s" % (resource_key, deployment_id))
        # TODO(Nate): Clear status-message on delete
        res = {'resources': {resource_key: {'status': 'DELETED'}}}
        for hosted in resource.get('hosts', []):
            res['resources'][hosted] = {'status': 'DELETED'}
        LOG.info(msg)
        tasks.resource_postback.delay(context['deployment_id'], res)
        return

    if context.get('simulation') is True:
        results = {'resources': {resource_key: {'status': 'DELETED'}}}
        for hosted in resource.get('hosts', []):
            results['resources'][hosted] = {
                'status': 'DELETED',
                'status-message': ''
            }
        # Send data back to deployment
        tasks.resource_postback.delay(context['deployment_id'], results)
        return results

    if not api:
        api = provider.Provider.connect(context, region)
    res = {}
    try:
        api.delete(instance_id)
        LOG.info('Database instance %s deleted.', instance_id)
        # TODO(Nate): Add status-message to current resource
        res = {'resources': {resource_key: {'status': 'DELETING'}}}
        for hosted in resource.get('hosts', []):
            res['resources'][hosted] = {
                'status': 'DELETED',
                'status-message': 'Host %s is being deleted'
            }
    except pyexc.NotFound as rese:
        if rese.code == '404':  # already deleted
            # TODO(Nate): Remove status-message on current resource
            res = {
                'resources': {
                    resource_key: {
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
            # not too sure what this is, so maybe retry a time or two
            delete_instance_task.retry(exc=rese)
    except Exception as exc:
        # might be an api fluke, try again
        delete_instance_task.retry(exc=exc)
    tasks.resource_postback.delay(context['deployment_id'], res)
    return res


@task.task(default_retry_delay=5, max_retries=60)
@statsd.collect
def wait_on_del_instance(context, api=None):
    """Wait for the specified instance to be deleted."""
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

    wait_on_del_instance.on_failure = on_failure

    assert 'region' in context, "No region defined in context"
    assert 'resource_key' in context, 'No resource key in context'
    assert 'resource' in context, 'No resource defined in context'

    key = context.get('resource_key')
    resource = context.get('resource')
    instance = resource.get('instance', {})
    region = instance.get('region') or context.get('region')
    instance_id = instance.get('id')
    instance = None
    status = None
    deployment_id = context["deployment_id"]

    if not instance_id or context.get('simulation'):
        msg = ("Instance ID is not available for Database, skipping "
               "wait_on_delete_instance_task for resource %s in deployment "
               "%s" % (key, deployment_id))
        LOG.info(msg)
        results = {
            'resources': {
                key: {
                    'status': 'DELETED',
                    'status-message': msg
                }
            }
        }
        tasks.resource_postback.delay(deployment_id, results)
        return

    if not api:
        api = provider.Provider.connect(context, region)
    try:
        if resource['type'] == 'cache':
            instance = dbaas.get_instance(DBAASContext(context, region=region),
                                          instance_id)
            if 'instance' in instance:
                status = instance['instance']['status']
            elif 'status_code' in instance and instance['status_code'] == 404:
                status = 'DELETED'
            else:
                raise pyexc.NotFound(instance.get('reason'))
        else:
            instance = api.get(instance_id)
            status = instance.status
    except dbaas.CDBException as exc:
        if str(exc) != "404: Not Found":
            raise
    except pyexc.NotFound:
        pass

    if not instance or ('DELETED' == status):
        res = {
            'resources': {
                key: {
                    'status': 'DELETED',
                    'status-message': ''
                }
            }
        }
        for hosted in resource.get('hosts', []):
            res['resources'].update({
                hosted: {
                    'status': 'DELETED',
                    'status-message': ''
                }
            })
    else:
        msg = ("Waiting on state DELETED. Instance %s is in state %s" %
               (key, status))
        res = {
            'resources': {
                key: {
                    'status': 'DELETING',
                    "status-message": msg
                }
            }
        }
        tasks.resource_postback.delay(context['deployment_id'], res)
        wait_on_del_instance.retry(exc=exceptions.CheckmateException(msg))

    tasks.resource_postback.delay(context['deployment_id'], res)
    return res


@task.task(default_retry_delay=2, max_retries=30)
@statsd.collect
def delete_database(context, api=None):
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

    assert 'region' in context, "Region not supplied in context"
    region = context.get('region')
    assert 'resource' in context, "Resource not supplied in context"
    resource = context.get('resource')
    assert 'index' in resource, 'Resource does not have an index'
    key = resource.get('index')

    if not api:
        api = provider.Provider.connect(context, region)

    deployment_id = context["deployment_id"]
    resource_key = context["resource_key"]

    instance = resource.get("instance")
    host_instance = resource.get("host_instance")
    if not (instance and host_instance):
        msg = ("Cannot find instance/host-instance for database to delete. "
               "Skipping delete_database call for resource %s in deployment "
               "%s - Instance Id: %s, Host Instance Id: %s" %
               (resource_key, context["deployment_id"], instance,
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

    db_name = resource.get('instance', {}).get('name')
    instance_id = resource.get('instance', {}).get('host_instance')
    instance = None
    try:
        instance = api.get(instance_id)
    except pyexc.ClientException as respe:
        if respe.code != '404':
            delete_database.retry(exc=respe)
    if not instance or (instance.status == 'DELETED'):
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
    elif instance.status == 'BUILD':  # can't delete when instance in BUILD
        delete_database.retry(exc=exceptions.CheckmateException(
            "Waiting on instance to be out of BUILD status"))
    try:
        instance.delete_database(db_name)
    except pyexc.ClientException as respe:
        delete_database.retry(exc=respe)
    LOG.info('Database %s deleted from instance %s', db_name, instance_id)
    ret = {'resources': {key: {'status': 'DELETED'}}}
    tasks.resource_postback.delay(deployment_id, ret)
    return ret


@task.task(default_retry_delay=10, max_retries=10)
@statsd.collect
def delete_user(context, instance_id, username, region, api=None):
    """Delete a database user from an instance."""
    utils.match_celery_logging(LOG)
    if api is None:
        api = provider.Provider.connect(context, region)

    instance = api.get(instance_id)
    instance.delete_user(username)
    LOG.info('Deleted user %s from database instance %s', username,
             instance_id)


@task.task(default_retry_delay=10, max_retries=10)
@statsd.collect
def delete_configuration(context, config_id):
    """Delete database configuration referenced by config_id.

    Note: region is set to `None` when the database instance is deleted
    so we need to grab it from the resource. Of the two possibilies - one in
    'instance' and one in 'desired-state' - 'instance' seems the more
    appropriate choice, as indicated in the region assignment line below.
    """
    region = context.get('resource', {}).get('instance', {}).get('region')
    context = DBAASContext(context, region=region)
    utils.match_celery_logging(LOG)
    try:
        dbaas.delete_configuration(context, config_id)
        LOG.info('Deleted database configuration %s', config_id)
    except dbaas.CDBException as exc:
        if exc.message.startswith('404'):  # pylint: disable=E1101
            LOG.info('Database configuration %s does not exist.', config_id)
        else:
            raise exc
