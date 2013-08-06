'''
Components
'''

#!/usr/bin/env python
import copy
import logging

from checkmate.classes import ExtensibleDict
from checkmate.common import schema
from checkmate.exceptions import CheckmateValidationException


LOG = logging.getLogger(__name__)


class Component(ExtensibleDict):
    """
    TODO: docstring
    """
    def __init__(self, *args, **kwargs):
        self._provider = kwargs.pop('provider', None)
        ExtensibleDict.__init__(self, *args, **kwargs)
        if 'id' not in self:
            LOG.warning("No id in %s", self)

    @property
    def provider(self):
        """
        TODO: docstring
        """
        return self._provider

    def __repr__(self):
        provider = None
        if self._provider:
            provider = self._provider.key
        return "<%s id='%s' provider='%s'>" % (self.__class__.__name__,
                                               self.get('id'), provider)

    @classmethod
    def inspect(cls, obj):
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
        return errors

    @property
    def provides(self):
        """Returns the 'provides' list in the expanded format"""
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
        return results

    @property
    def requires(self):
        """Returns the 'requires' list in the expanded format"""
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
