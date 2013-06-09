# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232,E1101,E1103
import copy
import json
import logging
import os
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()

from celery.app.task import Context
import bottle
from bottle import HTTPError
import mox
from mox import IgnoreArg, ContainsKeyValue
from webtest import TestApp

import checkmate
from checkmate import deployments, keys, test
from checkmate.common import tasks as common_tasks
from checkmate.deployment import (
    Deployment,
    generate_keys,
)
from checkmate.deployments import (
    Manager,
    Router,
    delete_deployment_task,
    update_all_provider_resources,
    resource_postback,
)
from checkmate.exceptions import (
    CheckmateValidationException,
    CheckmateException,
    CheckmateDoesNotExist,
    CheckmateBadState,
)
from checkmate.inputs import Input
from checkmate.providers import base
from checkmate.providers.base import ProviderBase
from checkmate.middleware import RequestContext
from checkmate.utils import yaml_to_dict

LOG = logging.getLogger(__name__)
os.environ['CHECKMATE_DOMAIN'] = 'checkmate.local'


class TestDeployments(unittest.TestCase):
    def test_key_generation_all(self):
        """Test that key generation works"""
        deployment = Deployment({
            'id': 'test',
            'name': 'test',
        })
        generate_keys(deployment)
        self.assertIn('resources', deployment)
        self.assertIn('deployment-keys', deployment['resources'])
        keys_resource = deployment['resources']['deployment-keys']
        self.assertItemsEqual(['instance', 'type'], keys_resource.keys())
        self.assertItemsEqual(['private_key', 'public_key', 'public_key_ssh'],
                              keys_resource['instance'].keys())
        self.assertEqual(keys_resource['type'], 'key-pair')

    def test_key_generation_public(self):
        """Test that key generation works if a private key is supplied"""
        private, _ = keys.generate_key_pair()
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
        keys_resource = deployment['resources']['deployment-keys']
        self.assertItemsEqual(['instance', 'type'], keys_resource.keys())
        self.assertItemsEqual(['private_key', 'public_key', 'public_key_ssh'],
                              keys_resource['instance'].keys())
        self.assertEqual(keys_resource['type'], 'key-pair')

    def test_key_generation_and_settings_sync(self):
        """Test that key generation refreshes settings"""
        private, _ = keys.generate_key_pair()
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
            'operation': {
                'complete': 0,
                'estimated-duration': 0,
                'tasks': 3
            },
            'plan': {'services': {}},
            'environment': {
                'name': 'environment',
                'providers': {},
            },
        }
        original = copy.copy(deployment)
        parsed = Manager.plan(Deployment(deployment),
                              RequestContext())
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
        for _, case in cases.iteritems():
            parsed = Deployment.parse_constraints(case['parse'])
            expected = case['expected']
            for constraint in expected:
                self.assertIn(constraint, parsed)
                parsed.remove(constraint)
            self.assertEqual(parsed, [], msg="Parsed has extra constraints: %s"
                             % parsed)


class TestDeploymentDeployer(unittest.TestCase):
    def setUp(self):
        self._mox = mox.Mox()

    def tearDown(self):
        self._mox.UnsetStubs()

    def test_deployer(self):
        """Test the deployer works on a minimal deployment"""
        db = self._mox.CreateMockAnything()
        manager = Manager({'default': db})
        db.save_workflow(IgnoreArg(), IgnoreArg(), IgnoreArg(),
                         tenant_id=IgnoreArg()).AndReturn(True)
        db.save_deployment(
            IgnoreArg(), IgnoreArg(), IgnoreArg(),
            tenant_id=IgnoreArg(), partial=False
        ).AndReturn(True)

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
        self._mox.ReplayAll()
        parsed = manager.plan(Deployment(deployment), RequestContext())
        operation = manager.deploy(parsed, RequestContext())
        self._mox.VerifyAll()
        expected = {
            'status': 'IN PROGRESS',
            'tasks': 2,
            'complete': 0,
            'estimated-duration': 0,
            'link': '/T1000/workflows/test',
            'last-change': None,
            'type': 'BUILD',
        }
        operation['last-change'] = None  # skip comparing/mocking times

        self.assertDictEqual(expected, operation)
        self.assertEqual(parsed['status'], "PLANNED")


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

        Manager.plan(deployment, RequestContext())
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

        resource_count = 0
        #test resource dns-names without a deployment name
        for k, resource in deployment['resources'].iteritems():
            if k != "connections":
                regex = r"%s\d+.checkmate.local" % resource['service']
                self.assertRegexpMatches(resource['dns-name'], regex)
                resource_count += 1
        self.assertEqual(resource_count, 8)

    def test_static_resource_generator(self):
        """Test the parser generates the right number of static resources"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                name: test deplo yment\n
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

        parsed = Manager.plan(deployment, RequestContext())
        resources = parsed['resources']
        self.assertIn("myResource", resources)
        expected = {'component': 'small_widget',
                    #dns-name with a deployment name
                    'dns-name': 'sharedwidget.checkmate.local',
                    'index': 'myResource',
                    'instance': {},
                    'provider': 'base',
                    'type': 'widget'}
        self.assertDictEqual(resources['myResource'], expected)

    def test_providerless_static_resource_generator(self):
        """Test the parser generates providerless static resources"""
        private, _ = keys.generate_key_pair()
        deployment = Deployment(yaml_to_dict("""
                id: test
                name: test_deployment
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
        parsed = Manager.plan(deployment, RequestContext())
        resources = parsed['resources']

        # User
        self.assertIn("myUser", resources)
        expected = {
            'index': 'myUser',
            'type': 'user',
            'instance': {
                'name': 'test_user',
                'password': 'secret',
            }
        }
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

        parsed = Manager.plan(deployment, RequestContext())
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
        Manager.plan(deployment, RequestContext())
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
        Manager.plan(deployment, RequestContext())
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
        Manager.plan(deployment, RequestContext())
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
        Manager.plan(deployment, RequestContext())
        self.assertEquals(deployment['resources'].values()[0]['component'],
                          'small_widget')


class TestDeploymentSettings(unittest.TestCase):

    def test_get_setting(self):
        """Test the get_setting function"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                environment:
                  name: environment
                  providers:
                    base:
                      vendor: test
                      catalog:
                        compute:
                          dummy_server:
                            is: compute
                            provides:
                            - compute: foo
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
                        - "wordpress/version": 3.1.4
                        - "wordpress/create": true
                      relations:
                        web:
                          service: web
                          attributes:
                            algorithm: round-robin
                  options:
                    my_server_type:
                      constrains:
                      - type: compute
                        service: web
                        setting: os
                    my_url:
                      type: url
                      default: 'git://fqdn:1000/path'
                      constrains:
                      - type: compute
                        service: web
                        setting: protocol
                        attribute: protocol
                      - type: compute
                        service: master
                        setting: protocol
                        attribute: scheme
                      - type: compute
                        service: web
                        setting: domain
                        attribute: hostname
                  resources:
                    "my keys":
                      type: key-pair
                      constrains:
                      - setting: server_key
                        resource_type: compute
                        service: web
                        attribute: private_key
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
            'type': "widget",
            'expected': "big",
        },  {
            'case': "Provider setting is used even with service param",
            'name': "size",
            'provider': "base",
            'service': 'web',
            'type': "widget",
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
        }, {
            'case': "Constrains reading url scheme",
            'name': "protocol",
            'type': 'compute',
            'provider': "base",
            'service': 'master',
            'expected': "git",
        }, {
            'case': "Url protocol is aliased to scheme",
            'name': "protocol",
            'type': 'compute',
            'provider': "base",
            'service': 'web',
            'expected': "git",
        }, {
            'case': "Constrains reading url hostname",
            'name': "domain",
            'type': 'compute',
            'provider': "base",
            'service': 'web',
            'expected': "fqdn",
        },  {
            'case': "Relation setting is used when relation passed in",
            'name': "algorithm",
            'type': 'compute',
            'relation': 'web',
            'service': 'wordpress',
            'expected': "round-robin",
        },  {
            'case': "Set in blueprint/providers",
            'name': "memory",
            'type': 'compute',
            'expected': "4 Gb",
        },
        ]

        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        parsed = Manager.plan(deployment, RequestContext())
        for test in cases[:-1]:  # TODO: last case broken without env providers
            value = parsed.get_setting(test['name'],
                                       service_name=test.get('service'),
                                       provider_key=test.get('provider'),
                                       resource_type=test.get('type'),
                                       relation=test.get('relation'))
            self.assertEquals(value, test['expected'], msg=test['case'])
            LOG.debug("Test '%s' success=%s", test['case'],
                      value == test['expected'])

        msg = "Coming from static resource constraint"
        value = parsed.get_setting("server_key", service_name="web",
                                   resource_type="compute")
        self.assertIn('-----BEGIN RSA PRIVATE KEY-----\n', value, msg=msg)

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

        parsed = Manager.plan(deployment, RequestContext())
        resources = parsed['resources']
        self.assertIn("myResource", resources)
        self.assertIn("myUser", resources)
        self.assertEqual(resources['myUser']['instance']['name'], 'bar')
        self.assertEqual(deployment.get_setting('resources/myUser/name'),
                         'bar')

    def test_get_false_settings(self):
        """Test the get_setting function when the setting is false"""
        deployment = Deployment(yaml_to_dict("""
            id: '1'
            blueprint:
              services:
                lb:
                  component:
                    interface: http
                    type: load-balancer
                    constraints:
                    - algorithm: false
              options:
                false-but-true-default:
                  default: true
                  type: boolean
                  label: Create DNS records
                  constrains:
                  - service: lb
                    resource_type: load-balancer
                    setting: create_dns
                false-default:
                  default: false
                  type: boolean
                  constrains:
                  - service: lb
                    resource_type: load-balancer
                    setting: dont_create_dns
                string-false:
                  default: "false"
                  type: boolean
                  constrains:
                  - service: lb
                    resource_type: load-balancer
                    setting: string-false
            inputs:
              blueprint:
                false-but-true-default: False
            environment:
              name: environment
              providers:
                base:
                  vendor: test
                  catalog:
                    load-balancer:
                      dummy_lb:
                        provides:
                        - load-balancer: http
        """))
        cases = [{
            'case': "False in inputs",
            'provider': "base",
            'service': 'lb',
            'type': "load-balancer",
            'name': "create_dns",
            'expected': False
        }, {
            'case': "False as a default",
            'service': 'lb',
            'type': "load-balancer",
            'name': "dont_create_dns",
            'expected': False
        }, {
            'case': "String is 'False'",
            'service': 'lb',
            'type': "load-balancer",
            'name': "string-false",
            'expected': "False"
        }
        ]

        base.PROVIDER_CLASSES['test.base'] = ProviderBase
        parsed = Manager.plan(deployment, RequestContext())
        for test in cases[:-1]:  # TODO: last case broken without env providers
            value = parsed.get_setting(test['name'],
                                       service_name=test.get('service'),
                                       provider_key=test.get('provider'),
                                       resource_type=test.get('type'),
                                       relation=test.get('relation'))
            self.assertEquals(value, test['expected'], msg=test['case'])
            LOG.debug("Test '%s' success=%s", test['case'],
                      value == test['expected'])

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
        planned = Manager.plan(deployment, RequestContext())
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
        self.assertRaises(CheckmateValidationException,
                          Manager.plan, deployment,
                          RequestContext())

    def test_objectify(self):
        deployment = Deployment({})
        msg = "Untyped option should remain unchanged"
        self.assertEqual(deployment._objectify({}, 0), 0, msg=msg)

        msg = "Typed, non-object option should remain unchanged"
        self.assertEqual(deployment._objectify({'type': 'string'}, 0), 0,
                         msg=msg)

        msg = "Typed option should return type"
        self.assertIsInstance(deployment._objectify({'type': 'url'},
                                                    'http://fqdn'),
                              Input, msg=msg)

    def test_apply_constraint_attribute(self):
        deployment = yaml_to_dict("""
              id: '1'
              blueprint:
                options:
                  my_option:
                    default: 'thedefaultwidgetvaluegoeshere'
                    constrains:
                    - type: blah
                      service: foo
                      setting: fa
                      attribute: widget""")
        deployment = Deployment(deployment)
        option = deployment['blueprint']['options']['my_option']
        constraint = option['constrains'][0]
        self.assertRaises(CheckmateException, deployment._apply_constraint,
                          "my_option", constraint, option=option,
                          option_key="my_option")


class TestDeploymentScenarios(unittest.TestCase):

    def test_deployment_scenarios(self):
        base.PROVIDER_CLASSES['test.base'] = ProviderBase

        data_dir = os.path.join(os.path.dirname(__file__), '../data')

        # No objects
        path = os.path.join(data_dir, "deployment - none objects.yaml")
        with file(path, 'r') as f:
            content = f.read()
        self.assertRaisesRegexp(CheckmateValidationException, "Blueprint not "
                                "found. Nothing to do.",
                                self.plan_deployment, content)

    @staticmethod
    def plan_deployment(content):
        """ Wrapper for deployment planning """
        deployment = Deployment(yaml_to_dict(content))
        return Manager.plan(deployment, RequestContext())


class TestDeploymentsAPI(unittest.TestCase):
    """Test GET /deployments endpoint"""

    def setUp(self):
        self._mox = mox.Mox()

        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = TestApp(self.filters)

        self.manager = self._mox.CreateMockAnything()
        self.router = deployments.Router(self.root_app, self.manager)

        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def _assert_good_count(self, ret, expected_count):
        self.assertIsNotNone(ret, "No count returned")
        self.assertIn("count", ret, "Return does not contain count")
        self.assertEqual(expected_count, ret.get("count", -1),
                         "Wrong count returned")

    def test_get_count(self):
        self.manager.count(tenant_id="123").AndReturn(3)
        self._mox.ReplayAll()
        res = self.app.get('/123/deployments/count')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 3)


class TestPostDeployments(unittest.TestCase):
    """ Test POST /deployments endpoint """

    def setUp(self):
        self._mox = mox.Mox()

        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.tenant = "T1000"
        self.app = TestApp(self.filters)

        self.manager = self._mox.CreateMockAnything()
        self.router = Router(self.root_app, self.manager)

        self._deployment = {
            'id': '1234',
            'tenantId': 'T1000',
            'environment': {},
            'blueprint': {
                'name': 'Test',
                'services': {}
            }
        }

        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_post_asynchronous(self):
        """ Test that POST /deployments?asynchronous=1 returns a 202 """
        self.manager.save_deployment(IgnoreArg(), api_id='1234',
                                     tenant_id="T1000").AndReturn(None)
        self._mox.StubOutWithMock(checkmate.deployments.router, "tasks")
        tasks = checkmate.deployments.router.tasks
        tasks.process_post_deployment = self._mox.CreateMockAnything()
        tasks.process_post_deployment.delay(IgnoreArg(),
                                            IgnoreArg()).AndReturn(None)

        self._mox.ReplayAll()
        res = self.app.post('/deployments?asynchronous=1',
                            json.dumps(self._deployment),
                            content_type='application/json')
        self.assertEqual(res.status, '202 Accepted')
        self.assertEqual(res.content_type, 'application/json')

    def test_post_synchronous(self):
        """ Test that POST /deployments returns a 202 """
        self.manager.select_driver('1234').AndReturn(self.manager)
        self.manager.save_deployment(self._deployment, IgnoreArg(),
                                     tenant_id="T1000").AndReturn(None)
        self._mox.StubOutWithMock(checkmate.deployments.router, "tasks")
        tasks = checkmate.deployments.router.tasks
        tasks.process_post_deployment(IgnoreArg(), IgnoreArg(),
                                      driver=IgnoreArg()).AndReturn(None)

        self._mox.ReplayAll()
        res = self.app.post('/deployments',
                            json.dumps(self._deployment),
                            content_type='application/json')
        self.assertEqual(res.status, '202 Accepted')
        self.assertEqual(res.content_type, 'application/json')


class TestCloneDeployments(unittest.TestCase):
    """ Test clone_deployment """

    def setUp(self):
        self._mox = mox.Mox()
        self._deployment = {
            'id': '1234',
            'status': 'PLANNED',
            'environment': {},
            'blueprint': {
                'meta-data': {
                    'schema-version': '0.7'
                }
            }
        }

    def tearDown(self):
        self._mox.UnsetStubs()

    def test_clone_deployment_failure_path(self):
        """ Test when deployment status is not 'DELETED', clone
        deployment operation would fail """

        manager = Manager({})
        self._mox.StubOutWithMock(manager, "get_a_deployment")
        manager.get_a_deployment('1234', tenant_id='T1000')\
            .AndReturn(self._deployment)

        self._mox.ReplayAll()
        try:
            manager.clone('1234', {}, tenant_id='T1000')
            self.fail("Expected exception not raised.")
        except CheckmateBadState:
            pass

    def test_clone_deployment_happy_path(self):
        """ clone deployment success """
        self._deployment['status'] = 'DELETED'

        manager = Manager({})
        self._mox.StubOutWithMock(manager, "get_a_deployment")
        manager.get_a_deployment('1234', tenant_id='T1000')\
            .AndReturn(self._deployment)

        context = RequestContext(simulation=False)
        self._mox.StubOutWithMock(manager, "deploy")
        manager.deploy(IgnoreArg(), context)

        manager.get_a_deployment(IgnoreArg(), tenant_id='T1000')\
            .AndReturn({'id': 'NEW'})
        self._mox.ReplayAll()
        manager.clone('1234', context, tenant_id='T1000')
        self._mox.VerifyAll()

    def test_clone_deployment_simulation(self):
        """ clone deployment simulation """
        self._deployment['status'] = 'DELETED'

        manager = Manager({})
        self._mox.StubOutWithMock(manager, "get_a_deployment")
        manager.get_a_deployment('1234', tenant_id='T1000')\
            .AndReturn(self._deployment)

        context = RequestContext(simulation=True)
        self._mox.StubOutWithMock(manager, "deploy")
        manager.deploy(IgnoreArg(), context)

        manager.get_a_deployment(IgnoreArg(), tenant_id='T1000')\
            .AndReturn(self._deployment)

        self._mox.ReplayAll()
        manager.clone('1234', context, tenant_id='T1000')
        self._mox.VerifyAll()


class TestDeleteDeployments(unittest.TestCase):
    """ Test delete_deployment """

    def __init__(self, methodName="runTest"):
        self._mox = mox.Mox()
        unittest.TestCase.__init__(self, methodName)

    def setUp(self):
        bottle.request.bind({})
        bottle.request.context = Context()
        bottle.request.context.tenant = None
        self._deployment = {
            'id': '1234',
            'status': 'PLANNED',
            'environment': {},
            'blueprint': {
                'meta-data': {
                    'schema-version': '0.7'
                }
            }
        }
        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_bad_status(self):
        """ Test when deployment status is invalid for delete """
        manager = self._mox.CreateMockAnything()
        router = Router(bottle.default_app(), manager)
        manager.get_deployment('1234').AndReturn(self._deployment)
        manager.save_deployment('1234', IgnoreArg(), tenant_id=None,
                                partial=False).AndReturn(None)

        self._mox.ReplayAll()
        try:
            router.delete_deployment('1234')
            self.fail("Delete deployment with bad status did not raise "
                      "exception")
        except HTTPError as exc:
            self.assertEqual(400, exc.status)
            self.assertIn("Deployment 1234 cannot be deleted while in status "
                          "PLANNED", exc.output)

    def test_not_found(self):
        """ Test deployment not found """
        manager = self._mox.CreateMockAnything()
        router = Router(bottle.default_app(), manager)
        manager.get_deployment('1234').AndReturn(None)
        self._mox.ReplayAll()
        try:
            router.delete_deployment('1234')
            self.fail("Delete deployment with not found did not raise "
                      "exception")
        except HTTPError as exc:
            self.assertEqual(404, exc.status)
            self.assertIn("No deployment with id 1234", exc.output)

    def test_no_tasks(self):
        """ Test when there are no resource tasks for delete """
        self._deployment['status'] = 'UP'
        db = self._mox.CreateMockAnything()
        manager = Manager({'default': db})
        router = Router(bottle.default_app(), manager)
        self._mox.StubOutWithMock(manager, "get_a_deployment")
        manager.get_deployment('1234').AndReturn(self._deployment)

        self._mox.StubOutWithMock(checkmate.deployments.router, "Plan")
        checkmate.deployments.router.Plan = self._mox.CreateMockAnything()
        mock_plan = self._mox.CreateMockAnything()
        checkmate.deployments.router.Plan.__call__(
            IgnoreArg()).AndReturn(mock_plan)
        mock_plan.plan_delete(IgnoreArg()).AndReturn([])
        self._mox.StubOutWithMock(checkmate.deployments.tasks.
                                  delete_deployment_task, "delay")
        checkmate.deployments.tasks.delete_deployment_task.delay('1234')\
            .AndReturn(True)
        delete_op = {
            'link': '/canvases/1234',
            'type': 'DELETE',
            'status': 'NEW',
            'tasks': 0,
            'complete': 0,
        }
        self._mox.StubOutWithMock(manager, 'save_deployment')
        manager.save_deployment(
            ContainsKeyValue('operation', delete_op),
            api_id='1234',
            tenant_id=None).AndReturn(None)
        self._mox.ReplayAll()
        router.delete_deployment('1234')
        self._mox.VerifyAll()
        self.assertEqual(202, bottle.response.status_code)

    def test_happy_path(self):
        """ When it all goes right """
        self._deployment['status'] = 'UP'

        mock_driver = self._mox.CreateMockAnything()
        manager = Manager({'default': mock_driver})
        router = Router(bottle.default_app(), manager)

        mock_driver.get_deployment(
            '1234', with_secrets=False).AndReturn(self._deployment)
        self._mox.StubOutWithMock(checkmate.deployments, "Plan")
        checkmate.deployments.router.Plan = self._mox.CreateMockAnything()
        mock_plan = self._mox.CreateMockAnything()
        checkmate.deployments.router.Plan.__call__(
            IgnoreArg()).AndReturn(mock_plan)
        mock_delete_step1 = self._mox.CreateMockAnything()
        mock_delete_step2 = self._mox.CreateMockAnything()
        mock_steps = [mock_delete_step1, mock_delete_step2]
        mock_plan.plan_delete(IgnoreArg()).AndReturn(mock_steps)
        self._mox.StubOutWithMock(common_tasks.update_operation, "s")
        mock_subtask = self._mox.CreateMockAnything()
        common_tasks.update_operation.s('1234', status='IN PROGRESS')\
            .AndReturn(mock_subtask)
        mock_subtask.delay().AndReturn(True)
        self._mox.StubOutClassWithMocks(checkmate.deployments.router, "chord")
        mock_chord = checkmate.deployments.router.chord(mock_steps)
        mock_delete_dep = self._mox.CreateMockAnything()
        delete_op = {
            'link': '/canvases/1234',
            'type': 'DELETE',
            'status': 'NEW',
            'tasks': 0,
            'complete': 0,
        }
        self._mox.StubOutWithMock(manager, "save_deployment")
        manager.save_deployment(ContainsKeyValue('operation', delete_op),
                                api_id='1234',
                                tenant_id=None).AndReturn(None)
        self._mox.StubOutWithMock(
            checkmate.deployments.tasks.delete_deployment_task, "si"
        )
        checkmate.deployments.tasks.delete_deployment_task.si(IgnoreArg())\
            .AndReturn(mock_delete_dep)
        mock_chord.__call__(IgnoreArg(), interval=IgnoreArg(),
                            max_retries=IgnoreArg()).AndReturn(True)
        self._mox.ReplayAll()
        router.delete_deployment('1234')
        self._mox.VerifyAll()
        self.assertEquals(202, bottle.response.status_code)

    def test_delete_deployment_task(self):
        """ Test the final delete task itself """
        self._deployment['tenantId'] = '4567'
        self._deployment['status'] = 'UP'
        mock_driver = self._mox.CreateMockAnything()
        mock_driver.get_deployment('1234').AndReturn(self._deployment)

        self._mox.StubOutWithMock(common_tasks.update_deployment_status,
                                  "delay")
        common_tasks.update_deployment_status.delay('1234', "DELETED",
                                                    driver=mock_driver
                                                    ).AndReturn(True)
        self._mox.StubOutWithMock(common_tasks.update_operation, "delay")
        common_tasks.update_operation.delay('1234', status="COMPLETE",
                                            complete=0, driver=mock_driver
                                            ).AndReturn(True)
        self._mox.ReplayAll()
        delete_deployment_task('1234', driver=mock_driver)
        self._mox.VerifyAll()


class TestGetResourceStuff(unittest.TestCase):
    """ Test resource and resource status endpoints """

    def setUp(self):
        self._mox = mox.Mox()
        bottle.request.bind({})
        bottle.request.context = Context()
        bottle.request.context.tenant = None
        self._deployment = {
            'id': '1234',
            'status': 'PLANNED',
            'environment': {},
            'blueprint': {},
            'resources': {
                "fake": {'status': 'PLANNED'},
                '1': {'status': 'BUILD',
                      'instance': {'ip': '1234'}},
                '2': {'status': 'ERROR',
                      'status-message': 'An error happened',
                      'error-message': 'A certain error happened'},
                '3': {'status': 'ERROR',
                      'error-message': 'whoops',
                      'trace': 'stacktrace'},
                '9': {'status-message': 'I have an unknown status'}
            }
        }
        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_happy_resources(self):
        """ When getting the resources should work """
        db = self._mox.CreateMockAnything()
        manager = Manager({'default': db})
        router = Router(bottle.default_app(), manager)
        db.get_deployment('1234', with_secrets=False)\
            .AndReturn(self._deployment)
        self._mox.ReplayAll()
        ret = json.loads(router.get_deployment_resources('1234'))
        self.assertDictEqual(self._deployment.get('resources'), ret)

    def test_happy_status(self):
        """ When getting the resource statuses should work """
        db = self._mox.CreateMockAnything()
        manager = Manager({'default': db})
        router = Router(bottle.default_app(), manager)
        db.get_deployment('1234', with_secrets=False)\
            .AndReturn(self._deployment)
        self._mox.ReplayAll()
        ret = json.loads(router.get_resources_statuses('1234'))
        self.assertNotIn('fake', ret)
        for key in ['1', '2', '3', '9']:
            self.assertIn(key, ret)
        self.assertEquals('A certain error happened',
                          ret.get('2', {}).get('message'))
        self.assertNotIn('trace', ret.get('3', {'trace': 'FAIL'}))

    def test_no_resources(self):
        """ Test when no resources in deployment """
        del self._deployment['resources']
        db = self._mox.CreateMockAnything()
        manager = Manager({'default': db})
        router = Router(bottle.default_app(), manager)
        db.get_deployment('1234', with_secrets=False)\
            .AndReturn(self._deployment)

        self._mox.ReplayAll()
        self.assertRaisesRegexp(CheckmateDoesNotExist, "No resources found "
                                "for deployment 1234",
                                router.get_deployment_resources, '1234')

    def test_no_res_status(self):
        """ Test when no resources in deployment """
        del self._deployment['resources']
        db = self._mox.CreateMockAnything()
        manager = Manager({'default': db})
        router = Router(bottle.default_app(), manager)
        db.get_deployment('1234', with_secrets=False)\
            .AndReturn(self._deployment)

        self._mox.ReplayAll()
        self.assertRaisesRegexp(CheckmateDoesNotExist, "No resources found "
                                "for deployment 1234",
                                router.get_resources_statuses, '1234')

    def test_dep_404(self):
        """ Test when deployment not found """
        db = self._mox.CreateMockAnything()
        manager = Manager({'default': db})
        router = Router(bottle.default_app(), manager)
        db.get_deployment('1234', with_secrets=False).AndReturn(None)

        self._mox.ReplayAll()
        try:
            router.get_deployment_resources('1234')
            self.fail("get_deployment_resources with not found did not raise"
                      " exception")
        except CheckmateDoesNotExist as exc:
            self.assertIn("No deployment with id 1234", exc.message)

    def test_dep_404_status(self):
        """ Test when deployment not found """
        db = self._mox.CreateMockAnything()
        manager = Manager({'default': db})
        router = Router(bottle.default_app(), manager)
        db.get_deployment('1234', with_secrets=False).AndReturn(None)

        self._mox.ReplayAll()
        try:
            router.get_resources_statuses('1234')
            self.fail("get_deployment_resources with not found did not raise"
                      " exception")
        except CheckmateDoesNotExist as exc:
            self.assertIn("No deployment with id 1234", exc.message)

    def test_status_trace(self):
        """ Make sure trace is included if query param present """
        db = self._mox.CreateMockAnything()
        manager = Manager({'default': db})
        router = Router(bottle.default_app(), manager)
        db.get_deployment('1234', with_secrets=False)\
            .AndReturn(self._deployment)

        self._mox.ReplayAll()
        bottle.request.environ['QUERY_STRING'] = "?trace"
        ret = json.loads(router.get_resources_statuses('1234'))
        self.assertNotIn('fake', ret)
        for key in ['1', '2', '3', '9']:
            self.assertIn(key, ret)
        self.assertEquals('A certain error happened',
                          ret.get('2', {}).get('message'))
        self.assertIn('trace', ret.get('3', {}))


class TestPostbackHelpers(unittest.TestCase):
    """ Test deployment update helpers """

    def setUp(self):
        self._mox = mox.Mox()
        bottle.request.bind({})
        bottle.request.context = Context()
        bottle.request.context.tenant = None
        self._deployment = {
            'id': '1234',
            'status': 'PLANNED',
            'environment': {},
            'blueprint': {},
            'resources': {
                "fake": {'status': 'PLANNED'},
                '1': {'index': '1',
                      'status': 'BUILD',
                      'instance': {'ip': '1234'},
                      'provider': 'foo'},
                '2': {'index': '2',
                      'status': 'ERROR',
                      'status-message': 'An error happened',
                      'error-message': 'A certain error happened',
                      'provider': 'bar'},
                '3': {'index': '3',
                      'status': 'ERROR',
                      'error-message': 'whoops',
                      'trace': 'stacktrace',
                      'provider': 'bam'},
                '9': {'index': '9',
                      'status-message': 'I have an unknown status',
                      'provider': 'foo'}
            }
        }
        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_provider_update(self):
        """ Test mass provider resource updates """
        db = self._mox.CreateMockAnything()
        manager = Manager({'default': db})
        router = Router(bottle.default_app(), manager)
        db.get_deployment('1234').AndReturn(self._deployment)
        self._mox.StubOutWithMock(
            checkmate.deployments.tasks.resource_postback, "delay")
        checkmate.deployments.tasks.resource_postback.delay(
            '1234', IgnoreArg(), driver=db).AndReturn(True)
        self._mox.ReplayAll()
        ret = update_all_provider_resources('foo', '1234', 'NEW',
                                            message='I test u',
                                            trace='A trace',
                                            driver=db)
        self.assertIn('instance:1', ret)
        self.assertIn('instance:9', ret)
        self.assertEquals('NEW', ret.get('instance:1', {}).get('status'))
        self.assertEquals('NEW', ret.get('instance:9', {}).get('status'))
        self.assertEquals('I test u', ret.get('instance:1',
                                              {}).get('status-message'))
        self.assertEquals('I test u', ret.get('instance:9',
                                              {}).get('status-message'))
        self.assertEquals('A trace', ret.get('instance:1',
                                             {}).get('trace'))
        self.assertEquals('A trace', ret.get('instance:9',
                                             {}).get('trace'))


class TestDeploymentDisplayOutputs(unittest.TestCase):
    def test_parse_source_URI_options(self):
        fxn = Deployment.parse_source_URI
        result = fxn("options://username")
        expected = {
            'scheme': 'options',
            'netloc': 'username',
            'path': 'username',
            'query': '',
            'fragment': '',
        }
        self.assertDictEqual(result, expected)

    @unittest.skip('Looks like there is a python 2.7.4/2.7.1 issue')
    def test_parse_source_URI_python24(self):
        '''
        This seems to fail in python 2.7.1, but not 2.7.4

        2.7.1 parses ?type=compute as /?type=compute
        '''
        fxn = Deployment.parse_source_URI
        result = fxn("resources://status?type=compute")
        expected = {
            'scheme': 'resources',
            'netloc': 'status',
            'path': 'status',
            'query': 'type=compute',
            'fragment': '',
        }
        self.assertDictEqual(result, expected)

    def test_generation(self):
        """ Test Display Output Processing """
        deployment = Deployment(yaml_to_dict("""
            blueprint:
              id: 0255a076c7cf4fd38c69b6727f0b37ea
              services: {}
              options:
                region:
                  type: string
                  default: South
              display-outputs:
                "Region":
                  type: string
                  source: options://region
            environment:
              providers: {}
            inputs:
              blueprint:
                region: North
            """))
        outputs = deployment.calculate_outputs()
        expected = {
            "Region": {
                "type": "string",
                "value": "North"
            }
        }
        self.assertDictEqual(expected, outputs)


class TestCeleryTasks(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_resource_postback(self):
        db = self.mox.CreateMockAnything()
        target = {
            'id': '1234',
            'status': 'UP',
            'environment': {},
            'blueprint': {
                'meta-data': {
                    'schema-version': '0.7'
                }
            },
            'resources': {
                '0': {
                    'instance': {}
                },
            }
        }
        db.get_deployment('1234', with_secrets=True).AndReturn(target)
        expected = {
            'resources': {
                '0': {
                    'instance': {
                        'field_name': 1,
                    }
                }
            }
        }
        db.save_deployment('1234', expected, None, partial=True)\
            .AndReturn(None)
        self.mox.ReplayAll()
        contents = {
            'instance:0': {
                'field_name': 1
            }
        }
        resource_postback('1234', contents, driver=db)
        self.mox.VerifyAll()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
