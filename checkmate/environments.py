#!/usr/bin/env python
# pylint: disable=E0611
from bottle import get, post, put, delete, request, \
        response, abort
import logging
import uuid

from checkmate.db import get_driver, any_id_problems, any_tenant_id_problems
from checkmate.exceptions import CheckmateException
from checkmate.providers import get_provider_class
from checkmate.utils import read_body, write_body, extract_sensitive_data,\
        with_tenant

LOG = logging.getLogger(__name__)
db = get_driver('checkmate.db.sql.Driver')


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
        entity = db.get_environment(id)
    else:
        entity = db.get_environment(id, with_secrets=True)
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
def get_providers(environment_id, tenant_id=None):
    entity = db.get_environment(environment_id)
    if not entity:
        abort(404, 'No environment with id %s' % environment_id)

    providers = entity.get('providers', {})

    return write_body(providers, request, response)


@get('/environments/<environment_id>/providers/<provider_id>')
@with_tenant
def get_provider(environment_id, provider_id, tenant_id=None):
    entity = db.get_environment(environment_id)
    if not entity:
        abort(404, 'No environment with id %s' % environment_id)

    providers = entity.get('providers', {})
    provider = providers.get(provider_id, {})

    return write_body(provider, request, response)


@get('/environments/<environment_id>/providers/<provider_id>/catalog')
@with_tenant
def get_catalog(environment_id, provider_id, tenant_id=None):
    entity = db.get_environment(environment_id, with_secrets=True)
    if not entity:
        abort(404, 'No environment with id %s' % environment_id)
    environment = Environment(entity)
    provider = environment.get_provider(provider_id)
    if 'type' in request.query:
        catalog = provider.get_catalog(request.context,
                type_filter=request.query['type'])
    else:
        catalog = provider.get_catalog(request.context)

    return write_body(catalog, request, response)


#
# Environment Code
#
class Environment():
    def __init__(self, environment):
        self.dict = environment

    def select_provider(self, resource=None):
        providers = self.get_providers()
        applicable = [p for key, p in providers.iteritems()
                        if resource in p.provides()]
        if applicable:
            return applicable[0]
        else:
            LOG.debug("No '%s' providers found in: %s" % (resource, self.dict))
            return None

    def get_providers(self):
        """ Returns provider class instances for this environment """
        providers = self.dict.get('providers', None)
        if not providers:
            raise CheckmateException("Environment does not have providers")
        common = providers.get('common', {})

        results = {}
        for key, provider in providers.iteritems():
            if key == 'common':
                continue
            vendor = provider.get('vendor', common.get('vendor', None))
            if not vendor:
                raise CheckmateException("No vendor specified for '%s'" % key)
            provider_class = get_provider_class(vendor, key)
            results[key] = provider_class(provider)
        return results

    def get_provider(self, key):
        """ Returns provider class instance from this environment """
        providers = self.dict.get('providers', None)
        if not providers:
            raise CheckmateException("Environment does not have providers")
        common = providers.get('common', {})

        provider = providers[key]
        vendor = provider.get('vendor', common.get('vendor', None))
        if not vendor:
            raise CheckmateException("No vendor specified for '%s'" % key)
        provider_class = get_provider_class(vendor, key)
        return provider_class(provider)
