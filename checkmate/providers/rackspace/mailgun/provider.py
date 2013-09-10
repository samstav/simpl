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
"""
Mailgun provider module.
"""
import copy
import logging

from SpiffWorkflow import specs

from checkmate.providers import base
from checkmate.providers.rackspace import base as rsbase
from checkmate import utils

LOG = logging.getLogger(__name__)
CATALOG_TEMPLATE = utils.yaml_to_dict("""
mail-relay:
  relay_instance:
    id: relay_instance
    is: mail-relay
    provides:
    - mail-relay: smtp
    options: {}
""")


class Provider(rsbase.RackspaceProviderBase):
    """Provider class from Mailgun."""
    name = 'mailgun'
    vendor = 'rackspace'
    method = name

    __status_mapping__ = {
        'ACTIVE': 'ACTIVE',
    }

    def generate_template(self, deployment, resource_type, service, context,
                          index, key, definition):
        templates = base.ProviderBase.generate_template(
            self, deployment, resource_type, service, context, index,
            key, definition
        )
        return templates

    def get_catalog(self, context, type_filter=None, **kwargs):
        '''Return stored/override catalog if it exists, else connect, build,
        and return one.
        '''

        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #        this for every provider
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
        ''':param resource: the dict of the resource generated by
                generate_template earlier
        :returns: returns the root task in the chain of tasks
        TODO(any): use environment keys instead of private key
        '''
        queued_task_dict = context.get_queued_task_dict(
            deployment=deployment['id'], resource=key)
        create_domain_task = specs.Celery(
            wfspec, 'Create Relay Domain %s (%s)' % (key, resource['service']),
            'checkmate.providers.rackspace.mailgun.create_domain',
            call_args=[
                queued_task_dict,
                "test.local",
                "hard-coded"
            ],
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['create', 'root', 'final']
            ),
            properties={'estimated_duration': 20}
        )

        return dict(
            root=create_domain_task,
            final=create_domain_task,
            create=create_domain_task
        )

    def delete_resource_tasks(self, resource, key, wfspec, deployment, context,
                              wait_on=None):
        ''':param resource: the dict of the resource generated by
                generate_template earlier
        :returns: returns the root task in the chain of tasks
        TODO(any): use environment keys instead of private key
        '''
        queued_task_dict = context.get_queued_task_dict(
            deployment=deployment['id'], resource=key)
        delete_domain_task = specs.Celery(
            wfspec, 'Delete Relay Domain %s (%s)' % (key, resource['service']),
            'checkmate.providers.rackspace.mailgun.delete_domain',
            call_args=[
                queued_task_dict,
                resource.get('id')
            ],
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['delete', 'root', 'final']
            ),
            properties={'estimated_duration': 20}
        )

        return dict(
            root=delete_domain_task,
            final=delete_domain_task,
            delete=delete_domain_task
        )

    @staticmethod
    def get_resources(context, tenant_id=None):
        """Proxy request through to provider"""
        api = Provider.connect(context)
        return api.list() or []

    @staticmethod
    def connect(context):
        '''Use context info to connect to API and return api object.'''
        return getattr(rsbase.RackspaceProviderBase._connect(context),
                       Provider.method)