#!/usr/bin/env python
'''
Blueprint dict-like class
'''
import copy
import logging

from checkmate.classes import ExtensibleDict
from checkmate.common import schema
from checkmate.exceptions import CheckmateValidationException

LOG = logging.getLogger(__name__)


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
        """Detect version and convert to current if necessary and able"""
        converters = {
            'v0.6': cls.from_v0_6,
        }
        version = obj.get('meta-data', {}).get('schema-version', 'v0.6')
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

            # convert types

            option_type = option.get('type')
            if option_type is None:
                option['type'] = 'string'
                LOG.warn("Converted option with missing 'type' to 'string' in "
                         "blueprint '%s'", data.get('id'))
            elif option_type in ['select', 'combo']:
                option['type'] = 'string'
                LOG.warn("Converted 'type' from '%s' to 'string' in "
                         "blueprint '%s'", option_type, data.get('id'))
            elif option_type == 'int':
                option['type'] = 'integer'
                LOG.warn("Converted 'type' from 'int' to 'integer' "
                         " in blueprint '%s'", data.get('id'))
            elif option_type == 'region':
                option['type'] = 'string'
                LOG.warn("Converted 'type' from 'region' to 'string' "
                         " in blueprint '%s'", data.get('id'))

            # move 'regex' to constraint

            if 'regex' in option:
                constraint = {'regex': option['regex']}
                if 'constraints' not in option:
                    option['constraints'] = [constraint]
                else:
                    option['constraints'].append(constraint)
                del option['regex']
                LOG.warn("Converted 'regex' attribute in an option in "
                         "blueprint '%s'", data.get('id'))

            # move 'protocols' to constraint

            if 'protocols' in option:
                constraint = {'protocols': option['protocols']}
                if 'constraints' not in option:
                    option['constraints'] = [constraint]
                else:
                    option['constraints'].append(constraint)
                del option['protocols']
                LOG.warn("Converted 'protocols' attribute in an option in "
                         "blueprint '%s'", data.get('id'))

            # move 'choice' to display-hints

            if 'choice' in option:
                if 'display-hints' not in option:
                    option['display-hints'] = {'choice': option['choice']}
                else:
                    option['display-hints']['choice'] = option['choice']
                del option['choice']
                LOG.warn("Converted 'choice' attribute in an option in "
                         "blueprint '%s'", data.get('id'))

            # move 'sample' to display-hints

            if 'sample' in option:
                if 'display-hints' not in option:
                    option['display-hints'] = {'sample': option['sample']}
                else:
                    option['display-hints']['sample'] = option['sample']
                del option['sample']
                LOG.warn("Converted 'sample' attribute in an option in "
                         "blueprint '%s'", data.get('id'))

        # tag version and log conversion

        version = data.get('meta-data', {}).get('schema-version')
        if (version or 'v0.6') < 'v0.7':

            if 'meta-data' not in data:
                data['meta-data'] = {}
            data['meta-data']['schema-version'] = 'v0.7'
            LOG.info("Converted blueprint '%s' from %s to %s",
                     data.get('id'), version, 'v0.7')

        return data

    @classmethod
    def inspect(cls, obj):
        errors = schema.validate(obj, schema.BLUEPRINT_SCHEMA)
        errors.extend(schema.validate_inputs(obj))
        if obj:
            errors.extend(schema.validate_options(obj.get('options')))
        return errors
