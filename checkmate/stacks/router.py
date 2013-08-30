'''
Deployments Resource Router

Handles API calls to /deployments and routes them appropriately
'''
import logging
import os

import bottle  # pylint: disable=E0611


from checkmate import db
from checkmate import utils

LOG = logging.getLogger(__name__)
DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))
DRIVERS = {'default': DB, 'simulation': SIMULATOR_DB}


class Router(object):
    '''Route /stacks/ calls.'''

    def __init__(self, app, manager):
        '''Takes a bottle app and routes traffic for it.'''
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
        '''Get existing stacks.'''
        return self.manager.get_stacks(
            bottle.request.context,
            tenant_id
        )

    @utils.with_tenant
    def post_stack(self, tenant_id=None):
        '''Create a stack.'''
        return self.manager.create_stack(
            bottle.request.context,
            tenant_id,
            utils.read_body(bottle.request),
            bottle.request.headers.get("X-Auth-Key")
        )

    @utils.with_tenant
    def get_stack(self, stack_id, tenant_id=None):
        '''Get existing stack.'''
        return self.manager.get_stack(
            bottle.request.context,
            tenant_id,
            stack_id
        )

    @utils.with_tenant
    def get_stack_resources(self, stack_id, tenant_id=None):
        '''Get existing stack resources.'''
        return self.manager.get_stack_resources(
            bottle.request.context,
            tenant_id,
            stack_id
        )

    @utils.with_tenant
    def get_stack_resource(self, name, stack_id, resource_id, tenant_id=None):
        '''Get existing stack resource.'''
        return self.manager.get_stack_resource(
            bottle.request.context,
            tenant_id,
            name,
            stack_id,
            resource_id
        )
