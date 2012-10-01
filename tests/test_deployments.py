#!/usr/bin/env python
import copy
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
from mox import Mox
import mox
import checkmate
from bottle import Bottle
import bottle
import json
from celery.app.task import Context
import os
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate.deployments import Deployment, plan, get_deployments_count, \
        get_deployments_by_bp_count, _deploy
from checkmate.exceptions import CheckmateValidationException
from checkmate.providers.base import PROVIDER_CLASSES, ProviderBase
from checkmate.middleware import RequestContext
from checkmate.utils import yaml_to_dict


class TestDeployments(unittest.TestCase):
    def test_parser(self):
        """Test the parser works on a minimal deployment"""
        deployment = {
                'id': 'test',
                'blueprint': {
                    'name': 'test bp',
                    },
                'environment': {
                    'name': 'environment',
                    'providers': {},
                    },
                }
        original = copy.copy(deployment)
        parsed = plan(Deployment(deployment), RequestContext())
        del parsed['status']  # we expect this to get added
        del parsed['created']  # we expect this to get added
        self.assertDictEqual(original, parsed.__dict__())


    def test_deployer(self):
        """Test the deployer works on a minimal deployment"""
        deployment = {
                'id': 'test',
                'tenantId': 'T1000',
                'blueprint': {
                    'name': 'test bp',
                    },
                'environment': {
                    'name': 'environment',
                    'providers': {},
                    },
                }
        original = copy.copy(deployment)
        parsed = plan(Deployment(deployment), RequestContext())
        workflow = _deploy(parsed, RequestContext())
        #print json.dumps(parsed._data, indent=2)
        self.assertIn("wf_spec", workflow)
        self.assertEqual(parsed['status'], "LAUNCHED")


    def test_resource_generator(self):
        """Test the parser generates the right number of resources"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    back:
                      component: &widget
                        id: widget
                        type: widget
                        interface: foo
                    front:
                      component: *widget
                      relations:
                        middle: foo
                    middle:
                      component: *widget
                      relations:
                        back: foo
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
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
                    common:
                      credentials:
                      - password: secret
                        username: tester
                inputs:
                  services:
                    middle:
                      widget:
                        count: 4
            """))

        PROVIDER_CLASSES['test.base'] = ProviderBase

        parsed = plan(deployment, RequestContext())
        services = parsed['blueprint']['services']
        self.assertEqual(len(services['front']['instances']), 1)
        self.assertEqual(len(services['middle']['instances']), 4)
        self.assertEqual(len(services['back']['instances']), 1)
        #import json
        #print json.dumps(parsed, indent=2)


class TestComponentSearch(unittest.TestCase):
    """ Test code that finds components """
    def test_component_find_by_type(self):
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      component:
                        type: widget
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      vendor: test
                      catalog:
                        widget:
                          small_widget:
                            is: widget
                            provides:
                            - widget: foo
            """))
        PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        self.assertEquals(deployment['resources'].values()[0]['component'],
                'small_widget')

    def test_component_find_by_type_and_interface(self):
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      component:
                        type: widget
                        interface: foo
                    two:
                      component:
                        type: widget
                        interface: bar
                environment:
                  name: environment
                  providers:
                    base:
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
            """))
        PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        components = [r['component'] for r in deployment['resources'].values()]
        self.assertIn('big_widget', components)
        self.assertIn('small_widget', components)

    def test_component_finding(self):
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      component:
                        type: widget
                        interface: foo
                    two:
                      component:
                        id: big_widget
                environment:
                  name: environment
                  providers:
                    base:
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
                    common:
                      credentials:
                      - password: secret
                        username: tester
            """))
        PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        components = [r['component'] for r in deployment['resources'].values()]
        self.assertIn('big_widget', components)
        self.assertIn('small_widget', components)


class TestDeploymentSettings(unittest.TestCase):

    def test_get_setting(self):
        """Test the get_setting function"""
        deployment = Deployment(yaml_to_dict("""
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - compute: foo
                        vendor: bar
                    common:
                      credentials:
                      - password: secret
                      constraints:
                      - region: place
                blueprint:
                  services:
                    web:
                      component:
                      type: compute
                  options:
                    my_server_type:
                      constrains:
                      - type: compute
                        service: web
                        setting: os
                settings:
                    keys:
                        environment:
                            private: "this is a private key"
                            public: "this is a public key"
                            cert: "certificate data"
                        count: 3
                    setting_1: "Single value"
                    setting_2:
                        compound: "value"
                inputs:
                  blueprint:
                    domain: example.com
                    my_server_type: Ubuntu 11.10  # an option with constraint
                  providers:
                    base:
                      compute:
                        memory: 4 Gb
                  services:
                    web:
                      compute:
                        case-whitespace-test: 512mb
                        gigabyte-test: 8 gigabytes
                        mb-test: 512 Mb
                        memory: 2 Gb
                        number-only-test: 512
            """))
        cases = [{
                  'case': "Path in settings",
                  'name': "keys/environment/public",
                  'expected': "this is a public key"
                },
                {
                  'case': "Path in settings 2",
                  'name': "keys/count",
                  'expected': 3
                },
                {
                  'case': "Path in settings 3",
                  'name': "setting_1",
                  'expected': "Single value"
                },
                {
                  'case': "Not in settings path",
                  'name': "keys/bob/foo",
                  'expected': None
                },
                {
                  'case': "Partial path in settings",
                  'name': "keys/environment/public/his",
                  'expected': None
                },
                {
                  'case': "Path in settings 4",
                  'name': "setting_2/compound",
                  'expected': "value"
                },
                {
                'case': "Set in blueprint/inputs",
                'name': "domain",
                'expected': "example.com",
                }, {
                'case': "Set in blueprint/inputs with service/provider scope",
                'name': "os",
                'service': "web",
                'expected': "Ubuntu 11.10",
                }, {
                'case': "Set in blueprint/inputs with no service scope",
                'name': "os",
                'expected': None,
                }, {
                'case': "Set in blueprint/service under provider/resource",
                'name': "memory",
                'service': "web",
                'type': 'compute',
                'expected': "2 Gb",
                }, {
                'case': "Set in environments/providers/common",
                'name': "region",
                'provider': "common",
                'service': "constraints",
                'expected': "place",
                },  {
                'case': "Set in blueprint/providers",
                'name': "memory",
                'type': 'compute',
                'expected': "4 Gb",
                'add': """ - FIXME: broken without env providers
                    environment:
                      name: environment
                      providers:
                        base:
                          provides:
                          - compute: foo
                          vendor: test""",
                }
            ]

        PROVIDER_CLASSES['test.base'] = ProviderBase
        for test in cases[:-1]:  # TODO: last case broken without env providers
            value = deployment.get_setting(test['name'],
                    service_name=test.get('service'),
                    provider_key=test.get('provider'),
                    resource_type=test.get('type'))
            self.assertEquals(value, test['expected'], test['case'])

    def test_get_input_provider_option(self):
        deployment = Deployment(yaml_to_dict("""
                environment:
                  providers:
                    base
                blueprint:
                  services:
                    web:
                  options:
                    my_server_type:
                      constrains:
                      - resource_type: compute
                        service: web
                        setting: os
                inputs:
                  blueprint:
                    domain: example.com
                    my_server_type: Ubuntu 11.10
                  providers:
                    base:
                      compute:
                        os: X
                  services:
                    web:
                      compute:
                        case-whitespace-test: 512mb
                        gigabyte-test: 8 gigabytes
                        mb-test: 512 Mb
                        memory: 2 Gb
                        number-only-test: 512
            """))
        fxn = deployment._get_input_provider_option
        self.assertEqual(fxn('os', 'base', resource_type='compute'), 'X')

    def test_get_bad_options(self):
        self.assertRaises(CheckmateValidationException, Deployment,
                yaml_to_dict("""
                environment:
                  providers:
                    base
                blueprint:
                  services:
                    web:
                  options:
                    my_server_type:
                      constrains:
                      - resource_type: compute
                        service: web
                        setting: os
                inputs:
                  blueprint:
                    domain: example.com
                    my_server_type: Ubuntu 11.10
                  providers:
                    base:
                      compute:
                        # Missing!
                  services:
                    web:
                      compute:
                        case-whitespace-test: 512mb
                        gigabyte-test: 8 gigabytes
                        mb-test: 512 Mb
                        memory: 2 Gb
                        number-only-test: 512
            """))

class TestDeploymentCounts(unittest.TestCase):
    """ Tests getting deployment numbers """
    
    def __init__(self, methodName="runTest"):
        self._mox = mox.Mox()
        self._deploymets = {}
        unittest.TestCase.__init__(self, methodName)
        
    def setUp(self):
        self._deploymets = json.load(open(os.path.join(os.path.dirname(__file__),'data', 'deployments.json')))
        self._mox.StubOutWithMock(checkmate.deployments, "db")
        bottle.request.bind({})
        bottle.request.context = Context()
        bottle.request.context.tenant = None
        unittest.TestCase.setUp(self)
        
    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)
    
    def test_get_count_all(self):
        checkmate.deployments.db.get_deployments(tenant_id=mox.IgnoreArg()).AndReturn(self._deploymets)
        self._mox.ReplayAll()
        self._assert_good_count(json.loads(get_deployments_count()), 3)
    
    def test_get_count_tenant(self):
        # remove the extra deployment
        self._deploymets.pop("3fgh")
        checkmate.deployments.db.get_deployments(tenant_id="12345").AndReturn(self._deploymets)
        self._mox.ReplayAll()
        self._assert_good_count(json.loads(get_deployments_count(tenant_id="12345")), 2)
        
    def test_get_count_deployment(self):
        checkmate.deployments.db.get_deployments(tenant_id=None).AndReturn(self._deploymets)
        self._mox.ReplayAll()
        self._assert_good_count(json.loads(get_deployments_by_bp_count("blp-123-aabc-efg")), 2)
    
    def test_get_count_deployment_and_tenant(self):
        raw_deployments = self._deploymets.copy()
        raw_deployments.pop("3fgh")
        self._deploymets.pop("2def")
        self._deploymets.pop("1abc")
        checkmate.deployments.db.get_deployments(tenant_id="854673").AndReturn(self._deploymets)
        checkmate.deployments.db.get_deployments(tenant_id="12345").AndReturn(raw_deployments)
        self._mox.ReplayAll()
        self._assert_good_count(json.loads(get_deployments_by_bp_count("blp-123-aabc-efg", tenant_id="854673")), 1)
        self._assert_good_count(json.loads(get_deployments_by_bp_count("blp123avc", tenant_id="12345")), 1)

    def _assert_good_count(self, ret, expected_count):
        self.assertIsNotNone(ret, "No count returned")
        self.assertIn("count", ret, "Return does not contain count")
        self.assertEqual(expected_count, ret.get("count", -1), "Wrong count returned")


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
