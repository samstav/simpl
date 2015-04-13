# encoding: utf-8
"""Rackspace Provider base module."""
import collections
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
    'hongkong': 'HKG',
}

# Rackspace UK account IDs begin at 10 million
UK_ACCOUNT_MIN_ID = 10**7


class RackspaceProviderBase(base.ProviderBase):

    """Provides shared methods for Rackspace providers."""

    vendor = 'rackspace'

    def __init__(self, provider, key=None):
        """Init for Rackspace provider base."""
        super(RackspaceProviderBase, self).__init__(provider, key=key)
        self._catalog_cache = {}

    def get_catalog(self, context, type_filter=None):
        """Overrides base catalog and handles multiple regions."""
        result = super(RackspaceProviderBase, self).get_catalog(
            context, type_filter=type_filter)

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
        """Use context info to connect to API and return api object."""
        # FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, collections.MutableMapping):
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
        if region not in pyrax.regions:
            raise exceptions.CheckmateValidationException(
                friendly_message=(
                    "Specified region '%(region)s' not available. "
                    "Available regions: %(avail)s"
                    % dict(region=region, avail=pyrax.regions))
            )

        return pyrax

    def _validate_region(self, context):
        """Check that a blueprint is compatible with the user's region.

        For example, if the user has a UK account and the blueprint is trying
        to use non-UK resources, this in invalid. Conversely, if a user has a
        non-UK account and is trying to access UK resources, this is also
        invalid.

        If either case is true, raise a
        :class:`checkmate.exceptions.CheckmateValidationException`.
        """
        if (context.tenant.isdigit() and
                int(context.tenant) >= UK_ACCOUNT_MIN_ID):
            # This is a UK account
            if not context.region == 'LON':
                raise exceptions.CheckmateValidationException(
                    "UK account cannot access non-UK resources")
        else:
            # This is a non-UK account (including IAD, DFW, ORD, SYD, HKG)
            if context.region == 'LON':
                raise exceptions.CheckmateValidationException(
                    "Non-UK account cannot access UK resources")

    def find_components(self, context, **kwargs):
        """Find the componentat that match the supplied key/value arguments.

        Overrides
        :meth:`checkmate.providers.base.ProviderBase.find_components`.
        """
        try:
            self._validate_region(context)
        except exceptions.CheckmateValidationException:
            # If we have a region mismatch problem, don't offer to provide any
            # components.
            return []
        else:
            return super(RackspaceProviderBase, self).find_components(context,
                                                                      **kwargs)
