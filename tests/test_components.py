#!/usr/bin/env python
import unittest2 as unittest

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
        self.assertEqual(c.provider().key, 1)
        self.assertNotIn('provider', c)


if __name__ == '__main__':
    unittest.main()
