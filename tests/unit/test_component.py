# pylint: disable=W0212
"""Tests for Component class."""
import unittest

from checkmate import component as cmcomp
from checkmate.exceptions import CheckmateValidationException
from checkmate.utils import yaml_to_dict


class TestComponent(unittest.TestCase):
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
        comp = cmcomp.Component(data)
        self.assertDictEqual(comp._data, data)

    def test_schema_validation(self):
        self.assertRaises(CheckmateValidationException,
                          cmcomp.Component.__init__, cmcomp.Component(),
                          {'invalid': 'field'})

    def test_provider_attribute(self):
        """Check that passing in special value gets processed correctly"""
        class Dummy(object):
            """Helper class to mock a Provider."""
            key = 1
        comp = cmcomp.Component({}, provider=Dummy())
        self.assertEqual(comp.provider.key, 1)
        self.assertNotIn('provider', comp)

    def test_provides_property_list(self):
        """Check that components parses provides as  list correctly"""
        data = yaml_to_dict("""
                id: component1
                provides:
                - database: mysql
                - compute: linux
            """)
        comp = cmcomp.Component(data)
        expected = yaml_to_dict("""
                    database:mysql:
                      resource_type: database
                      interface: mysql
                    compute:linux:
                      resource_type: compute
                      interface: linux
            """)
        self.assertDictEqual(comp.provides, expected)

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
        comp = cmcomp.Component({})
        comp._data = data  # bypass validation until we support this syntax
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
        self.assertDictEqual(comp.provides, expected)

    def test_requires_property_list(self):
        """Check that components parses requires list correctly"""
        data = yaml_to_dict("""
                id: component1
                requires:
                - compute: linux
                - database: mysql
                - host: linux
            """)
        comp = cmcomp.Component(data)
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
        self.assertDictEqual(comp.requires, expected)

    def test_requires_property_host(self):
        """Check that components parses 'host' shorthand"""
        data = yaml_to_dict("""
                id: component1
                requires:
                - host: linux
            """)
        comp = cmcomp.Component(data)
        expected = yaml_to_dict("""
                    host:linux:
                      relation: host
                      interface: linux
            """)
        self.assertDictEqual(comp.requires, expected)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
