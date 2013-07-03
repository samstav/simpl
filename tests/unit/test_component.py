# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''

import unittest

from checkmate.component import Component
from checkmate.exceptions import CheckmateValidationException
from checkmate.utils import yaml_to_dict


class ComponentTestCase(unittest.TestCase):
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
        class dummy(object):
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
                - host: linux
            """)
        c = Component(data)
        expected = yaml_to_dict("""
                    database:mysql:
                      resource_type: database
                      interface: mysql
                    compute:linux:
                      resource_type: compute
                      interface: linux
                    host:linux:
                      interface: linux
                      relation: host
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
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
