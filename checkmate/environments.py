#!/usr/bin/env python
# pylint: disable=E0611
from bottle import get, post, put, delete, request, \
        response, abort
import logging
import uuid

from checkmate.utils import read_body, write_body, extract_sensitive_data
from checkmate.db import get_driver, any_id_problems, any_tenant_id_problems

LOG = logging.getLogger(__name__)
db = get_driver('checkmate.db.sql.Driver')


#
# Environments
#
@get('/environments')
@get('/<tenant_id>/environments')
def get_environments(tenant_id=None):
    return write_body(db.get_environments(tenant_id=tenant_id), request,
            response)


@post('/environments')
@post('/<tenant_id>/environments')
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
@put('/<tenant_id>/environments/<id>')
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
@get('/<tenant_id>/environments/<id>')
def get_environment(id, tenant_id=None):
    if 'with_secrets' in request.query:  # TODO: verify admin-ness
        entity = db.get_environment(id)
    else:
        entity = db.get_environment(id, with_secrets=True)
    if not entity:
        abort(404, 'No environment with id %s' % id)
    return write_body(entity, request, response)


@delete('/environments/<id>')
@delete('/<tenant_id>/environments/<id>')
def delete_environment(id, tenant_id=None):
    entity = db.get_environment(id)
    if not entity:
        abort(404, 'No environment with id %s' % id)
    return write_body(entity, request, response)
