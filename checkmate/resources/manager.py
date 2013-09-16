import logging

from checkmate import db

LOG = logging.getLogger(__name__)


class Manager(object):
    def get_resources(self, tenant_id=None, offset=None,
                      limit=None, query=None):
        return db.get_driver().get_resources(tenant_id=tenant_id,
                                             offset=offset,
                                             limit=limit,
                                             query=query)
