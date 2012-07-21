#!/usr/bin/env python
import logging
import uuid

# pylint: disable=E0611
from bottle import get, post, put, delete, request, response, abort
from Crypto.PublicKey import RSA  # pip install pycrypto
from Crypto.Hash import SHA512, MD5
from Crypto import Random

from checkmate.common import schema
from checkmate.components import Component
from checkmate.db import get_driver, any_id_problems
from checkmate.exceptions import CheckmateException
from checkmate.providers import get_provider_class, PROVIDER_CLASSES
from checkmate.utils import read_body, write_body, extract_sensitive_data,\
        with_tenant

LOG = logging.getLogger(__name__)
db = get_driver()


#
# Environments
#
@get('/environments')
@with_tenant
def get_environments(tenant_id=None):
    return write_body(db.get_environments(tenant_id=tenant_id), request,
            response)


@post('/environments')
@with_tenant
def post_environment(tenant_id=None):
    entity = read_body(request)
    if 'environment' in entity:
        entity = entity['environment']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    body, secrets = extract_sensitive_data(entity)
    results = db.save_environment(entity['id'], body, secrets,
            tenant_id=tenant_id)

    return write_body(results, request, response)


@put('/environments/<id>')
@with_tenant
def put_environment(id, tenant_id=None):
    entity = read_body(request)
    if 'environment' in entity:
        entity = entity['environment']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    body, secrets = extract_sensitive_data(entity)
    results = db.save_environment(id, body, secrets, tenant_id=tenant_id)

    return write_body(results, request, response)


@get('/environments/<id>')
@with_tenant
def get_environment(id, tenant_id=None):
    if 'with_secrets' in request.query:  # TODO: verify admin-ness
        entity = db.get_environment(id, with_secrets=True)
    else:
        entity = db.get_environment(id)
    if not entity:
        abort(404, 'No environment with id %s' % id)
    return write_body(entity, request, response)


@delete('/environments/<id>')
@with_tenant
def delete_environment(id, tenant_id=None):
    entity = db.get_environment(id)
    if not entity:
        abort(404, 'No environment with id %s' % id)
    return write_body(entity, request, response)


#
# Providers and Resources
#
@get('/environments/<environment_id>/providers')
@with_tenant
def get_environment_providers(environment_id, tenant_id=None):
    entity = db.get_environment(environment_id)
    if not entity:
        abort(404, 'No environment with id %s' % environment_id)

    providers = entity.get('providers', {})

    return write_body(providers, request, response)


@get('/environments/<environment_id>/providers/<provider_id>')
@with_tenant
def get_environment_provider(environment_id, provider_id, tenant_id=None):
    entity = db.get_environment(environment_id)
    if not entity:
        abort(404, 'No environment with id %s' % environment_id)

    providers = entity.get('providers', {})
    provider = providers.get(provider_id, {})

    return write_body(provider, request, response)


@get('/environments/<environment_id>/providers/<provider_id>/catalog')
@with_tenant
def get_provider_catalog(environment_id, provider_id, tenant_id=None):
    entity = db.get_environment(environment_id, with_secrets=True)
    if not entity:
        abort(404, 'No environment with id %s' % environment_id)
    environment = Environment(entity)
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        abort(404, "Invalid provider: %s" % provider_id)
    if 'type' in request.query:
        catalog = provider.get_catalog(request.context,
                type_filter=request.query['type'])
    else:
        catalog = provider.get_catalog(request.context)

    return write_body(catalog, request, response)


@get('/environments/<environment_id>/providers/<provider_id>/catalog/'
        '<component_id>')
@with_tenant
def get_component(environment_id, provider_id, component_id, tenant_id=None):
    entity = db.get_environment(environment_id, with_secrets=True)
    if not entity:
        abort(404, 'No environment with id %s' % environment_id)
    print "ENTITY: %s" % entity
    environment = Environment(entity)
    print "ENVIRONMENT: %s" % environment
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        abort(404, "Invalid provider: %s" % provider_id)
    component = provider.get_component(request.context, component_id)
    if component:
        return write_body(component, request, response)
    else:
        abort(404, "Component %s not found or not available under this "
                "provider and environment (%s/%s)" % (component_id,
                environment_id, provider_id))


#
# Providers and Resources
#
@get('/providers')
@with_tenant
def get_providers(tenant_id=None):
    results = {}
    for key, provider in PROVIDER_CLASSES.iteritems():
        results[key] = dict(vendor=provider.vendor, name=provider.name,
                provides=provider({}).provides())
    return write_body(results, request, response)


#
# Environment Code
#
class Environment():
    def __init__(self, environment):
        self.dict = environment
        self.providers = None

    def select_provider(self, resource=None):
        providers = self.get_providers()
        for p in providers.values():
            for entry in p.provides():
                if resource in entry:
                    return p
        LOG.debug("No '%s' providers found in: %s" % (resource, self.dict))
        return None

    def get_providers(self):
        """ Returns provider class instances for this environment """
        if not self.providers:
            providers = self.dict.get('providers', None)
            if providers:
                common = providers.get('common', {})
            else:
                LOG.debug("Environment does not have providers")

            results = {}
            for key, provider in providers.iteritems():
                if key == 'common':
                    continue
                vendor = provider.get('vendor', common.get('vendor', None))
                if not vendor:
                    raise CheckmateException("No vendor specified for '%s'" % key)
                provider_class = get_provider_class(vendor, key)
                results[key] = provider_class(provider, key=key)
                LOG.debug("'%s' provides %s" % (key,
                        ', '.join('%s:%s' % e.items()[0] for e
                                  in results[key].provides())))

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
	print "BLUEPRINT: %s " % blueprint_entry
	print "ENVIRONMENT.CONTEXT: %s " % context
        resource_type = blueprint_entry.get('type')
        interface = blueprint_entry.get('interface')
        for provider in self.get_providers().values():
            matches = []
            if resource_type or interface:
                if provider.provides(resource_type=resource_type,
                    interface=interface):  # we can narrow down search
                    # normalize 'type' to 'resource_type'
                    params = {}
                    params.update(blueprint_entry)
                    if 'type' in params:
                        del params['type']
                    params['resource_type'] = resource_type
                    matches = provider.find_components(context, **params)
            else:
                matches = provider.find_components(context, **blueprint_entry)
	    print "MATCHES: %s" % matches
            if matches:
                if len(matches) == 1:
                    return Component(matches[0], provider=provider)
                else:
                    LOG.warning("Ambiguous component %s matches: %s" %
                            (blueprint_entry, matches))

    def get_interface_map(self):
        """Get interfaces available from environment and providers that
        provide them

        :returns: dict of {interface={provider_key=[resource list]}}
        example:
        {
            'mysql': {
                    'databases': ['database'],
                    'chef-local': ['database'],
                }
            }
        """
        results = {}
        for provider_key, provider in self.get_providers().iteritems():
            for item in provider.provides():
                resource_type, interface = item.items()[0]
                assert resource_type in schema.RESOURCE_TYPES
                if interface in results:
                    interface_entry = results[interface]
                    if provider_key in interface_entry:
                        provider_entry = interface_entry[provider_key]
                        if resource_type not in provider_entry:
                            provider_entry.append(resource_type)
                    else:
                        provider_entry = [resource_type]
                    interface_entry[provider_key] = provider_entry

                    if len(interface_entry) > 1:
                        LOG.warning("More than one provider for '%s': %s" % (
                                interface, results[interface]))
                else:
                    results[interface] = {provider_key: [resource_type]}
        return results

    def generate_key_pair(self, bits=2048):
        """Generates a private/public key pair.

        returns them as a private, public tuple of dicts. The dicts have key,
        and PEM values. The public key also has an ssh value in it"""
        key = RSA.generate(2048)
        private_string = key.exportKey('PEM')
        public = key.publickey()
        public_string = public.exportKey('PEM')
        ssh = public.exportKey('OpenSSH')
        return (dict(key=key, PEM=private_string),
                dict(key=public, PEM=public_string, ssh=ssh))

    def get_ssh_public_key(self, private_key):
        """Generates an ssh public key from a private key public_string"""
        key = RSA.importKey(private_key)
        return key.publickey().exportKey('OpenSSH')

    def HashSHA512(self, value, salt=None):
        if not salt:
            salt = Random.get_random_bytes(8).encode('base64').strip()
        h = SHA512.new(salt)
        h.update(value)
        return "$6$%s$%s" % (salt, h.hexdigest())

    def HashMD5(self, value, salt=None):
        if not salt:
            salt = Random.get_random_bytes(8).encode('base64').strip()
        h = MD5.new(salt)
        h.update(value)
        return "$1$%s$%s" % (salt, h.hexdigest())
