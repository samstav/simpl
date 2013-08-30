"""
Rackspace Loadbalancer provider manager.
"""
import logging
import pyrax

from checkmate import exceptions
from checkmate import utils

LOG = logging.getLogger(__name__)


class Manager(object):
    """Contains loadbalancer provider model and logic for interaction."""

    @staticmethod
    def enable_content_caching(lbid, api, simulate=False):
        """Enables content caching on specified loadbalancer."""
        if simulate:
            clb = utils.Simulation(status='ACTIVE')
            clb.content_caching = True
        else:
            try:
                clb = api.get(lbid)
                clb.content_caching = True
            except pyrax.exceptions.ClientException as exc:
                raise exceptions.CheckmateException('ClientException occurred '
                                                    'enabling content caching '
                                                    'on lb %s: %s' % (lbid,
                                                                      exc))
        results = {
            'id': lbid,
            'status': clb.status,
            'caching': clb.content_caching
        }
        return results
