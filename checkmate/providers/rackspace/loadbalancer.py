import logging
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery

from checkmate.providers import ProviderBase

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        create_lb = Celery(wfspec, 'Create LB',
                       'stockton.lb.distribute_create_loadbalancer',
                       call_args=[Attrib('context'),
                       resource.get('dns-name'), 'PUBLIC', 'HTTP', 80],
                       dns=True,
                       defines={"Resource": key},
                       properties={'estimated_duration': 30})
        return {'root': create_lb, 'final': create_lb}

    def get_catalog(self, context, type_filter=None):
        #TODO: add more than just regions
        results = {}

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context.catalog:
                if service['type'] == 'rax:load-balancer':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
            results['regions'] = regions

        return results
