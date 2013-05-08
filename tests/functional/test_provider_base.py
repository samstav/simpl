# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import logging
import uuid

import mox
from mox import IsA
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()

from checkmate.deployments import Deployment
from checkmate.exceptions import CheckmateException
from checkmate.middleware import RequestContext
from checkmate.providers.base import (ProviderBase,
                                      PROVIDER_CLASSES,
                                      CheckmateInvalidProvider,
                                      ProviderBasePlanningMixIn)
from checkmate.test import StubbedWorkflowBase, TestProvider
from checkmate.utils import yaml_to_dict

LOG = logging.getLogger(__name__)


class TestProviderBasePlanningMixIn(unittest.TestCase):

    def __init__(self, methodName="runTest"):
        self._mox = mox.Mox()
        self._prov_planner = ProviderBasePlanningMixIn()
        self._prov_planner.key = "test_key"
        self._req_context = RequestContext()
        unittest.TestCase.__init__(self, methodName=methodName)

    def test_template(self):
        template = self._prov_planner.generate_template(
            {'id': "1234567890", 'name': 'test_deployment'},
            "test_type",
            None,
            self._req_context)
        self.assertIn("type", template, "No type")
        self.assertEqual("test_type",
                         template.get("type", "NONE"),
                         "Type not set")
        self.assertIn("provider", template, "No provider in template")
        self.assertEqual("test_key",
                         template.get("provider", "NONE"),
                         "Provider not set")
        self.assertIn("instance", template, "No instance in template")
        self.assertIn("dns-name", template, "No dns-name in template")
        self.assertEqual("test_type",
                         template.get("dns-name", "NONE"),
                         "dns-name not set")
        req_ctx_dict = self._req_context.get_queued_task_dict()
        self.assertIn("metadata", req_ctx_dict, "No metadata in template")
        self.assertIn("RAX-CHECKMATE",
                      req_ctx_dict.get("metadata", {}),
                      "No metadata set")
        LOG.info("RAX-CHECKMATE: {}"
                 .format(req_ctx_dict.get("metadata")
                 .get("RAX-CHECKMATE")))

    def test_template_without_deployment_name(self):
        template = self._prov_planner.generate_template({'id': "1234567890"},
                                                        "test_type",
                                                        None,
                                                        self._req_context)
        self.assertEqual("test_type",
                         template.get("dns-name", "NONE"),
                         "dns-name not set")


class TestProviderBase(unittest.TestCase):
    def test_provider_bad_override(self):
        """Raise error if invalid provider data passed in"""
        # Common mistake, pass object with key as base, instead of object
        data = yaml_to_dict("""
              base:
                  provides:
                  - widget: foo
                  vendor: test
            """)
        self.assertRaises(CheckmateInvalidProvider, ProviderBase, data)

    def test_provider_catalog_override(self):
        """Test that an injected catalog works"""
        data = yaml_to_dict("""
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
        base = ProviderBase(data, key='base')
        self.assertDictEqual(base.get_catalog(None), data['catalog'])

    def test_provider_catalog_filter(self):
        """Test that get_catalog applies type filter"""
        data = yaml_to_dict("""
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
        base = ProviderBase(data, key='base')
        self.assertDictEqual(base.get_catalog(None), data['catalog'])
        widgets = base.get_catalog(None, type_filter='widget')
        self.assertDictEqual(widgets, {'widget': data['catalog']['widget']})
        gadgets = base.get_catalog(None, type_filter='gadget')
        self.assertDictEqual(gadgets, {'gadget': data['catalog']['gadget']})

    def test_provider_find_components(self):
        base = ProviderBase(yaml_to_dict("""
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
        """Correctly selects from components with same interface or type"""
        base = ProviderBase(yaml_to_dict("""
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
        provider = ProviderBase({})
        self.assertIsInstance(uuid.UUID(provider.evaluate("generate_uuid())")),
                              uuid.UUID)
        self.assertEqual(len(provider.evaluate("generate_password()")), 8)
        self.assertRaises(NameError, provider.evaluate, "unknown()")

    def test_get_setting(self):
        provider = ProviderBase(yaml_to_dict("""
                vendor: acme
                constraints:
                - foo: bar
                """))
        self.assertIsNone(provider.get_setting('test'))
        self.assertEqual(provider.get_setting('test', default=1), 1)
        self.assertEqual(provider.get_setting('foo'), 'bar')
        self.assertEqual(provider.get_setting('foo', default='ignore!'), 'bar')


class TestProviderBaseWorkflow(StubbedWorkflowBase):
    """ Test Option Data Flow in Workflow """

    def setUp(self):
        StubbedWorkflowBase.setUp(self)
        PROVIDER_CLASSES['test.base'] = TestProvider
        self.deployment = Deployment(yaml_to_dict("""
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
            'args': [IsA(dict),
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
            'args': [IsA(dict),
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
    """Test setting parsers"""

    def test_memory_parser(self):
        """Test parsing of memory strings"""
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
            self.assertEquals(ProviderBase.parse_memory_setting(case[0]),
                              case[1], "'%s' setting should return %s" %
                              (case[0], case[1]))

    def test_memory_parser_blanks(self):
        """Tests that blanks raise errors"""
        self.assertRaises(CheckmateException,
                          ProviderBase.parse_memory_setting,
                          None)
        self.assertRaises(CheckmateException,
                          ProviderBase.parse_memory_setting,
                          "")
        self.assertRaises(CheckmateException,
                          ProviderBase.parse_memory_setting,
                          " ")

    def test_memory_parser_bad_unit(self):
        """Test that unrecognized units raise errors"""
        self.assertRaises(CheckmateException,
                          ProviderBase.parse_memory_setting,
                          "1 widget")


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
