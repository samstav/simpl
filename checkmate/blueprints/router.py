'''
Blueprints Router
'''
import logging

#pylint: disable=E0611
from bottle import request

from checkmate import utils

LOG = logging.getLogger(__name__)


class Router(object):
    '''Route /blueprints/ calls'''

    def __init__(self, app, manager):
        '''Takes a bottle app and routes traffic for it

        :param manager: could be default manager or CacheManager
        '''
        self.app = app
        self.manager = manager

        # Blueprint list
        app.route('/blueprints', 'GET', self.get_blueprints)

    @utils.with_tenant
    @utils.formatted_response('blueprints', with_pagination=True)
    def get_blueprints(self, tenant_id=None, offset=None, limit=None):
        ''' Get existing blueprints '''
        details = request.query.get('details')
        return self.manager.get_blueprints(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit,
            details=details == '1'
        )
