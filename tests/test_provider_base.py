#!/usr/bin/env python
import json
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
from checkmate.providers.base import ProviderBase, PROVIDER_CLASSES,\
        CheckmateInvalidProvider, ProviderBasePlanningMixIn
from checkmate.test import StubbedWorkflowBase, TestProvider
from checkmate.utils import yaml_to_dict

LOG = logging.getLogger(__name__)

class TestProviderBasePlanningMixIn(unittest.TestCase):
    
    def __init__(self, methodName="runTest"):
        self._mox = mox.Mox()
        self._prov_planner = ProviderBasePlanningMixIn()
        self._prov_planner.key = "test_key"
        unittest.TestCase.__init__(self, methodName=methodName)
    
    def test_template(self):
        req_context = RequestContext()
        template = self._prov_planner.generate_template({'id':"1234567890"}, "test_type", None, req_context)
        self.assertIn("type", template, "No type")
        self.assertEqual("test_type", template.get("type","NONE"), "Type not set")
        self.assertIn("provider", template, "No provider in template")
        self.assertEqual("test_key", template.get("provider", "NONE"), "Provider not set")
        self.assertIn("instance", template, "No instance in template")
        self.assertIn("dns-name", template, "No dns-name in template")
        self.assertEqual("CM-1234567-test_type", template.get("dns-name","NONE"), "dns-name not set")
        req_ctx_dict = req_context.get_queued_task_dict()
        self.assertIn("metadata", req_ctx_dict, "No metadata in template")
        self.assertIn("RAX-CHKMT", req_ctx_dict.get("metadata",{}), "No metadata set")
        LOG.info("RAX-CHKMT: {}".format(req_ctx_dict.get("metadata").get("RAX-CHKMT")))

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
        self.assertRaises(CheckmateException, provider.evaluate,
                "unknown()")


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
                            'dns-name': 'CM-DEP-ID--db1.checkmate.local',
                            'instance': {}, 'provider': 'base',
                            'service': 'db', 'type': 'database',
                            'relations': {
                                'web-db': {'interface': 'mysql', 'source': '0',
                                'state': 'planned'}
                              }}],
                    'kwargs': None,
                    'result': {
                          'instance:0': {
                              'name': 'CM-DEP-ID--db1.checkmate.local',
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
                            'dns-name': 'CM-DEP-ID--web1.checkmate.local',
                            'instance': {'interfaces': {'mysql': {
                                'username': 'mysql_user', 'host': 'db.local',
                                'password': 'secret', 'database_name': 'dbX',
                                'port': 8888}},
                                'name': 'CM-DEP-ID--db1.checkmate.local'},
                            'provider': 'base', 'service': 'web',
                            'type': 'application', 'relations': {'web-db': {
                                'interface': 'mysql', 'state': 'planned',
                                'target': '1'}}}],
                    'kwargs': None,
                    'result': None,
                })
        self.workflow = self._get_stubbed_out_workflow(expected_calls=expected)
 
    def test_workflow_completion(self):
        """Verify workflow sequence and data flow"""
        self.mox.ReplayAll()

        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(), "Workflow did not "
                "complete")
        self.assertIn('instance:0', self.workflow.get_tasks()[-1].attributes)
        self.assertIn('mysql', self.workflow.get_tasks()[-1].attributes[
            'instance:0']['interfaces'])

        LOG.debug("RESOURCES: %s" % json.dumps(self.deployment['resources'],
                indent=2))
        last_task = self.workflow.get_tasks()[-1]
        LOG.debug("DELIVERED to '%s': %s" % (last_task.get_name(), json.dumps(
                last_task.attributes['instance:0'], indent=2)))


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
    # Run tests. Handle our parameters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
