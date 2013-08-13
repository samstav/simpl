'''
Placeholder for pure OpenStack providers

'''
import logging

from checkmate import providers

LOG = logging.getLogger(__name__)


class Provider(providers.ProviderBase):
    '''placeholder for identity provider.'''
    vendor = 'openstack'
    name = 'compute'
