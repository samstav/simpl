# Copyright (c) 2011-2013 Rackspace Hosting
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
import logging
import os
import string

import clouddb

from celery import canvas

import pyrax
import redis
from SpiffWorkflow import operators
from SpiffWorkflow import specs

from checkmate.common import caching
from checkmate.exceptions import (
    BLUEPRINT_ERROR,
    CheckmateException,
    CheckmateNoMapping,
)
from checkmate import middleware
from checkmate import providers
from checkmate.providers.rackspace import base
from checkmate import utils

LOG = logging.getLogger(__name__)

# Any names should become airport codes
REGION_MAP = {
    'dallas': 'DFW',
    'chicago': 'ORD',
    'london': 'LON',
    'sydney': 'SYD',
}
API_FLAVOR_CACHE = {}
REDIS = None
if 'CHECKMATE_CACHE_CONNECTION_STRING' in os.environ:
    try:
        REDIS = redis.from_url(os.environ['CHECKMATE_CACHE_CONNECTION_STRING'])
    except StandardError as exc:
        LOG.warn("Error connecting to Redis: %s", exc)


class Provider(providers.ProviderBase):
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
                          index, key, definition):
        templates = providers.ProviderBase.generate_template(self, deployment,
                                                             resource_type,
                                                             service, context,
                                                             index, self.key,
                                                             definition)
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
                    LOG.debug("Mapping flavor from '%s' to '%s'", memory, key)
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
                message = ("Could not identify which region to create "
                           "database in")
                raise CheckmateException(message,
                                         friendly_message=BLUEPRINT_ERROR)

            for template in templates:
                template['flavor'] = flavor
                template['disk'] = volume
                template['region'] = region
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
            if database['type'] == 'compute':
                instances_needed += 1
                volume_size_needed += database['disk']

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
        """Verify that the user has permissions to create database
        resources.
        """
        roles = ['identity:user-admin', 'dbaas:admin', 'dbaas:creator']
        if providers.user_has_access(context, roles):
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

            # Create resource tasks
            create_database_task = specs.Celery(
                wfspec,
                'Create Database',
                'checkmate.providers.rackspace.'
                'database.create_database',
                call_args=[
                    context.get_queued_task_dict(
                        deployment_id=deployment['id'],
                        resource_key=key
                    ),
                    db_name,
                    operators.PathAttrib(
                        'instance:%s/region' %
                        resource['hosted_on']
                    ),
                ],
                instance_id=operators.PathAttrib(
                    'instance:%s/id' % resource['hosted_on']
                ),
                merge_results=True,
                defines=dict(
                    resource=key,
                    provider=self.key,
                    task_tags=['create', 'root']
                ),
                properties={'estimated_duration': 80}
            )
            create_db_user = specs.Celery(
                wfspec,
                "Add DB User: %s" % username,
                'checkmate.providers.rackspace.database.add_user',
                call_args=[
                    context.get_queued_task_dict(
                        deployment_id=deployment['id'],
                        resource_key=key
                    ),
                    operators.PathAttrib('instance:%s/host_instance' % key),
                    [db_name],
                    username,
                    password,
                    operators.PathAttrib('instance:%s/host_region' % key),
                ],
                merge_results=True,
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
        elif component['is'] == 'compute':
            defines = dict(resource=key,
                           resource_type=resource_type,
                           interface=resource.get('interface'),
                           provider=self.key,
                           task_tags=['create', 'root'])
            create_instance_task = specs.Celery(
                wfspec,
                'Create Database Server',
                'checkmate.providers.rackspace.'
                'database.create_instance',
                call_args=[
                    context.get_queued_task_dict(
                        deployment_id=deployment['id'],
                        resource_key=key
                    ),
                    resource.get('dns-name'),
                    resource['flavor'],
                    resource['disk'],
                    None,
                    resource['region'],
                ],
                merge_results=True,
                defines=defines,
                properties={'estimated_duration': 80}
            )
            root = wfspec.wait_for(create_instance_task, wait_on)
            wait_task = specs.Celery(
                wfspec,
                'Wait on Database Instance %s' % key,
                'checkmate.providers.rackspace.database.tasks.wait_on_build',
                call_args=[
                    context.get_queued_task_dict(
                        deployment_id=deployment['id'],
                        resource_key=key,
                        resource=resource,
                        region=resource['region'],
                        resource_type=resource_type
                    ),
                    resource['region'],
                ],
                merge_results=True,
                defines=dict(
                    resource=key,
                    provider=self.key,
                    task_tags=['final']
                ),
                properties={'estimated_duration': 80,
                            'auto_retry_count': 3},
                instance=operators.PathAttrib('instance:%s' % key),
            )
            wait_task.follow(create_instance_task)
            return dict(root=root, final=wait_task)
        else:
            error_message = ("Unsupported component type '%s' for  provider "
                             "%s" % (component['is'], self.key))
            raise CheckmateException(error_message)

    def get_resource_status(self, context, deployment_id, resource, key,
                            sync_callable=None, api=None):
        from checkmate.providers.rackspace.database import sync_resource_task
        if (api is None and 'instance' in resource and
                'region' in resource['instance']):
            region = resource['instance']['region']
            api = Provider.connect(context, region=region)
        sync_resource_task(context, resource, key, api=api)

    @staticmethod
    def delete_one_resource(context):
        """Used by the ProviderTask baseclass to create delete tasks that
        are used to delete errored instances
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
        self._verify_existing_resource(resource, key)
        region = resource.get('region') or \
            resource.get('instance', {}).get('host_region')
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

        if resource.get('type') == 'compute':
            return self._delete_comp_res_tasks(wf_spec, context, key)
        if resource.get('type') == 'database':
            return self._delete_db_res_tasks(wf_spec, context, key)
        message = ("Cannot provide delete tasks for resource %s: Invalid "
                   "resource type '%s'" % (key, resource.get('type')))
        raise CheckmateException(message)

    @staticmethod
    def _delete_comp_res_tasks(wf_spec, context, key):
        """Delete Computer Resource Tasks."""
        delete_instance = specs.Celery(
            wf_spec, 'Delete Computer Resource Tasks (%s)' % key,
            'checkmate.providers.rackspace.database.delete_instance_task',
            call_args=[context], properties={'estimated_duration': 5})

        wait_on_delete = specs.Celery(
            wf_spec, 'Wait on delete Database (%s)' % key,
            'checkmate.providers.rackspace.database.wait_on_del_instance',
            call_args=[context], properties={'estimated_duration': 10})

        delete_instance.connect(wait_on_delete)
        return {'root': delete_instance, 'final': wait_on_delete}

    @staticmethod
    def _delete_comp_res_task(context):
        """Returns a chain of delete tasks to remove an instance
        :param context:
        :return:
        """
        from checkmate.providers.rackspace.database import \
            delete_instance_task, wait_on_del_instance
        return canvas.chain(
            delete_instance_task.si(context),
            wait_on_del_instance.si(context)
        )

    @staticmethod
    def _delete_db_res_task(context):
        """Returns a chain of delete task to remove a db resource
        :param context:
        :return:
        """
        from checkmate.providers.rackspace.database import \
            delete_database
        return canvas.chain(
            delete_database.si(context),
        )

    @staticmethod
    def _delete_db_res_tasks(wf_spec, context, key):
        """Return delete tasks for the specified database instance."""
        delete_db = specs.Celery(
            wf_spec, 'Delete DB Resource tasks (%s)' % key,
            'checkmate.providers.rackspace.database.delete_database',
            call_args=[context], properties={'estimated_duration': 15})

        return {'root': delete_db, 'final': delete_db}

    def get_catalog(self, context, type_filter=None, **kwargs):
        """Return stored/override catalog if it exists, else connect, build,
        and return one.
        """

        # TODO(any): maybe implement this an on_get_catalog so we don't have to
        #        do this for every provider
        results = providers.ProviderBase.get_catalog(
            self, context, type_filter=type_filter)
        if results:
            # We have a prexisting or overridecatalog stored
            return results

        # build a live catalog this would be the on_get_catalog called if no
        # stored/override existed
        region = getattr(context, 'region', None)
        if not region:
            region = Provider.find_a_region(context.catalog)
        api_endpoint = Provider.find_url(context.catalog, region)
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
            flavors = _get_flavors(api_endpoint, context.auth_token)
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['sizes'] = {
                str(f.id): {
                    'name': f.name,
                    'memory': f.ram
                } for f in flavors
            }

        self.validate_catalog(results)
        if type_filter is None:
            self._dict['catalog'] = results
        return results

    @staticmethod
    def get_resources(context, tenant_id=None):
        """Proxy request through to cloud database provider"""
        if not (pyrax.identity and pyrax.identity.authenticated):
            Provider.connect(context)
        db_hosts = []
        for region in pyrax.regions:
            api = Provider.connect(context, region=region)
            db_hosts += api.list()
        results = []
        for db_host in db_hosts:
            resource = {
                'status': db_host.status,
                'region': db_host.manager.api.region_name,
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
                    'flavor': db_host.flavor.id
                },
                'hosts': [],
                'flavor': db_host.flavor.id,
                'disk': db_host.volume.size,
                'type': 'compute'
            }
            results.append(resource)
        return results

    @staticmethod
    def find_url(catalog, region):
        """Returns a URL for a region/catalog."""
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
        return getattr(base.RackspaceProviderBase._connect(context, region),
                       Provider.method)


@caching.Cache(timeout=3600, sensitive_args=[1], store=API_FLAVOR_CACHE,
               backing_store=REDIS, backing_store_key='rax.database.flavors')
def _get_flavors(api_endpoint, auth_token):
    """Ask DBaaS for Flavors (RAM, CPU, HDD) options."""
    # the region must be supplied but is not used
    api = clouddb.CloudDB('ignore', 'ignore', 'DFW')
    api.client.auth_token = auth_token
    api.client.region_account_url = api_endpoint

    LOG.info("Calling Cloud Databases to get flavors for %s",
             api.client.region_account_url)
    return api.flavors.list_flavors()
