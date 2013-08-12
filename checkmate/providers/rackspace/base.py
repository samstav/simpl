# encoding: utf-8
"""
Rackspace Provider base module.
"""
from checkmate.providers import base

class RackspaceProviderBase(base.ProviderBase):
    """Provides shared methods for Rackspace providers."""
    vendor = 'rackspace'
    
    def __init__(self, provider, key=None):
        """Init for Rackspace provider base."""
        base.ProviderBase.__init__(self, provider, key=key)
        self._catalog_cache = {}

    # pylint: disable=W0613
    def get_catalog(self, context, type_filter=None):
        """Overrides base catalog and handles multiple regions."""
        result = base.ProviderBase.get_catalog(self, context,
                                               type_filter=type_filter)
        if result:
            return result
        region = context.get('region')
        if region in self._catalog_cache:
            catalog = self._catalog_cache[region]
            if type_filter and type_filter in catalog:
                result = {type_filter: catalog[type_filter]}
            else:
                result = catalog
        return result

    @staticmethod
    def get_regions(catalog, service_name):
        """Returns a list of available regions for service_name."""
        regions = []
        for service in catalog:
            if service.get('name') == service_name:
                for endpoint in service.get('endpoints', []):
                    if endpoint.get('region'):
                        regions.append(endpoint['region'])
        return regions
        