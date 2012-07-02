import logging
import random
import string

import clouddb
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery

from checkmate.exceptions import CheckmateNoMapping
from checkmate.providers import ProviderBase


LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    name = 'database'
    vendor = 'rackspace'

    def generate_template(self, deployment, resource_type, service, name=None):
        template = ProviderBase.generate_template(self,
                deployment, resource_type, service, name=name)

        flavor = self.get_deployment_setting(deployment, 'memory',
                resource_type=resource_type, service=service, default=512)
        #FIXME: mapping needs to be done
        if '512' in str(flavor):
            flavor = 1
        else:
            raise CheckmateNoMapping("No flavor mapping for '%s' in '%s'" % (
                    flavor, self.name))

        template['flavor'] = flavor
        return template

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
            wait_on=None):
        start_with = string.ascii_uppercase + string.ascii_lowercase
        password = '%s%s' % (random.choice(start_with),
                ''.join(random.choice(start_with + string.digits + '@?#_')
                for x in range(11)))
        db_name = 'db1'
        username = 'wp_user_%s' % db_name

        create_db_task = Celery(wfspec, 'Create DB',
               'checkmate.providers.rackspace.database.create_instance',
               call_args=[Attrib('context'),
                        resource.get('dns-name'), 1,
                        resource.get('flavor', 1),
                        [{'name': db_name}]],
               prefix=key,
               defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['create']),
               properties={'estimated_duration': 80})
        create_db_user = Celery(wfspec, "Add DB User:%s" % username,
               'checkmate.providers.rackspace.database.add_user',
               call_args=[Attrib('context'),
                        Attrib('id'), [db_name],
                        username, password],
               defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['final']),
               properties={'estimated_duration': 20})
        # Store these in the context for use by other tasks
        context['db_name'] = db_name
        context['db_username'] = username
        context['db_password'] = password
        create_db_task.connect(create_db_user)
        return dict(root=create_db_task, final=create_db_user)

    def get_catalog(self, context, type_filter=None):
        api = self._connect(context)
        results = {}

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context.catalog:
                if service['type'] == 'rax:database':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
            results['regions'] = regions

        if type_filter is None or type_filter == 'size':
            flavors = api.flavors.list_flavors()
            results['sizes'] = {
                f.id: {
                    'name': f.name,
                    } for f in flavors}

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
# Exploring Celery tasks from within CheckMate
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
def create_instance(context, instance_name, size, flavor,
                               databases, username=None, password=None,
                               api=None, prefix=None):
    """Creates a Cloud Database instancem, initial databases and user.

    databases is an array of dictionaries with keys to set the database
    name, character set and collation.  For example:

        databases=[{'name': 'db1'},
                   {'name': 'db2', 'character_set': 'latin5',
                    'collate': 'latin5_turkish_ci'}]
    """
    if api is None:
        api = _get_db_object(context)

    #try:
    instance = api.create_instance(instance_name, size, flavor,
                                          databases=databases)
    LOG.info("Created database instance %s (%s). Size %d, Flavor %d. "
            "Databases = %s" % (instance_name, instance.id, size, flavor,
            databases))
    #except clouddb.errors.ResponseError, exc:
    #    log(context,
    #        'Response error while trying to create database instance ' \
    #        '%s. Error %d %s. Retrying.' % (
    #          instance_name, exc.status, exc.reason))
    #    create_instance.retry(exc=exc)
    #except Exception, exc:
    #    log(context,
    #        'Error creating database instance %s. Error %s. Retrying.' % (
    #        instance_name, str(exc)))
    #    create_instance.retry()

    db_name_list = []
    for database in databases:
        db_name_list.append(database['name'])
        if username:
            add_user.delay(context, instance.id, db_name_list,
                                  username, password)

    results = dict(id=instance.id, name=instance.name, status=instance.status,
            hostname=instance.hostname)
    if prefix:
        # Add each value back in with the prefix
        results.update({'%s.%s' % (prefix, key): value for key, value in
                results.iteritems()})

    return results


@task(default_retry_delay=10, max_retries=10)
def add_databases(deployment, instance_id, databases, api=None):
    """Adds new database(s) to an existing instance.

    database is a list of dictionaries with a required key for database
    name and optional keys for setting the character set and collation.
    For example:

        databases = [{'name': 'mydb1'}]
        databases = [{'name': 'mydb2', 'character_set': 'latin5',
                    'collate': 'latin5_turkish_ci'}]
        databases = [{'name': 'mydb3'}, {'name': 'mydb4'}]
    """
    if api is None:
        api = _get_db_object(deployment)

    dbnames = []
    for db in databases:
        dbnames.append(db['name'])

    try:
        instance = api.get_instance(instance_id)
        instance.create_databases(databases)
        LOG.debug(
            'Added database(s) %s to instance %s' % (dbnames,
                                                     instance_id))
    except clouddb.errors.ResponseError, exc:
        LOG.debug(
            'Response error while trying to add new database(s) %s to ' \
            'instance %s. Error %d %s. Retrying.' % (
              dbnames, instance_id, exc.status, exc.reason))
        add_databases.retry(exc=exc)
    except Exception, exc:
        LOG.debug(
            'Error adding database(s) %s to instance %s. Error %s. ' \
            'Retrying.' % (
              dbnames, instance_id, str(exc)))
        add_databases.retry()


@task(default_retry_delay=10, max_retries=10)
def add_user(deployment, instance_id, databases, username,
                        password, api=None):
    """Add a database user to an instance for a database"""
    if api is None:
        api = _get_db_object(deployment)

    try:
        instance = api.get_instance(instance_id)
        instance.create_user(username, password, databases)
        LOG.debug(
            'Added user %s to %s on instance %s' % (username,
                                                    databases,
                                                    instance_id))
    except clouddb.errors.ResponseError, exc:
        LOG.debug(
            'Response error while trying to add database user %s to %s ' \
            'on instance %s. Error %s %s. Retrying.' % (
              username, databases, instance_id, exc.status,
              exc.reason))
        add_user.retry(exc=exc)
    except Exception, exc:
        LOG.debug(
            'Error creating database user %s, database %s, instance %s.' \
            ' Error %s. Retrying.' % (
              username, databases, instance_id, str(exc)))
        add_user.retry()


@task(default_retry_delay=10, max_retries=10)
def delete_instance(deployment, instance_id, api=None):
    """Deletes a database instance and its associated databases and
    users.
    """
    if api is None:
        api = _get_db_object(deployment)

    try:
        api.delete_instance(instanceid=instance_id)
        LOG.debug('Database instance %s deleted.' % instance_id)
    except clouddb.errors.ResponseError, exc:
        LOG.debug(
            'Response error while trying to delete database instance ' \
            '%s. Error %d %s. Retrying.' % (
              instance_id, exc.status, exc.reason))
        delete_database.retry(exc=exc)
    except Exception, exc:
        LOG.debug(
            'Error deleting database instance %s. Error %s. Retrying.' % (
            instance_id, str(exc)))
        delete_database.retry()


@task(default_retry_delay=10, max_retries=10)
def delete_database(deployment, instance_id, db, api=None):
    """Delete a database from an instance"""
    if api is None:
        api = _get_db_object(deployment)

    try:
        instance = api.get_instance(instance_id)
        instance.delete_database(db)
        LOG.debug('Database %s deleted from instance %s' % (db, instance_id))
    except clouddb.errors.ResponseError, exc:
        LOG.debug(
            'Response error while trying to delete database %s from ' \
            'instance %s. Error %d %s. Retrying.' % (
              db, instance_id, exc.status, exc.reason))
        delete_database.retry(exc=exc)
    except Exception, exc:
        LOG.debug(
            'Error deleting database %s from instance %s. Error %s. ' \
            'Retrying.' % (
              db, instance_id, str(exc)))
        delete_database.retry()


@task(default_retry_delay=10, max_retries=10)
def delete_user(deployment, instance_id, username, api=None):
    """Delete a database user from an instance."""
    """
    if api is None:
        api = _get_db_object(deployment)

    try:
        instance = api.get_instance(instanceid=instance_id)
        instance.delete_user(username)
        LOG.debug(
            'Deleted user %s from database instance %d' % (username,
                                                           instance_id))
    except clouddb.errors.ResponseError, exc:
        LOG.debug(
            'Response error while trying to delete database user %s to ' \
            '%s on instance %d. Error %d %s. Retrying.' % (
              username, database_name, instance_id, exc.status, exc.reason))
        delete_user.retry(exc=exc)
    except Exception, exc:
        LOG.debug(
            'Error deleting database user %s, database %s, instance %s.' \
            ' Error %s. Retrying.' % (
              username, database_name, instance_id, str(exc)))
        delete_user.retry(exc=exc)
    """
