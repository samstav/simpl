'''
Blueprints Manager

Handles blueprint logic
'''
import logging

from checkmate.base import ManagerBase

LOG = logging.getLogger(__name__)


class Manager(ManagerBase):
    '''Contains Blueprints Model and Logic for Accessing Blueprints'''

    def get_blueprints(self, tenant_id=None, offset=None, limit=None,
                       detail=False):
        ''' Get existing deployments '''
        return self.driver.get_blueprints(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit,
            #detail=detail
        )
