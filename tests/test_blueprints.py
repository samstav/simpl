#!/usr/bin/env python
import logging
import unittest2 as unittest
syntax_error
# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate.blueprints import Blueprint
from checkmate.exceptions import CheckmateValidationException
from checkmate.utils import yaml_to_dict


class TestBlueprints(unittest.TestCase):
    def test_schema(self):
        """Test the schema validates a blueprint with all possible fields"""
        blueprint = {
                'id': 'test',
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
                'options': [
                    {
                        "name": "foo",
                        "type": "int",
                        "default": 4,
                        "constrains": [
                            {
                               "service": "service1",
                               "type": "application",
                               "interface": "none"
                            }
                        ]
                    },
                    {
                        "name": "bar",
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
                    }
                ],
                'resources': {},
                }
        valid = Blueprint(blueprint)
        self.assertDictEqual(valid._data, blueprint)

    def test_schema_negative(self):
        """Test the schema validates a blueprint with bad fields"""
        blueprint = {
                'nope': None
                }
        self.assertRaises(CheckmateValidationException, Blueprint, blueprint)


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
