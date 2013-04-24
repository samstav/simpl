import logging

from checkmate.component import Component
from checkmate.exceptions import CheckmateException
from checkmate.providers import get_provider_class

LOG = logging.getLogger(__name__)


class Environment():
    def __init__(self, environment):
        self.dict = environment
        self.providers = None

    def select_provider(self, context, resource=None, interface=None):
        """ Return a provider for a given resource and (optional) interface """
        providers = self.get_providers(context)
        for provider in providers.values():
            for entry in provider.provides(context, resource_type=resource,
                                           interface=interface):
                if resource and resource in entry:
                    if interface is None or interface == entry[resource]:
                        return provider
                if not resource and interface in entry.values():
                    return provider
        LOG.debug("No '%s:%s' providers found in: %s" % (resource or '*',
                  interface or '*', self.dict))
        return None

    def get_providers(self, context):
        """ Returns provider class instances for this environment """
        if not self.providers:
            providers = self.dict.get('providers') or {}
            if providers:
                common = providers.get('common', {})
            else:
                LOG.debug("Environment does not have providers")

            results = {}
            for key, provider in providers.iteritems():
                if key == 'common':
                    continue
                if provider is None:
                    provider = {}
                vendor = provider.get('vendor', common.get('vendor', None))
                if not vendor:
                    raise CheckmateException("No vendor specified for '%s'" %
                                             key)
                provider_class = get_provider_class(vendor, key)
                results[key] = provider_class(provider, key=key)
                LOG.debug("'%s' provides %s" % (key,
                          ', '.join('%s:%s' % e.items()[0] for e
                          in results[key].provides(context))))

            self.providers = results
        return self.providers

    def get_provider(self, key):
        """ Returns provider class instance from this environment """
        if self.providers and key in self.providers:
            return self.providers[key]

        providers = self.dict.get('providers', None)
        if not providers:
            raise CheckmateException("Environment does not have providers")
        common = providers.get('common', {})

        provider = providers[key]
        vendor = provider.get('vendor', common.get('vendor', None))
        if not vendor:
            raise CheckmateException("No vendor specified for '%s'" % key)
        provider_class = get_provider_class(vendor, key)
        return provider_class(provider, key=key)

    def find_component(self, blueprint_entry, context):
        """Resolve blueprint component into actual provider component

        Examples of blueprint_entries:
        - type: application
          name: wordpress
          role: master
        - type: load-balancer
          interface: http
        - id: component_id
        """
        providers = self.get_providers(context)
        matches = []  # all components that match the blueprint entry

        # normalize 'type' to 'resource_type'
        params = {}
        params.update(blueprint_entry)
        resource_type = params.get('type', params.get('resource_type'))
        if 'type' in params:
            del params['type']
        params['resource_type'] = resource_type

        interface = params.get("interface")

        for provider in providers.values():
            if (not (resource_type or interface))\
                    or provider.provides(context, resource_type=resource_type,
                                          interface=interface):
                these_matches = provider.find_components(context, **params)
                if these_matches:
                    for match in these_matches:
                        matches.append(Component(match, provider=provider))

        if not matches:
            LOG.info("Did not find component match for: %s" % blueprint_entry)
            return None

        if len(matches) > 1:
            LOG.warning("Ambiguous component '%s' matches: %s" %
                        (blueprint_entry, matches))
            LOG.warning("Will use '%s.%s' as a default if no match is found" %
                        (matches[0].provider.key, matches[0]['id']))
        return matches[0]