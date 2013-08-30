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
Stacks Manager

Handles stack logic
"""
import json
import logging

import eventlet
import requests

from checkmate import base
from checkmate import exceptions
from checkmate import utils

LOG = logging.getLogger(__name__)


class Manager(base.ManagerBase):
    """Contains Stacks Model and Logic for Accessing Stacks."""

    def get_stacks(self, context, tenant_id):
        """Gets stacks and deployments."""
        results = {}
        jobs = eventlet.GreenPile(2)
        jobs.spawn(self.get_stacks_only, context, tenant_id)
        jobs.spawn(self.get_deployments_as_stacks, context, tenant_id)
        for ret in jobs:
            results = utils.merge_dictionary(
                results, ret, extend_lists=True)
        return results

    def get_stacks_only(self, context, tenant_id):
        """Get existing stacks."""

        headers = {
            'X-Auth-Token': context.auth_token,
            'Accept': 'application/json',
            'User-Agent': 'python-heatclient',
        }
        response = requests.get(
            'https://api.rs-heat.com/v1/%s/stacks' % tenant_id,
            headers=headers, verify=False)
        stacks = response.json()
        return stacks

    def get_deployments_as_stacks(self, context, tenant_id):
        """Get existing deployments as stack list."""

        stacks = {'stacks': []}

        results = self.driver.get_deployments(
            tenant_id=tenant_id,
        )

        for deployment in results['results'].itervalues():
            try:
                record = {
                    'id': deployment['id'],
                    'stack_name': deployment.get('name', '-no name-'),
                    'stack_status': deployment['status'],
                    'creation_time': deployment.get('created'),
                }
                stacks['stacks'].append(record)
            except StandardError:
                pass

        return stacks

    def create_stack(self, context, tenant_id, stack, auth_key):
        """Create Stack."""

        headers = {
            'X-Auth-Token': context.auth_token,
            'X-Auth-User': context.username,
            'X-Auth-Key': auth_key,
            'Accept': 'application/json',
            'Content-type': 'application/json',
            'User-Agent': 'python-heatclient',
        }
        url = 'https://api.rs-heat.com/v1/%s/stacks' % tenant_id
        self.http_log_req((url, "POST"), dict(headers=headers, verify=False,
                                              data=json.dumps(stack)))
        response = requests.post(url, headers=headers, verify=False,
                                 data=json.dumps(stack))
        try:
            stacks = response.json()
        except Exception:
            raise exceptions.CheckmateException(response.text)

        return stacks

    def get_stack(self, context, tenant_id, stack_id):
        """Get existing stack."""

        headers = {
            'X-Auth-Token': context.auth_token,
            'Accept': 'application/json',
            'User-Agent': 'python-heatclient',
        }
        response = requests.get(
            'https://api.rs-heat.com/v1/%s/stacks/%s' % (tenant_id, stack_id),
            headers=headers, verify=False)
        stack = response.json()
        return stack

    def get_stack_resources(self, context, tenant_id, stack_id):
        """Get existin stack resources."""

        headers = {
            'X-Auth-Token': context.auth_token,
            'Accept': 'application/json',
            'User-Agent': 'python-heatclient',
        }
        response = requests.get(
            'https://api.rs-heat.com/v1/%s/stacks/%s/resources' % (tenant_id,
                                                                   stack_id),
            headers=headers, verify=False)
        resources = response.json()
        return resources

    def get_stack_resource(self, context, tenant_id, name, stack_id,
                           resource_id):
        """Get existin stack resource."""

        headers = {
            'X-Auth-Token': context.auth_token,
            'Accept': 'application/json',
            'User-Agent': 'python-heatclient',
        }
        response = requests.get(
            'https://api.rs-heat.com/v1/%s/stacks/%s/%s/resources/%s' %
            (tenant_id, name, stack_id, resource_id),
            headers=headers, verify=False)
        resource = response.json()
        return resource

    def http_log_req(self, args, kwargs):
        """Log HTTP call as curl command."""
        if not LOG.level != logging.DEBUG:
            return

        string_parts = ['curl -i']
        for element in args:
            if element in ('GET', 'POST', 'DELETE', 'PUT'):
                string_parts.append(' -X %s' % element)
            else:
                string_parts.append(' %s' % element)

        for element in kwargs['headers']:
            header = ' -H "%s: %s"' % (element, kwargs['headers'][element])
            string_parts.append(header)

        if kwargs.get('verify') is False:
            string_parts.append(" -k ")

        if 'data' in kwargs:
            string_parts.append(" -d '%s'" % (kwargs['data']))
        LOG.debug("\nREQ: %s\n", "".join(string_parts))
