#!/usr/bin/env python
import copy
import logging
import unittest2 as unittest
syntax_error
# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

import mox

from checkmate.blueprints import Blueprint
from checkmate.exceptions import CheckmateValidationException
from checkmate import utils


class TestBlueprints(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_schema(self):
        """Test the schema validates a blueprint with all possible fields"""
        blueprint = {
                'id': 'test',
                'version': 'v0.7',
                'name': 'test',
                'services': {},
                'options': {},
                'resources': {},
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
        expected['version'] = 'v0.7'
        expected['log'] = [{'date': '2000-01-01 00:00:00 +0000',
                            'event': 'Converted from None to v0.7'}]
        self.mox.StubOutWithMock(utils, 'get_time_string')
        utils.get_time_string().AndReturn('2000-01-01 00:00:00 +0000')
        self.mox.ReplayAll()
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
                    'old_format_select': {
                        'type': 'select',
                        'choice': [{'name': 'First', 'value': 'A'},
                                   {'name': 'Second', 'value': 'B'}]
                    },
                    'old_format_combo': {
                        'type': 'combo',
                        'choice': [1, 2]
                    },'old_format_url': {
                        'type': 'url',
                        'protocols': ['http', 'https'],
                    },
                },
                'resources': {},
                }
        expected = {
                'id': 'test',
                'version': 'v0.7',
                'name': 'test',
                'services': {},
                'options': {
                    'old_format_int': {
                        'type': 'integer',
                        'constraints': [{'regex': '^[a-zA-Z]$'}]
                    },
                    'old_format_select': {
                        'type': 'string',
                        'choice': [{'name': 'First', 'value': 'A'},
                                   {'name': 'Second', 'value': 'B'}]
                    },
                    'old_format_combo': {
                        'type': 'string',
                        'choice': [1, 2]
                    },'old_format_url': {
                        'type': 'url',
                        'constraints': [{'protocols': ['http', 'https']}],
                    },
                },
                'resources': {},
                'log': [{'date': '2000-01-01 00:00:00 +0000',
                            'event': 'Converted from None to v0.7'}],
                }
        self.mox.StubOutWithMock(utils, 'get_time_string')
        utils.get_time_string().AndReturn('2000-01-01 00:00:00 +0000')
        self.mox.ReplayAll()
        converted = Blueprint(blueprint)
        self.assertDictEqual(converted._data, expected)

    def test_future_blueprint_version(self):
        """Test the an unsupported blueprint version is rejected"""
        blueprint = {
                'version': 'unrecognized'
                }
        self.assertRaisesRegexp(CheckmateValidationException, "This server "
                                "does not support version 'unrecognized' "
                                "blueprints", Blueprint, blueprint)


if __name__ == '__main__':
    # Run tests. Handle our parameters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
