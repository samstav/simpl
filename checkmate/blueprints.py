#!/usr/bin/env python
from bottle import get, post, put, request, response, abort
import copy
import logging
import uuid

from checkmate.classes import ExtensibleDict
from checkmate.common import schema
from checkmate.db import get_driver, any_id_problems
from checkmate.exceptions import CheckmateValidationException
from checkmate.utils import read_body, write_body, extract_sensitive_data, \
    with_tenant

LOG = logging.getLogger(__name__)
DB = get_driver()


#
# Blueprints
#
@get('/blueprints')
@with_tenant
def get_blueprints(tenant_id=None):
    """
    Returns blueprints for given tenant ID
    """
    return write_body(DB.get_blueprints(tenant_id=tenant_id), request,
                      response)


@post('/blueprints')
@with_tenant
def post_blueprint(tenant_id=None):
    """
    TODO: docstring
    """
    entity = read_body(request)
    if 'blueprint' in entity:
        entity = entity['blueprint']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    body, secrets = extract_sensitive_data(entity)
    results = DB.save_blueprint(entity['id'], body, secrets,
                                tenant_id=tenant_id)

    return write_body(results, request, response)


@put('/blueprints/<b_id>')
@with_tenant
def put_blueprint(b_id, tenant_id=None):
    """
    TODO: docstring
    """
    entity = read_body(request)
    if 'blueprint' in entity:
        entity = entity['blueprint']

    if any_id_problems(b_id):
        abort(406, any_id_problems(b_id))
    if 'id' not in entity:
        entity['id'] = str(b_id)

    body, secrets = extract_sensitive_data(entity)
    results = DB.save_blueprint(b_id, body, secrets, tenant_id=tenant_id)

    return write_body(results, request, response)


@get('/blueprints/<b_id>')
@with_tenant
def get_blueprint(b_id, tenant_id=None):
    """
    TODO: docstring
    """
    entity = DB.get_blueprint(b_id)
    if not entity:
        abort(404, 'No blueprint with id %s' % b_id)
    return write_body(entity, request, response)


class Blueprint(ExtensibleDict):
    """A checkmate blueprint.

    Acts like a dict. Includes validation, setting logic and other useful
    methods.
    """
    def __init__(self, *args, **kwargs):
        obj = dict(*args, **kwargs)
        Blueprint.convert(obj)
        ExtensibleDict.__init__(self, obj)

    @classmethod
    def is_supported_syntax(cls, obj):
        """Tests if the blueprint is in a supported syntax"""
        try:
            obj = copy.deepcopy(obj)
            Blueprint.convert(obj)
            return Blueprint.inspect(obj) == []
        except:
            return False


    @classmethod
    def convert(cls, obj):
        """Detect version and convert to current if necessaary and able"""
        converters = {
            'v0.6': cls.from_v0_6,
            }
        version = obj.get('version', 'v0.6')
        if version in converters:
            converters[version](obj)
        elif version != 'v0.7':
            raise CheckmateValidationException("This server does not support "
                                               "version '%s' blueprints" %
                                               version)

    @classmethod
    def from_v0_6(cls, data):
        """

        Convert a pre v0.7 blueprint to a v0.7 one

        Handles the following option changes:
        - no select or comobo types (convert them to strings)
        - no regex attirbute (move to constraint)
        - no protocols attribute (move to constraint)
        - set missing 'type' to 'string'

        """
        for option in data.get('options', {}).values():
            if 'regex' in option:
                constraint = {'regex': option['regex']}
                if 'constraints' not in option:
                    option['constraints'] = [constraint]
                else:
                    option['constraints'].append(constraint)
                del option['regex']
                LOG.warn("Converted 'regex' attribute in an option in "
                         "blueprint '%s'" % data.get('id'))
            option_type = option.get('type')
            if option_type is None:
                option['type'] = 'string'
                LOG.warn("Converted option with missing 'type' to 'string' in "
                         "blueprint '%s'" % data.get('id'))
            elif option_type in ['select', 'combo']:
                option['type'] = 'string'
                LOG.warn("Converted 'type' from '%s' to 'string' in "
                         "blueprint '%s'" % (option_type, data.get('id')))
            elif option_type == 'int':
                option['type'] = 'integer'
                LOG.warn("Converted 'type' from 'int' to 'integer' "
                         " in blueprint '%s'" % data.get('id'))
            if 'protocols' in option:
                constraint = {'protocols': option['protocols']}
                if 'constraints' not in option:
                    option['constraints'] = [constraint]
                else:
                    option['constraints'].append(constraint)
                del option['protocols']
                LOG.warn("Converted 'protocols' attribute in an option in "
                         "blueprint '%s'" % data.get('id'))
        if data.get('version', 'v0.1') < 'v0.7':
            data['version'] = 'v0.7'
        return data

    @classmethod
    def inspect(cls, obj):
        errors = schema.validate(obj, schema.BLUEPRINT_SCHEMA)
        errors.extend(schema.validate_inputs(obj))
        if obj:
            errors.extend(schema.validate_options(obj.get('options')))
        return errors
