'''The Resource Class is an extensible dict containing all of the details of
a deployment's resources
'''
import logging

from checkmate.common import schema
from checkmate.exceptions import (
    CheckmateException,
    CheckmateValidationException
)
from checkmate.providers import ProviderBase
from morpheus import MorpheusDict as dict

LOG = logging.getLogger(__name__)


def _validate(obj, obj_schema, deprecated_schema=[]):
    '''Validate Schema'''
    # First check includes deprecated keys
    errors = schema.validate(obj, obj_schema + deprecated_schema)
    if errors:
        raise CheckmateValidationException("Invalid resource: %s" %
                                           '\n'.join(errors))
    # Second check without deprecated keys logs a warning
    errors = schema.validate(obj, obj_schema)
    if errors:
        LOG.warn('DEPRECATED KEY: %s', errors)


class Resource(dict):
    '''A Checkmate resource: a deployment can have many resources'''
    SCHEMA = [
        'index', 'name', 'provider', 'relations', 'hosted_on',
        'hosts', 'type', 'component', 'dns-name', 'instance',
        'service', 'status', 'desired-state'
    ]
    SCHEMA_DEPRECATED = [
        'id', 'flavor', 'image', 'disk', 'region', 'protocol', 'port'
    ]

    def __init__(self, key, obj):
        if 'desired-state' in obj:
            if not isinstance(obj['desired-state'], Resource.DesiredState):
                obj['desired-state'] = Resource.DesiredState(obj['desired-state'])
        Resource.validate(obj)
        self.key = key
        super(Resource, self).__init__(**obj)

    def __setitem__(self, key, value):
        _validate({key: value}, Resource.SCHEMA, Resource.SCHEMA_DEPRECATED)
        if key == 'desired-state':
            if not isinstance(value, Resource.DesiredState):
                value = Resource.DesiredState(value)
        super(Resource, self).__setitem__(key, value)

    @classmethod
    def validate(cls, obj):
        '''Validate Resource Schema'''
        _validate(obj, Resource.SCHEMA, Resource.SCHEMA_DEPRECATED)
        if 'desired-state' in obj:
            Resource.DesiredState.validate(obj['desired-state'])

    class DesiredState(dict):
        '''The Desired State section of a Resource'''
        SCHEMA = [
            'region', 'flavor', 'image', 'disk', 'protocol',
            'port', 'status', 'databases'
        ]

        def __init__(self, obj):
            Resource.DesiredState.validate(obj)
            super(Resource.DesiredState, self).__init__(**obj)

        def __setitem__(self, key, value):
            _validate({key: value}, Resource.DesiredState.SCHEMA)
            super(Resource.DesiredState, self).__setitem__(key, value)

        @classmethod
        def validate(cls, obj):
            '''Validate Desired State Schema'''
            _validate(obj, Resource.DesiredState.SCHEMA)
