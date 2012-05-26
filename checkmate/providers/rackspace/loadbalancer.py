import logging
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery

from checkmate.providers import ProviderBase

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    def add_resource_tasks(self, resource, key, wfspec, deployment,
            stockton_deployment, wait_on=None):
        return Celery(wfspec, 'Create LB',
                       'stockton.lb.distribute_create_loadbalancer',
                       call_args=[Attrib('deployment'),
                       resource.get('dns-name'), 'PUBLIC', 'HTTP', 80],
                       dns=True,
                       defines={"Resource": key})
