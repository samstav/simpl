from bottle import get, post, put, request, response, abort
from checkmate.utils import read_body, write_body
from checkmate.db.common import get_driver
import logging
from copy import deepcopy

LOG = logging.getLogger(__name__)

DB = get_driver()


@get("/tenants")
def get_tenants():
    return write_body(DB.list_tenants(*request.query.getall('tag')),
                      request, response)


@put("/tenants/<tenant_id>")
def put_tenant(tenant_id):
    ten = {}
    if request.content_length > 0:
        ten = read_body(request)
    ten['tenant_id'] = tenant_id
    DB.save_tenant(ten)


@get("/tenants/<tenant_id>")
def get_tenant(tenant_id):
    if tenant_id:
        tenant = DB.get_tenant(tenant_id)
        if not tenant:
            abort(404, 'No tenant %s' % tenant_id)
        return write_body(tenant, request, response)


@post("/tenants/<tenant_id>")
def add_tenant_tags(tenant_id):
    if tenant_id:
        body = read_body(request)
        if not body.get('tags'):
            abort(401, 'Must supply tags')
        new = body.get('tags')
        if not isinstance(new, (list, tuple)):
            new = [new]
        DB.add_tenant_tags(tenant_id, *new)
        response.status = 204
