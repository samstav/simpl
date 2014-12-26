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

import copy
import logging

from checkmate.classes import ExtensibleDict
from checkmate.common import schema
from checkmate.exceptions import CheckmateValidationException

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

    @classmethod
    def inspect(cls, obj):
        return schema.validate(obj, schema.COMPONENT_SCHEMA)

    @property
    def provides(self):
        """Return the 'provides' list in the expanded format"""
        results = copy.copy(self._data.get('provides'))
        if isinstance(results, list):
            expanded_results = {}
            for entry in results:
                if len(entry) == 1:
                    item = entry.items()[0]
                    keys = ('resource_type', 'interface')
                    expanded = dict(zip(keys, item))
                    expanded_results['%s:%s' % item] = expanded
                else:
                    raise CheckmateValidationException("Provides has invalid "
                                                       "format: " % entry)
            results = expanded_results
        if isinstance(results, dict):
            for value in results.values():
                if 'type' in value:
                    if 'resource_type' in value:
                        msg = ("Component has both type and resource_type "
                               "specified in its provides section")
                        raise CheckmateValidationException(msg)
                    value['resource_type'] = value['type']
                    del value['type']
                    break
        if 'is' in self._data:
            key = self._data['is']
            if not results:
                results = {}
            if not any(v for v in results.itervalues()
                       if key == v.get('resource_type')):
                results[key] = {'resource_type': key}
        return results

    @property
    def requires(self):
        """Return the 'requires' list in the expanded format"""
        results = copy.copy(self._data.get('requires'))
        if isinstance(results, list):
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
                                                       "format: " % entry)
            results = expanded_results
        if isinstance(results, dict):
            for value in results.values():
                if 'type' in value:
                    if 'resource_type' in value:
                        msg = ("Component has both type and resource_type "
                               "specified in its requires section")
                        raise CheckmateValidationException(msg)
                    value['resource_type'] = value['type']
                    del value['type']
                    break
        return results
