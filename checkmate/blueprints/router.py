# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Blueprints Router."""

import logging
import math
import time
import uuid

import bottle

from checkmate.common import statsd
from checkmate import db
from checkmate import exceptions
from checkmate import utils

LOG = logging.getLogger(__name__)


class AnonymousRouter(object):

    """Route /anonymous/blueprints calls."""

    def __init__(self, app, manager=None):

        self.app = app
        self.manager = manager

        # Only adding anonymous routes if we have manager
        if self.manager:
            LOG.debug("Adding anonymous blueprint routes.")
            app.route('/anonymous/blueprints', 'GET', self.get_blueprints)
            app.route('/anonymous/blueprints/<api_id>', 'GET',
                      self.get_blueprint)

    @utils.formatted_response('blueprints', with_pagination=True)
    def get_blueprints(self, offset=None, limit=None):
        """Get existing anonymous blueprints."""
        start = time.time()
        results = {}
        if self.manager:
            details = bottle.request.query.get('details')
            remaining = math.floor(limit) if limit else None
            results = self.manager.get_blueprints(
                offset=offset,
                limit=remaining,
                details=details == '1',
            )
        duration = time.time() - start
        if duration <= 0.5:
            LOG.debug("Get blueprints took less than 500ms: %s", duration)
        elif duration <= 1:
            LOG.warn("Get blueprints took more than 500ms: %s", duration)
        else:
            LOG.error("Get blueprints took more than 1 seconds: %s", duration)

        return results

    def get_blueprint(self, api_id):
        """Get a blueprint."""
        blueprint = self.manager.get_blueprint(api_id)
        return blueprint


class Router(object):

    """Route /blueprints/ calls."""

    def __init__(self, app, manager, cache_manager=None,
                 anonymous_manager=None):
        """Takes a bottle app and routes traffic for it.

        :param manager: default manager
        :param cache_manager: optional cache (ex. Github) manager.
        :param anonymous_manager: optional cache (ex. Github) manager.
        """
        self.app = app
        self.manager = manager
        self.cache_manager = cache_manager
        self.anonymous_manager = anonymous_manager

        # Blueprint list
        app.route('/blueprints', 'GET', self.get_blueprints)
        app.route('/blueprints/<api_id>', 'GET', self.get_blueprint)
        app.route('/blueprints', 'POST', self.post_blueprint)
        app.route('/blueprints/<api_id>', 'PUT', self.put_blueprint)

    @statsd.collect
    @utils.with_tenant
    @utils.formatted_response('blueprints', with_pagination=True)
    def get_blueprints(self, tenant_id=None, offset=None, limit=None):
        """Get existing blueprints."""
        start = time.time()
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
        duration = time.time() - start
        if duration <= 0.5:
            LOG.debug("Get blueprints took less than 500ms: %s", duration)
        elif duration <= 1:
            LOG.warn("Get blueprints took more than 500ms: %s", duration)
        else:
            LOG.error("Get blueprints took more than 1 seconds: %s", duration)

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
