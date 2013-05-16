#!/usr/bin/env python
import logging
import uuid

from bottle import get, post, put, delete, request, response, abort, route

from checkmate.db import get_driver, any_id_problems
from checkmate.environment import Environment
from checkmate.providers import PROVIDER_CLASSES
from checkmate.utils import read_body, write_body, extract_sensitive_data, \
    with_tenant

LOG = logging.getLogger(__name__)
DB = get_driver()


#
# Environments
#
@get('/environments')
@with_tenant
def get_environments(tenant_id=None):
    """ Return all saved environments """
    if 'with_secrets' in request.query:
        if request.context.is_admin is True:
            LOG.info("Administrator accessing environments with secrets: %s" %
                     request.context.username)
            results = DB.get_environments(tenant_id=tenant_id,
                                          with_secrets=True)
        else:
            abort(403, "Administrator privileges needed for this operation")
    else:
        results = DB.get_environments(tenant_id=tenant_id)

    return write_body(
        results,
        request,
        response
    )


@post('/environments')
@with_tenant
def post_environment(tenant_id=None):
    """ Save given environment """
    entity = read_body(request)
    if 'environment' in entity:
        entity = entity['environment']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    body, secrets = extract_sensitive_data(entity)
    results = DB.save_environment(entity['id'], body, secrets,
                                  tenant_id=tenant_id)

    return write_body(results, request, response)


@put('/environments/<eid>')
@with_tenant
def put_environment(eid, tenant_id=None):
    """ Modify a given environment """
    entity = read_body(request)
    if 'environment' in entity:
        entity = entity['environment']

    if any_id_problems(eid):
        abort(406, any_id_problems(eid))
    if 'id' not in entity:
        entity['id'] = str(eid)

    existing = DB.get_environment(eid)
    body, secrets = extract_sensitive_data(entity)
    results = DB.save_environment(eid, body, secrets, tenant_id=tenant_id)
    if existing:
        response.status = 200  # OK - updated
    else:
        response.status = 201  # Created
    return write_body(results, request, response)


@get('/environments/<eid>')
@with_tenant
def get_environment(eid, tenant_id=None):
    """ Return an environment by its' ID """
    if 'with_secrets' in request.query:
        if request.context.is_admin is True:
            LOG.info("Administrator accessing environment %s secrets: %s" %
                    (id, request.context.username))
            entity = DB.get_environment(eid, with_secrets=True)
        else:
            abort(403, "Administrator privileges needed for this operation")
    else:
        entity = DB.get_environment(eid)
    if not entity:
        abort(404, 'No environment with id %s' % eid)
    if tenant_id is not None and tenant_id != entity.get('tenantId'):
        LOG.warning("Attempt to access environment %s from wrong tenant %s by "
                    "%s" % (eid, tenant_id, request.context.username))
        abort(404)
    return write_body(entity, request, response)


@delete('/environments/<eid>')
@with_tenant
def delete_environment(eid, tenant_id=None):
    """ Delete a given environment """
    entity = DB.get_environment(eid)
    if not entity:
        abort(404, 'No environment with id %s' % eid)
    return write_body(entity, request, response)


#
# Providers and Resources
#
@get('/environments/<environment_id>/providers')
@with_tenant
def get_environment_providers(environment_id, tenant_id=None):
    """ Return the providers in an environment """
    entity = DB.get_environment(environment_id)
    if not entity:
        abort(404, 'No environment with id %s' % environment_id)

    providers = entity.get('providers', {})

    return write_body(providers, request, response)


@get('/environments/<environment_id>/providers/<provider_id>')
@with_tenant
def get_environment_provider(environment_id, provider_id, tenant_id=None):
    """ Return a specific provider in an environment """
    entity = DB.get_environment(environment_id)
    if not entity:
        abort(404, 'No environment with id %s' % environment_id)

    environment = Environment(entity)
    provider = environment.get_provider(provider_id)
    if 'provides' not in provider._dict:
        provider.provides(request.context)

    return write_body(provider._dict, request, response)


@get('/environments/<environment_id>/providers/<provider_id>/catalog')
@with_tenant
def get_provider_environment_catalog(environment_id, provider_id,
                                     tenant_id=None):
    """ Return the catalog of a specific provider in an environment """
    entity = DB.get_environment(environment_id, with_secrets=True)
    if not entity:
        abort(404, 'No environment with id %s' % environment_id)
    environment = Environment(entity)
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        abort(404, "Invalid provider: %s" % provider_id)
    if 'type' in request.query:
        catalog = (provider.get_catalog(request.context,
                   type_filter=request.query['type']))
    else:
        catalog = provider.get_catalog(request.context)

    return write_body(catalog, request, response)


@get('/environments/<environment_id>/providers/<provider_id>/catalog/'
     '<component_id>')
@with_tenant
def get_environment_component(environment_id, provider_id, component_id,
                              tenant_id=None):
    """
    Return a specific component found in the catalog of a specific
    provider in an environment
    """
    entity = DB.get_environment(environment_id, with_secrets=True)
    if not entity:
        abort(404, 'No environment with id %s' % environment_id)
    environment = Environment(entity)
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        abort(404, "Invalid provider: %s" % provider_id)
    component = provider.get_component(request.context, component_id)
    if component:
        return write_body(component._data, request, response)
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
    """ Return a list of providers """
    results = {}
    for key, provider in PROVIDER_CLASSES.iteritems():
        results[key] = (dict(vendor=provider.vendor, name=provider.name,
                        provides=provider({}).provides(request.context)))
    return write_body(results, request, response)


@get('/providers/<provider_id>/catalog')
@with_tenant
def get_provider_catalog(provider_id, tenant_id=None):
    """ Return the catalog of a specific provider """
    vendor = None
    if "." in provider_id:
        vendor = provider_id.split(".")[0]
        provider_id = provider_id.split(".")[1]
    environment = Environment(dict(providers={provider_id:
                              dict(vendor=vendor)}))
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        abort(404, "Invalid provider: %s" % provider_id)
    if 'type' in request.query:
        catalog = (provider.get_catalog(request.context,
                   type_filter=request.query['type']))
    else:
        catalog = provider.get_catalog(request.context)

    return write_body(catalog, request, response)


@get('/providers/<provider_id>/catalog/<component_id>')
@with_tenant
def get_provider_component(provider_id, component_id, tenant_id=None):
    """ Return the component from the catalog of a specific Provider """
    vendor = None
    if "." in provider_id:
        vendor = provider_id.split(".")[0]
        provider_id = provider_id.split(".")[1]
    environment = Environment(dict(providers={provider_id:
                              dict(vendor=vendor)}))
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        abort(404, "Invalid provider: %s" % provider_id)
    component = provider.get_component(request.context, component_id)
    if component:
        return write_body(component._data, request, response)
    else:
        abort(404, "Component %s not found or not available under this "
              "provider (%s)" % (component_id, provider_id))


@route('/providers/<provider_id>/proxy/<path:path>')
@with_tenant
def provider_proxy(provider_id, tenant_id=None, path=None):
    """ Proxy a request through a provider """
    vendor = None
    if "." in provider_id:
        vendor = provider_id.split(".")[0]
        provider_id = provider_id.split(".")[1]
    environment = Environment(dict(providers={provider_id:
                              dict(vendor=vendor)}))
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        abort(404, "Invalid provider: %s" % provider_id)
    results = provider.proxy(path, request, tenant_id=tenant_id)

    return write_body(results, request, response)
