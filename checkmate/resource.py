# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#
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

"""The Resource Class.

An extensible dict containing all of the details of a deployment's resources.
"""

import logging

from morpheus import dict as exceptions
from morpheus import MorpheusDict as dict  # pylint: disable=W0622
import simplefsm
from simplefsm import exceptions as fsmexc

from checkmate.common import schema
from checkmate.exceptions import CheckmateValidationException

exceptions.ValidationError = CheckmateValidationException

LOG = logging.getLogger(__name__)


def _validate(obj, obj_schema, deprecated_schema=[]):
    """Validate Schema."""
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

    """A Checkmate resource.

    A deployment can have many resources.
    """

    SCHEMA = [
        'index', 'name', 'provider', 'relations', 'hosted_on',
        'hosts', 'type', 'component', 'dns-name', 'instance',
        'service', 'status', 'desired-state'
    ]
    SCHEMA_DEPRECATED = [
        'id', 'flavor', 'image', 'disk', 'region', 'protocol', 'port'
    ]

    FSM_TRANSITIONS = {
        'PLANNED': {'NEW', 'ACTIVE', 'DELETING'},
        'NEW': {'BUILD', 'ACTIVE', 'DELETING', 'ERROR'},
        'BUILD': {'CONFIGURE', 'ACTIVE', 'DELETING', 'ERROR'},
        'CONFIGURE': {'ACTIVE', 'DELETING', 'ERROR'},
        'ACTIVE': {'DELETING', 'ERROR'},
        'DELETING': {'DELETED', 'ERROR'},
        'DELETED': {},
        'ERROR': {'NEW', 'BUILD', 'CONFIGURE', 'ACTIVE', 'DELETING'}
    }

    def __init__(self, key, obj):
        obj['status'] = obj.get('status', 'PLANNED')
        self.fsm = simplefsm.SimpleFSM({
            'initial': obj['status'],
            'transitions': self.FSM_TRANSITIONS
        })
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
                    self.fsm.change_to(value)
                except fsmexc.InvalidStateError:
                    # This should raise a CheckmateBadState error with message:
                    #
                    # "Cannot transition from %s to %s" %
                    # (self.fsm.current, value))
                    #
                    # Temporarily softening to a warning in the log and
                    # setting state anyway.
                    LOG.warn("State change from %s to %s is invalid",
                             self.fsm.current, value)
                    self.fsm.force_change_to(value)
        super(Resource, self).__setitem__(key, value)

    @classmethod
    def validate(cls, obj):
        """Validate Resource Schema."""
        _validate(obj, Resource.SCHEMA, Resource.SCHEMA_DEPRECATED)
        if 'desired-state' in obj:
            Resource.DesiredState.validate(obj['desired-state'])

    class DesiredState(dict):

        """The Desired State section of a Resource."""

        __schema__ = [
            'region', 'flavor', 'image', 'disk', 'protocol',
            'port', 'status', 'databases', 'os-type', 'os', 'userdata',
            'config_drive', 'dns-A-name', 'networks', 'datastore-version',
            'datastore-type', 'config-params', 'size', 'disk',
            'boot_from_image', 'image-info', 'flavor-info', 'key_name', 'name',
            'public_key_ssh', 'master-db-id', 'replica-of', 'berks_entry',
            'run_list'
        ]
