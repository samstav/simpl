"""
Blueprints Router
"""
import logging
import math
import time
import uuid

import bottle

from checkmate import db
from checkmate import exceptions
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
        app.route('/blueprints/<api_id>', 'GET', self.get_blueprint)
        app.route('/blueprints', 'POST', self.post_blueprint)
        app.route('/blueprints/<api_id>', 'PUT', self.put_blueprint)

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

    @utils.with_tenant
    def post_blueprint(self, tenant_id=None):
        """Save a blueprint."""
        if (bottle.request.headers and
                'X-Source-Untrusted' in bottle.request.headers):
            LOG.info("X-Source-Untrusted: Rejecting Blueprint POST.")
            raise exceptions.CheckmateException(
                friendly_message="Unauthorized")

        entity = utils.read_body(bottle.request)

        return self.manager.save_blueprint(
            entity,
            tenant_id=tenant_id
        )

    @utils.with_tenant
    def put_blueprint(self, api_id, tenant_id=None):
        """Store a blueprint or overwrite an existing one."""
        if (bottle.request.headers and
                'X-Source-Untrusted' in bottle.request.headers):
            LOG.info("X-Source-Untrusted: Rejecting Blueprint PUT.")
            raise exceptions.CheckmateException(
                friendly_message="Unauthorized")

        entity = utils.read_body(bottle.request)

        if 'id' not in entity:
            entity['id'] = api_id or uuid.uuid4().hex
        if db.any_id_problems(entity['id']):
            raise exceptions.CheckmateValidationException(
                db.any_id_problems(entity['id']))
        if 'tenantId' in entity and tenant_id:
            if entity['tenantId'] != tenant_id:
                msg = "tenantId must match with current tenant ID"
                raise exceptions.CheckmateValidationException(
                    msg, friendly_message=msg)
        else:
            assert tenant_id, "Tenant ID must be specified in blueprint."
            entity['tenantId'] = tenant_id
        if 'created-by' not in entity:
            entity['created-by'] = bottle.request.environ['context'].username

        existing_blueprint = None

        if api_id:
            try:
                existing_blueprint = self.manager.get_blueprint(
                    api_id, tenant_id=tenant_id)
            except exceptions.CheckmateDoesNotExist:
                LOG.debug("Blueprint not found: %s", api_id)

        results = self.manager.save_blueprint(
            entity,
            api_id=api_id,
            tenant_id=tenant_id
        )

        # Return response (with new resource location in header)
        if existing_blueprint:
            bottle.response.status = 200  # OK - updated
        else:
            bottle.response.status = 201  # Created
            location = []
            if tenant_id:
                location.append('/%s' % tenant_id)
            location.append('/blueprints/%s' % results['id'])
            bottle.response.add_header('Location', "".join(location))

        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def get_blueprint(self, api_id, tenant_id=None):
        """Get a blueprint."""
        blueprint = self.manager.get_blueprint(api_id, tenant_id=tenant_id)
        if not blueprint:
            blueprint = self.cache_manager.get_blueprint(str(api_id))
        return blueprint
