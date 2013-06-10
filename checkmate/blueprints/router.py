import os
import logging

#pylint: disable=E0611
from bottle import request

from checkmate import utils
from checkmate import db

LOG = logging.getLogger(__name__)
DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))


class Router(object):
    '''Route /deployments/ calls'''

    def __init__(self, app, manager):
        '''Takes a bottle app and routes traffic for it'''
        self.app = app
        self.manager = manager

        # Deployment list
        app.route('/blueprints', 'GET', self.get_blueprints)

    @utils.with_tenant
    @utils.formatted_response('deployments', with_pagination=True)
    def get_blueprints(self, tenant_id=None, offset=None, limit=None):
        ''' Get existing deployments '''
        detail = request.query.get('detail')
        return self.manager.get_blueprints(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit,
            detail=detail == '1'
        )
