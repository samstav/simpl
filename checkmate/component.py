# Copyright (c) 2011-2013 Rackspace Hosting
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

"""Components.

A component is a representation of a server, database, load balancer, app,
and so on.
"""

import logging

from checkmate import constraints
from checkmate.classes import ExtensibleDict
from checkmate import functions
from checkmate import inputs
from checkmate.common import schema
from checkmate.exceptions import CheckmateValidationException
from checkmate import utils

LOG = logging.getLogger(__name__)

COMPONENT_SCHEMA = schema.get_schema(__name__)


class Component(ExtensibleDict):

    """TODO: docstring."""

    __schema__ = COMPONENT_SCHEMA

    def __init__(self, *args, **kwargs):
        self._provider = kwargs.pop('provider', None)
        ExtensibleDict.__init__(self, *args, **kwargs)
        if 'id' not in self:
            LOG.warning("No id in %s", self)

    @property
    def provider(self):
        """TODO: docstring."""
        return self._provider

    def __repr__(self):
        provider = None
        if self._provider:
            provider = self._provider.key
        return "<%s id='%s' provider='%s'>" % (self.__class__.__name__,
                                               self.get('id'), provider)

    def check_input(self, value, option_name, **kwargs):
        """Check if the value of an option passes constraints."""
        options = self.get('options') or {}
        option = options.get(option_name) or kwargs.get('option') or {}
        option_constraints = option.get('constraints')
        if option_constraints:
            # Handle special defaults
            if utils.is_evaluable(value):
                value = utils.evaluate(value[1:])

            if value is None:
                return True  # don't validate null inputs

            for entry in option_constraints:
                parsed = functions.parse(
                    entry,
                    options=kwargs.get('options'),
                    services=kwargs.get('services'),
                    resources=kwargs.get('resources'),
                    inputs=kwargs.get('inputs'))
                constraint = constraints.Constraint.from_constraint(parsed)
                if not constraint.test(inputs.Input(value)):
                    msg = ("The input for option '%s' did not pass "
                           "validation. The value was '%s'. The "
                           "validation rule was %s" %
                           (option_name,
                            value if option.get('type') != 'password'
                            else '*******',
                            constraint.message))
                    raise CheckmateValidationException(msg)
        return True

    @classmethod
    def inspect(cls, obj):
        return schema.validate(obj, schema.COMPONENT_SCHEMA)

    @property
    def provides(self):
        """Return the 'provides' list in the expanded format"""
        results = self.get('provides') or []
        expanded_results = {}
        for entry in results:
            if len(entry) == 1:
                value = entry.values()[0]
                if isinstance(value, dict):
                    expanded_results[entry.keys()[0]] = value
                else:
                    item = entry.items()[0]
                    if entry.keys()[0] == 'host':
                        keys = ('relation', 'interface')
                    else:
                        keys = ('resource_type', 'interface')
                    expanded = dict(zip(keys, item))
                    expanded_results['%s:%s' % item] = expanded
            else:
                raise CheckmateValidationException("Provides has invalid "
                                                   "format: %s" % entry)
        return expanded_results

    @property
    def requires(self):
        """Return the 'requires' list in the expanded format"""
        results = self.get('requires') or []
        expanded_results = {}
        for entry in results:
            if len(entry) == 1:
                value = entry.values()[0]
                if isinstance(value, dict):
                    expanded_results[entry.keys()[0]] = value
                else:
                    item = entry.items()[0]
                    if entry.keys()[0] == 'host':
                        keys = ('relation', 'interface')
                    else:
                        keys = ('resource_type', 'interface')
                    expanded = dict(zip(keys, item))
                    expanded_results['%s:%s' % item] = expanded
            else:
                raise CheckmateValidationException("Requires has invalid "

    @property
    def uses(self):
        """Return the 'uses' list as an expanded dict."""
        results = self.get('uses') or []
        expanded_results = {}
        for entry in results:
            if len(entry) == 1:
                value = entry.values()[0]
                if isinstance(value, dict):
                    expanded_results[entry.keys()[0]] = value
                else:
                    item = entry.items()[0]
                    if entry.keys()[0] == 'host':
                        keys = ('relation', 'interface')
                    else:
                        keys = ('resource_type', 'interface')
                    expanded = dict(zip(keys, item))
                    expanded_results['%s:%s' % item] = expanded
            else:
                raise CheckmateValidationException("'Uses' has invalid "
                                                   "format: " % entry)
        for value in expanded_results.itervalues():
            if 'type' in value:
                if 'resource_type' in value:
                    msg = ("Component has both type and resource_type "
                           "specified in its 'uses' section")
                    raise CheckmateValidationException(msg)
                value['resource_type'] = value.pop('type')
        return expanded_results
