# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import copy
import unittest2 as unittest

from checkmate.blueprints import Blueprint
from checkmate.exceptions import CheckmateValidationException


class TestBlueprints(unittest.TestCase):

    def test_schema(self):
        """Test the schema validates a blueprint with all possible fields"""
        blueprint = {
            'id': 'test',
            'version': '1.1.0',
            'meta-data': {
                'schema-version': 'v0.7',
            },
            'name': 'test',
            'services': {},
            'options': {},
            'resources': {},
            'display-outputs': {},
            'documentation': {},
        }
        valid = Blueprint(blueprint)
        self.assertDictEqual(valid._data, blueprint)

    def test_schema_with_options(self):
        blueprint = {
            'id': 'test',
            'name': 'test',
            'services': {},
            'options': {
                "foo": {
                    "type": "integer",
                    "default": 4,
                    "constrains": [
                        {
                            "service": "service1",
                            "type": "application",
                            "interface": "none"
                        }
                    ]
                },
                "bar": {
                    "type": "string",
                    "default": "Empty",
                    "display-hints": {
                        "group": "An option group",
                        "weight": 1
                    },
                    "constrains": [
                        {
                            "service": "service2",
                            "type": "application",
                            "interface": "another"
                        }
                    ]
                },
            },
            'resources': {},
        }
        expected = copy.deepcopy(blueprint)
        expected['meta-data'] = {'schema-version': 'v0.7'}
        valid = Blueprint(blueprint)
        self.assertDictEqual(valid._data, expected)

    def test_schema_negative(self):
        """Test the schema validates a blueprint with bad fields"""
        blueprint = {
            'nope': None
        }
        self.assertRaises(CheckmateValidationException, Blueprint, blueprint)

    def test_conversion_from_pre_v0_dot_7(self):
        """Test that blueprints syntax from pre v0.7 gets converted"""
        blueprint = {
            'id': 'test',
            'name': 'test',
            'services': {},
            'options': {
                'old_format_int': {
                    'type': 'int',
                    'regex': '^[a-zA-Z]$'
                },
                'old_format_select_and_choice': {
                    'type': 'select',
                    'choice': [{'name': 'First', 'value': 'A'},
                               {'name': 'Second', 'value': 'B'}]
                },
                'old_format_combo_and_sample': {
                    'type': 'combo',
                    'choice': [1, 2],
                    'sample': 'like this!',
                },
                'old_format_url': {
                    'type': 'url',
                    'protocols': ['http', 'https'],
                },
                'old_format_region': {
                    'type': 'region',
                },
            },
            'resources': {},
        }
        expected = {
            'id': 'test',
            'meta-data': {
                'schema-version': 'v0.7',
            },
            'name': 'test',
            'services': {},
            'options': {
                'old_format_int': {
                    'type': 'integer',
                    'constraints': [{'regex': '^[a-zA-Z]$'}]
                },
                'old_format_select_and_choice': {
                    'type': 'string',
                    'display-hints': {
                        'choice': [{'name': 'First', 'value': 'A'},
                                   {'name': 'Second', 'value': 'B'}],
                    },
                },
                'old_format_combo_and_sample': {
                    'type': 'string',
                    'display-hints': {
                        'choice': [1, 2],
                        'sample': 'like this!',
                    },
                },
                'old_format_url': {
                    'type': 'url',
                    'constraints': [{'protocols': ['http', 'https']}],
                },
                'old_format_region': {
                    'type': 'string',
                },
            },
            'resources': {},
        }
        converted = Blueprint(blueprint)
        self.assertDictEqual(converted._data, expected)

    def test_future_blueprint_version(self):
        """Test the an unsupported blueprint version is rejected"""
        blueprint = {
            'meta-data': {
                'schema-version': 'unrecognized',
            },
        }
        self.assertRaisesRegexp(CheckmateValidationException, "This server "
                                "does not support version 'unrecognized' "
                                "blueprints", Blueprint, blueprint)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import os
    import sys
    sys.path.insert(1, os.path.join(sys.path[0], '../..'))
    from tests.utils import run_with_params
    run_with_params(sys.argv[:])
