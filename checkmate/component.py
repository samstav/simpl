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

"""Components.

A component is a representation of a server, database, load balancer, app,
and so on.
"""

import logging

from checkmate.classes import ExtensibleDict
from checkmate.common import schema
from checkmate import constraints
from checkmate import functions
from checkmate import inputs
from checkmate.exceptions import CheckmateValidationException
from checkmate import utils

LOG = logging.getLogger(__name__)

COMPONENT_DOCS = schema.get_docs(__name__)
COMPONENT_SCHEMA = schema.get_schema(__name__)
COERCER = schema.Schema([schema.ConnectionPoint(coerce=True)])


class Component(ExtensibleDict):

    """TODO: docstring."""

    documentation = COMPONENT_DOCS
    __schema__ = staticmethod(COMPONENT_SCHEMA)

    def __init__(self, *args, **kwargs):
        self._provider = kwargs.pop('provider', None)
        ExtensibleDict.__init__(self, *args, **kwargs)
        if 'id' not in self:
            LOG.warning("No id in %s", self)

    @property
    def provider(self):
        """Provider instance."""
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
        return schema.validate(obj, cls.__schema__, docs=cls.documentation)

    @property
    def provides(self):
        """Return the 'provides' list as an expanded dict."""
        results = self.get('provides') or []
        COERCER(results)
        expanded_results = {}
        for entry in results:
            if 'name' in entry:
                name = entry['name']
            elif 'resource_type' in entry and 'interface' in entry:
                name = '%s:%s' % (entry['resource_type'], entry['interface'])
            elif entry.get('relation') == 'host' and 'interface' in entry:
                name = 'host:%s' % entry['interface']
            else:
                raise CheckmateValidationException(
                    "'provides' has an ambiguous entry: %s" % entry)
            if name in expanded_results:
                raise CheckmateValidationException(
                    "'provides' has conflicting entries: %s" % name)
            expanded_results[name] = entry
        return expanded_results

    @property
    def requires(self):
        """Return the 'requires' list as an expanded dict."""
        results = self.get('requires') or []
        COERCER(results)
        expanded_results = {}
        for entry in results:
            if 'name' in entry:
                name = entry['name']
            elif 'resource_type' in entry and 'interface' in entry:
                name = '%s:%s' % (entry['resource_type'], entry['interface'])
            elif entry.get('relation') == 'host' and 'interface' in entry:
                name = 'host:%s' % entry['interface']
            else:
                raise CheckmateValidationException(
                    "'requires' has an ambiguous entry: %s" % entry)
            if name in expanded_results:
                raise CheckmateValidationException(
                    "'requires' has conflicting entries: %s" % name)
            expanded_results[name] = entry
        return expanded_results

    @property
    def supports(self):
        """Return the 'supports' list as an expanded dict."""
        results = self.get('supports') or []
        COERCER(results)
        expanded_results = {}
        for entry in results:
            if 'name' in entry:
                name = entry['name']
            elif 'resource_type' in entry and 'interface' in entry:
                name = '%s:%s' % (entry['resource_type'], entry['interface'])
            elif entry.get('relation') == 'host' and 'interface' in entry:
                name = 'host:%s' % entry['interface']
            else:
                raise CheckmateValidationException(
                    "'supports' has an ambiguous entry: %s" % entry)
            if name in expanded_results:
                raise CheckmateValidationException(
                    "'supports' has conflicting entries: %s" % name)
            expanded_results[name] = entry
        return expanded_results
