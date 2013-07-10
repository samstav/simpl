'''
Rackspace Cloud Databases Provider
'''
import copy
import logging


from celery.task import task, current
import clouddb
from clouddb.errors import ResponseError

from .manager import Manager
from .provider import Provider
from .tasks import (
    wait_on_build as _wait_on_build,
    sync_resource_task as _sync_resource_task,
)

from checkmate.deployments import resource_postback
from checkmate.deployments.tasks import reset_failed_resource_task
from checkmate.exceptions import (
    CheckmateException,
    CheckmateBadState,
)
from checkmate.utils import (
    match_celery_logging,
)

LOG = logging.getLogger(__name__)

API_FLAVOR_CACHE = {}

#FIXME: delete tasks talk to database directly, so we load drivers and manager
import os
from checkmate import db
from checkmate import deployments
DRIVERS = {}
DB = DRIVERS['default'] = db.get_driver()
SIMULATOR_DB = DRIVERS['simulation'] = db.get_driver(
    connection_string=os.environ.get(
        'CHECKMATE_SIMULATOR_CONNECTION_STRING',
        os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')
    )
)
MANAGERS = {'deployments': deployments.Manager(DRIVERS)}
get_resource_by_id = MANAGERS['deployments'].get_resource_by_id


#
# Celery tasks
#
@task(default_retry_delay=30, max_retries=120, acks_late=True)
def wait_on_build(context, instance_id, region, api=None):
    '''Celery task registration for backwards comp.'''
    _wait_on_build(context, instance_id, api=api)


@task
def sync_resource_task(context, resource, resource_key, api=None):
    '''Celery task registration for backwards comp.'''
    _sync_resource_task(context, resource, api=api)


@task(default_retry_delay=10, max_retries=2)
def create_instance(context, instance_name, flavor, size, databases, region,
                    api=None):
    '''Creates a Cloud Database instance with optional initial databases.

    :param databases: an array of dictionaries with keys to set the database
    name, character set and collation.  For example:

        databases=[{'name': 'db1'},
                   {'name': 'db2', 'character_set': 'latin5',
                    'collate': 'latin5_turkish_ci'}]
    '''
    match_celery_logging(LOG)
    if context.get('simulation') is True:
        resource_key = context['resource']
        instance_id = {
            'instance:%s' % resource_key: {
                'id': "DBS%s" % resource_key
            }
        }
        resource_postback.delay(context['deployment'], instance_id)
        results = {
            'instance:%s' % resource_key: {
                'id': "DBS%s" % resource_key,
                'name': instance_name,
                'status': "ACTIVE",
                'region': region,
                'interfaces': {
                    'mysql': {
                        'host': "srv%s.rackdb.net" % resource_key
                    }
                },
                'databases': {}
            }
        }
        if databases:
            db_results = results[resource_key]['databases']
            for database in databases:
                data = copy.copy(database)
                data['interfaces'] = {
                    'mysql': {
                        'host': "srv%s.rackdb.net" % resource_key,
                        'database_name': database['name'],
                    }
                }
                db_results[database['name']] = data

        # Send data back to deployment
        resource_postback.delay(context['deployment'], results)
        return results

    if not api:
        api = Provider.connect(context, region)

    if databases is None:
        databases = []

    flavor = int(flavor)
    size = int(size)

    instance_key = 'instance:%s' % context['resource']
    dep_id = context['deployment']
    instance = api.create_instance(instance_name, flavor, size,
                                   databases=databases)
    instance_id = {
        instance_key: {
            'id': instance.id
        }
    }
    resource_postback.delay(dep_id, instance_id)
    LOG.info("Created database instance %s (%s). Size %s, Flavor %s. "
             "Databases = %s", instance.name, instance.id, size, flavor,
             databases)

    # Return instance and its interfaces
    results = {
        instance_key: {
            'id': instance.id,
            'name': instance.name,
            'status': 'BUILD',
            'region': region,
            'flavor': flavor,
            'interfaces': {
                'mysql': {
                    'host': instance.hostname
                }
            },
            'databases': {}
        }
    }

    # Return created databases and their interfaces
    if databases:
        db_results = results['instance:%s' % context['resource']]['databases']
        for database in databases:
            data = copy.copy(database)
            data['interfaces'] = {
                'mysql': {
                    'host': instance.hostname,
                    'database_name': database['name'],
                }
            }
            db_results[database['name']] = data

    # Send data back to deployment
    resource_postback.delay(context['deployment'], results)
    return results


@task(default_retry_delay=15, max_retries=40)  # max 10 minute wait
def create_database(context, name, region, character_set=None, collate=None,
                    instance_id=None, instance_attributes=None, api=None):
    '''Create a database resource.

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
    '''

    match_celery_logging(LOG)

    if context.get('simulation') is True:
        resource_key = context['resource']
        hostname = "srv%s.rackdb.net" % resource_key
        database_name = name
        results = {
            'instance:%s' % resource_key: {
                'name': database_name,
                'host_instance': instance_id or 'DBS%s' % resource_key,
                'host_region': region,
                'interfaces': {
                    'mysql': {
                        'host': hostname,
                        'database_name': database_name
                    },
                }
            }
        }
        # Send data back to deployment
        resource_postback.delay(context['deployment'], results)
        return results

    database = {'name': name}
    if character_set:
        database['character_set'] = character_set
    if collate:
        database['collate'] = collate
    databases = [database]

    if not api:
        api = Provider.connect(context, region)

    reset_failed_resource_task.delay(context["deployment"],
                                     context["resource"])

    instance_key = 'instance:%s' % context['resource']
    if not instance_id:
        # Create instance & database
        instance_name = '%s_instance' % name
        size = 1
        flavor = '1'
        if instance_attributes:
            instance_name = instance_attributes.get('name', instance_name)
            size = instance_attributes.get('size', size)
            flavor = instance_attributes.get('flavor', flavor)

        instance = create_instance(context, instance_name, size, flavor,
                                   databases, region, api=api)
        instance_id = instance.get(instance_key, {}).get('id')
        wait_on_build.delay(context, instance_id, region, api=api)
        # create_instance calls its own postback
        results = {
            instance_key: instance['instance']['databases'][name]
        }
        results[instance_key]['host_instance'] = instance_id
        results[instance_key]['host_region'] = instance['region']
        results[instance_key]['flavor'] = flavor
        return results

    instance = api.get_instance(instance_id)
    if instance.status != "ACTIVE":
        current.retry(
            exc=CheckmateBadState("Database instance is not active.")
        )
    try:
        instance.create_databases(databases)
        results = {
            instance_key: {
                'name': name,
                'id': name,
                'host_instance': instance_id,
                'host_region': region,
                'flavor': instance.flavor['id'],
                'status': "BUILD",
                'interfaces': {
                    'mysql': {
                        # pylint: disable=E1103
                        'host': instance.hostname,
                        'database_name': name
                    },
                }
            }
        }
        LOG.info('Created database(s) %s on instance %s',
                 [d['name'] for d in databases], instance_id)
        # Send data back to deployment
        resource_postback.delay(context['deployment'], results)
        return results
    except clouddb.errors.ResponseError as exc:
        LOG.exception(exc)
        if str(exc) == '400: Bad Request':
            current.retry(exc=exc, throw=True)  # Do not retry. Will fail.
        # Expected while instance is being created. So retry
        return current.retry(exc=exc)


@task(default_retry_delay=10, max_retries=10)
def add_databases(context, instance_id, databases, region, api=None):
    '''Adds new database(s) to an existing instance.

    :param databases: a list of dictionaries with a required key for database
    name and optional keys for setting the character set and collation.
    For example:

        databases = [{'name': 'mydb1'}]
        databases = [{'name': 'mydb2', 'character_set': 'latin5',
                    'collate': 'latin5_turkish_ci'}]
        databases = [{'name': 'mydb3'}, {'name': 'mydb4'}]
    '''
    match_celery_logging(LOG)

    dbnames = []
    for database in databases:
        dbnames.append(database['name'])

    if context.get('simulation') is True:
        return dict(database_names=dbnames)

    if not api:
        api = Provider.connect(context, region)

    instance = api.get_instance(instance_id)
    instance.create_databases(databases)
    LOG.info('Added database(s) %s to instance %s', dbnames, instance_id)
    return dict(database_names=dbnames)


@task(default_retry_delay=10, max_retries=10)
def add_user(context, instance_id, databases, username, password, region,
             api=None):
    '''Add a database user to an instance for one or more databases.'''
    match_celery_logging(LOG)

    assert instance_id, "Instance ID not supplied"

    instance_key = 'instance:%s' % context['resource']
    if context.get('simulation') is True:
        results = {
            instance_key: {
                'username': username,
                'password': password,
                'status': "ACTIVE",
                'interfaces': {
                    'mysql': {
                        'host': "srv%s.rackdb.net" % context['resource'],
                        'database_name': databases[0],
                        'username': username,
                        'password': password,
                    }
                }
            }
        }
        # Send data back to deployment
        resource_postback.delay(context['deployment'], results)
        return results

    results = {instance_key: {'status': "CONFIGURE"}}
    resource_postback.delay(context['deployment'], results)

    if not api:
        api = Provider.connect(context, region)

    LOG.debug('Obtaining instance %s', instance_id)
    instance = api.get_instance(instance_id)

    try:
        instance.create_user(username, password, databases)
        LOG.info('Added user %s to %s on instance %s', username, databases,
                 instance_id)
    except clouddb.errors.ResponseError as exc:
        # This could be '422 Unprocessable Entity', meaning the instance is not
        # up yet
        if '422' in exc.args[0]:
            current.retry(exc=exc)
        else:
            raise exc

    results = {
        instance_key: {
            'username': username,
            'password': password,
            'status': "ACTIVE",
            'interfaces': {
                'mysql': {
                    'host': instance.hostname,
                    'database_name': databases[0],
                    'username': username,
                    'password': password,
                }
            }
        }
    }
    # Send data back to deployment
    resource_postback.delay(context['deployment'], results)

    return results


@task(default_retry_delay=2, max_retries=60)
def delete_instance_task(context, api=None):
    '''Deletes a database server instance and its associated databases and
    users.
    '''

    match_celery_logging(LOG)

    def on_failure(exc, task_id, args, kwargs, einfo):
        '''Handle task failure.'''
        dep_id = args[0].get('deployment_id')
        key = args[0].get('resource_key')
        if dep_id and key:
            k = "instance:%s" % key
            ret = {
                k: {
                    'status': 'ERROR',
                    'status-message': (
                        'Unexpected error while deleting '
                        'database instance %s' % key
                    ),
                    'error-message': str(exc)
                }
            }
            resource_postback.delay(dep_id, ret)
        else:
            LOG.error("Missing deployment id and/or resource key in "
                      "delete_instance error callback.")

    delete_instance_task.on_failure = on_failure

    assert "deployment_id" in context, "No deployment id in context"
    assert 'region' in context, "No region defined in context"
    assert 'resource_key' in context, 'No resource key in context'
    assert 'resource' in context, 'No resource defined in context'

    region = context.get('region')
    key = context.get('resource_key')
    resource = context.get('resource')
    inst_key = "instance:%s" % key
    resource_key = context.get("resource_key")
    deployment_id = context.get("deployment_id")
    instance_id = resource.get('instance', {}).get('id')
    if not instance_id:
        msg = ("Instance ID is not available for Database server Instance, "
               "skipping delete_instance_task for resource %s in deployment %s",
               (resource_key, deployment_id))
        res = {inst_key: {'status': 'DELETED'}}
        for hosted in resource.get('hosts', []):
            res.update({
                'instance:%s' % hosted: {
                    'status': 'DELETED',
                }
            })
        LOG.info(msg)
        resource_postback.delay(context['deployment_id'], res)
        return

    if context.get('simulation') is True:
        results = {inst_key: {'status': 'DELETED'}}
        for hosted in resource.get('hosts', []):
            results.update({
                'instance:%s' % hosted: {
                    'status': 'DELETED',
                    'status-message': ''
                }
            })
        # Send data back to deployment
        resource_postback.delay(context['deployment_id'], results)
        return results

    if not api:
        api = Provider.connect(context, region)
    res = {}
    try:
        api.delete_instance(instance_id)
        LOG.info('Database instance %s deleted.', instance_id)
        res = {inst_key: {'status': 'DELETING'}}
        for hosted in resource.get('hosts', []):
            res.update({
                'instance:%s' % hosted: {
                    'status': 'DELETING',
                    'status-message': 'Host %s is being deleted'
                }
            })
    except ResponseError as rese:
        if rese.status == 404:  # already deleted
            res = {inst_key: {'status': 'DELETED'}}
            for hosted in resource.get('hosts', []):
                res.update({
                    'instance:%s' % hosted: {
                        'status': 'DELETED',
                        'status-message': ''
                    }
                })
        else:
            # not too sure what this is, so maybe retry a time or two
            delete_instance_task.retry(exc=rese)
    except Exception as exc:
        # might be an api fluke, try again
        delete_instance_task.retry(exc=exc)
    resource_postback.delay(context['deployment_id'], res)
    return res


@task(default_retry_delay=5, max_retries=60)
def wait_on_del_instance(context, api=None):
    '''Wait for the specified instance to be deleted.'''

    match_celery_logging(LOG)

    def on_failure(exc, task_id, args, kwargs, einfo):
        '''Handle task failure.'''
        dep_id = args[0].get('deployment_id')
        key = args[0].get('resource_key')
        if dep_id and key:
            k = "instance:%s" % key
            ret = {
                k: {
                    'status': 'ERROR',
                    'status-message': (
                        'Unexpected error while deleting '
                        'database instance %s' % key
                    ),
                    'error-message': str(exc)
                }
            }
            resource_postback.delay(dep_id, ret)
        else:
            LOG.error("Missing deployment id and/or resource key in "
                      "delete_instance error callback.")

    wait_on_del_instance.on_failure = on_failure

    assert 'region' in context, "No region defined in context"
    assert 'resource_key' in context, 'No resource key in context'
    assert 'resource' in context, 'No resource defined in context'

    region = context.get('region')
    key = context.get('resource_key')
    resource = context.get('resource')
    inst_key = "instance:%s" % key
    instance_id = resource.get('instance', {}).get('id')
    instance = None
    deployment_id = context["deployment_id"]

    if not instance_id:
        msg = ("Instance ID is not available for Database, skipping "
               "wait_on_delete_instance_task for resource %s in deployment "
               "%s" % (key, deployment_id))
        LOG.info(msg)
        results = {
            inst_key: {
                'status': 'DELETED',
                'status-message': msg
            }
        }
        resource_postback.delay(deployment_id, results)
        return

    if not api:
        api = Provider.connect(context, region)
    try:
        instance = api.get_instance(instance_id)
    except ResponseError:
        pass

    if not instance or ('DELETED' == instance.status):
        res = {inst_key: {'status': 'DELETED'}}
        for hosted in resource.get('hosts', []):
            res.update({
                'instance:%s' % hosted: {
                    'status': 'DELETED',
                    'status-message': ''
                }
            })
    else:
        msg = ("Waiting on state DELETED. Instance %s is in state %s" % (key,
               instance.status))
        res = {
            inst_key: {
                'status': 'DELETING',
                "status-message": msg
            }
        }
        resource_postback.delay(context['deployment_id'], res)
        wait_on_del_instance.retry(exc=CheckmateException(msg))

    resource_postback.delay(context['deployment_id'], res)
    return res


@task(default_retry_delay=2, max_retries=30)
def delete_database(context, api=None):
    '''Delete a database from an instance.'''

    match_celery_logging(LOG)

    def on_failure(exc, task_id, args, kwargs, einfo):
        '''Handle task failure.'''
        dep_id = args[0].get('deployment_id')
        key = args[0].get('resource_key')
        if dep_id and key:
            k = "instance:%s" % key
            ret = {
                k: {
                    'status': 'ERROR',
                    'status-message': (
                        'Unexpected error while deleting '
                        'database %s' % key
                    ),
                    'error-message': str(exc)
                }
            }
            resource_postback.delay(dep_id, ret)
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
    inst_key = "instance:%s" % key

    if not api:
        api = Provider.connect(context, region)

    deployment_id = context["deployment_id"]
    resource_key = context["resource_key"]

    instance = resource.get("instance")
    host_instance = resource.get("host_instance")
    if not (instance and host_instance):
        msg = ("Cannot find instance/host-instance for database to delete. "
               "Skipping delete_database call for resource %s in deployment %s "
               "- Instance Id: %s, Host Instance Id: %s",
               (resource_key, context["deployment_id"], instance,
                host_instance))
        results = {
            inst_key: {
                'status': 'DELETED',
                'status-message': msg
            }
        }
        LOG.info(msg)
        resource_postback.delay(deployment_id, results)
        return

    db_name = resource.get('instance', {}).get('name')
    instance_id = resource.get('instance', {}).get('host_instance')
    instance = None
    try:
        instance = api.get_instance(instance_id)
    except ResponseError as respe:
        if respe.status != 404:
            delete_database.retry(exc=respe)
    if not instance or (instance.status == 'DELETED'):
        # instance is gone, so is the db
        return {
            inst_key: {
                'status': 'DELETED',
                'status-message': (
                    'Host %s was deleted' % resource.get('hosted_on')
                )
            }
        }
    elif instance.status == 'BUILD':  # can't delete when instance in BUILD
        delete_database.retry(exc=CheckmateException("Waiting on instance to "
                                                     "be out of BUILD status"))
    try:
        instance.delete_database(db_name)
    except ResponseError as respe:
        delete_database.retry(exc=respe)
    LOG.info('Database %s deleted from instance %s', db_name, instance_id)
    ret = {inst_key: {'status': 'DELETED'}}
    resource_postback.delay(deployment_id, ret)
    return ret


@task(default_retry_delay=10, max_retries=10)
def delete_user(context, instance_id, username, region, api=None):
    '''Delete a database user from an instance.'''
    match_celery_logging(LOG)
    if api is None:
        api = Provider.connect(context, region)

    instance = api.get_instance(instanceid=instance_id)
    instance.delete_user(username)
    LOG.info('Deleted user %s from database instance %d', username,
             instance_id)


#Database provider specific exceptions
class CheckmateDatabaseBuildFailed(CheckmateException):
    """Error building database."""
    pass
