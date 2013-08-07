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
    CheckmateUserException,
    UNEXPECTED_ERROR,
)

LOG = logging.getLogger(__name__)


class Manager(object):
    '''Contains database provider model and logic for interaction.'''

    @staticmethod
    def wait_on_build(instance_id, api, callback, simulate=False):
        '''Checks provider resource.  Returns True when built otherwise False.
        If resource goes into error state, raises exception.
        '''
        assert api, "API is required in wait_on_build"
        data = {}
        try:
            if simulate:
                data['status'] = 'ACTIVE'
            else:
                data['status'] = api.get(instance_id).status
        except cdb_errors.ClientException as exc:
            raise CheckmateResumableException(str(exc), utils.get_class_name(
                exc), "Error occurred in db provider", "")
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
                                              utils.get_class_name(
                                                  CheckmateException),
                                              data['status-message'], '')
        elif data['status'] in ['ACTIVE', 'DELETED']:
            data['status-message'] = ''
        else:
            callback(data)
            msg = 'DB instance in status %s' % data['status']
            info = 'DB status is not ACTIVE'
            raise CheckmateResumableException(msg,
                                              utils.get_class_name(
                                                  CheckmateException),
                                              info, '')

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
            raise CheckmateRetriableException(str(exc),
                                              utils.get_class_name(exc),
                                              UNEXPECTED_ERROR,
                                              '')
        except Exception as exc:
            raise CheckmateUserException(str(exc), utils.get_class_name(exc),
                                         UNEXPECTED_ERROR, '')
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

    @staticmethod
    def create_database(name, instance_id, api, callback, context,
                        character_set=None, collate=None, instance_attrs=None,
                        simulate=False):
        '''Creates database in existing db instance.  Returns
        instance, dbs and its interfaces. If resource goes into
        error state, raises exception.
        '''
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
            instance = utils.Simulation(id=instance_id, name=name,
                                        hostname='srv2.rackdb.net',
                                        flavor=flavor)
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
                except CheckmateResumableException:
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
                raise CheckmateResumableException('Database instance is not '
                                                  'active.', '',
                                                  UNEXPECTED_ERROR, '')
            try:
                instance.create_database(name, character_set, collate)
            except cdb_errors.ClientException as exc:
                LOG.exception(exc)
                if exc.code == 400:
                    raise
                else:
                    raise CheckmateResumableException(str(exc),
                                                      str(exc.details),
                                                      UNEXPECTED_ERROR, '')
            except Exception as exc:
                raise CheckmateUserException(str(exc),
                                             utils.get_class_name(exc),
                                             UNEXPECTED_ERROR, '')

        results = {
            'host_instance': instance.id,
            'host_region': context.region,
            'name': name,
            'id': name,
            'status': 'BUILD',
            'flavor': instance.flavor.id,
            'interfaces': {
                'mysql': {
                    'host': instance.hostname,
                    'database_name': name
                }
            }
        }
        LOG.info('Created database %s on instance %s', name, instance_id)
        return results

    @staticmethod
    def add_user(instance_id, databases, username, password,
                 api, callback, simulate=False):
        ''' Add a database user to an instance for one or more databases.
            Returns instance data.
        '''

        assert instance_id, "Instance ID not supplied"

        if simulate:
            instance = utils.Simulation(hostname='srv0.rackdb.net', status='ACTIVE')
        else:
            try:
                instance = api.get(instance_id)
            except cdb_errors.ClientException as exc:
                raise CheckmateResumableException(str(exc),
                                                  utils.get_class_name(exc),
                                                  "Error occurred in db provider", "")

            callback({'status': instance.status})

            if instance.status != "ACTIVE":
                raise CheckmateResumableException('Database instance is '
                                                  'not active.', 'help',
                                                  'status error', '')
            try:
                instance.create_user(username, password, databases)
            except cdb_errors.ClientException as exc:
                raise CheckmateResumableException(str(exc), utils.get_class_name(exc),
                                                  'RS_DB_ClientException', "")
            except Exception as exc:
                raise CheckmateUserException(str(exc), utils.get_class_name(exc),
                                             UNEXPECTED_ERROR, '')

        LOG.info('Added user %s to %s on instance %s', username, databases, instance_id)

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

