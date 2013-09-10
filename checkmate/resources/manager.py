import logging

from checkmate import base

LOG = logging.getLogger(__name__)


class Manager(base.ManagerBase):
    def get_resources(self, tenant_id=None, offset=None, limit=None,
                      resource_type=None, provider=None):
        return self.driver.get_resources(tenant_id=tenant_id,
                                         offset=offset,
                                         limit=limit,
                                         resource_type=resource_type,
                                         provider=provider)
