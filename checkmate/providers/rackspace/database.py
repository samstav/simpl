import logging
import random
import string

import clouddb
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery

from checkmate.deployments import Deployment
from checkmate.exceptions import CheckmateException, CheckmateNoMapping, \
        CheckmateNoTokenError
from checkmate.providers import ProviderBase

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    name = 'database'
    vendor = 'rackspace'

    def generate_template(self, deployment, resource_type, service, context,
            name=None):
        template = ProviderBase.generate_template(self,
                deployment, resource_type, service, context, name=name)

        catalog = self.get_catalog(context)
        flavor = deployment.get_setting('memory', resource_type=resource_type,
                service_name=service, provider_key=self.key, default=1)
        if isinstance(flavor, int):
            pass
        else:
            number = flavor.split(' ')[0]
            for key, value in catalog['lists']['sizes'].iteritems():
                if number == str(value['memory']):
                    LOG.debug("Mapping flavor from '%s' to '%s'" % (flavor,
                            key))
                    flavor = key
                    break
        if not isinstance(flavor, int):
            raise CheckmateNoMapping("No flavor mapping for '%s' in '%s'" % (
                    flavor, self.key))

        template['flavor'] = flavor
        return template

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
            wait_on=None):
        service_name = None
        for name, service in deployment['blueprint']['services'].iteritems():
            if key in service.get('instances', []):
                service_name = name
                break

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
            deployment.settings()['db_password'] = password

        # Database name
        db_name = deployment.get_setting('db_name',
                resource_type=resource.get('type'), provider_key=self.key,
                service_name=service_name)
        if not db_name:
            db_name = 'db1'
            deployment.settings()['db_name'] = db_name

        # User name
        username = deployment.get_setting('username',
                resource_type=resource.get('type'), provider_key=self.key,
                service_name=service_name)
        if not username:
            username = 'wp_user_%s' % db_name
            deployment.settings()['db_username'] = username

        create_db_task = Celery(wfspec, 'Create DB',
               'checkmate.providers.rackspace.database.create_instance',
               call_args=[context.get_queued_task_dict(),
                        resource.get('dns-name'),
                        resource.get('disk', 1),
                        resource.get('flavor', 1),
                        [{'name': db_name}]],
               prefix=key,
               defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['create']),
               properties={'estimated_duration': 80})
        create_db_user = Celery(wfspec, "Add DB User:%s" % username,
               'checkmate.providers.rackspace.database.add_user',
               call_args=[context.get_queued_task_dict(),
                        Attrib('id'), [db_name],
                        username, password],
               defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['final']),
               properties={'estimated_duration': 20})

        create_db_task.connect(create_db_user)
        return dict(root=create_db_task, final=create_db_user)

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
            results['database'] = dict(mysql_instance={
                'id': 'mysql_instance',
                'is': 'database',
                'provides': [{'database': 'mysql'}]})

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
                f.id: {
                    'name': f.name,
                    'memory': f.ram
                    } for f in flavors}

        self.validate_catalog(results)
        return results

    def _connect(self, context):
        """Use context info to connect to API and return api object"""
        #FIXME: handle region in context
        if not context.auth_tok:
            raise CheckmateNoTokenError()

        def find_url(catalog):
            for service in catalog:
                if service['type'] == 'rax:database':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        return endpoint['publicURL']

        def find_a_region(catalog):
            for service in catalog:
                if service['type'] == 'rax:database':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        return endpoint['region']

        api = clouddb.CloudDB(context.user, 'dummy',
                find_a_region(context.catalog) or 'DFW')
        api.client.auth_token = context.auth_tok
        url = find_url(context.catalog)
        api.client.region_account_url = url

        return api


#
# Celery tasks
#
from celery.task import task
import clouddb

REGION_MAP = {'DFW': 'dallas',
              'ORD': 'chicago',
              'LON': 'london'}


def _get_db_object(context):
    region = context['region']
    # Map to clouddb library known names (it uses full names)
    if region in REGION_MAP:
        region = REGION_MAP[region]
    return clouddb.CloudDB(context['username'], context['apikey'],
                           region)


@task(default_retry_delay=10, max_retries=2)
def create_instance(context, instance_name, size, flavor, databases,
        prefix=None, api=None):
    """Creates a Cloud Database instance with optional initial databases.

    :param databases: an array of dictionaries with keys to set the database
    name, character set and collation.  For example:

        databases=[{'name': 'db1'},
                   {'name': 'db2', 'character_set': 'latin5',
                    'collate': 'latin5_turkish_ci'}]
    """
    if not api:
        api = _get_db_object(context)

    instance = api.create_instance(instance_name, size, flavor,
                                          databases=databases)
    LOG.info("Created database instance %s (%s). Size %s, Flavor %s. "
            "Databases = %s" % (instance_name, instance.id, size, flavor,
            databases))

    results = dict(id=instance.id, name=instance.name, status=instance.status,
            hostname=instance.hostname)
    if prefix:
        # Add each value back in with the prefix
        results.update({'%s.%s' % (prefix, key): value for key, value in
                results.iteritems()})

    return results


@task(default_retry_delay=10, max_retries=10)
def add_databases(context, instance_id, databases, api=None):
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
        api = _get_db_object(context)

    dbnames = []
    for db in databases:
        dbnames.append(db['name'])

    instance = api.get_instance(instance_id)
    instance.create_databases(databases)
    LOG.info('Added database(s) %s to instance %s' % (dbnames, instance_id))
    return dict(databases=dbnames)


@task(default_retry_delay=10, max_retries=10)
def add_user(context, instance_id, databases, username, password, api=None):
    """Add a database user to an instance for one or more databases"""
    if not api:
        api = _get_db_object(context)

    instance = api.get_instance(instance_id)
    instance.create_user(username, password, databases)
    LOG.info('Added user %s to %s on instance %s' % (username, databases,
            instance_id))
    return dict(db_username=username, db_password=password)


@task(default_retry_delay=10, max_retries=10)
def delete_instance(context, instance_id, api=None):
    """Deletes a database server instance and its associated databases and
    users.
    """
    if not api:
        api = _get_db_object(context)

    api.delete_instance(instanceid=instance_id)
    LOG.info('Database instance %s deleted.' % instance_id)


@task(default_retry_delay=10, max_retries=10)
def delete_database(deployment, instance_id, db, api=None):
    """Delete a database from an instance"""
    if not api:
        api = _get_db_object(deployment)

    instance = api.get_instance(instance_id)
    instance.delete_database(db)
    LOG.info('Database %s deleted from instance %s' % (db, instance_id))


@task(default_retry_delay=10, max_retries=10)
def delete_user(deployment, instance_id, username, api=None):
    """Delete a database user from an instance."""
    if api is None:
        api = _get_db_object(deployment)

    instance = api.get_instance(instanceid=instance_id)
    instance.delete_user(username)
    LOG.info('Deleted user %s from database instance %d' % (username,
            instance_id))
