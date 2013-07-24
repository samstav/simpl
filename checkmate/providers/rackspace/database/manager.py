# encoding: utf-8
# pylint: disable=E1103
'''
Rackspace Cloud Databases provider manager.
'''
import copy
import logging

from pyrax import exceptions as cdb_errors

from checkmate import utils
from checkmate.exceptions import (
    CheckmateDoesNotExist,
    CheckmateException,
    CheckmateResumableException,
    CheckmateRetriableException,
)

LOG = logging.getLogger(__name__)


class Manager(object):
    '''Contains database provider model and logic for interaction.'''

    @staticmethod
    def wait_on_build(instance_id, api, callback, simulate=False):
        '''Checks provider resource.  Returns True when built otherwise False.
        If resource goes into error state, raises exception.
        '''
        assert api, "API is required in wait_on_build_pop"
        data = {}
        try:
            if simulate:
                data['status'] = 'ACTIVE'
            else:
                data['status'] = api.get(instance_id).status
        except cdb_errors.ClientException as exc:
            raise CheckmateResumableException(str(exc), 'Error occurred in db '
                                              'provider', type(exc).__name__)
        except StandardError as exc:
            data['status'] = 'ERROR'
            data['status-message'] = 'Error waiting on resource to build'
            data['error-message'] = exc.message
            callback(data)
            raise exc

        if data['status'] == 'ERROR':
            data['status-message'] = 'Instance went into status ERROR'
            callback(data)
            raise CheckmateRetriableException(data['status-message'],
                                              'Workflow is retriable',
                                              'Provider Error', True)
        elif data['status'] in ['ACTIVE', 'DELETED']:
            data['status-message'] = ''
        else:
            callback(data)
            msg = 'DB instance in status %s' % data['status']
            info = 'DB status is not ACTIVE'
            raise CheckmateResumableException(msg, info, 'Retriable')

        return data

    @staticmethod
    def sync_resource(resource, api, simulate=False):
        '''Syncronizes provider status with checkmate resource status.'''
        if simulate:
            results = {'status': 'ACTIVE'}
        else:
            instance = resource.get("instance") or {}
            instance_id = instance.get("id")
            try:
                if not instance_id:
                    raise CheckmateDoesNotExist("Instance is blank or has no "
                                                "ID.")
                database = api.get(instance_id)
                LOG.info("Marking database instance %s as %s", instance_id,
                         database.status)
                results = {'status': database.status}
            except (cdb_errors.ClientException, CheckmateDoesNotExist):
                LOG.info("Marking database instance %s as DELETED",
                         instance_id)
                results = {'status': 'DELETED'}
        return results

    @staticmethod
    def create_instance(instance_name, flavor, size, databases, context,
                        api, callback, simulate=False):
        '''Creates a Cloud Database instance with optional initial databases.

        :param databases: an array of dictionaries with keys to set the
        database name, character set and collation.  For example:

            databases=[{'name': 'db1'},
                       {'name': 'db2', 'character_set': 'latin5',
                        'collate': 'latin5_turkish_ci'}]
        '''
        assert api, "API is required in create_instance"
        databases = databases or []
        flavor = int(flavor)
        size = int(size)

        try:
            if simulate:
                volume = utils.Simulation(size=1)
                instance = utils.Simulation(
                    id="DBS%s" % context.get('resource'), name=instance_name,
                    hostname='db1.rax.net', volume=volume)
            else:
                instance = api.create(instance_name, flavor=flavor,
                                      volume=size, databases=databases)
        except cdb_errors.ClientException as exc:
            raise CheckmateRetriableException(str(exc), "",
                                              utils.get_class_name(exc),
                                              action_required=True)

        except Exception as exc:
            raise CheckmateException('Provider error occurred in '
                                     'create_instance.', exc)
        if callable(callback):
            callback({'id': instance.id})

        LOG.info("Created database instance %s (%s). Size %s, Flavor %s. "
                 "Databases = %s", instance.name, instance.id, size,
                 flavor, databases)

        # Return instance and its interfaces
        results = {
            'id': instance.id,
            'name': instance.name,
            'status': 'BUILD',
            'region': context.get('region'),
            'flavor': flavor,
            'disk': instance.volume.size,
            'interfaces': {
                'mysql': {
                    'host': instance.hostname
                }
            },
            'databases': {}
        }

        # Return created databases and their interfaces
        if databases:
            db_results = results['databases']
            for database in databases:
                data = copy.copy(database)
                data['interfaces'] = {
                    'mysql': {
                        'host': instance.hostname,
                        'database_name': database.get('name'),
                    }
                }
                db_results[database['name']] = data

        return results
