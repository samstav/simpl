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

"""Rackspace Cloud DNS provider module."""

import logging
import os
import sys

import eventlet.greenpool
import pyrax
import SpiffWorkflow.operators
from SpiffWorkflow.specs import Celery
import tldextract

from checkmate.common import caching
from checkmate.providers import base
from checkmate.providers.rackspace import base as rsbase

LOG = logging.getLogger(__name__)
DNS_API_CACHE = {}


class Provider(rsbase.RackspaceProviderBase):

    """Rackspace Cloud DNS provider class."""

    name = 'dns'
    vendor = 'rackspace'
    method = 'cloud_dns'

    @caching.CacheMethod(timeout=3600, sensitive_args=[1], store=DNS_API_CACHE)
    def _get_limits(self, url, api):
        """Returns the Cloud DNS API limits."""
        return api.get_absolute_limits()

    def _is_new_domain(self, domain, context):
        """Returns True if domain does not already exist on this account."""
        if domain and context:
            api = self.connect(context)
            dom = self._my_list_domains_info(api, domain)
            return not dom
        return False

    @staticmethod
    def _my_list_domains_info(api, dom_name):
        """Fetch information for specified domain name."""
        try:
            return api.find(name=dom_name)
        except pyrax.exceptions.NotFound as resp_error:
            if resp_error.code != '404':
                LOG.warn("Error checking record limits for %s", dom_name,
                         exc_info=True)

    def _check_record_limits(self, context, dom_name, max_records,
                             num_new_recs):
        """Raise API error if adding domain records will violate limits."""
        if num_new_recs > 0:
            api = self.connect(context)
            if dom_name:
                num_recs = 0
                dom = self._my_list_domains_info(api, dom_name)
                if dom:
                    try:
                        num_recs = len(dom.list_records())
                    except pyrax.exceptions.ClientException as resp_error:
                        num_recs = 0
                        if resp_error.code != '404':
                            LOG.warn("Error getting records for %s", dom_name,
                                     exc_info=True)
                if num_recs + num_new_recs > max_records:
                    return {
                        'type': "INSUFFICIENT-CAPACITY",
                        'message': "Domain %s would have %s records after "
                                   "this operation. You may only have "
                                   "up to %s records for a domain."
                                   % (dom_name, num_recs + num_new_recs,
                                      max_records),
                        'provider': self.name,
                        'severity': "CRITICAL",
                    }

    def verify_limits(self, context, resources):
        messages = []
        api = self.connect(context)
        limits = self._get_limits(self._find_url(context['catalog']), api)
        max_doms = limits.get('absolute', {}).get('domains', sys.maxint)
        max_recs = limits.get('absolute', {}).get('records per domain',
                                                  sys.maxint)
        cur_doms = len(api.list())
        while True:
            try:
                cur_doms = cur_doms + len(api.list_next_page())
            except pyrax.exceptions.NoMoreResults:
                break
        # get a list of the possible domains
        domain_names = []
        for resource in resources:
            if resource.get('dns-name'):
                domain_names.append(resource['dns-name'])

        # find the ones that are new
        pile = eventlet.greenpool.GreenPile()
        for dom in domain_names:
            pile.spawn(self._is_new_domain, dom, context)
        num_new = len([val for val in pile if val])
        # if they are going to create more domains than they
        # should, respond
        if (num_new + cur_doms) > max_doms:
            messages.append({
                'type': "INSUFFICIENT-CAPACITY",
                'message': ("This deployment would create %s domains. "
                            "You have %s domains available."
                            % (num_new, max_doms - cur_doms)),
                'provider': self.name,
                'severity': "CRITICAL"
            })

        def _count_filter_records(resources):
            """Make sure we're not exceeding the record count."""
            handled = {}
            for resource in resources:
                dom = parse_domain(resource.get('dns-name'))
                if dom not in handled:
                    handled[dom] = True
                    yield (dom,
                           len([d for d in resources
                                if parse_domain(d.get('dns-name')) == dom]))

        for dom_name, num_recs in _count_filter_records(resources):
            pile.spawn(self._check_record_limits, context, dom_name, max_recs,
                       num_recs)
        messages.extend([msg for msg in pile if msg])
        return messages

    def verify_access(self, context):
        roles = ['identity:user-admin', 'admin', 'dnsaas:admin',
                 'dnsaas:creator']
        if base.user_has_access(context, roles):
            return {
                'type': "ACCESS-OK",
                'message': "You have access to create Cloud DNS records",
                'provider': self.name,
                'severity': "INFORMATIONAL"
            }
        else:
            return {
                'type': "NO-ACCESS",
                'message': ("You do not have access to create Cloud DNS"
                            " records"),
                'provider': self.name,
                'severity': "CRITICAL"
            }

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        inputs = deployment.get('inputs', {})
        hostname = resource.get('dns-name')

        create_dns_task = Celery(
            wfspec,
            'Create DNS Record',
            'checkmate.providers.rackspace.dns.'
            'create_record',
            call_args=[
                SpiffWorkflow.operators.Attrib('context'),
                inputs.get('domain', 'localhost'),
                hostname,
                'A',
                SpiffWorkflow.operators.Attrib('vip')
            ],
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['final', 'root', 'create']
            ),
            properties={'estimated_duration': 30}
        )
        return dict(root=create_dns_task, final=create_dns_task)

    def get_catalog(self, context, type_filter=None, **kwargs):
        # TODO(any): add more than just regions
        results = {}

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context['catalog']:
                if service['type'] == 'dnsextension:dns':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
            results['regions'] = regions

        return results

    @staticmethod
    def get_resources(context, tenant_id=None):
        """Proxy request through to provider."""
        api = Provider.connect(context)
        return [domain._info for domain in api.list()]

    @staticmethod
    def _find_url(catalog):
        """Find the public endpoint for the DNS service."""
        for service in catalog:
            if service['name'] == 'cloudDNS':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    return endpoint['publicURL']

    @staticmethod
    def connect(context, region=None):
        """Use context info to connect to API and return api object."""
        return getattr(rsbase.RackspaceProviderBase._connect(context, region),
                       Provider.method)


def parse_domain(domain_str):
    """Return "domain.com" for "sub2.sub1.domain.com"."""
    if not domain_str:
        return ""
    extractor = tldextract.TLDExtract(
        cache_file=os.environ.get('CHECKMATE_TLD_CACHE_FILE', None))
    domain_data = extractor(domain_str)
    return '%s.%s' % (domain_data.domain, domain_data.tld)
