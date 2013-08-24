# pylint: disable=R0904

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

"""Tests for Provider Base."""
import logging
import uuid

import mox
import unittest

from checkmate import deployment as cmdep
from checkmate import exceptions as cmexc
from checkmate.providers import base as cmbase
from checkmate import test as cmtest
from checkmate import utils

LOG = logging.getLogger(__name__)


class TestProviderBase(unittest.TestCase):
    def test_provider_bad_override(self):
        """Raise error if invalid provider data passed in."""
        # Common mistake, pass object with key as base, instead of object
        data = utils.yaml_to_dict("""
              base:
                  provides:
                  - widget: foo
                  vendor: test
            """)
        self.assertRaises(
            cmbase.CheckmateInvalidProvider, cmbase.ProviderBase, data)

    def test_provider_catalog_override(self):
        """Test that an injected catalog works."""
        data = utils.yaml_to_dict("""
                  provides:
                  - widget: foo
                  - widget: bar
                  vendor: test
                  catalog:
                    widget:
                      small_widget:
                        is: widget
                        provides:
                        - widget: foo
                      big_widget:
                        is: widget
                        provides:
                        - widget: bar
            """)
        base = cmbase.ProviderBase(data, key='base')
        self.assertDictEqual(base.get_catalog(None), data['catalog'])

    def test_provider_catalog_filter(self):
        """Test that get_catalog applies type filter."""
        data = utils.yaml_to_dict("""
                  vendor: test
                  catalog:
                    widget:
                      small_widget:
                        is: widget
                        provides:
                        - widget: foo
                    gadget:
                      big_gadget:
                        is: gadget
                        provides:
                        - gadget: bar
            """)
        base = cmbase.ProviderBase(data, key='base')
        self.assertDictEqual(base.get_catalog(None), data['catalog'])
        widgets = base.get_catalog(None, type_filter='widget')
        self.assertDictEqual(widgets, {'widget': data['catalog']['widget']})
        gadgets = base.get_catalog(None, type_filter='gadget')
        self.assertDictEqual(gadgets, {'gadget': data['catalog']['gadget']})

    def test_provider_find_components(self):
        base = cmbase.ProviderBase(utils.yaml_to_dict("""
                  provides:
                  - widget: foo
                  - widget: bar
                  vendor: test
                  catalog:
                    widget:
                      small_widget:
                        is: widget
                        provides:
                        - widget: foo
                      big_widget:
                        is: widget
                        provides:
                        - widget: bar
            """), key='base')

        found = base.find_components(None, resource_type='widget')
        self.assertEqual(len(found), 2)
        self.assertIn(found[0]['id'], ['small_widget', 'big_widget'])
        self.assertIn(found[1]['id'], ['small_widget', 'big_widget'])

    def test_provider_select_components(self):
        """Correctly selects from components with same interface or type."""
        base = cmbase.ProviderBase(utils.yaml_to_dict("""
                  provides:
                  - widget: foo
                  - widget: bar
                  - gadget: foo
                  vendor: test
                  catalog:
                    widget:
                      small_widget:
                        is: widget
                        provides:
                        - widget: foo
                      big_widget:
                        is: widget
                        provides:
                        - widget: bar
                      gadget:
                        is: gadget
                        provides:
                        - gadget: foo
            """), key='base')

        found = base.find_components(None, resource_type='widget')
        self.assertEqual(len(found), 2)
        self.assertIn(found[0]['id'], ['small_widget', 'big_widget'])
        self.assertIn(found[1]['id'], ['small_widget', 'big_widget'])

        found = base.find_components(None, resource_type='gadget')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['id'], 'gadget')

        found = base.find_components(None, interface='foo')
        self.assertEqual(len(found), 2)
        self.assertIn(found[0]['id'], ['small_widget', 'gadget'])
        self.assertIn(found[1]['id'], ['small_widget', 'gadget'])

        found = base.find_components(None, resource_type='widget',
                                     interface='foo')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['id'], 'small_widget',)

    def test_evaluate(self):
        provider = cmbase.ProviderBase({})
        self.assertIsInstance(uuid.UUID(provider.evaluate("generate_uuid()")),
                              uuid.UUID)
        self.assertEqual(len(provider.evaluate("generate_password()")), 8)
        self.assertRaises(NameError, provider.evaluate, "unknown()")

    def test_get_setting(self):
        provider = cmbase.ProviderBase(utils.yaml_to_dict("""
                vendor: acme
                constraints:
                - foo: bar
                """))
        self.assertIsNone(provider.get_setting('test'))
        self.assertEqual(provider.get_setting('test', default=1), 1)
        self.assertEqual(provider.get_setting('foo'), 'bar')
        self.assertEqual(provider.get_setting('foo', default='ignore!'), 'bar')

    def test_get_resource_status(self):
        """Mox tests for get_resource_status of provider base."""
        _mox = mox.Mox()
        data = {"provides": "foo"}
        base = cmbase.ProviderBase(data)
        deployment_id = "someid123"
        key = "0"
        api = "dummy_api_object"
        resource = {
            'name': 'db1.checkmate.local',
            'provider': 'base',
            'status': 'ACTIVE',
            'region': 'ORD',
            'instance': {
                'id': 'dummy_id',
                'databases': ''
            }
        }

        def sync_resource_task(ctx, resource, key, api):
            """Dummy method for testing."""
            return {
                'ctx': ctx,
                'resource': resource,
                'key': key,
                'api': api
            }

        ctx = "dummy_queued_task_dict"
        context_mock = _mox.CreateMockAnything()
        context_mock.get_queued_task_dict(deployment=deployment_id,
                                          resource=key).AndReturn(ctx)

        expected = {
            'ctx': ctx,
            'resource': resource,
            'key': key,
            'api': api,
        }

        _mox.ReplayAll()
        results = base.get_resource_status(context_mock, deployment_id,
                                           resource, key,
                                           sync_callable=sync_resource_task)
        _mox.UnsetStubs()
        self.assertItemsEqual(expected, results)


class TestProviderBaseWorkflow(cmtest.StubbedWorkflowBase):
    """Test Option Data Flow in Workflow."""

    def setUp(self):
        cmtest.StubbedWorkflowBase.setUp(self)
        cmbase.PROVIDER_CLASSES['test.base'] = cmtest.TestProvider
        self.deployment = cmdep.Deployment(utils.yaml_to_dict("""
                id: 'DEP-ID-1000'
                blueprint:
                  name: test mysql connection
                  services:
                    web:
                      component:
                        id: web_app
                      relations:
                        db: mysql
                    db:
                      component:
                        id: database_instance
                environment:
                  name: test
                  providers:
                    base:
                      vendor: test
                      provides:
                      - application: http
                      - database: mysql
                      catalog:
                        application:
                          web_app:
                            id: web_app
                            is: application
                            provides:
                            - application: http
                            requires:
                            - database: mysql
                        database:
                          database_instance:
                            id: database_instance
                            is: database
                            provides:
                            - database: mysql
            """))
        expected = []
        expected.append({
            'call': 'checkmate.providers.test.create_resource',
            'args': [mox.IsA(dict),
                        {'index': '1', 'component': 'database_instance',
                            'dns-name': 'db1.checkmate.local',
                            'instance': {}, 'provider': 'base',
                            'service': 'db', 'type': 'database',
                            'relations': {
                                'web-db': {'interface': 'mysql', 'source': '0',
                                'state': 'planned'}
                            }
                         }
                     ],
            'kwargs': None,
            'result': {
                'instance:0': {
                    'name': 'db1.checkmate.local',
                    'interfaces': {
                        'mysql': {
                            'username': 'mysql_user',
                            'host': 'db.local',
                            'database_name': 'dbX',
                            'port': 8888,
                            'password': 'secret',
                        },
                    }
                }
            },
            'post_back_result': True,
        })
        expected.append({
            'call': 'checkmate.providers.test.create_resource',
            'args': [mox.IsA(dict),
                    {'index': '0', 'component': 'web_app',
                    'dns-name': 'web1.checkmate.local',
                    'instance': {'interfaces': {'mysql': {
                        'username': 'mysql_user', 'host': 'db.local',
                        'password': 'secret', 'database_name': 'dbX',
                        'port': 8888}},
                        'name': 'db1.checkmate.local'},
                    'provider': 'base', 'service': 'web',
                    'type': 'application', 'relations': {'web-db': {
                        'interface': 'mysql', 'state': 'planned',
                        'target': '1'}}}],
            'kwargs': None,
            'result': None,
        })
        self.workflow = self._get_stubbed_out_workflow(expected_calls=expected)


class TestProviderBaseParser(unittest.TestCase):
    """Test setting parsers."""

    def test_memory_parser(self):
        """Test parsing of memory strings."""
        cases = [
            ["1 megabyte", 1],
            ["1 gigabyte", 1024],
            ["1 terabyte", 1024 ** 2],

            # Plural
            ["10 megabytes", 10],
            ["100 gigabytes", 100 * 1024],
            ["1000 terabytes", 1000 * 1024 ** 2],

            # Case
            ["1 MegaByte", 1],
            ["1 GigaByte", 1024],
            ["1 TeraByte", 1024 ** 2],

            # Abbreviations
            ["1 mB", 1],
            ["1 Gb", 1024],
            ["1 TB", 1024 ** 2],

            # Spacing
            ["1mb", 1],
            ["10  gb", 10 * 1024],
            [" 100   tb   ", 100 * (1024 ** 2)],

            # Integers
            ["10", 10],
            [10, 10],
            [" 100 ", 100],
        ]
        for case in cases:
            self.assertEquals(
                cmbase.ProviderBase.parse_memory_setting(case[0]),
                case[1], "'%s' setting should return %s" % (case[0], case[1])
            )

    def test_memory_parser_blanks(self):
        """Tests that blanks raise errors."""
        self.assertRaises(cmexc.CheckmateException,
                          cmbase.ProviderBase.parse_memory_setting,
                          None)
        self.assertRaises(cmexc.CheckmateException,
                          cmbase.ProviderBase.parse_memory_setting,
                          "")
        self.assertRaises(cmexc.CheckmateException,
                          cmbase.ProviderBase.parse_memory_setting,
                          " ")

    def test_memory_parser_bad_unit(self):
        """Test that unrecognized units raise errors."""
        self.assertRaises(cmexc.CheckmateException,
                          cmbase.ProviderBase.parse_memory_setting,
                          "1 widget")


if __name__ == '__main__':
    import sys

    cmtest.run_with_params(sys.argv[:])
