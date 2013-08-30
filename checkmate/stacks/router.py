# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
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
"""
Deployments Resource Router

Handles API calls to /deployments and routes them appropriately
"""
import logging
import os

import bottle  # pylint: disable=E0611


from checkmate import db
from checkmate import exceptions
from checkmate import utils

LOG = logging.getLogger(__name__)
DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))
DRIVERS = {'default': DB, 'simulation': SIMULATOR_DB}


class Router(object):
    """Route /stacks/ calls."""

    def __init__(self, app, manager):
        """Takes a bottle app and routes traffic for it."""
        self.app = app
        self.manager = manager

        # Deployment list
        app.route('/stacks', 'GET', self.get_stacks)
        app.route('/stacks', 'POST', self.post_stack)
        app.route('/stacks/<stack_id>', 'GET', self.get_stack)
        app.route('/stacks/<stack_id>/resources', 'GET',
                  self.get_stack_resources)
        app.route('/stacks/<name>/<stack_id>/resources/<resource_id>', 'GET',
                  self.get_stack_resource)

    @utils.with_tenant
    def get_stacks(self, tenant_id=None):
        """Get existing stacks."""
        return self.manager.get_stacks(
            bottle.request.context,
            tenant_id
        )

    @utils.with_tenant
    def post_stack(self, tenant_id=None):
        """Create a stack."""
        return self.manager.create_stack(
            bottle.request.context,
            tenant_id,
            utils.read_body(bottle.request),
            bottle.request.headers.get("X-Auth-Key")
        )

    def post_stack_compat(self, tenant_id=None):
        """Create a stack coming from Reach with compoatibility attributes."""
        stack = utils.read_body(bottle.request)
        try:
            del stack['blueprint']
            inputs = stack.pop('inputs')
            blueprint_inputs = inputs.pop('blueprint')
            # Get API key - we added this input on the way out to Reach
            api_key = blueprint_inputs.pop('API Key')
        except Exception:
            LOG.error("Cannot parse HOT template", exc_info=True)
            raise exceptions.CheckmateException("Unable to parse HOT template")

        body = {
            'stack_name': stack.pop('name'),
            'parameters': blueprint_inputs,
            'disable_rollback': True,
            'template': stack,
        }
        return self.manager.create_stack(
            bottle.request.context,
            tenant_id,
            body,
            bottle.request.headers.get("X-Auth-Key") or api_key
        )

    @utils.with_tenant
    def get_stack(self, stack_id, tenant_id=None):
        """Get existing stack."""
        return self.manager.get_stack(
            bottle.request.context,
            tenant_id,
            stack_id
        )

    @utils.with_tenant
    def get_stack_resources(self, stack_id, tenant_id=None):
        """Get existing stack resources."""
        return self.manager.get_stack_resources(
            bottle.request.context,
            tenant_id,
            stack_id
        )

    @utils.with_tenant
    def get_stack_resource(self, name, stack_id, resource_id, tenant_id=None):
        """Get existing stack resource."""
        return self.manager.get_stack_resource(
            bottle.request.context,
            tenant_id,
            name,
            stack_id,
            resource_id
        )
