import copy
import logging
import random
import string

from celery.task import task, current  # @UnresolvedImport
import clouddb
from SpiffWorkflow.operators import PathAttrib
from SpiffWorkflow.specs import Celery

from checkmate.deployments import resource_postback, alt_resource_postback
from checkmate.exceptions import CheckmateException,  CheckmateNoTokenError
from checkmate.providers import ProviderBase
from checkmate.utils import match_celery_logging
from checkmate.workflows import wait_for
from clouddb.errors import ResponseError

LOG = logging.getLogger(__name__)

# Any names should become airport codes
REGION_MAP = {'dallas': 'DFW',
              'chicago': 'ORD',
              'london': 'LON'}


class Provider(ProviderBase):
    name = 'database'
    vendor = 'rackspace'

    def generate_template(self, deployment, resource_type, service, context,
                          name=None):
        template = ProviderBase.generate_template(self, deployment,
                                                  resource_type, service,
                                                  context, name=name)

        catalog = self.get_catalog(context)

        if resource_type == 'compute':
            # Get flavor
            # Find same or next largest size and get flavor ID
            flavor = None
            memory = self.parse_memory_setting(deployment.get_setting('memory',
                                               resource_type=resource_type,
                                               service_name=service,
                                               provider_key=self.key) or 512)

            # Find the available memory size that satisfies this
            matches = [e['memory'] for e in catalog['lists']['sizes'].values()
                       if int(e['memory']) >= memory]
            if not matches:
                raise CheckmateNoMapping("No flavor has at least '%s' memory" %
                                         memory)
            match = str(min(matches))
            for key, value in catalog['lists']['sizes'].iteritems():
                if match == str(value['memory']):
                    LOG.debug("Mapping flavor from '%s' to '%s'" % (memory,
                                                                    key))
                    flavor = key
                    break
            if not flavor:
                raise CheckmateNoMapping("No flavor mapping for '%s' in '%s'" %
                                         (memory, self.key))

            # Get volume size
            volume = deployment.get_setting('disk',
                                            resource_type=resource_type,
                                            service_name=service,
                                            provider_key=self.key, default=1)

            # Get region
            region = deployment.get_setting('region',
                                            resource_type=resource_type,
                                            service_name=service,
                                            provider_key=self.key)
            if not region:
                raise CheckmateException("Could not identify which region to "
                                         "create database in")

            template['flavor'] = flavor
            template['disk'] = volume
            template['region'] = region
        elif resource_type == 'database':
            pass
        return template

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        wait_on, service_name, component = self._add_resource_tasks_helper(
            resource, key, wfspec, deployment, context, wait_on)

        resource_type = resource.get('type', resource.get('resource_type'))
        if component['is'] == 'database':
            # Database name
            db_name = deployment.get_setting('database/name',
                                             resource_type=resource_type,
                                             provider_key=self.key,
                                             service_name=service_name)
            if not db_name:
                db_name = 'db1'

            # User name
            username = deployment.get_setting('database/username',
                                              resource_type=resource_type,
                                              provider_key=self.key,
                                              service_name=service_name)
            if not username:
                username = 'wp_user_%s' % db_name

            # Password
            password = deployment.get_setting('database/password',
                                              resource_type=resource_type,
                                              provider_key=self.key,
                                              service_name=service_name)
            if not password:
                password = self.evaluate("generate_password()")
            elif password.startswith('=generate'):
                password = self.evaluate(password[1:])

            if password:
                start_with = string.ascii_uppercase + string.ascii_lowercase
                if password[0] not in start_with:
                    raise CheckmateException("Database password must start "
                                             "with one of '%s'" % start_with)

            # Create resource tasks
            create_database_task = Celery(wfspec,
                                          'Create Database',
                                          'checkmate.providers.rackspace.'
                                          'database.create_database',
                                          call_args=[
                                              context.get_queued_task_dict(
                                                  deployment=deployment['id'],
                                                  resource=key),
                                              db_name,
                                              PathAttrib(
                                                  'instance:%s/region' %
                                                  resource['hosted_on']),
                                          ],
                                          instance_id=PathAttrib(
                                              'instance:%s/id' %
                                              resource['hosted_on']),
                                          merge_results=True,
                                          defines=dict(resource=key,
                                                       provider=self.key,
                                                       task_tags=['create']),
                                          properties={
                                              'estimated_duration': 80
                                          })
            create_db_user = Celery(wfspec,
                                    "Add DB User: %s" % username,
                                    'checkmate.providers.rackspace.database.'
                                    'add_user',
                                    call_args=[
                                        context.get_queued_task_dict(
                                            deployment=deployment['id'],
                                            resource=key),
                                        PathAttrib(
                                            'instance:%s/host_instance' % key),
                                        [db_name],
                                        username, password,
                                        PathAttrib(
                                            'instance:%s/host_region' % key),
                                    ],
                                    merge_results=True,
                                    defines=dict(resource=key,
                                                 provider=self.key,
                                                 task_tags=['final']),
                                    properties={
                                        'estimated_duration': 20
                                    })

            create_db_user.follow(create_database_task)
            root = wait_for(wfspec, create_database_task, wait_on)
            if 'task_tags' in root.properties:
                root.properties['task_tags'].append('root')
            else:
                root.properties['task_tags'] = ['root']
            return dict(root=root, final=create_db_user)
        elif component['is'] == 'compute':
            defines = dict(resource=key,
                           resource_type=resource_type,
                           interface=resource.get('interface'),
                           provider=self.key,
                           task_tags=['create', 'root'])
            create_instance_task = Celery(wfspec,
                                          'Create Database Server',
                                          'checkmate.providers.rackspace.'
                                          'database.create_instance',
                                          call_args=[
                                              context.get_queued_task_dict(
                                                  deployment=deployment['id'],
                                                  resource=key),
                                              resource.get('dns-name'),
                                              resource['flavor'],
                                              resource['disk'],
                                              None,
                                              resource['region'],
                                          ],
                                          merge_results=True,
                                          defines=defines,
                                          properties={
                                              'estimated_duration': 80
                                          })
            root = wait_for(wfspec, create_instance_task, wait_on)
            wait_on_build = Celery(wfspec,
                                   'Wait on Database Instance %s' % key,
                                   'checkmate.providers.rackspace.database.'
                                   'wait_on_build',
                                   call_args=[
                                       context.get_queued_task_dict(
                                           deployment=deployment['id'],
                                           resource=key),
                                       PathAttrib("instance:%s/id" % key),
                                       resource['region']
                                   ],
                                   merge_results=True,
                                   defines=dict(resource=key,
                                                provider=self.key,
                                                task_tags=['final']),
                                   properties={
                                       'estimated_duration': 80
                                   })
            wait_on_build.follow(create_instance_task)
            return dict(root=root, final=wait_on_build)
        else:
            raise CheckmateException("Unsupported component type '%s' for "
                                     "provider %s" % (component['is'],
                                                      self.key))

    def delete_resource_tasks(self, context, deployment_id, resource, key):
        self._verify_existing_resource(resource, key)
        region = resource.get('region') or \
            resource.get('instance', {}).get('host_region')
        ctx = context.get_queued_task_dict(deployment_id=deployment_id,
                                           resource_key=key,
                                           resource=resource,
                                           region=region)
        if resource.get('type') == 'compute':
            return self._delete_comp_res_tasks(ctx, deployment_id,
                                               resource, key)
        if resource.get('type') == 'database':
            return self._delete_db_res_tasks(ctx, deployment_id, resource,
                                             key)
        raise CheckmateException("Cannot provide delete tasks for resource %s:"
                                 " Invalid resource type '%s'"
                                 % (key, resource.get('type')))

    def _delete_comp_res_tasks(self, ctx, deployment_id, resource, key):
        return (delete_instance.s(ctx) |
                alt_resource_postback.s(deployment_id) |
                wait_on_del_instance.si(ctx) |
                alt_resource_postback.s(deployment_id))

    def _delete_db_res_tasks(self, context, deployment_id, resource, key):
        """ Return delete tasks for the specified database instance """
        return (delete_database.s(context) |
                alt_resource_postback.s(deployment_id))

    def get_catalog(self, context, type_filter=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one"""

        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #        this for every provider
        results = ProviderBase.get_catalog(self, context,
                                           type_filter=type_filter)
        if results:
            # We have a prexisting or overridecatalog stored
            return results

        # build a live catalog this would be the on_get_catalog called if no
        # stored/override existed
        api = self._connect(context)
        if type_filter is None or type_filter == 'database':
            results['database'] = dict(mysql_database={
                'id': 'mysql_database',
                'is': 'database',
                'provides': [{'database': 'mysql'}],
                'requires': [{'compute': dict(relation='host',
                             interface='mysql', type='compute')}],
                'options': {
                    'database/name': {
                        'type': 'string',
                        'default': 'db1'
                    },
                    'database/username': {
                        'type': 'string',
                        'required': "true"
                    },
                    'database/password': {
                        'type': 'string',
                        'required': "false"
                    }
                }})
        if type_filter is None or type_filter == 'compute':
            results['compute'] = dict(mysql_instance={
                'id': 'mysql_instance',
                'is': 'compute',
                'provides': [{'compute': 'mysql'}],
                'options': {
                    'disk': {
                        'type': 'integer',
                        'choice': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                        'unit': 'Gb',
                    },
                    'memory': {
                        'type': 'integer',
                        'choice': [512, 1024, 2048, 4096],
                        'unit': 'Mb',
                    },
                }
            })

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context.catalog:
                if service['type'] == 'rax:database':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['regions'] = regions

        if type_filter is None or type_filter == 'size':
            flavors = api.flavors.list_flavors()
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['sizes'] = {
                str(f.id): {
                    'name': f.name,
                    'memory': f.ram
                    } for f in flavors}

        self.validate_catalog(results)
        if type_filter is None:
            self._dict['catalog'] = results
        return results

    def evaluate(self, function_string):
        """Overrides base for generate_password"""
        if function_string.startswith('generate_password('):
            start_with = string.ascii_uppercase + string.ascii_lowercase
            password = '%s%s' % (random.choice(start_with),
                                 ''.join(random.choice(start_with +
                                                       string.digits + '@?#_')
                                 for x in range(11)))
            return password
        return ProviderBase.evaluate(self, function_string)

    @staticmethod
    def _connect(context, region=None):
        """Use context info to connect to API and return api object"""
        #FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, dict):
            from checkmate.middleware import RequestContext
            context = RequestContext(**context)
        if not context.auth_token:
            raise CheckmateNoTokenError()

        # Make sure we use airport codes (translate cities to that)
        if region in REGION_MAP:
            region = REGION_MAP[region]

        def find_url(catalog, region):
            for service in catalog:
                if service['type'] == 'rax:database':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if endpoint.get('region') == region:
                            return endpoint['publicURL']

        def find_a_region(catalog):
            """Any region"""
            for service in catalog:
                if service['type'] == 'rax:database':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        return endpoint['region']

        if not region:
            region = find_a_region(context.catalog) or 'DFW'

        #TODO: instead of hacking auth using a token, submit patch upstream
        url = find_url(context.catalog, region)
        if not url:
            raise CheckmateException("Unable to locate region url for DBaaS "
                                     "for region '%s'" % region)
        api = clouddb.CloudDB(context.username, 'dummy', region)
        api.client.auth_token = context.auth_token
        api.client.region_account_url = url

        return api


#
# Celery tasks
#
@task(default_retry_delay=10, max_retries=2)
def create_instance(context, instance_name, flavor, size, databases, region,
                    api=None):
    """Creates a Cloud Database instance with optional initial databases.

    :param databases: an array of dictionaries with keys to set the database
    name, character set and collation.  For example:

        databases=[{'name': 'db1'},
                   {'name': 'db2', 'character_set': 'latin5',
                    'collate': 'latin5_turkish_ci'}]
    """
    match_celery_logging(LOG)
    if context.get('simulation') is True:
        resource_key = context['resource']
        hostname = "srv%s.rackdb.net" % resource_key
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
        api = Provider._connect(context, region)

    if databases is None:
        databases = []

    flavor = int(flavor)
    size = int(size)

    instance = api.create_instance(instance_name, flavor, size,
                                   databases=databases)
    LOG.info("Created database instance %s (%s). Size %s, Flavor %s. "
             "Databases = %s" % (instance.name, instance.id, size, flavor,
                                 databases))

    # Return instance and its interfaces
    results = {
        'instance:%s' % context['resource']: {
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


@task(default_retry_delay=30, max_retries=120, acks_late=True)
def wait_on_build(context, instance_id, region, api=None):
    """ Check to see if DB Instance has finished building """

    match_celery_logging(LOG)
    if context.get('simulation') is True:
        results = {}
        results['status'] = "ACTIVE"
        results['id'] = instance_id
        instance_key = "instance:%s" % context['resource']
        results = {instance_key: results}
        resource_postback.delay(context['deployment'], results)
        return

    if api is None:
        api = Provider._connect(context, region)

    assert instance_id, "ID must be provided"
    LOG.debug("Getting Instance %s" % instance_id)

    instance = api.get_instance(instance_id)

    results = {}

    if instance.status == "ERROR":
        results['status'] = "ERROR"
        msg = ("Instance %s build failed" % instance_id)
        results['errmessage'] = msg
        instance_key = "instance:%s" % context['resource']
        results = {instance_key: results}
        resource_postback.delay(context['deployment'], results)
        raise CheckmateException(msg)
    elif instance.status == "ACTIVE":
        results['status'] = "ACTIVE"
        results['id'] = instance_id
        instance_key = "instance:%s" % context['resource']
        results = {instance_key: results}
        resource_postback.delay(context['deployment'], results)
        return results
    else:
        msg = ("DB Instance status is %s, retrying" % instance.status)
        return wait_on_build.retry(exc=CheckmateException(msg))


@task(default_retry_delay=15, max_retries=40)  # max 10 minute wait
def create_database(context, name, region, character_set=None, collate=None,
                    instance_id=None, instance_attributes=None, api=None):
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
        api = Provider._connect(context, region)

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
        current.retry(exc=CheckmateException("Database instance is not active."))
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
        LOG.info('Created database(s) %s on instance %s' % (
                 [db['name'] for db in
                  databases], instance_id))
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
    """Adds new database(s) to an existing instance.

    :param databases: a list of dictionaries with a required key for database
    name and optional keys for setting the character set and collation.
    For example:

        databases = [{'name': 'mydb1'}]
        databases = [{'name': 'mydb2', 'character_set': 'latin5',
                    'collate': 'latin5_turkish_ci'}]
        databases = [{'name': 'mydb3'}, {'name': 'mydb4'}]
    """
    match_celery_logging(LOG)

    dbnames = []
    for db in databases:
        dbnames.append(db['name'])

    if context.get('simulation') is True:
        return dict(database_names=dbnames)

    if not api:
        api = Provider._connect(context, region)

    instance = api.get_instance(instance_id)
    instance.create_databases(databases)
    LOG.info('Added database(s) %s to instance %s' % (dbnames, instance_id))
    return dict(database_names=dbnames)


@task(default_retry_delay=10, max_retries=10)
def add_user(context, instance_id, databases, username, password, region,
             api=None):
    """Add a database user to an instance for one or more databases"""
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
        api = Provider._connect(context, region)

    LOG.debug('Obtaining instance %s' % instance_id)
    instance = api.get_instance(instance_id)

    try:
        instance.create_user(username, password, databases)
        LOG.info('Added user %s to %s on instance %s' % (username, databases,
                 instance_id))
    except clouddb.errors.ResponseError as exc:
        # This could be '422 Unprocessable Entity', meaning the instance is not
        # up yet
        if '422' in exc.message:
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
def delete_instance(context, api=None):
    """Deletes a database server instance and its associated databases and
    users.
    """

    match_celery_logging(LOG)

    def on_failure(exc, task_id, args, kwargs, einfo):
        """ Handle task failure """
        dep_id = args[0].get('deployment_id')
        key = args[0].get('resource_key')
        if dep_id and key:
            k = "instance:%s" % key
            ret = {k: {'status': 'ERROR',
                       'errmessage': ('Unexpected error while deleting '
                                      'database instance %s' % key),
                       'trace': 'Task %s: %s' % (task_id, einfo.traceback)}}
            resource_postback.delay(dep_id, ret)
        else:
            LOG.error("Missing deployment id and/or resource key in "
                      "delete_instance error callback.")

    delete_instance.on_failure = on_failure

    assert 'region' in context, "No region defined in context"
    assert 'resource_key' in context, 'No resource key in context'
    assert 'resource' in context, 'No resource defined in context'

    region = context.get('region')
    key = context.get('resource_key')
    resource = context.get('resource')
    inst_key = "instance:%s" % key
    instance_id = resource.get('instance', {}).get('id')
    if not instance_id:
        raise CheckmateException("No instance id supplied for resource %s"
                                 % key)

    if context.get('simulation') is True:
        results = {inst_key: {'status': 'DELETED'}}
        for hosted in resource.get('hosts', []):
            results.update({
                'instance:%s' % hosted: {
                    'status': 'DELETED',
                    'statusmsg': 'Host %s was deleted'
                }
            })
        # Send data back to deployment
        resource_postback.delay(context['deployment'], results)
        return results

    if not api:
        api = Provider._connect(context, region)

    try:
        api.delete_instance(instance_id)
        LOG.info('Database instance %s deleted.' % instance_id)
    except ResponseError as rese:
        if rese.status == 404:  # already deleted
            res = {inst_key: {'status': 'DELETED'}}
            for hosted in resource.get('hosts', []):
                res.update({
                    'instance:%s' % hosted: {
                        'status': 'DELETED',
                        'statusmsg': 'Host %s was deleted'
                    }
                })
            return res
        else:
            # not too sure what this is, so maybe retry a time or two
            delete_instance.retry(exc=rese)
    except Exception as exc:
        # might be an api fluke, try again
        delete_instance.retry(exc=exc)
    res = {inst_key: {'status': 'DELETING'}}
    for hosted in resource.get('hosts', []):
        res.update({
            'instance:%s' % hosted: {
                'status': 'DELETING',
                'statusmsg': 'Host %s is being deleted'
            }
        })
    return res


@task(default_retry_delay=5, max_retries=60)
def wait_on_del_instance(context, api=None):
    """ Wait for the specified instance to be deleted """

    match_celery_logging(LOG)

    def on_failure(exc, task_id, args, kwargs, einfo):
        """ Handle task failure """
        dep_id = args[0].get('deployment_id')
        key = args[0].get('resource_key')
        if dep_id and key:
            k = "instance:%s" % key
            ret = {k: {'status': 'ERROR',
                       'errmessage': ('Unexpected error while deleting '
                                      'database instance %s' % key),
                       'trace': 'Task %s: %s' % (task_id, einfo.traceback)}}
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
    if not instance_id:
        raise CheckmateException("No instance id supplied for resource %s"
                                 % key)
    if not api:
        api = Provider._connect(context, region)
    instance = None
    try:
        instance = api.get_instance(instance_id)
    except ResponseError as respe:
        if 404 == respe.status:  # already gone
            res = {inst_key: {'status': 'DELETED'}}
            for hosted in resource.get('hosts', []):
                res.update({
                    'instance:%s' % hosted: {
                        'status': 'DELETED',
                        'statusmsg': 'Host %s was deleted'
                    }
                })
            return res
        else:
            # not too sure what this is, so maybe retry a time or two
            wait_on_del_instance.retry(exc=respe)
    if not instance or ('DELETED' == instance.status):
        res = {inst_key: {'status': 'DELETED'}}
        for hosted in resource.get('hosts', []):
            res.update({
                'instance:%s' % hosted: {
                    'status': 'DELETED',
                    'statusmsg': 'Host %s was deleted'
                }
            })
        return res
    else:
        wait_on_del_instance.retry(exc=CheckmateException("Timeout waiting on "
                                   "instance %s delete" % key))


@task(default_retry_delay=2, max_retries=30)
def delete_database(context, api=None):
    """Delete a database from an instance"""

    match_celery_logging(LOG)

    def on_failure(exc, task_id, args, kwargs, einfo):
        """ Handle task failure """
        dep_id = args[0].get('deployment_id')
        key = args[0].get('resource_key')
        if dep_id and key:
            k = "instance:%s" % key
            ret = {k: {'status': 'ERROR',
                       'errmessage': ('Unexpected error while deleting '
                                      'database %s' % key),
                       'trace': 'Task %s: %s' % (task_id, einfo.traceback)}}
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
    assert 'instance' in resource, 'Instance data not in resource'
    assert 'host_instance' in resource.get('instance', {}), ('Instance id not'
                                                             ' in resource '
                                                             'instance')
    instance_id = resource.get('instance', {}).get('host_instance')
    assert 'name' in resource.get('instance', {}), ('Database name not in'
                                                    ' resource instance')
    db_name = resource.get('instance', {}).get('name')

    if not api:
        api = Provider._connect(context, region)

    instance = None
    try:
        instance = api.get_instance(instance_id)
    except ResponseError as respe:
        if respe.status != 404:
            delete_database.retry(exc=respe)
    if not instance or (instance.status == 'DELETED'):
        # instance is gone, so is the db
        return {inst_key: {'status': 'DELETED',
                           'statusmsg': ('Host %s was deleted'
                                         % resource.get('hosted_on'))}}
    elif instance.status == 'BUILD':  # can't delete when instance in BUILD
        delete_database.retry(exc=CheckmateException("Waiting on instance to "
                                                     "be out of BUILD status"))
    try:
        instance.delete_database(db_name)
    except ResponseError as respe:
        delete_database.retry(exc=respe)
    LOG.info('Database %s deleted from instance %s' % (db_name, instance_id))
    return {inst_key: {'status': 'DELETED'}}


@task(default_retry_delay=10, max_retries=10)
def delete_user(context, instance_id, username, region, api=None):
    """Delete a database user from an instance."""
    match_celery_logging(LOG)
    if api is None:
        api = Provider._connect(context, region)

    instance = api.get_instance(instanceid=instance_id)
    instance.delete_user(username)
    LOG.info('Deleted user %s from database instance %d' % (username,
             instance_id))
