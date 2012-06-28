import logging

from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery, Transform

from checkmate.providers import ProviderBase, register_providers
from checkmate.workflows import wait_for

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    name = 'load-balancer'
    vendor = 'rackspace'

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        create_lb = Celery(wfspec, 'Create LB',
                'stockton.lb.distribute_create_loadbalancer',
                call_args=[Attrib('context'),
                resource.get('dns-name'), 'PUBLIC', 'HTTP', 80],
                dns=True,  # TODO: shouldn't this be parameterized?
                defines=dict(resource=key,
                    provider=self.key,
                    task_tags=['create', 'root']),
                properties={'estimated_duration': 30})

        save_lbid = Transform(wfspec, "Get LB ID",
                transforms=[
                    "my_task.attributes['lbid']=my_task.attributes['id']"],
                defines=dict(resource=key, provider=self.key,
                        task_tags=['final']),
                description="Copies LB ID to lbid field so it doesn't"
                        "conflict with other id fields")
        create_lb.connect(save_lbid)

        return dict(root=create_lb, final=save_lbid)

    def add_connection_tasks(self, resource, key, relation, relation_key,
            wfspec, deployment):
        interface = relation['interface']

        if interface == 'http':
            # Get all tasks we need to precede the LB Add Node task
            finals = self.find_tasks(wfspec, resource=relation['target'],
                    tag='final')
            create_lb = self.find_tasks(wfspec, resource=key,
                    provider=self.key, tag='final')[0]

            #Create the add node task
            add_node = Celery(wfspec,
                    "Add LB Node:%s" % relation['target'],
                    'stockton.lb.distribute_add_node',
                    call_args=[Attrib('context'),  Attrib('lbid'),
                            Attrib('private_ip'), 80],
                    defines=dict(relation=relation_key, provider=self.key,
                            task_tags=['final']),
                    properties={'estimated_duration': 20})

            #Make it wait on all other provider completions
            finals.append(create_lb)
            wait_for(wfspec, add_node, finals,
                    name="Wait before adding to LB:%s" % relation['target'],
                    description="Wait for Load Balancer ID "
                            "and for server to be fully configured before "
                            "adding it to load balancer",
                    defines=dict(relation=relation_key,
                                provider=self.key,
                                task_tags=['root']))

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


register_providers([Provider])
