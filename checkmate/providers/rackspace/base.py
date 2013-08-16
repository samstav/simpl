# encoding: utf-8
"""
Rackspace Provider base module.
"""
import logging

from checkmate.providers import base

LOG = logging.getLogger(__name__)


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
    def get_regions(catalog, service_name=None, resource_type=None):
        """Returns a list of available regions.

        Optionally filter by service name and/or resource type.
        """
        regions = set()
        for service in catalog:
            if ((service_name is None or service.get('name') == service_name)
                    and (resource_type is None or
                         service.get('type') == resource_type)):
                for endpoint in service.get('endpoints', []):
                    if endpoint.get('region'):
                        regions.add(endpoint['region'])
        if not regions:
            LOG.warning('No regions found for type %s and service name %s',
                        resource_type or '*', service_name or '*')
        return list(regions)
