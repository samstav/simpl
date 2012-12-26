#!/usr/bin/env python
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate.components import Component
from checkmate.exceptions import CheckmateValidationException
from checkmate.utils import yaml_to_dict


class TestComponents(unittest.TestCase):
    def test_schema_multiple_interfaces_ok(self):
        """Check that components support entries with the same key"""
        data = yaml_to_dict("""
                id: component1
                provides:
                - database: mysql
                - database: mssql
                requires:
                - database: mysql
                - database: mssql
            """)
        c = Component(data)
        self.assertDictEqual(c._data, data)

    def test_schema_validation(self):
        self.assertRaises(CheckmateValidationException, Component.__init__,
                Component(), {'invalid': 'field'})

    def test_provider_attribute(self):
        """Check that passing in special value gets processed correctly"""
        class dummy():
            key = 1
        c = Component({}, provider=dummy())
        self.assertEqual(c.provider.key, 1)
        self.assertNotIn('provider', c)

    def test_provides_property_list(self):
        """Check that components parses provides as  list correctly"""
        data = yaml_to_dict("""
                id: component1
                provides:
                - database: mysql
                - compute: linux
            """)
        c = Component(data)
        expected = yaml_to_dict("""
                    database:mysql:
                      resource_type: database
                      interface: mysql
                    compute:linux:
                      resource_type: compute
                      interface: linux
            """)
        self.assertDictEqual(c.provides, expected)

    def test_provides_property_dict(self):
        """Check that components parses provides as a dictionary correctly"""
        data = yaml_to_dict("""
                id: component1
                provides:
                  "host":
                    resource_type: compute
                    relation: host
                    interface: linux
                  "data":
                    resource_type: database
                    interface: mysql
                  "logs":
                    resource_type: database
                    interface: mysql
            """)
        c = Component({})
        c._data = data  # bypass validation until we support this syntax
        expected = yaml_to_dict("""
                  host:
                    resource_type: compute
                    relation: host
                    interface: linux
                  data:
                    resource_type: database
                    interface: mysql
                  logs:
                    resource_type: database
                    interface: mysql
            """)
        self.assertDictEqual(c.provides, expected)

    def test_requires_property_list(self):
        """Check that components parses requires list correctly"""
        data = yaml_to_dict("""
                id: component1
                requires:
                - compute: linux
                - database: mysql
            """)
        c = Component(data)
        expected = yaml_to_dict("""
                    database:mysql:
                      resource_type: database
                      interface: mysql
                    compute:linux:
                      resource_type: compute
                      interface: linux
            """)
        self.assertDictEqual(c.requires, expected)

    def test_requires_property_host(self):
        """Check that components parses 'host' shorthand"""
        data = yaml_to_dict("""
                id: component1
                requires:
                - host: linux
            """)
        c = Component(data)
        expected = yaml_to_dict("""
                    host:linux:
                      relation: host
                      interface: linux
            """)
        self.assertDictEqual(c.requires, expected)


if __name__ == '__main__':
    # Run tests. Handle our paramsters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
