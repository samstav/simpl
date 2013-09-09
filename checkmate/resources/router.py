import logging

LOG = logging.getLogger(__name__)


class Router(object):
    def __init__(self, app, manager):
        self.app = app
        self.manager = manager

        app.route('/resources', 'GET', self.get_resources)

    def get_resources(self, tenant_id=None, offset=None, limit=None):
        return self.manager.get_resources(tenant_id=tenant_id, offset=offset,
                                          limit=limit)
