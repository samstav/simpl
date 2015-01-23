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

"""Provider module for interfacing with Cloud Block Storage."""

import copy
import logging

from checkmate.exceptions import (
    BLUEPRINT_ERROR,
    CheckmateException,
)
from checkmate import middleware
from checkmate.providers import base
from checkmate.providers.rackspace.block import cbs
from SpiffWorkflow import specs

COMPONENT_ID = 'rax:block_volume'
CATALOG_TEMPLATE = {
    'volume': {
        COMPONENT_ID: {
            'id': COMPONENT_ID,
            'is': 'volume',
            'provides': [{'volume': 'iscsi'}],
            'options': {}
        }
    }
}

LOG = logging.getLogger(__name__)


class Provider(base.ProviderBase):

    """Provider class for Cloud Block Storage."""

    name = 'block'
    vendor = 'rackspace'

    __status_mapping__ = {
        'available': 'ACTIVE',
    }

    def generate_template(self, deployment, resource_type, service, context,
                          index, key, definition):
        templates = base.ProviderBase.generate_template(
            self, deployment, resource_type, service, context, index, self.key,
            definition
        )

        # Get volume size
        size = deployment.get_setting('size',
                                      resource_type=resource_type,
                                      service_name=service,
                                      provider_key=self.key,
                                      default=100)

        # Get region
        region = deployment.get_setting('region',
                                        resource_type=resource_type,
                                        service_name=service,
                                        provider_key=self.key)
        if not region:
            message = ("Could not identify which region to create "
                       "volume in")
            raise CheckmateException(message, friendly_message=BLUEPRINT_ERROR)

        for template in templates:
            template['desired-state']['size'] = size
            template['desired-state']['region'] = region

        return templates

    def verify_limits(self, context, resources):
        """Verify that deployment stays within absolute resource limits."""

        # Block storage absolute limits are currently hard-coded
        # The limits are per customer per region.
        volume_size_limit = 1000
        instance_limit = 25

        volumes_needed = 0
        total_size_needed = 0
        for resource in resources:
            if resource['type'] == 'volume':
                volumes_needed += 1
                total_size_needed += resource['desired-state']['size']

        instances = cbs.list_volumes(context['access'], context['region'])
        instances_used = len(instances)
        volume_size_used = 0
        for instance in instances:
            volume_size_used += instance['size']

        instances_available = instance_limit - instances_used
        quota_size_available = volume_size_limit - volume_size_used

        messages = []
        if volumes_needed > instances_available:
            messages.append({
                'type': "INSUFFICIENT-CAPACITY",
                'message': "This deployment would create %s Block Volumes "
                           "instances.  You have %s instances available."
                           % (volumes_needed, instances_available),
                'provider': "block",
                'severity': "CRITICAL"
            })
        if total_size_needed > quota_size_available:
            messages.append({
                'type': "INSUFFICIENT-CAPACITY",
                'message': "This deployment would require %s GB in disk "
                           "space.  You have %s GB available."
                           % (total_size_needed, quota_size_available),
                'provider': "block",
                'severity': "CRITICAL"
            })
        return messages

    def verify_access(self, context):
        """Verify that the user has permissions to create volumes."""
        roles = ['identity:user-admin', 'admin', 'cbs:admin', 'cbs:creator']
        if base.user_has_access(context, roles):
            return {
                'type': "ACCESS-OK",
                'message': "You have access to create Block Storage volumes",
                'provider': "block",
                'severity': "INFORMATIONAL"
            }
        else:
            return {
                'type': "NO-ACCESS",
                'message': ("You do not have access to create Block Storage "
                            "volumes"),
                'provider': "block",
                'severity': "CRITICAL"
            }

    def get_catalog(self, context, type_filter=None, **kwargs):
        """Return stored/override catalog if it exists, else connect, build,
        and return one."""
        results = base.ProviderBase.get_catalog(self, context,
                                                type_filter=type_filter)
        if results:
            # We have a prexisting or overridecatalog stored
            return results

        # build a live catalog ()this would be the on_get_catalog called if no
        # stored/override existed
        results = copy.deepcopy(CATALOG_TEMPLATE)
        return results

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        wait_on, service_name, component = self._add_resource_tasks_helper(
            resource, key, wfspec, deployment, context, wait_on)

        assert component['id'] == COMPONENT_ID

        # Create resource tasks
        create_volume_task = specs.Celery(
            wfspec,
            'Create Volume %s' % key,
            'checkmate.providers.rackspace.block.tasks.create_volume',
            call_args=[
                context.get_queued_task_dict(
                    deployment_id=deployment['id'],
                    resource_key=key
                ),
                resource['desired-state']['region'],
                resource['desired-state']['size'],
            ],
            tags=self.generate_resource_tag(
                context.base_url, context.tenant, deployment['id'],
                resource['index']
            ),
            merge_results=True,
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['create', 'root', 'final']
            ),
            properties={'estimated_duration': 10}
        )

        return dict(root=create_volume_task, final=create_volume_task)

    def delete_resource_tasks(self, wf_spec, context, deployment_id, resource,
                              key):
        instance = resource.get('instance', {})
        region = instance.get('region') or instance.get('host_region')
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

        delete_volume = specs.Celery(
            wf_spec, 'Delete Block Volume (%s)' % key,
            'checkmate.providers.rackspace.block.tasks.delete_volume',
            call_args=[context, region, instance['id']],
            properties={'estimated_duration': 15})

        return {'root': delete_volume, 'final': delete_volume}

    @staticmethod
    def connect(context, region=None):
        """Return API connection."""
        return cbs
