'''The Resource Class is an extensible dict containing all of the details of
a deployment's resources
'''
from checkmate.common import schema
from checkmate.exceptions import (
    CheckmateException,
    CheckmateValidationException
)
from checkmate.providers import ProviderBase


def _validate(obj, obj_schema):
    '''Validate Schema'''
    errors = schema.validate(obj, obj_schema)
    if errors:
        raise CheckmateValidationException("Invalid resource: %s" %
                                           '\n'.join(errors))


class Resource(dict):
    '''A Checkmate resource: a deployment can have many resources'''
    SCHEMA = [
        'index', 'name', 'provider', 'relations', 'hosted_on',
        'hosts', 'type', 'component', 'dns-name', 'instance',
        'service', 'status', 'desired-state'
    ]

    def __init__(self, key, obj):
        if 'desired-state' in obj:
            if not isinstance(obj['desired-state'], Resource.DesiredState):
                obj['desired-state'] = Resource.DesiredState(obj['desired-state'])
        Resource.validate(obj)
        self.key = key
        super(Resource, self).__init__(**obj)

    def __setitem__(self, key, value):
        _validate({key: value}, Resource.SCHEMA)
        if key == 'desired-state':
            if not isinstance(value, Resource.DesiredState):
                value = Resource.DesiredState(value)
        super(Resource, self).__setitem__(key, value)

    @classmethod
    def validate(cls, obj):
        '''Validate Resource Schema'''
        _validate(obj, Resource.SCHEMA)
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
