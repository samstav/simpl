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

"""Provider module for interfacing with Cloud Databases."""

import copy
import logging
import os
import string

from celery import canvas

import pyrax
import redis
from SpiffWorkflow import operators
from SpiffWorkflow import specs

from checkmate.common import caching
from checkmate.common import schema
from checkmate.exceptions import (
    BLUEPRINT_ERROR,
    CheckmateException,
    CheckmateNoMapping,
)
from checkmate import middleware
from checkmate.providers import base as cmbase
from checkmate.providers.rackspace import base
from checkmate.providers.rackspace.database import dbaas
from checkmate import utils

LOG = logging.getLogger(__name__)
API_FLAVOR_CACHE = {}
REDIS = None
if 'CHECKMATE_CACHE_CONNECTION_STRING' in os.environ:
    try:
        REDIS = redis.from_url(os.environ['CHECKMATE_CACHE_CONNECTION_STRING'])
    except StandardError as exc:
        LOG.warn("Error connecting to Redis: %s", exc)
CATALOG_TEMPLATE = schema.load_catalog(os.path.join(os.path.dirname(__file__),
                                                    'catalog.yaml'))


class Provider(cmbase.ProviderBase):

    """Provider class for Cloud Databases."""

    name = 'database'
    method = 'cloud_databases'
    vendor = 'rackspace'

    __status_mapping__ = {
        'ACTIVE': 'ACTIVE',
        'BLOCKED': 'ERROR',
        'BUILD': 'BUILD',
        'DELETED': 'DELETED',
        'ERROR': 'ERROR',
        'REBOOT': 'CONFIGURE',
        'RESIZE': 'CONFIGURE',
        'SHUTDOWN': 'CONFIGURE',
    }

    def generate_template(self, deployment, resource_type, service, context,
                          index, key, definition, planner):
        """Generate templates incl. `desired-state` based on passed in args."""
        templates = cmbase.ProviderBase.generate_template(
            self, deployment, resource_type, service, context, index, self.key,
            definition, planner
        )
        catalog = self.get_catalog(context)

        if resource_type in ('compute', 'cache'):
            # Get flavor
            # Find same or next largest size and get flavor ID
            flavor = None
            memory = self.parse_memory_setting(
                deployment.get_setting('memory',
                                       resource_type=resource_type,
                                       service_name=service,
                                       provider_key=self.key) or 512
            )

            # Find the available memory size that satisfies this
            # 'memory' in the blueprint maps to 'flavor' in the provider
            matches = [e['memory'] for e in catalog['lists']['sizes'].values()
                       if int(e['memory']) >= memory]
            if not matches:
                raise CheckmateNoMapping("No flavor has at least '%s' memory" %
                                         memory)
            match = str(min(matches))
            for key, value in catalog['lists']['sizes'].iteritems():
                if match == str(value['memory']):
                    flavor = key
                    if resource_type == 'cache':
                        flavor = str(int(flavor) + 100)
                    LOG.debug("Mapping flavor from '%s' to '%s'", memory, key)
                    break

            if not flavor:
                raise CheckmateNoMapping("No flavor mapping for '%s' in '%s'" %
                                         (memory, self.key))

            # Get volume size
            volume = deployment.get_setting('disk',
                                            resource_type=resource_type,
                                            service_name=service,
                                            provider_key=self.key)

            # Get region
            region = deployment.get_setting('region',
                                            resource_type=resource_type,
                                            service_name=service,
                                            provider_key=self.key)
            if not region:
                message = ("Could not identify which region to create "
                           "database in")
                raise CheckmateException(message,
                                         friendly_message=BLUEPRINT_ERROR)

            # 'flavor' in the blueprint maps to datastore type in the provider
            datastore_type = deployment.get_setting(
                'flavor',
                resource_type=resource_type,
                service_name=service,
                provider_key=self.key
            )
            datastore_ver = deployment.get_setting(
                'version',
                resource_type=resource_type,
                service_name=service,
                provider_key=self.key
            )

            # Set sane defaults for datastore_type and datastore_ver
            if not datastore_type:
                if resource_type == 'cache':
                    datastore_type = 'redis'
                else:
                    datastore_type = 'mysql'

            if not datastore_ver:
                datastore_ver = dbaas.latest_datastore_ver(context,
                                                           datastore_type)

            if not volume and datastore_type != 'redis':
                volume = 1

            # Retrieve a current list of config params from dbaas
            params = dbaas.get_config_params(context, datastore_type,
                                             datastore_ver)

            # Add settings that match a config param to config_params
            config_params = {}
            for param in params:
                option = deployment.get_setting(param['name'],
                                                resource_type=resource_type,
                                                service_name=service,
                                                provider_key=self.key)
                if option:
                    config_params[param['name']] = option

            # Handle replica instance
            replica_of = None
            relations = {}
            for r_id, resource in planner.resources.iteritems():
                if (resource['type'] == 'database-replica' and
                        resource['service'] == service):
                    master_db = resource['desired-state']['master-db-id']
                    replica_of = planner.resources[master_db]['hosted_on']
                    master_index = planner.resources[replica_of]['index']
                    relation_key = 'replica-of-%s' % master_index
                    relations = {
                        relation_key: {
                            'key': relation_key,
                            'type': 'reference',
                            'target': master_index,
                        }
                    }
                    break

            for template in templates:
                template['desired-state']['flavor'] = flavor
                template['desired-state']['region'] = region
                template['desired-state']['datastore-type'] = datastore_type
                template['desired-state']['datastore-version'] = datastore_ver
                if volume:
                    template['desired-state']['disk'] = volume
                if config_params:
                    template['desired-state']['config-params'] = config_params
                if replica_of:
                    template['desired-state']['replica-of'] = replica_of
                    template['relations'] = relations

        # Handle replica database
        elif resource_type == 'database-replica':
            master_db = definition['requires']['database:mysql']
            master_service = master_db['satisfied-by']['service']
            master_db_id = None
            for r_id, resource in planner.resources.iteritems():
                if resource['service'] == master_service:
                    master_db_id = r_id

            for template in templates:
                template['desired-state']['master-db-id'] = master_db_id

        elif resource_type == 'database':
            pass

        return templates

    def verify_limits(self, context, resources):
        """Verify that deployment stays within absolute resource limits."""
        # Cloud databases absolute limits are currently hard-coded
        # The limits are per customer per region.
        volume_size_limit = 150
        instance_limit = 25

        instances_needed = 0
        volume_size_needed = 0
        for database in resources:
            if database['type'] in ('compute', 'cache'):
                instances_needed += 1
                volume_size_needed += database['desired-state']['disk']

        cdb = self.connect(context)
        instances = cdb.list()
        instances_used = len(instances)
        volume_size_used = 0
        for instance in instances:
            volume_size_used += instance.volume.size

        instances_available = instance_limit - instances_used
        volume_size_available = volume_size_limit - volume_size_used

        messages = []
        if instances_needed > instances_available:
            messages.append({
                'type': "INSUFFICIENT-CAPACITY",
                'message': "This deployment would create %s Cloud Database "
                           "instances.  You have %s instances available."
                           % (instances_needed, instances_available),
                'provider': "database",
                'severity': "CRITICAL"
            })
        if volume_size_needed > volume_size_available:
            messages.append({
                'type': "INSUFFICIENT-CAPACITY",
                'message': "This deployment would require %s GB in disk "
                           "space.  You have %s GB available."
                           % (volume_size_needed, volume_size_available),
                'provider': "database",
                'severity': "CRITICAL"
            })
        return messages

    def verify_access(self, context):
        """Verify user has permissions to create database resources."""
        roles = ['identity:user-admin', 'admin', 'dbaas:admin',
                 'dbaas:creator']
        if cmbase.user_has_access(context, roles):
            return {
                'type': "ACCESS-OK",
                'message': "You have access to create Cloud Databases",
                'provider': "database",
                'severity': "INFORMATIONAL"
            }
        else:
            return {
                'type': "NO-ACCESS",
                'message': "You do not have access to create Cloud Databases",
                'provider': "database",
                'severity': "CRITICAL"
            }

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        """Set up Celery task flow based on resource type."""
        wait_on, service_name, component = self._add_resource_tasks_helper(
            resource, key, wfspec, deployment, context, wait_on)

        resource_type = resource.get('type', resource.get('resource_type'))
        if component['is'] in ['database', 'database-replica']:
            # For now, ignore all of this if we're spinning up a Redis
            # instance. We definitely don't need the create_database task, but
            # we may need the add_user task.
            if resource.get('component') == 'redis_database':
                return

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
                username = 'db_user_%s' % db_name

            # Password
            password = deployment.get_setting('database/password',
                                              resource_type=resource_type,
                                              provider_key=self.key,
                                              service_name=service_name)
            if not password:
                password = utils.generate_password(
                    valid_chars=''.join(
                        [string.ascii_letters, string.digits, '@?#_']
                    ),
                    min_length=12
                )

            elif password.startswith('=generate'):
                password = self.evaluate(password[1:])

            if password:
                start_with = string.ascii_uppercase + string.ascii_lowercase
                if password[0] not in start_with:
                    error_message = ("Database password must start with one "
                                     "of '%s'" % start_with)
                    raise CheckmateException(error_message)

            is_replica = component['is'] == 'database-replica'

            # Create resource tasks
            create_database_task = specs.Celery(
                wfspec,
                'Create Database %s for resource %s' % (db_name, key),
                'checkmate.providers.rackspace.database.tasks.create_database',
                call_args=[
                    context.get_queued_task_dict(
                        deployment_id=deployment['id'],
                        resource_key=key
                    ),
                    db_name,
                    operators.PathAttrib(
                        'resources/%s/instance/region' %
                        resource['hosted_on']
                    ),
                ],
                instance_id=operators.PathAttrib(
                    'resources/%s/instance/id' % resource['hosted_on']
                ),
                replica=is_replica,
                defines=dict(
                    resource=key,
                    provider=self.key,
                    task_tags=['create', 'root']
                ),
                properties={'estimated_duration': 80}
            )
            create_db_user = specs.Celery(
                wfspec,
                "Add DB User %s for resource %s" % (username, key),
                'checkmate.providers.rackspace.database.tasks.add_user',
                call_args=[
                    context.get_queued_task_dict(
                        deployment_id=deployment['id'],
                        resource_key=key
                    ),
                    operators.PathAttrib(
                        'resources/%s/instance/host_instance' % key),
                    [db_name],
                    username,
                    password,
                    operators.PathAttrib(
                        'resources/%s/instance/host_region' % key),
                ],
                replica=is_replica,
                defines=dict(
                    resource=key,
                    provider=self.key,
                    task_tags=['final']
                ),
                properties={'estimated_duration': 20}
            )

            create_db_user.follow(create_database_task)
            root = wfspec.wait_for(create_database_task, wait_on)
            return dict(root=root, final=create_db_user)
        elif component['is'] in ('compute', 'cache'):
            defines = dict(resource=key,
                           resource_type=resource_type,
                           interface=resource.get('interface'),
                           provider=self.key,
                           task_tags=['create', 'root'])
            LOG.info('Resource: %s', resource)
            if component['is'] == 'cache':
                name = 'cache'
            else:
                name = resource.get('interface') or 'database'

            # Create resource tasks
            root = None
            if 'config-params' in resource.get('desired-state', {}):
                create_config_task = specs.Celery(
                    wfspec,
                    'Create Database %s %s Configuration' % (name.capitalize(),
                                                             key),
                    'checkmate.providers.rackspace.database.tasks.'
                    'create_configuration',
                    call_args=[
                        context.get_queued_task_dict(
                            deployment_id=deployment['id'],
                            resource_key=key
                        ),
                        '%s-%s' % (name, key),
                        resource['desired-state']['datastore-type'],
                        resource['desired-state']['datastore-version'],
                        resource['desired-state']['config-params']
                    ],
                    defines=defines,
                    properties={'estimated_duration': 10}
                )
                root = wfspec.wait_for(create_config_task, wait_on)

            # Check for replica status and set needed variables
            replica_id = resource.get('desired-state', {}).get('replica-of')
            replica_of = None
            wait_for_master = None
            if replica_id:
                replica_of = operators.PathAttrib(
                    'resources/%s/instance/id' % replica_id)
                wait_for_master = wfspec.find_task_specs(resource=replica_id,
                                                         tag='final')

            create_instance_task = specs.Celery(
                wfspec,
                'Create %s Server %s' % (name.capitalize(), key),
                'checkmate.providers.rackspace.database.tasks.'
                'create_instance',
                call_args=[
                    context.get_queued_task_dict(
                        deployment_id=deployment['id'],
                        resource_key=key
                    ),
                    resource.get('dns-name'),
                    resource['desired-state']
                ],
                replica_of=replica_of,
                config_id=operators.PathAttrib(
                    'resources/%s/instance/configuration/id' % key),
                defines=defines,
                properties={'estimated_duration': 80}
            )

            if root:
                create_instance_task.follow(root)
            else:
                root = wfspec.wait_for(create_instance_task, wait_on)

            # No 'final' task for the master DB means master DB creation is
            # not a part of this workflow (it was a part of a previous
            # workflow). i.e. we're scaling up replication on an existing
            # deployment. Otherwise, wait for the master instance to come up.
            if wait_for_master:
                root.follow(wait_for_master[0])

            wait_task = specs.Celery(
                wfspec,
                'Wait on %s Instance %s' % (name.capitalize(), key),
                'checkmate.providers.rackspace.database.tasks.wait_on_build',
                call_args=[
                    context.get_queued_task_dict(
                        deployment_id=deployment['id'],
                        resource_key=key,
                        resource=resource,
                        region=resource['desired-state']['region'],
                        resource_type=resource_type
                    ),
                ],
                defines=dict(
                    resource=key,
                    provider=self.key,
                    task_tags=['final']
                ),
                properties={'estimated_duration': 80,
                            'auto_retry_count': 3},
                instance=operators.PathAttrib('resources/%s/instance' % key)
            )
            wait_task.follow(create_instance_task)
            return dict(root=root, final=wait_task)
        elif resource.get('component') != 'redis_cache':
            error_message = ("Unsupported component type '%s' for  provider "
                             "%s" % (component['is'], self.key))
            raise CheckmateException(error_message)

    def get_resource_status(self, context, deployment_id, resource, key,
                            sync_callable=None, api=None):
        """Sync deployment's resource to actual state, and return status."""
        from checkmate.providers.rackspace.database import tasks
        if (api is None and 'instance' in resource and
                'region' in resource['instance']):
            region = resource['instance']['region']
            api = Provider.connect(context, region=region)
        return tasks.sync_resource_task(context, resource, api=api)

    @staticmethod
    def delete_one_resource(context):
        """Used by ProviderTask to create delete tasks for errored instances.

        :param context:
        :return:
        """
        resource_type = context.get("resource_type")
        assert resource_type is not None
        if resource_type == 'compute':
            return Provider._delete_comp_res_task(context)
        if resource_type == 'database':
            return Provider._delete_db_res_task(context)
        raise CheckmateException("Unknown resource type for resource")

    def delete_resource_tasks(self, wf_spec, context, deployment_id, resource,
                              key):
        """Delete `resource` from deployment `deployment_id`."""
        self._verify_existing_resource(resource, key)
        region = (resource.get('region') or
                  resource.get('instance', {}).get('host_region'))
        if isinstance(context, middleware.RequestContext):
            context = context.get_queued_task_dict(deployment_id=deployment_id,
                                                   resource_key=key,
                                                   resource=resource,
                                                   region=region)
        else:
            context['deployment_id'] = deployment_id
            context['resource_key'] = key
            context['resource'] = resource
            context['region'] = region

        if resource.get('type') in ('compute', 'cache'):
            return self._delete_comp_res_tasks(wf_spec, context, key)
        if resource.get('type') in ['database', 'database-replica']:
            return self._delete_db_res_tasks(wf_spec, context, key)
        message = ("Cannot provide delete tasks for resource %s: Invalid "
                   "resource type '%s'" % (key, resource.get('type')))
        raise CheckmateException(message)

    @staticmethod
    def _delete_comp_res_tasks(wf_spec, context, key):
        """Delete Compute Resource Tasks."""
        delete_instance = specs.Celery(
            wf_spec, 'Delete Compute Resource Tasks (%s)' % key,
            'checkmate.providers.rackspace.database.tasks.'
            'delete_instance_task',
            call_args=[context],
            properties={'estimated_duration': 5}
        )

        wait_on_delete = specs.Celery(
            wf_spec, 'Wait on delete Database (%s)' % key,
            'checkmate.providers.rackspace.database.tasks.'
            'wait_on_del_instance',
            call_args=[context],
            properties={'estimated_duration': 10}
        )

        delete_instance.connect(wait_on_delete)

        # if a configuration exists, delete it too
        config_id = context['resource'].get(
            'instance', {}).get('configuration', {}).get('id')
        if config_id:
            delete_configuration = specs.Celery(
                wf_spec, 'Delete Database Configuration (%s)' % config_id,
                'checkmate.providers.rackspace.database.tasks.'
                'delete_configuration',
                call_args=[context, config_id],
                properties={'estimated_duration': 10}
            )
            wait_on_delete.connect(delete_configuration)

        return {'root': delete_instance, 'final': wait_on_delete}

    @staticmethod
    def _delete_comp_res_task(context):
        """Return a chain of delete tasks to remove an instance.

        :param context:
        :return:
        """
        from checkmate.providers.rackspace.database import tasks
        return canvas.chain(
            tasks.delete_instance_task.si(context),
            tasks.wait_on_del_instance.si(context)
        )

    @staticmethod
    def _delete_db_res_task(context):
        """Return a chain of delete task to remove a db resource.

        :param context:
        :return:
        """
        from checkmate.providers.rackspace.database import tasks
        return canvas.chain(
            tasks.delete_database.si(context),
        )

    @staticmethod
    def _delete_db_res_tasks(wf_spec, context, key):
        """Return delete tasks for the specified database instance."""
        delete_db = specs.Celery(
            wf_spec, 'Delete DB Resource tasks (%s)' % key,
            'checkmate.providers.rackspace.database.tasks.delete_database',
            call_args=[context],
            properties={'estimated_duration': 15}
        )

        return {'root': delete_db, 'final': delete_db}

    def get_catalog(self, context, type_filter=None, **kwargs):
        """Return stored/override catalog if it exists, else build one."""
        # TODO(any): maybe implement this an on_get_catalog so we don't have to
        #        do this for every provider
        results = cmbase.ProviderBase.get_catalog(
            self, context, type_filter=type_filter)
        if results:
            # We have a prexisting or overridecatalog stored
            return results

        # build a live catalog this would be the on_get_catalog called if no
        # stored/override existed
        region = context.get('region')
        if not region:
            region = Provider.find_a_region(context['catalog'])
        api_endpoint = Provider.find_url(context['catalog'], region)
        if type_filter is None or type_filter == 'database':
            results['database'] = copy.deepcopy(CATALOG_TEMPLATE['database'])
        if type_filter is None or type_filter == 'cache':
            results['cache'] = copy.deepcopy(CATALOG_TEMPLATE['cache'])
        if type_filter is None or type_filter == 'compute':
            results['compute'] = copy.deepcopy(CATALOG_TEMPLATE['compute'])

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context['catalog']:
                if service['type'] == 'rax:database':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['regions'] = regions

        if type_filter is None or type_filter == 'size':
                                          context['auth_token'])
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['sizes'] = {
                str(f['id']): {
                    'name': f.get('name'),
                    'memory': f.get('ram')
                } for f in flavors if 'id' in f
            }

        self.validate_catalog(results)
        if type_filter is None:
            self._dict['catalog'] = results
        return results

    @staticmethod
    def get_resources(context, tenant_id=None):
        """Proxy request through to cloud database provider."""
        if not (pyrax.identity and pyrax.identity.authenticated):
            Provider.connect(context)
        db_hosts = []
        for region in pyrax.regions:
            api = Provider.connect(context, region=region)
            try:
                db_hosts += api.list()
            except AttributeError as exc:
                # TODO(zns): fix upstream. Ignore pyrax error parsing redis.
                if "object has no attribute 'volume'" not in str(exc):
                    raise
        results = []
        for db_host in db_hosts:
            if int(db_host.flavor.id) >= 100:  # redis flavors
                resource = {
                    'status': db_host.status,
                    'provider': 'database',
                    'dns-name': db_host.name,
                    'instance': {
                        'status': db_host.status,
                        'name': db_host.name,
                        'region': db_host.manager.api.region_name,
                        'id': db_host.id,
                        'interfaces': {
                            'redis': {
                                'host': db_host.hostname
                            }
                        },
                        'flavor': db_host.flavor.id,
                    },
                    'type': 'database',
                    'meta-data': {
                        'display-hints': {
                            'icon-20x20': "/images/edis-icon-20x20",
                            'tattoo': "/images/redis-tattoo.png",
                        }
                    }
                }
            else:
                resource = {
                    'status': db_host.status,
                    'provider': 'database',
                    'dns-name': db_host.name,
                    'instance': {
                        'status': db_host.status,
                        'name': db_host.name,
                        'region': db_host.manager.api.region_name,
                        'id': db_host.id,
                        'interfaces': {
                            'mysql': {
                                'host': db_host.hostname
                            }
                        },
                        'flavor': db_host.flavor.id,
                        'disk': db_host.volume.size,
                    },
                    'hosts': [],
                    'type': 'compute',
                    'meta-data': {
                        'display-hints': {
                            'icon-20x20': "/images/mysql-small.png",
                            'tattoo': "/images/mysql-tattoo.png",
                        }
                    }
                }
            results.append(resource)
        return results

    @staticmethod
    def find_url(catalog, region):
        """Return a URL for a region/catalog."""
        for service in catalog:
            if service['type'] == 'rax:database':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    if endpoint.get('region') == region:
                        return endpoint['publicURL']

    @staticmethod
    def find_a_region(catalog):
        """Any region."""
        for service in catalog:
            if service['type'] == 'rax:database':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    return endpoint['region']

    @staticmethod
    def connect(context, region=None):
        """Use context info to connect to API and return api object."""
        return getattr(base.RackspaceProviderBase._connect(
            context, region or context.get('region')), Provider.method)


@caching.Cache(timeout=3600, sensitive_args=[2], store=API_FLAVOR_CACHE,
               backing_store=REDIS, backing_store_key='rax.database.flavors',
               ignore_args=[0])
def _get_flavors(context, api_endpoint, auth_token):
    """Ask DBaaS for Flavors (RAM, CPU, HDD) options."""
    # the region must be supplied but is not used
    api = Provider.connect(context)
    LOG.info("Calling Cloud Databases to get flavors for %s",
             api.management_url)
    results = api.list_flavors() or []
    return [flavor._info for flavor in results]  # pylint: disable=W0212
