import logging

from checkmate import base

LOG = logging.getLogger(__name__)


class Manager(base.ManagerBase):
    def get_resources(self, tenant_id=None, offset=None, limit=None,
                      resource_ids=None):
        return self.driver.get_resources(tenant_id=tenant_id,
                                         offset=offset,
                                         limit=limit,
                                         resource_ids=resource_ids)
