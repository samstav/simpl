import logging

from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery

from checkmate.providers import ProviderBase, register_providers

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    name = 'dns'
    vendor = 'rackspace'

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        inputs = deployment.get('inputs', {})
        hostname = resource.get('dns-name')

        create_dns_task = Celery(wfspec, 'Create DNS Record',
                           'stockton.dns.distribute_create_record',
                           call_args=[Attrib('context'),
                           inputs.get('domain', 'localhost'), hostname,
                           'A', Attrib('vip')],
                           defines=dict(resource=key,
                                        provider=self.key,
                                        task_tags=['final', 'root', 'create']),
                           properties={'estimated_duration': 30})
        return dict(root=create_dns_task, final=create_dns_task)

    def get_catalog(self, context, type_filter=None):
        #TODO: add more than just regions
        results = {}

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context.catalog:
                if service['type'] == 'dnsextension:dns':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
            results['regions'] = regions

        return results


register_providers([Provider])
