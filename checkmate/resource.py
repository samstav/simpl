'''The Resource Class is an extensible dict containing all of the details of
a deployment's resources
'''
import logging

from checkmate.common import schema
from checkmate.common.fysom import Fysom, FysomError
from checkmate.exceptions import (
    CheckmateException,
    CheckmateValidationException
)
from checkmate.providers import ProviderBase
from morpheus import MorpheusDict as dict
from morpheus import dict as exceptions

exceptions.ValidationError = CheckmateValidationException

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

    FYSOM_STATES = {
        'PLANNED': {
            'description': 'Not Started',
            'events': [
                {'name': 'new', 'dst': 'NEW'},
                {'name': 'active', 'dst': 'ACTIVE'},
                {'name': 'deleting', 'dst': 'DELETING'},
            ],
        },
        'NEW': {
            'description': 'Starting to build',
            'events': [
                {'name': 'build', 'dst': 'BUILD'},
                {'name': 'active', 'dst': 'ACTIVE'},
                {'name': 'deleting', 'dst': 'DELETING'},
                {'name': 'error', 'dst': 'ERROR'},
            ],
        },
        'BUILD': {
            'description': 'Resource is being built',
            'events': [
                {'name': 'configure', 'dst': 'CONFIGURE'},
                {'name': 'active', 'dst': 'ACTIVE'},
                {'name': 'deleting', 'dst': 'DELETING'},
                {'name': 'error', 'dst': 'ERROR'},
            ],
        },
        'CONFIGURE': {
            'description': 'Resource is being configured',
            'events': [
                {'name': 'active', 'dst': 'ACTIVE'},
                {'name': 'deleting', 'dst': 'DELETING'},
                {'name': 'error', 'dst': 'ERROR'},
            ],
        },
        'ACTIVE': {
            'description': 'Resource is configured and ready for use',
            'events': [
                {'name': 'deleting', 'dst': 'DELETING'},
                {'name': 'error', 'dst': 'ERROR'},
            ],
        },
        'DELETING': {
            'description': 'Resource is being deleted',
            'events': [
                {'name': 'deleted', 'dst': 'DELETED'},
                {'name': 'error', 'dst': 'ERROR'},
            ],
        },
        'DELETED': {
            'description': 'Resource has been deleted'
        },
        'ERROR': {
            'description': 'There was an error working on this resource',
            'events': [
                {'name': 'new', 'dst': 'NEW'},
                {'name': 'build', 'dst': 'BUILD'},
                {'name': 'configure', 'dst': 'CONFIGURE'},
                {'name': 'active', 'dst': 'ACTIVE'},
                {'name': 'deleting', 'dst': 'DELETING'},
            ],
        },
    }

    def __init__(self, key, obj):
        self.fsm = Fysom({
            'initial': self.get('status', 'PLANNED'),
            'events': schema.get_state_events(Resource.FYSOM_STATES),
        })
        if 'status' not in obj:
            obj['status'] = self.fsm.current
        Resource.validate(obj)
        if 'desired-state' in obj:
            if not isinstance(obj['desired-state'], Resource.DesiredState):
                obj['desired-state'] = Resource.DesiredState(
                    obj['desired-state'])
        self.key = key
        super(Resource, self).__init__(**obj)

    def __setitem__(self, key, value):
        _validate({key: value}, Resource.SCHEMA, Resource.SCHEMA_DEPRECATED)
        if key == 'desired-state':
            if not isinstance(value, Resource.DesiredState):
                value = Resource.DesiredState(value)
        elif key == 'status':
            if value != self.fsm.current:
                LOG.info("Resource %s going from %s to %s",
                         self.get('id'), self.get('status'), value)
                try:
                    self.fsm.go_to(value)
                except FysomError:
                    # This should raise a CheckmateBadState error with message:
                    #
                    # "Cannot transition from %s to %s" %
                    # (self.fsm.current, value))
                    #
                    # Temporarily softening to a warning in the log and
                    # setting state anyway.
                    LOG.warn("State change from %s to %s is invalid",
                             self.fsm.current, value)
                    self.fsm.force_go_to(value)
        super(Resource, self).__setitem__(key, value)

    @classmethod
    def validate(cls, obj):
        '''Validate Resource Schema'''
        _validate(obj, Resource.SCHEMA, Resource.SCHEMA_DEPRECATED)
        if 'desired-state' in obj:
            Resource.DesiredState.validate(obj['desired-state'])
            
    @staticmethod
    def format_postback(key, resource_kwargs, instance_kwargs=None,
        desired_kwargs=None):
        """Return formatted resource for deployment postback"""
        resources = {
            'resources': {
                str(key): resource_kwargs
            }
        }
        if instance_kwargs:
            resources['resources'][key]['instance'] = instance_kwargs

        Resource.validate(resources)
        return resources

    @staticmethod
    def get_checkmate_status(status, status_schema):
        """Return checkmate status for resource based on schema"""
        if status_schema and status and status in status_schema:
            return schema[status]
        else:
            LOG.debug("Resource status %s was not found in schema" % status)
            return "ERROR"

    class DesiredState(dict):
        '''The Desired State section of a Resource'''
        __schema__ = [
            'region', 'flavor', 'image', 'disk', 'protocol',
            'port', 'status', 'databases'
        ]
