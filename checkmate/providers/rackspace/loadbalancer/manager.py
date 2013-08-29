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
            except pyrax.exceptions.ClientException:
                raise exceptions.CheckmateException('ClientException occurred '
                                                    'enabling content caching '
                                                    'on lb %s', lbid)
        results = {
            'id': lbid,
            'status': clb.status,
            'caching': clb.content_caching
        }
        return results

    @staticmethod
    def enable_ssl_termination(lbid, port, secure_only, cert, private_key,
                               api, simulate=False):
        """Enables ssl termination on specified loadbalancer."""
        if simulate:
            clb = utils.Simulation(status='ACTIVE')
        else:
            try:
                clb = api.get(lbid)
                clb.add_ssl_termination(securePort=port, enabled=True,
                                        secureTrafficOnly=False,
                                        certificate=cert,
                                        privatekey=private_key)
            except pyrax.exceptions.ClientException:
                raise exceptions.CheckmateException('Error occurred enabling '
                                                    'ssl termination on lb %s'
                                                    , lbid)
        results = {
            'id': lbid,
            'status': clb.status,
            'secure_port': port,
            'secure_only': secure_only,
        }
        return results