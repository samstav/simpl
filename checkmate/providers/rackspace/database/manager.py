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
# pylint: disable=E1103,R0913

"""Rackspace Cloud Databases provider manager."""

import logging

from pyrax import exceptions as cdb_errors

from checkmate import exceptions as cmexc
from checkmate.providers.rackspace.database import dbaas
from checkmate import utils

LOG = logging.getLogger(__name__)


class Manager(object):

    """Database provider model and logic for interaction."""

    @staticmethod
    def wait_on_build(context, instance_id, callback, simulate=False):
        """Check provider resource.

        Returns True when built otherwise False.
        If resource goes into error state, raises exception.
        """
        data = {}
        try:
            if simulate:
                data['status'] = 'ACTIVE'
            else:
                details = dbaas.get_instance(context, instance_id)
                data['status'] = details.get('instance', {}).get('status')
        except cdb_errors.ClientException as exc:
            raise cmexc.CheckmateException(
                str(exc),
                friendly_message="Error occurred in database provider",
                options=cmexc.CAN_RESUME)
        except (StandardError, dbaas.CDBException) as exc:
            data['status'] = 'ERROR'
            data['status-message'] = 'Error waiting on resource to build'
            data['error-message'] = exc.message
            callback(data)
            raise

        if data['status'] == 'ERROR':
            data['status-message'] = 'Instance went into status ERROR'
            callback(data)
            exc = cmexc.CheckmateException(
                data['status-message'],
                friendly_message=data['status-message'],
                options=cmexc.CAN_RESET)
            raise exc
        elif data['status'] in ['ACTIVE', 'DELETED']:
            data['status-message'] = ''
        else:
            callback(data)
            msg = 'DB instance in status %s' % data['status']
            info = 'Database status is not ACTIVE'
            raise cmexc.CheckmateException(
                msg,
                friendly_message=info,
                options=cmexc.CAN_RESUME)

        return data

    @staticmethod
    def sync_resource(resource, api, simulate=False):
        """Syncronize provider status with checkmate resource status."""
        if simulate:
            results = {'status': 'ACTIVE'}
        else:
            instance = resource.get("instance") or {}
            instance_id = instance.get("id")
            try:
                if not api or not instance_id:
                    raise cmexc.CheckmateDoesNotExist("Instance is blank or "
                                                      "has no ID.")
                database = api.get(instance_id)
                LOG.info("Marking database instance %s as %s", instance_id,
                         database.status)
                results = {'status': database.status}
            except (cdb_errors.ClientException, cmexc.CheckmateDoesNotExist):
                LOG.info("Marking database instance %s as DELETED",
                         instance_id)
                results = {'status': 'DELETED'}
        return results

    @staticmethod
    def create_instance(context, instance_name, desired_state, callback,
                        config_id=None, simulate=False, replica_of=None):
        """Create a Cloud Database instance with optional initial databases."""
        try:
            instance = dbaas.create_instance(
                context, instance_name, desired_state.get('flavor'),
                size=desired_state.get('disk'),
                config_id=config_id,
                dstore_type=desired_state.get('datastore-type'),
                dstore_ver=desired_state.get('datastore-version'),
                databases=desired_state.get('databases'),
                users=desired_state.get('users'),
                replica_of=replica_of,
                simulate=simulate
            )
        except dbaas.CDBException as exc:
            raise cmexc.CheckmateException(str(exc), options=cmexc.CAN_RETRY)
        except Exception as exc:
            raise cmexc.CheckmateException(str(exc))

        if callable(callback):
            callback({'id': instance.get('id')})

        LOG.info("Created database instance %s (%s). Size %s, Flavor %s. "
                 "Databases = %s", instance.get('name'), instance.get('id'),
                 desired_state.get('disk'), desired_state.get('flavor'),
                 desired_state.get('databases'))

        return instance

    @staticmethod
    def create_database(name, instance_id, api, callback, context,
                        character_set=None, collate=None, instance_attrs=None,
                        replica=False, simulate=False):
        """Create database in existing db instance.

        Returns instance, dbs and its interfaces. If resource goes into
        error state, raises exception.
        """
        assert api, "API is required in create_database_pop"
        assert callback, 'Callback is required in create_database_pop.'

        database = {'name': name}
        if character_set:
            database['character_set'] = character_set
        if collate:
            database['collate'] = collate
        databases = [database]

        if simulate:
            flavor = utils.Simulation(id='1')
            status = 'ACTIVE'
            instance = utils.Simulation(id=instance_id, name=name,
                                        hostname='srv2.rackdb.net',
                                        flavor=flavor,
                                        port=3306)
        # TODO(Nate): Pretty sure this inst being used.
        elif not instance_id:
            attrs = {'name': '%s_instance' % name, 'flavor': '1', 'size': 1}
            if not instance_attrs:
                instance_attrs = {}
            instance_name, flavor, size = [instance_attrs.get(k, attrs[k]) for
                                           k in ['name', 'flavor', 'size']]

            data = Manager.create_instance(instance_name, flavor, size,
                                           databases, context, api, callback)
            while data.get('status') == 'BUILD':
                try:
                    data.update(Manager.wait_on_build(data.get('id'), api,
                                                      callback))
                except cmexc.CheckmateException as exc:
                    if exc.resumable:
                        LOG.info('DB instance in status %s, waiting on ACTIVE '
                                 'status', data['status'])
            results = data.get('databases', {}).get(name)
            results['host_instance'] = data.get('id')
            results['host_region'] = data.get('region')
            results['flavor'] = flavor
            results['disk'] = size
            return results
        else:
            instance = api.get(instance_id)
            callback({'status': instance.status})

            if instance.status != "ACTIVE":
                raise cmexc.CheckmateException('Database instance is not '
                                               'active.',
                                               options=cmexc.CAN_RESUME)
            status = 'BUILD'
            if replica:
                # It was created as part of the replication process
                status = instance.status
            else:
                try:
                    instance.create_database(name, character_set, collate)
                except cdb_errors.ClientException as exc:
                    LOG.exception(exc)
                    if exc.code == '400':
                        raise
                    else:
                        raise cmexc.CheckmateException(
                            str(exc), options=cmexc.CAN_RESUME)
                except Exception as exc:
                    raise cmexc.CheckmateException(str(exc))

        results = {
            'host_instance': instance.id,
            'host_region': context.region,
            'name': name,
            'id': name,
            'status': status,
            'flavor': instance.flavor.id,
            'interfaces': {
                'mysql': {
                    'host': instance.hostname,
                    'database_name': name,
                    'port': getattr(instance, 'port', 3306)
                }
            }
        }
        LOG.info('Created database %s on instance %s', name, instance_id)
        return results

    @staticmethod
    def add_user(instance_id, databases, username, password,
                 api, callback, simulate=False, replica=False):
        """Add a database user to an instance for one or more databases.

        Returns instance data.
        """
        assert instance_id, "Instance ID not supplied"

        if simulate:
            instance = utils.Simulation(hostname='srv0.rackdb.net',
                                        status='ACTIVE')
        else:
            try:
                instance = api.get(instance_id)
            except cdb_errors.ClientException as exc:
                raise cmexc.CheckmateException(
                    str(exc), friendly_message="Error in database provider",
                    options=cmexc.CAN_RESUME)

            callback({'status': instance.status})

            if instance.status != "ACTIVE":
                raise cmexc.CheckmateException('Database instance is '
                                               'not active.',
                                               options=cmexc.CAN_RESUME)
            if not replica:  # No need to create user on replica db
                try:
                    instance.create_user(username, password, databases)
                except cdb_errors.ClientException as exc:
                    raise cmexc.CheckmateException(str(exc),
                                                   options=cmexc.CAN_RESUME)
                except Exception as exc:
                    raise cmexc.CheckmateException(str(exc),
                                                   options=cmexc.CAN_RESUME)

                LOG.info('Added user %s to %s on instance %s', username,
                         databases, instance_id)

        results = {
            'username': username,
            'password': password,
            'status': 'ACTIVE',
            'interfaces': {
                'mysql': {
                    'host': instance.hostname,
                    'database_name': databases[0],
                    'username': username,
                    'password': password,
                }
            }
        }

        return results
