#!/usr/bin/env python
# pylint: disable=E0611
from bottle import get, post, put, request, response, abort
import logging
import uuid

from checkmate.db import get_driver, any_id_problems
from checkmate.utils import read_body, write_body, extract_sensitive_data,\
        with_tenant

LOG = logging.getLogger(__name__)
db = get_driver('checkmate.db.sql.Driver')


#
# Components
#
@get('/components')
@with_tenant
def get_components(tenant_id=None):
    return write_body(db.get_components(tenant_id=tenant_id), request,
            response)


@post('/components')
@with_tenant
def post_component(tenant_id=None):
    entity = read_body(request)
    if 'component' in entity:
        entity = entity['component']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    body, secrets = extract_sensitive_data(entity)
    results = db.save_component(entity['id'], body, secrets,
            tenant_id=tenant_id)

    return write_body(results, request, response)


@put('/components/<id>')
@with_tenant
def put_component(id, tenant_id=None):
    entity = read_body(request)
    if 'component' in entity:
        entity = entity['component']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    body, secrets = extract_sensitive_data(entity)
    results = db.save_component(id, body, secrets, tenant_id=tenant_id)

    return write_body(results, request, response)


@get('/components/<id>')
@with_tenant
def get_component(id, tenant_id=None):
    entity = db.get_component(id)
    if not entity:
        abort(404, 'No component with id %s' % id)
    return write_body(entity, request, response)
