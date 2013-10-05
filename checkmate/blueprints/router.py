"""
Blueprints Router
"""
import logging

import bottle

from checkmate import utils

LOG = logging.getLogger(__name__)


class Router(object):
    """Route /blueprints/ calls"""

    def __init__(self, app, manager, cache_manager=None):
        """Takes a bottle app and routes traffic for it.

        :param manager: default manager
        :param cache_manager: optional cache (ex. Github) manager.
        """
        self.app = app
        self.manager = manager
        self.cache_manager = cache_manager

        # Blueprint list
        app.route('/blueprints', 'GET', self.get_blueprints)

    @utils.with_tenant
    @utils.formatted_response('blueprints', with_pagination=True)
    def get_blueprints(self, tenant_id=None, offset=None, limit=None):
        """Get existing blueprints."""
        local = self.manager.get_blueprints(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit
        )
        local_count = len(local['results'])

        combined = {}
        if self.cache_manager and self.cache_manager is not self.manager:
            remaining = math.floor(limit - local_count) if limit else None
            if offset:
                relative_offset = math.floor(offset - local_count)
            else:
                relative_offset = None
            details = bottle.request.query.get('details')
            combined = self.cache_manager.get_blueprints(
                tenant_id=tenant_id,
                offset=relative_offset,
                limit=remaining,
                details=details == '1',
                roles=bottle.request.environ['context'].roles
            )
            total = local['collection-count'] + combined['collection-count']
            combined['results'].update(local['results'])  # local overrides
            combined['collection-count'] = total

        return combined or local
