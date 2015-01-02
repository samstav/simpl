# pylint: disable=W0212

# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
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

"""Tests for Component class."""

import unittest

from checkmate import component as cmcomp
from checkmate import exceptions as cmexc
from checkmate import utils


class TestComponent(unittest.TestCase):
    def test_schema_multiple_interfaces(self):
        """Check that components support entries with the same key."""
        data = utils.yaml_to_dict("""
                id: component1
                provides:
                - database: mysql
                - database: mssql
                requires:
                - database: mysql
                - database: mssql
                supports:
                - database: mysql
                - database: mssql
            """)
        comp = cmcomp.Component(data)
        self.assertEqual(comp._data, data)

    def test_schema_validation(self):
        self.assertRaises(cmexc.CheckmateValidationException,
                          cmcomp.Component.__init__, cmcomp.Component(),
                          {'invalid': 'field'})

    def test_provider_attribute(self):
        """Check that passing in special value gets processed correctly."""
        class Dummy(object):
            """Helper class to mock a Provider."""
            key = 1
        comp = cmcomp.Component({}, provider=Dummy())
        self.assertEqual(comp.provider.key, 1)
        self.assertNotIn('provider', comp)

    def test_provides_property_list(self):
        """Check that components parses provides as  list correctly."""
        data = utils.yaml_to_dict("""
                id: component1
                provides:
                - database: mysql
                - compute: linux
                - longform:  # Check that name stays
                    resource_type: cache
                    interface: redis
            """)
        comp = cmcomp.Component(data)
        expected = utils.yaml_to_dict("""
                    database:mysql:
                      resource_type: database
                      interface: mysql
                    compute:linux:
                      resource_type: compute
                      interface: linux
                    longform:
                      resource_type: cache
                      interface: redis
            """)
        self.assertEqual(comp.provides, expected)

    def test_requires_property_list(self):
        """Check that components parses requires list correctly."""
        data = utils.yaml_to_dict("""
                id: component1
                requires:
                - compute: linux
                - database: mysql
                - host: linux
            """)
        comp = cmcomp.Component(data)
        expected = utils.yaml_to_dict("""
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
        self.assertEqual(comp.requires, expected)

    def test_requires_property_host(self):
        """Check that components parses 'host' shorthand."""
        data = utils.yaml_to_dict("""
                id: component1
                requires:
                - host: linux
            """)
        comp = cmcomp.Component(data)
        expected = utils.yaml_to_dict("""
                host:linux:
                  relation: host
                  interface: linux
            """)
        self.assertEqual(comp.requires, expected)

    def test_supports_property(self):
        """Check that components parses supports list correctly."""
        data = utils.yaml_to_dict("""
                id: component1
                supports:
                - compute: linux               # shorthand
                - backend:                     # long form
                    resource_type: database
                    interface: mysql
                - host: linux                  # host relation
            """)
        comp = cmcomp.Component(data)
        expected = utils.yaml_to_dict("""
                backend:
                  resource_type: database
                  interface: mysql
                compute:linux:
                  resource_type: compute
                  interface: linux
                host:linux:
                  interface: linux
                  relation: host
            """)
        self.assertEqual(comp.supports, expected)

    def test_input_validation(self):
        """Check that components can test option constraints."""
        data = utils.yaml_to_dict("""
                id: component1
                options:
                  foo:
                    type: int
                    constraints:
                    - greater-than: 2
            """)
        comp = cmcomp.Component(data)
        self.assertTrue(comp.check_input(3, 'foo'))
        with self.assertRaises(cmexc.CheckmateValidationException):
            comp.check_input(1, 'foo')


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
