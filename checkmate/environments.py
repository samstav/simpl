# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Environments."""

import copy
import logging
import os
import uuid

import bottle

from checkmate.common import schema
from checkmate import db
from checkmate import environment as cm_env
from checkmate.providers import base as providers_base
from checkmate import utils

LOG = logging.getLogger(__name__)
DB = db.get_driver()
ANONYMOUS_CATALOG = schema.load_catalog(
    os.path.join(
        os.path.dirname(__file__),
        os.path.pardir,
        'ui', 'rook', 'static', 'scripts', 'common', 'services', 'catalog',
        'catalog.yml'))


@bottle.get('/environments')
@utils.with_tenant
def get_environments(tenant_id=None):
    """Return all saved environments."""
    if 'with_secrets' in bottle.request.query:
        context = bottle.request.environ['context']
        if context.is_admin is True:
            LOG.info("Administrator accessing environments with secrets: %s",
                     context.username)
            results = DB.get_environments(tenant_id=tenant_id,
                                          with_secrets=True)
        else:
            bottle.abort(
                403, "Administrator privileges needed for this operation")
    else:
        results = DB.get_environments(tenant_id=tenant_id)

    return utils.write_body(
        results,
        bottle.request,
        bottle.response
    )


@bottle.post('/environments')
@utils.with_tenant
def post_environment(tenant_id=None):
    """Save given environment."""
    entity = utils.read_body(bottle.request)
    if 'environment' in entity:
        entity = entity['environment']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if db.any_id_problems(entity['id']):
        bottle.abort(406, db.any_id_problems(entity['id']))

    body, secrets = utils.extract_sensitive_data(entity)
    results = DB.save_environment(entity['id'], body, secrets,
                                  tenant_id=tenant_id)

    return utils.write_body(results, bottle.request, bottle.response)


@bottle.put('/environments/<eid>')
@utils.with_tenant
def put_environment(eid, tenant_id=None):
    """Modify a given environment."""
    entity = utils.read_body(bottle.request)
    if 'environment' in entity:
        entity = entity['environment']

    if db.any_id_problems(eid):
        bottle.abort(406, db.any_id_problems(eid))
    if 'id' not in entity:
        entity['id'] = str(eid)

    existing = DB.get_environment(eid)
    body, secrets = utils.extract_sensitive_data(entity)
    results = DB.save_environment(eid, body, secrets, tenant_id=tenant_id)
    if existing:
        bottle.response.status = 200  # OK - updated
    else:
        bottle.response.status = 201  # Created
    return utils.write_body(results, bottle.request, bottle.response)


@bottle.get('/environments/<eid>')
@utils.with_tenant
def get_environment(eid, tenant_id=None):
    """Return an environment by its' ID."""
    context = bottle.request.environ['context']
    if 'with_secrets' in bottle.request.query:
        if context.is_admin is True:
            LOG.info("Administrator accessing environment %s secrets: %s",
                     eid, context.username)
            entity = DB.get_environment(eid, with_secrets=True)
        else:
            bottle.abort(
                403, "Administrator privileges needed for this operation")
    else:
        entity = DB.get_environment(eid)
    if not entity:
        bottle.abort(404, 'No environment with id %s' % eid)
    if tenant_id is not None and tenant_id != entity.get('tenantId'):
        LOG.warning("Attempt to access environment %s from wrong tenant %s by "
                    "%s", eid, tenant_id, context.username)
        bottle.abort(404)
    return utils.write_body(entity, bottle.request, bottle.response)


@bottle.delete('/environments/<eid>')
@utils.with_tenant
def delete_environment(eid, tenant_id=None):
    """Delete a given environment."""
    entity = DB.get_environment(eid)
    if not entity:
        bottle.abort(404, 'No environment with id %s' % eid)
    return utils.write_body(entity, bottle.request, bottle.response)


#
# Environment Providers
#
@bottle.get('/environments/<environment_id>/providers')
@utils.with_tenant
def get_environment_providers(environment_id, tenant_id=None):
    """Return the providers in an environment."""
    entity = DB.get_environment(environment_id)
    if not entity:
        bottle.abort(404, 'No environment with id %s' % environment_id)

    providers = entity.get('providers', {})

    return utils.write_body(providers, bottle.request, bottle.response)


@bottle.get('/environments/<environment_id>/providers/<provider_id>')
@utils.with_tenant
def get_environment_provider(environment_id, provider_id, tenant_id=None):
    """Return a specific provider in an environment."""
    entity = DB.get_environment(environment_id)
    if not entity:
        bottle.abort(404, 'No environment with id %s' % environment_id)

    environment = cm_env.Environment(entity)
    provider = environment.get_provider(provider_id)
    if 'provides' not in provider._dict:
        provider.provides(bottle.request.environ['context'])

    return utils.write_body(provider._dict, bottle.request, bottle.response)


@bottle.get('/environments/<environment_id>/providers/<provider_id>/catalog')
@utils.with_tenant
def get_provider_environment_catalog(environment_id, provider_id,
                                     tenant_id=None):
    """Return the catalog of a specific provider in an environment."""
    entity = DB.get_environment(environment_id, with_secrets=True)
    if not entity:
        bottle.abort(404, 'No environment with id %s' % environment_id)
    environment = cm_env.Environment(entity)
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        bottle.abort(404, "Invalid provider: %s" % provider_id)
    if 'type' in bottle.request.query:
        catalog = provider.get_catalog(
            bottle.request.environ['context'],
            type_filter=bottle.request.query['type'])
    else:
        catalog = provider.get_catalog(bottle.request.environ['context'])

    return utils.write_body(catalog, bottle.request, bottle.response)


@bottle.get('/environments/<environment_id>/providers/<provider_id>/catalog/'
            '<component_id>')
@utils.with_tenant
def get_environment_component(environment_id, provider_id, component_id,
                              tenant_id=None):
    """Return a component from catalog of a specific provider/environment."""
    entity = DB.get_environment(environment_id, with_secrets=True)
    if not entity:
        bottle.abort(404, 'No environment with id %s' % environment_id)
    environment = cm_env.Environment(entity)
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        bottle.abort(404, "Invalid provider: %s" % provider_id)
    component = provider.get_component(bottle.request.environ['context'],
                                       component_id)
    if component:
        return utils.write_body(
            component._data, bottle.request, bottle.response)
    else:
        bottle.abort(404, "Component %s not found or not available under this "
                     "provider and environment (%s/%s)" %
                     (component_id, environment_id, provider_id))


#
# Providers and Resources
#
@bottle.get('/providers')
@utils.with_tenant
def get_providers(tenant_id=None):
    """Return a list of providers."""
    results = {}
    for key, provider in providers_base.PROVIDER_CLASSES.iteritems():
        results[key] = (dict(
            vendor=provider.vendor,
            name=provider.name,
            provides=provider({}).provides(bottle.request.environ['context'])
        ))
    return utils.write_body(results, bottle.request, bottle.response)


@bottle.get('/anonymous/catalog')
def get_anonymous_catalog():
    """Return generic, anonymous (unauthenticated) catalog."""
    return utils.write_body(ANONYMOUS_CATALOG, bottle.request, bottle.response)


@bottle.get('/providers/<provider_id>/catalog')
@utils.with_tenant
def get_provider_catalog(provider_id, tenant_id=None):
    """Return the catalog of a specific provider."""
    vendor = None
    type_filter = None
    if "." in provider_id:
        vendor = provider_id.split(".")[0]
        provider_id = provider_id.split(".")[1]
    environment = cm_env.Environment(
        dict(providers={provider_id: dict(vendor=vendor)}))
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        bottle.abort(404, "Invalid provider: %s" % provider_id)

    if 'type' in bottle.request.query:
        type_filter = bottle.request.query.pop('type')
    if type_filter:
        catalog = (provider.get_catalog(bottle.request.environ['context'],
                                        type_filter=type_filter))
    else:
        if len(bottle.request.query) > 16:
            bottle.abort(403, "Invalid url parameters.")
        if 'source' in bottle.request.query:
            catalog = provider.get_remote_catalog(
                bottle.request.environ['context'], **bottle.request.query)
        else:
            catalog = provider.get_catalog(bottle.request.environ['context'],
                                           **bottle.request.query)

    return utils.write_body(catalog, bottle.request, bottle.response)


@bottle.get('/providers/<provider_id>/catalog/<component_id>')
@utils.with_tenant
def get_provider_component(provider_id, component_id, tenant_id=None):
    """Return the component from the catalog of a specific Provider."""
    vendor = None
    if "." in provider_id:
        vendor = provider_id.split(".")[0]
        provider_id = provider_id.split(".")[1]
    environment = cm_env.Environment(
        dict(providers={provider_id: dict(vendor=vendor)}))
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        bottle.abort(404, "Invalid provider: %s" % provider_id)
    if len(bottle.request.query) > 16:
        bottle.abort(403, "Invalid url parameters.")
    component = provider.get_component(bottle.request.environ['context'],
                                       component_id)
    if component:
        return utils.write_body(
            component._data, bottle.request, bottle.response)
    else:
        bottle.abort(404, "Component %s not found or not available under this "
                     "provider (%s)" % (component_id, provider_id))


@bottle.route('/providers/<provider_id>/resources')
@utils.with_tenant
def provider_get_resources(provider_id, tenant_id=None):
    """Proxy a request through a provider."""
    vendor = None
    if "." in provider_id:
        vendor = provider_id.split(".")[0]
        provider_id = provider_id.split(".")[1]
    environment = cm_env.Environment(
        dict(providers={provider_id: dict(vendor=vendor)}))
    try:
        provider = environment.get_provider(provider_id)
    except KeyError:
        bottle.abort(404, "Invalid provider: %s" % provider_id)
    results = provider.get_resources(bottle.request.environ['context'],
                                     tenant_id=tenant_id)

    return utils.write_body(results, bottle.request, bottle.response)
