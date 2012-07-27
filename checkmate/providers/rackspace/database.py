import copy
import logging
import random
import string

from celery.task import task
import clouddb
from SpiffWorkflow.operators import Attrib, PathAttrib
from SpiffWorkflow.specs import Celery

from checkmate.common import schema
from checkmate.deployments import Deployment, resource_postback
from checkmate.exceptions import CheckmateException, CheckmateNoMapping, \
        CheckmateNoTokenError
from checkmate.providers import ProviderBase
from checkmate.workflows import wait_for

LOG = logging.getLogger(__name__)

# Any names should become airport codes
REGION_MAP = {'dallas': 'DFW',
              'chicago': 'ORD',
              'london': 'LON'}


class Provider(ProviderBase):
    name = 'database'
    vendor = 'rackspace'

    def provides(self, resource_type=None, interface=None):
        return [dict(database='mysql', compute='mysql')]

    def generate_template(self, deployment, resource_type, service, context,
            name=None):
        template = ProviderBase.generate_template(self,
                deployment, resource_type, service, context, name=name)

        catalog = self.get_catalog(context)

        if resource_type == 'compute':
            # Get flavor
            memory = deployment.get_setting('memory', resource_type=resource_type,
                    service_name=service, provider_key=self.key) or 512

            # Find same or next largest size and get flavor ID
            size = '512'
            flavor = '1'
            number = str(memory).split(' ')[0]
            for key, value in catalog['lists']['sizes'].iteritems():
                if int(number) <= int(value['memory']):
                    if key > size:
                        size = str(value['memory'])
                        flavor = str(key)

            # Get volume size
            volume = deployment.get_setting('disk', resource_type=resource_type,
                    service_name=service, provider_key=self.key, default=1)

            # Get region
            region = deployment.get_setting('region', resource_type=resource_type,
                    service_name=service, provider_key=self.key)
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

        if component['is'] == 'database':
            # Database name
            db_name = deployment.get_setting('database_name',
                    resource_type=resource.get('type'), provider_key=self.key,
                    service_name=service_name)
            if not db_name:
                db_name = 'db1'

            # User name
            username = deployment.get_setting('username',
                    resource_type=resource.get('type'), provider_key=self.key,
                    service_name=service_name)
            if not username:
                username = 'wp_user_%s' % db_name

            # Password
            password = deployment.get_setting('password',
                    resource_type=resource.get('type'), provider_key=self.key,
                    service_name=service_name)
            start_with = string.ascii_uppercase + string.ascii_lowercase
            if password:
                if password[0] not in start_with:
                    raise CheckmateException("Database password must start with "
                            "one of '%s'" % start_with)
            else:
                password = '%s%s' % (random.choice(start_with),
                    ''.join(random.choice(start_with + string.digits + '@?#_')
                    for x in range(11)))

            create_database_task = Celery(wfspec, 'Create Database',
                   'checkmate.providers.rackspace.database.create_database',
                   call_args=[context.get_queued_task_dict(
                                    deployment=deployment['id'],
                                    resource=key),
                            db_name,
                            PathAttrib('instance/region'),
                        ],
                   instance_id=PathAttrib('instance/id'),
                   merge_results=True,
                   defines=dict(resource=key,
                                provider=self.key,
                                task_tags=['create']),
                   properties={'estimated_duration': 80})
            create_db_user = Celery(wfspec, "Add DB User: %s" % username,
                   'checkmate.providers.rackspace.database.add_user',
                   call_args=[context.get_queued_task_dict(
                                    deployment=deployment['id'],
                                    resource=key),
                            PathAttrib('instance/host_instance'),
                            [db_name],
                            username, password,
                            PathAttrib('instance/host_region'),
                            ],
                   merge_results=True,
                   defines=dict(resource=key,
                                provider=self.key,
                                task_tags=['final']),
                   properties={'estimated_duration': 20})

            create_db_user.follow(create_database_task)
            root = wait_for(wfspec, create_database_task, wait_on)
            if 'task_tags' in root.properties:
                root.properties['task_tags'].append('root')
            else:
                root.properties['task_tags'] = ['root']
            return dict(root=root, final=create_db_user)
        elif component['is'] == 'compute':
            create_instance_task = Celery(wfspec, 'Create Database Server',
                   'checkmate.providers.rackspace.database.create_instance',
                   call_args=[context.get_queued_task_dict(
                                    deployment=deployment['id'],
                                    resource=key),
                            resource.get('dns-name'),
                            resource.get('disk', 1),
                            resource.get('flavor', '1'),
                            None,
                            resource['region'],
                        ],
                   defines=dict(resource=key,
                                provider=self.key,
                                task_tags=['create', 'final']),
                   properties={'estimated_duration': 80})
            root = wait_for(wfspec, create_instance_task, wait_on)
            if 'task_tags' in root.properties:
                root.properties['task_tags'].append('root')
            else:
                root.properties['task_tags'] = ['root']
            return dict(root=root, final=create_instance_task)
        else:
            raise CheckmateException("Unsupported component type '%s' for "
                    "provider %s" % (component['is'], self.key))

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

        # build a live catalog ()this would be the on_get_catalog called if no
        # stored/override existed
        api = self._connect(context)
        if type_filter is None or type_filter == 'database':
            results['database'] = dict(mysql_database={
                'id': 'mysql_database',
                'is': 'database',
                'provides': [{'database': 'mysql'}],
                'requires': [{'compute': dict(relation='host',
                        interface='mysql')}],
                })
        if type_filter is None or type_filter == 'compute':
            results['compute'] = dict(mysql_instance={
                'id': 'mysql_instance',
                'is': 'compute',
                'provides': [{'compute': 'mysql'}],
                'options': {
                        'disk': {
                                'type': 'int',
                                'choice': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                                'unit': 'Gb',
                            },
                        'memory': {
                                'type': 'int',
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
        return results

    @staticmethod
    def _connect(context, region=None):
        """Use context info to connect to API and return api object"""
        #FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, dict):
            from checkmate.server import RequestContext
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
def create_instance(context, instance_name, size, flavor, databases, region,
        api=None):
    """Creates a Cloud Database instance with optional initial databases.

    :param databases: an array of dictionaries with keys to set the database
    name, character set and collation.  For example:

        databases=[{'name': 'db1'},
                   {'name': 'db2', 'character_set': 'latin5',
                    'collate': 'latin5_turkish_ci'}]
    """
    if not api:
        api = Provider._connect(context, region)

    instance = api.create_instance(instance_name, size, flavor,
                                          databases=databases)
    LOG.info("Created database instance %s (%s). Size %s, Flavor %s. "
            "Databases = %s" % (instance.name, instance.id, size, flavor,
            databases))

    # Return instance and its interfaces
    results = {
            'id': instance.id,  # here for compatiblity only. We should remove
            #this once we figure out how to map attributes in Spiff workflow
            #with depth (i.e. not just key, but subkeys)
            'instance':  {
                    'id': instance.id,
                    'name': instance.name,
                    'status': instance.status,
                    'region': region,
                    'interfaces': {
                            'mysql': {
                                    'host': instance.hostname,
                                },
                        },
                    'databases': {}
                },
        }

    # Return created databases and their interfaces
    db_results = results['instance']['databases']
    for database in databases:
        data = copy.copy(database)
        data['interfaces'] = {
                'mysql': {
                        'host': instance.hostname,
                        'database_name': database['name'],
                    },
            }
        db_results[database['name']] = data

    canonicalized_results = schema.translate_dict(results)

    # Send data back to deployment
    resource_postback.delay(context['deployment'], context['resource'],
            canonicalized_results)

    return canonicalized_results


@task(default_retry_delay=10, max_retries=10)
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
    database = {'name': name}
    if character_set:
        database['character_set'] = character_set
    if collate:
        database['collate'] = collate
    databases = [database]

    if not api:
        api = Provider._connect(context, region)

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
        results = {
                'instance': instance['instance']['databases'][name]
            }
        results['instance']['host_instance'] = instance['id']
        results['instance']['host_region'] = instance['region']
        return results

    instance = api.get_instance(instance_id)

    instance.create_databases(databases)
    results = {
            'instance': {
                    'name': name,
                    'host_instance': instance_id,
                    'host_region': region,
                    'interfaces': {
                            'mysql': {
                                    'host': instance.hostname,
                                    'database_name': name,
                                },
                        },
                },
        }
    LOG.info('Created database(s) %s on instance %s' % ([db['name'] for db in
            databases], instance_id))
    # Send data back to deployment
    resource_postback.delay(context['deployment'], context['resource'],
            results)
    return results


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
    if not api:
        api = Provider._connect(context, region)

    dbnames = []
    for db in databases:
        dbnames.append(db['name'])

    instance = api.get_instance(instance_id)
    instance.create_databases(databases)
    LOG.info('Added database(s) %s to instance %s' % (dbnames, instance_id))
    return dict(database_names=dbnames)


@task(default_retry_delay=10, max_retries=10)
def add_user(context, instance_id, databases, username, password, region,
        api=None):
    """Add a database user to an instance for one or more databases"""
    if not api:
        api = Provider._connect(context, region)

    instance = api.get_instance(instance_id)

    try:
        instance.create_user(username, password, databases)
        LOG.info('Added user %s to %s on instance %s' % (username, databases,
                instance_id))
    except clouddb.errors.ResponseError as exc:
        # This could be '422 Unprocessable Entity', meaning the instance is not
        # up yet
        if '422' in exc.message:
            add_user.retry(exc=exc)
        else:
            raise exc

    results = dict(instance=results, interfaces=dict(mysql=dict(
            username=username, password=password)))
    # Send data back to deployment
    resource_postback.delay(context['deployment'], context['resource'],
            results)

    return results


@task(default_retry_delay=10, max_retries=10)
def delete_instance(context, instance_id, region, api=None):
    """Deletes a database server instance and its associated databases and
    users.
    """
    if not api:
        api = Provider._connect(context, region)

    api.delete_instance(instanceid=instance_id)
    LOG.info('Database instance %s deleted.' % instance_id)


@task(default_retry_delay=10, max_retries=10)
def delete_database(context, instance_id, db, region, api=None):
    """Delete a database from an instance"""
    if not api:
        api = Provider._connect(context, region)

    instance = api.get_instance(instance_id)
    instance.delete_database(db)
    LOG.info('Database %s deleted from instance %s' % (db, instance_id))


@task(default_retry_delay=10, max_retries=10)
def delete_user(context, instance_id, username, region, api=None):
    """Delete a database user from an instance."""
    if api is None:
        api = Provider._connect(context, region)

    instance = api.get_instance(instanceid=instance_id)
    instance.delete_user(username)
    LOG.info('Deleted user %s from database instance %d' % (username,
            instance_id))
