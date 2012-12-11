"""Chef Solo configuration management provider"""
import logging

from checkmate.providers import ProviderBase

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    """Implements a Chef Solo configuration management provider"""
    name = 'chef-solo'
    vendor = 'opscode'

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
