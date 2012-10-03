#!/usr/bin/env python
# pylint: disable=E0611
from bottle import get, post, put, request, response, abort #@UnresolvedImport
import logging
import uuid

from checkmate.db import get_driver, any_id_problems
from checkmate.utils import read_body, write_body, extract_sensitive_data,\
        with_tenant

LOG = logging.getLogger(__name__)
db = get_driver()


#
# Blueprints
#
@get('/blueprints')
@with_tenant
def get_blueprints(tenant_id=None):
    return write_body(db.get_blueprints(tenant_id=tenant_id), request,
            response)


@post('/blueprints')
@with_tenant
def post_blueprint(tenant_id=None):
    entity = read_body(request)
    if 'blueprint' in entity:
        entity = entity['blueprint']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    body, secrets = extract_sensitive_data(entity)
    results = db.save_blueprint(entity['id'], body, secrets,
            tenant_id=tenant_id)

    return write_body(results, request, response)


@put('/blueprints/<id>')
@with_tenant
def put_blueprint(id, tenant_id=None):
    entity = read_body(request)
    if 'blueprint' in entity:
        entity = entity['blueprint']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    body, secrets = extract_sensitive_data(entity)
    results = db.save_blueprint(id, body, secrets, tenant_id=tenant_id)

    return write_body(results, request, response)


@get('/blueprints/<id>')
@with_tenant
def get_blueprint(id, tenant_id=None):
    entity = db.get_blueprint(id)
    if not entity:
        abort(404, 'No blueprint with id %s' % id)
    return write_body(entity, request, response)
