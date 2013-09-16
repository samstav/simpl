import bottle
import logging

from checkmate import utils

LOG = logging.getLogger(__name__)


class Router(object):
    def __init__(self, app, manager):
        self.app = app
        self.manager = manager

        app.route('/resources', 'GET', self.get_resources)

    @utils.with_tenant
    @utils.formatted_response('resources', with_pagination=True)
    def get_resources(self, tenant_id=None, offset=None, limit=None):
        limit = utils.cap_limit(limit, tenant_id)  # Avoid DoS from huge limit
        query = {}
        query['resource_ids'] = bottle.request.query.getall('id')
        query['provider'] = bottle.request.query.get('provider')
        query['resource_type'] = bottle.request.query.get('type')
        return self.manager.get_resources(tenant_id=tenant_id, offset=offset,
                                          limit=limit,
                                          query=query)
