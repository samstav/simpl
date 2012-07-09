#!/usr/bin/env python
# pylint: disable=E0611
from bottle import get, post, put, request, response, abort
import json
import logging
import uuid

from checkmate.classes import ExtensibleDict
from checkmate.common import schema
from checkmate.db import get_driver, any_id_problems
from checkmate.exceptions import CheckmateValidationException
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


class Component(ExtensibleDict):
    def __init__(self, *args, **kwargs):
        self._provider = kwargs.pop('provider', None)
        ExtensibleDict.__init__(self, *args, **kwargs)
        if 'id' not in self:
            LOG.warning("No id in %s" % self)

    def provider(self):
        return self._provider

    def __repr__(self):
        provider = None
        if self._provider:
            provider = self._provider.key
        return "<%s id='%s' provider='%s'>" % (self.__class__.__name__,
                self.get('id'), provider)

    @classmethod
    def validate(cls, obj):
        errors = schema.validate(obj, schema.COMPONENT_SCHEMA)
        if 'provides' in obj:
            if not isinstance(obj['provides'], list):
                errors.append("Provides not a list in %s: %s" % (
                        obj.get('id', 'N/A'), obj['provides']))
            for item in obj['provides']:
                if not isinstance(item, dict):
                    errors.append("Requirement not a dict in %s: %s" % (
                            obj.get('id', 'N/A'), item))
                else:
                    value = item.values()[0]
                    # convert short form to long form
                    if not isinstance(value, dict):
                        value = {'interface': value}
                    interface = value['interface']
                    if interface not in schema.INTERFACE_SCHEMA:
                        errors.append("Invalid interface in provides: %s" %
                                item)
                    if item.keys()[0] not in schema.RESOURCE_TYPES:
                        errors.append("Invalid resource type in provides: %s" %
                                item)
        if 'requires' in obj:
            if not isinstance(obj['requires'], list):
                errors.append("Requires not a list in %s: %s" % (
                        obj.get('id', 'N/A'), obj['requires']))
            for item in obj['requires']:
                if not isinstance(item, dict):
                    errors.append("Requirement not a dict in %s: %s" % (
                            obj.get('id', 'N/A'), item))
                else:
                    value = item.values()[0]
                    # convert short form to long form
                    if not isinstance(value, dict):
                        value = {'interface': value}
                    interface = value['interface']
                    if interface not in schema.INTERFACE_SCHEMA:
                        errors.append("Invalid interface in requires: %s" %
                                item)
                    if item.keys()[0] not in schema.RESOURCE_TYPES:
                        errors.append("Invalid resource type in requires: %s" %
                                item)
        if 'is' in obj:
            if obj['is'] not in schema.RESOURCE_TYPES:
                errors.append("Invalid resource type: %s" % obj['is'])
        if errors:
            raise CheckmateValidationException("Invalid component: %s" %
                    '\n'.join(errors))
