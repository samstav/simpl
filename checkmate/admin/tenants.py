'''
Tenants
'''
import logging

from checkmate import base
from checkmate.exceptions import CheckmateDoesNotExist

LOG = logging.getLogger(__name__)


class Manager(base.ManagerBase):
    '''Contains Tenants Model and Logic for Accessing Tenants.'''

    def list_tenants(self, *tags):
        '''Get existing tenants.'''
        return self.driver.list_tenants(*tags)

    def save_tenant(self, tenant_id, body):
        '''Save tenant (and overwrite).'''
        body['id'] = tenant_id
        self.driver.save_tenant({
            'id': tenant_id,
            'tags': body.get('tags', []),
        })

    def get_tenant(self, tenant_id):
        '''Get a single tenant.'''
        if tenant_id:
            tenant = self.driver.get_tenant(tenant_id)
            if not tenant:
                raise CheckmateDoesNotExist('No tenant %s' % tenant_id)
            return tenant

    def add_tenant_tags(self, tenant_id, tags):
        '''Add a set of tags to an individual tenant.'''
        if tenant_id:
            if tags is None:
                tags = []
            elif not isinstance(tags, (list, tuple)):
                tags = [tags]
            self.driver.add_tenant_tags(tenant_id, *tags)
