#!/usr/bin/env python
import copy
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
import mox
import checkmate
import bottle
import json
from celery.app.task import Context
import os
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import keys
from checkmate.deployments import (Deployment, plan, get_deployments_count,
                                   get_deployments_by_bp_count, _deploy, Plan,
                                   generate_keys)
from checkmate.exceptions import (CheckmateValidationException,
                                  CheckmateException)
from checkmate.providers import base
from checkmate.providers.base import ProviderBase
from checkmate.middleware import RequestContext
from checkmate.utils import yaml_to_dict, dict_to_yaml

os.environ['CHECKMATE_DOMAIN'] = 'checkmate.local'


class TestDeployments(unittest.TestCase):
    def test_schema(self):
        """Test the schema validates a deployment with all possible fields"""
        deployment = {
                'id': 'test',
                'name': 'test',
                'inputs': {},
                'includes': {},
                'resources': {},
                'workflow': "abcdef",
                'status': "NEW",
                'created': "yesterday",
                'tenantId': "T1000",
                'blueprint': {
                    'name': 'test bp',
                    },
                'environment': {
                    'name': 'environment',
                    'providers': {},
                    },
                }
        valid = Deployment(deployment)
        self.assertDictEqual(valid._data, deployment)

    def test_schema_negative(self):
        """Test the schema validates a deployment with bad fields"""
        deployment = {
                'nope': None
                }
        self.assertRaises(CheckmateValidationException, Deployment, deployment)

    def test_key_generation_all(self):
        """Test that key generation works"""
        deployment = Deployment({
                'id': 'test',
                'name': 'test',
                })
        generate_keys(deployment)
        self.assertIn('resources', deployment)
        self.assertIn('deployment-keys', deployment['resources'])
        self.assertItemsEqual(['instance', 'type'],
                             deployment['resources']['deployment-keys'].keys())
        self.assertItemsEqual(['private_key', 'public_key', 'public_key_ssh'],
                             deployment['resources']['deployment-keys']\
                             ['instance'].keys())
        self.assertEqual(deployment['resources']['deployment-keys']['type'],
                         'key-pair')

    def test_key_generation_public(self):
        """Test that key generation works if a private key is supplied"""
        private, public = keys.generate_key_pair()
        deployment = Deployment({
                'id': 'test',
                'name': 'test',
                'resources': {
                    'deployment-keys': {
                        'instance': {
                            'private_key': private['PEM']
                        }
                    }
                }
                })
        generate_keys(deployment)
        self.assertItemsEqual(['instance', 'type'],
                             deployment['resources']['deployment-keys'].keys())
        self.assertItemsEqual(['private_key', 'public_key', 'public_key_ssh'],
                             deployment['resources']['deployment-keys']\
                             ['instance'].keys())
        self.assertEqual(deployment['resources']['deployment-keys']['type'],
                         'key-pair')

    def test_key_generation_and_settings_sync(self):
        """Test that key generation refreshes settings"""
        private, public = keys.generate_key_pair()
        deployment = Deployment({
                'id': 'test',
                'name': 'test',
                'resources': {
                    'deployment-keys': {
                        'instance': {
                            'private_key': private['PEM']
                        }
                    }
                }
                })
        # Should pick up keys
        settings = deployment.settings()
        self.assertDictEqual(settings.get('keys', {}).get('deployment', {}),
                             {'private_key': private['PEM']})
        generate_keys(deployment)
        settings = deployment.settings()
        self.assertItemsEqual(['private_key', 'public_key', 'public_key_ssh'],
                             settings['keys']['deployment'].keys())


class TestDeploymentParser(unittest.TestCase):
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
        self.assertDictEqual(original, parsed._data)

    def test_constrain_format_handling(self):
        cases = {
                    'full': {
                              'parse': [{
                                            'setting': 'my setting',
                                            'service': 'web',
                                            'type': 'compute'
                                        }],
                              'expected': [{
                                            'setting': 'my setting',
                                            'service': 'web',
                                            'type': 'compute'
                                           }],
                            },
                    'key/value': {
                                    'parse': {
                                                  'version': '1.2.3',
                                                  'create': True,
                                             },
                                    'expected': [{
                                                    'setting': 'version',
                                                    'value': '1.2.3'
                                                 }, {
                                                    'setting': 'create',
                                                    'value': True
                                                 }]
                                  },
                    'option': {
                              'parse': [{
                                            'setting': '/resources/id/value'
                                        }],
                              'expected': [{
                                            'setting': '/resources/id/value'
                                           }],
                            },
                }
        for name, case in cases.iteritems():
            parsed = Deployment.parse_constraints(case['parse'])
            expected = case['expected']
            for constraint in expected:
                self.assertIn(constraint, parsed)
                parsed.remove(constraint)
            self.assertEqual(parsed, [], msg="Parsed has extra constraints: %s"
                             % parsed)


class TestDeploymentDeployer(unittest.TestCase):
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


class TestDeploymentResourceGenerator(unittest.TestCase):
    def test_component_resource_generator(self):
        """Test the parser generates the right number of resources"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    front:
                      component:
                        id: start_widget
                      relations:
                        middle: foo
                    middle:
                      component:
                        id: link_widget
                      relations:
                        back: bar
                    back:
                      component:
                        id: big_widget
                    side:
                      component:
                        id: big_widget
                        constraints:
                        - count: 2
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      vendor: test
                      catalog:
                        widget:
                          start_widget:
                            is: widget
                            requires:
                            - widget: foo
                          link_widget:
                            is: widget
                            provides:
                            - widget: foo
                            requires:
                            - widget: bar
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
                inputs:
                  services:
                    middle:
                      widget:
                        count: 4
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        plan(deployment, RequestContext())
        resources = deployment['resources'].values()
        self.assertEqual(len([r for r in resources
                              if r.get('service') == 'front']), 1)
        self.assertEqual(len([r for r in resources
                              if r.get('service') == 'middle']), 4,
                         msg="Expecting inputs to generate 4 resources")
        self.assertEqual(len([r for r in resources
                              if r.get('service') == 'back']), 1)
        self.assertEqual(len([r for r in resources
                              if r.get('service') == 'side']), 2,
                         msg="Expecting constraint to generate 2 resources")

    def test_static_resource_generator(self):
        """Test the parser generates the right number of static resources"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    "single":
                      component:
                        type: widget
                  resources:
                    "myResource":  # provided by a provider
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
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        parsed = plan(deployment, RequestContext())
        resources = parsed['resources']
        self.assertIn("myResource", resources)
        expected = {'component': 'small_widget',
                    'dns-name': 'CM-test-sharedmyResource.checkmate.local',
                    'index': 'myResource',
                    'instance': {},
                    'provider': 'base',
                    'type': 'widget'}
        self.assertDictEqual(resources['myResource'], expected)

    def test_providerless_static_resource_generator(self):
        """Test the parser generates providerless static resources"""
        private, public = keys.generate_key_pair()
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  resources:
                    "myUser":  # providerless
                      type: user
                      name: test_user
                      password: secret
                    "anyKey":
                      type: key-pair
                    "myKey":
                      type: key-pair
                      private_key: |
                        %s
                environment:
                  name: environment
                  providers: {}
            """ % "\n                        ".join(private['PEM'].split(
                "\n"))))
        parsed = plan(deployment, RequestContext())
        resources = parsed['resources']

        # User
        self.assertIn("myUser", resources)
        expected = {'index': 'myUser',
                    'type': 'user',
                    'instance': {
                        'name': 'test_user',
                        'password': 'secret',
                        }
                    }
        # Make sure hash value was generated
        self.assertIn("hash", resources['myUser']['instance'])
        # Pull hash value into expected
        expected['instance']['hash'] = resources['myUser']['instance']['hash']
        self.assertDictEqual(resources['myUser'], expected)

        # Key pair
        self.assertIn("myKey", resources)
        self.assertItemsEqual(resources['myKey']['instance'].keys(),
                            ["private_key", "public_key", "public_key_ssh"])
        self.assertEqual(resources['myKey']['instance']['private_key'].strip(
                         '\n'),
                         private['PEM'])

        self.assertIn("anyKey", resources)
        self.assertItemsEqual(resources['anyKey']['instance'].keys(),
                            ["private_key", "public_key", "public_key_ssh"])


class TestDeploymentRelationParser(unittest.TestCase):
    def test_blueprint_relation_parser(self):
        """Test that parser handles relations listed in blueprints"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    balanced:
                      component:
                        id: balancer_widget
                      relations:
                        front: foo  # short syntax
                    front:
                      component:
                        resource_type: widget
                        interface: foo
                        constraints:
                        - count: 2
                      relations:
                        "allyourbase":  # long syntax
                          service: back
                          interface: bar
                    back:
                      component:
                        type: widget
                        interface: bar
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          balancer_widget:
                            is: widget
                            requires:
                            - widget: foo
                          small_widget:
                            is: widget
                            requires:
                            - widget: bar
                            provides:
                            - widget: foo
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        parsed = plan(deployment, RequestContext())
        expected_connections = {
                                  'balanced-front': {'interface': 'foo'},
                                  'allyourbase': {'interface': 'bar'},
                                }
        self.assertDictEqual(parsed['resources']['connections'],
                             expected_connections)


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
        base.PROVIDER_CLASSES['test.base'] = ProviderBase
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
        base.PROVIDER_CLASSES['test.base'] = ProviderBase
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
        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        components = [r['component'] for r in deployment['resources'].values()]
        self.assertIn('big_widget', components)
        self.assertIn('small_widget', components)

    def test_component_find_with_role(self):
        """ Make sure roles match in component and provider """
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      component:
                        role: master
                        type: widget
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
                            roles:
                            - web
                            - master
                            is: widget
                            provides:
                            - widget: foo
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
                            roles:
                            - web
            """))
        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        self.assertEquals(deployment['resources'].values()[0]['component'],
                'small_widget')



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
                      constraints:
                      - type: widget
                        setting: size
                        value: big
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
                      constraints:
                      - count: 2
                    wordpress:  #FIXME: remove backwards compatibility
                      component:
                        type: compute
                        constraints:
                          "wordpress/version": 3.1.4
                          "wordpress/create": true
                  options:
                    my_server_type:
                      constrains:
                      - type: compute
                        service: web
                        setting: os
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
        deployment._data.update(yaml_to_dict("""
                    keys:
                        environment:
                            private: "this is a private key"
                            public: "this is a public key"
                            cert: "certificate data"
                        count: 3
                    setting_1: "Single value"
                    setting_2:
                        compound: "value"
                        """))
        cases = [{
                    'case': "Path in settings",
                    'name': "keys/environment/public",
                    'expected': "this is a public key"
                }, {
                    'case': "Path in settings 2",
                    'name': "keys/count",
                    'expected': 3
                }, {
                    'case': "Path in settings 3",
                    'name': "setting_1",
                    'expected': "Single value"
                }, {
                    'case': "Not in settings path",
                    'name': "keys/bob/foo",
                    'expected': None
                }, {
                    'case': "Partial path in settings",
                    'name': "keys/environment/public/his",
                    'expected': None
                }, {
                    'case': "Path in settings 4",
                    'name': "setting_2/compound",
                    'expected': "value"
                }, {
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
                    'provider': "base",
                    'expected': "place",
                }, {
                    'case': "Set in environments/providers/...",
                    'name': "size",
                    'provider': "base",
                    'resource_type': "widget",
                    'expected': "big",
                },  {
                    'case': "Provider setting is used even with service param",
                    'name': "size",
                    'provider': "base",
                    'service': 'web',
                    'resource_type': "widget",
                    'expected': "big",
                },  {
                    'case': "Set in blueprint/service as constraint",
                    'name': "count",
                    'type': 'compute',
                    'service': 'web',
                    'expected': 2,
                }, {  # FIXME: remove backwards compatibility
                    'case': "Constraint as key/value pair",
                    'name': "wordpress/version",
                    'type': 'compute',
                    'provider': "base",
                    'service': 'wordpress',
                    'expected': "3.1.4",
                }, {  # FIXME: remove backwards compatibility
                    'case': "Constraint with multiple key/value pairs",
                    'name': "wordpress/create",
                    'type': 'compute',
                    'provider': "base",
                    'service': 'wordpress',
                    'expected': True,
                },  {
                    'case': "Set in blueprint/providers",
                    'name': "memory",
                    'type': 'compute',
                    'expected': "4 Gb",
                }
            ]

        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        for test in cases[:-1]:  # TODO: last case broken without env providers
            value = deployment.get_setting(test['name'],
                    service_name=test.get('service'),
                    provider_key=test.get('provider'),
                    resource_type=test.get('type'))
            self.assertEquals(value, test['expected'], test['case'])
            LOG.debug("Test '%s' success=%s" % (test['case'],
                                                 value == test['expected']))

    def test_get_setting_static(self):
        """Test the get_setting function used with static resources"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                inputs:
                  blueprint:
                    prefix: bar
                blueprint:
                  name: test bp
                  services:
                    "single":
                      component:
                        id: small_widget
                  resources:
                    "myResource":  # provided by a provider
                      type: widget
                    "myUser":
                      type: user
                  options:
                    prefix:
                      constrains:
                      - setting: resources/myUser/name
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
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        parsed = plan(deployment, RequestContext())
        resources = parsed['resources']
        self.assertIn("myResource", resources)
        self.assertIn("myUser", resources)
        self.assertEqual(resources['myUser']['instance']['name'], 'bar')
        self.assertEqual(deployment.get_setting('resources/myUser/name'),
                         'bar')

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

    def test_get_static_resource_constraint(self):
        deployment = Deployment(yaml_to_dict("""
                id: '1'
                blueprint:
                  services:
                    "single":
                      component:
                        id: big_widget
                  resources:
                    "myUser":
                      type: user
                      name: john
                      constrains:
                      - service: single
                        setting: username
                        attribute: name
                      - setting: password
                        type: widget
                environment:
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
            """))
        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        planned = plan(deployment, RequestContext())
        # Use service and type
        value = planned.get_setting('username', service_name='single',
                                    resource_type='widget')
        self.assertEqual(value, 'john')
        # Use only type
        value = planned.get_setting('password', resource_type='widget')
        self.assertGreater(len(value), 0)

    def test_handle_missing_options(self):
        """Validate missing options handled correctly"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                environment:
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          bar: {}
                blueprint:
                  services:
                    web:
                      component:
                        id: bar
                  options:
                    foo:
                      required: true
                inputs: {}
            """))
        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        self.assertRaises(CheckmateValidationException, plan, deployment,
            RequestContext())


class TestDeploymentCounts(unittest.TestCase):
    """ Tests getting deployment numbers """

    def __init__(self, methodName="runTest"):
        self._mox = mox.Mox()
        self._deploymets = {}
        unittest.TestCase.__init__(self, methodName)

    def setUp(self):
        self._deploymets = json.load(open(os.path.join(
                os.path.dirname(__file__), 'data', 'deployments.json')))
        self._mox.StubOutWithMock(checkmate.deployments, "DB")
        bottle.request.bind({})
        bottle.request.context = Context()
        bottle.request.context.tenant = None
        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_get_count_all(self):
        checkmate.deployments.DB.get_deployments(tenant_id=mox.IgnoreArg()
                                                 ).AndReturn(self._deploymets)
        self._mox.ReplayAll()
        self._assert_good_count(json.loads(get_deployments_count()), 3)

    def test_get_count_tenant(self):
        # remove the extra deployment
        self._deploymets.pop("3fgh")
        checkmate.deployments.DB.get_deployments(tenant_id="12345").AndReturn(
                self._deploymets)
        self._mox.ReplayAll()
        self._assert_good_count(json.loads(get_deployments_count(
                tenant_id="12345")), 2)

    def test_get_count_deployment(self):
        checkmate.deployments.DB.get_deployments(tenant_id=None).AndReturn(
                self._deploymets)
        self._mox.ReplayAll()
        self._assert_good_count(json.loads(get_deployments_by_bp_count(
                "blp-123-aabc-efg")), 2)

    def test_get_count_deployment_and_tenant(self):
        raw_deployments = self._deploymets.copy()
        raw_deployments.pop("3fgh")
        self._deploymets.pop("2def")
        self._deploymets.pop("1abc")
        checkmate.deployments.DB.get_deployments(tenant_id="854673"
                                                 ).AndReturn(self._deploymets)
        checkmate.deployments.DB.get_deployments(tenant_id="12345"
                                                 ).AndReturn(raw_deployments)
        self._mox.ReplayAll()
        self._assert_good_count(json.loads(get_deployments_by_bp_count(
                "blp-123-aabc-efg", tenant_id="854673")), 1)
        self._assert_good_count(json.loads(get_deployments_by_bp_count(
                "blp123avc", tenant_id="12345")), 1)

    def _assert_good_count(self, ret, expected_count):
        self.assertIsNotNone(ret, "No count returned")
        self.assertIn("count", ret, "Return does not contain count")
        self.assertEqual(expected_count, ret.get("count", -1),
                         "Wrong count returned")


class TestDeploymentPlanning(unittest.TestCase):
    """Tests the Plan() class and its deployment planning logic"""
    def test_find_components_positive(self):
        """Test the Plan() class can find components"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    by_id:
                      component:
                        id: widget_with_id
                    by_interface:
                      component:
                        interface: foo
                    by_type:
                      component:
                        resource_type: gadget
                    by_type_and_interface:
                      component:
                        interface: bar
                        resource_type: gadget
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          widget_with_id:
                            id: widget_with_id
                            is: widget
                          foo_widget:
                            is: widget
                            provides:
                            - widget: foo
                    gbase:
                      vendor: test
                      catalog:
                        gadget:
                          bar_gadget:
                            is: gadget
                            provides:
                            - gadget: bar
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        base.PROVIDER_CLASSES['test.gbase'] = ProviderBase

        planner = Plan(deployment)
        planner.plan(RequestContext())

        services = planner['services']
        self.assertIn('by_id', services)
        self.assertIn('by_interface', services)
        self.assertIn('by_type', services)
        self.assertIn('by_type_and_interface', services)
        self.assertEqual(len(services), 4)

        component = services['by_id']['component']
        self.assertEqual(component['id'], 'widget_with_id')
        self.assertEqual(component['provider'], 'checkmate.base')
        self.assertEqual(component['provider-key'], 'base')

        component = services['by_interface']['component']
        self.assertEqual(component['id'], 'foo_widget')
        self.assertEqual(component['provider'], 'checkmate.base')
        self.assertEqual(component['provider-key'], 'base')

        component = services['by_type']['component']
        self.assertEqual(component['id'], 'bar_gadget')
        self.assertEqual(component['provider'], 'checkmate.base')
        self.assertEqual(component['provider-key'], 'gbase')

        component = services['by_type_and_interface']['component']
        self.assertEqual(component['id'], 'bar_gadget')
        self.assertEqual(component['provider'], 'checkmate.base')
        self.assertEqual(component['provider-key'], 'gbase')

    def test_find_components_not_found(self):
        """Test the Plan() class fails missing components"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    by_id:
                      component:
                        id: widget_with_id  # id does not exist in catalog
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          foo_widget:
                            is: widget
                            provides:
                            - widget: foo
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        planner = Plan(deployment)
        self.assertRaises(CheckmateException, planner.plan, RequestContext())

    def test_find_components_mismatch(self):
        """Test the Plan() class skips mismatched components"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    by_id:
                      component:
                        id: widget_with_id
                        resource_type: gadget  # only widget in catalog
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          widget_with_id:
                            id: widget_with_id
                            is: widget
                            provides:
                            - widget: foo
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        planner = Plan(deployment)
        self.assertRaises(CheckmateException, planner.plan, RequestContext())

    def test_resolve_relations(self):
        """Test the Plan() class can parse relations"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    main:
                      component:
                        id: main_widget
                      relations:
                        explicit: foo
                    explicit:
                      component:
                        id: foo_widget
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          main_widget:
                            is: widget
                            requires:
                            - widget: foo
                          foo_widget:
                            is: widget
                            provides:
                            - widget: foo
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        planner = Plan(deployment)
        planner.plan(RequestContext())
        services = planner['services']
        component = services['main']['component']
        widget_foo = component['requires']['widget:foo']
        expected = {'interface': 'foo',
                    'resource_type': 'widget',
                    'satisfied-by': {
                        'name': 'main-explicit',
                        'relation-key': 'main-explicit',
                        'service': 'explicit',
                        'component': 'foo_widget',
                        'target': 'widget:foo',
                        }
                    }
        self.assertDictEqual(widget_foo, expected)

    #FIXME: re-enable this when done with v0.2
    @unittest.skip("Not compatible with v0.2 relations")
    def test_resolve_relations_negative(self):
        """Test the Plan() class detects unused/duplicate relations"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    main:
                      component:
                        id: main_widget
                      relations:
                        explicit: foo
                        "duplicate-provides":
                          service: named
                          interface: foo
                    explicit:
                      component:
                        id: foo_widget
                    named:
                      component:
                        id: foo_widget
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          main_widget:
                            is: widget
                            requires:
                            - widget: foo
                          foo_widget:
                            is: widget
                            provides:
                            - widget: foo
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        planner = Plan(deployment)
        self.assertRaises(CheckmateValidationException, planner.plan,
                          RequestContext())

    def test_resolve_requirements(self):
        """Test the Plan() class can resolve all requirements"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    main:
                      component:
                        id: main_widget
                      relations:
                        explicit: foo
                    explicit:
                      component:
                        id: foo_widget
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          main_widget:
                            is: widget
                            requires:
                            - widget: foo
                            - host: bar
                          foo_widget:
                            is: widget
                            provides:
                            - widget: foo
                            requires:
                            - host: linux
                          bar_widget:
                            is: widget
                            provides:
                            - widget: bar
                            requires:
                            - gadget: mysql
                          bar_gadget:
                            is: gadget
                            provides:
                            - gadget: mysql
                          linux_instance:
                            is: compute
                            provides:
                            - compute: linux
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        planner = Plan(deployment)
        planner.plan(RequestContext())
        services = planner['services']

        component = services['main']['component']
        widget_foo = component['requires']['widget:foo']
        expected = {'interface': 'foo',
                    'resource_type': 'widget',
                    'satisfied-by': {
                        'name': 'main-explicit',
                        'relation-key': 'main-explicit',
                        'service': 'explicit',
                        'component': 'foo_widget',
                        'target': 'widget:foo',
                        }
                    }
        self.assertDictEqual(widget_foo, expected)

        host_bar = component['requires']['host:bar']
        expected = {'interface': 'bar',
                    'relation': 'host',
                    'satisfied-by': {
                        'name': 'host:bar',
                        'service': 'main',
                        'component': 'bar_widget',
                        'target': 'widget:bar',
                        }
                    }
        self.assertDictEqual(host_bar, expected)

        self.assertIn('gadget:mysql', services['main']['extra-components'])
        recursive = services['main']['extra-components']['host:bar']
        expected = {'interface': 'mysql',
                    'resource_type': 'gadget',
                    'satisfied-by': {
                        'name': 'gadget:mysql',
                        'service': 'main',
                        'component': 'bar_gadget',
                        'target': 'gadget:mysql',
                        }
                    }
        self.assertDictEqual(recursive['requires']['gadget:mysql'], expected)

        host = planner.resources['3']
        self.assertNotIn('relations', host, msg="Host is not supposed to have "
                                                "any relations but host")

    def test_relation_names(self):
        """Test the Plan() class handles relation naming correctly"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    front:
                      component:
                        id: start_widget
                      relations:
                        middle: foo  # shorthand
                    middle:
                      component:
                        id: link_widget
                      relations:
                        "john":  # long form
                          service: back
                          interface: bar
                    back:
                      component:
                        id: big_widget  # implicit requirement for gadget:mysql
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      vendor: test
                      catalog:
                        widget:
                          start_widget:
                            is: widget
                            requires:
                            - widget: foo
                          link_widget:
                            is: widget
                            provides:
                            - widget: foo
                            requires:
                            - widget: bar
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
                            requires:
                            - gadget: mysql
                          end_gadget:
                            is: gadget
                            provides:
                            - gadget: mysql
                            requires:
                            - host: linux
                          another_end:
                            is: compute
                            provides:
                            - compute: linux
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        plan(deployment, RequestContext())
        resources = deployment['resources']

        expected = yaml_to_dict("""
                  front-middle:       # easy to see this is service-to-service
                    interface: foo
                  gadget:mysql:       # this is within one service
                    interface: mysql
                  john:               # this is explicitely named
                    interface: bar
                                      # 'host' does not exist
            """)
        self.assertDictEqual(resources['connections'], expected)

    def test_relation_v02_features(self):
        """Test the Plan() class handles relation features we used for v0.2"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    main:
                      component:
                        id: main_widget
                      relations:
                        "varnish/master":
                          service: explicit
                          interface: foo
                          attribute: ip
                    explicit:
                      component:
                        id: foo_widget
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        widget:
                          main_widget:
                            is: widget
                            requires:
                            - widget: foo
                            - host: bar
                          foo_widget:
                            is: widget
                            provides:
                            - widget: foo
                          bar_widget:
                            is: widget
                            provides:
                            - widget: bar
                            requires:
                            - gadget: mysql
                          bar_gadget:
                            is: gadget
                            provides:
                            - gadget: mysql
            """))

        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        plan(deployment, RequestContext())
        resources = deployment['resources']

        expected = {'varnish/master': {'interface': 'foo'}}
        self.assertDictEqual(resources['connections'], expected)

        relations = resources['0']['relations']
        self.assertIn('varnish/master', relations)
        self.assertIn('attribute', relations['varnish/master'])
        self.assertEqual(relations['varnish/master']['attribute'], 'ip')


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
