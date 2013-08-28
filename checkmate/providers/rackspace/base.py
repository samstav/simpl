# encoding: utf-8
"""
Rackspace Provider base module.
"""
import logging
import pyrax

from checkmate import exceptions
from checkmate import middleware
from checkmate.providers import base
from checkmate import server

LOG = logging.getLogger(__name__)

REGION_MAP = {
    'dallas': 'DFW',
    'chicago': 'ORD',
    'virginia': 'IAD',
    'london': 'LON',
    'sydney': 'SYD',
}


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

    @staticmethod
    def _connect(context, region=None):
        '''Use context info to connect to API and return api object.'''
        #FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, dict):
            context = middleware.RequestContext(**context)
        elif not isinstance(context, middleware.RequestContext):
            message = ("Context passed into connect is an unsupported type "
                       "%s." % type(context))
            raise exceptions.CheckmateException(message)
        if not context.auth_token:
            raise exceptions.CheckmateNoTokenError()

        if context.auth_source not in server.DEFAULT_AUTH_ENDPOINTS:
            pyrax_settings = {
                'identity_type': 'keystone',
                'verify_ssl': False,
                'auth_endpoint': context.auth_source
            }
        else:
            pyrax_settings = {'identity_type': 'rackspace'}

        if region in REGION_MAP:
            region = REGION_MAP[region]
        if not region:
            region = getattr(context, 'region', None)
            if not region:
                region = 'DFW'

        if not pyrax.get_setting("identity_type"):
            for key, value in pyrax_settings.items():
                pyrax.set_setting(key, value)

        pyrax.auth_with_token(context.auth_token, context.tenant,
                              context.username, region)

        return pyrax
