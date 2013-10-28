# pylint: disable=C0103,C0302,E1101,R0904,W0212

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

"""Tests for Deployments."""
import bottle
import copy
import json
import logging
import os
import time
import unittest

from celery.app import task
import mock
import mox
from SpiffWorkflow import Workflow

from checkmate.common import tasks as common_tasks
from checkmate import deployment as cmdep
from checkmate import deployments as cmdeps
from checkmate import exceptions
from checkmate import inputs as cminp
from checkmate import keys
from checkmate import middleware as cmmid
from checkmate import operations
from checkmate.providers import base
from checkmate import utils
from checkmate import workflow
from checkmate import workflow_spec
from checkmate.workflows import tasks as wf_tasks

LOG = logging.getLogger(__name__)
os.environ['CHECKMATE_DOMAIN'] = 'checkmate.local'


class TestDeployments(unittest.TestCase):
    def test_key_generation_all(self):
        deployment = cmdep.Deployment({
            'id': 'test',
            'name': 'test',
        })
        cmdep.generate_keys(deployment)
        self.assertIn('resources', deployment)
        self.assertIn('deployment-keys', deployment['resources'])
        keys_resource = deployment['resources']['deployment-keys']
        self.assertItemsEqual(['instance', 'type'], keys_resource.keys())
        self.assertItemsEqual(['private_key', 'public_key', 'public_key_ssh'],
                              keys_resource['instance'].keys())
        self.assertEqual(keys_resource['type'], 'key-pair')

    def test_key_generation_public(self):
        private, _ = keys.generate_key_pair()
        deployment = cmdep.Deployment({
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
        cmdep.generate_keys(deployment)
        keys_resource = deployment['resources']['deployment-keys']
        self.assertItemsEqual(['instance', 'type'], keys_resource.keys())
        self.assertItemsEqual(['private_key', 'public_key', 'public_key_ssh'],
                              keys_resource['instance'].keys())
        self.assertEqual(keys_resource['type'], 'key-pair')

    def test_key_generation_and_settings_sync(self):
        private, _ = keys.generate_key_pair()
        deployment = cmdep.Deployment({
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
        cmdep.generate_keys(deployment)
        settings = deployment.settings()
        self.assertItemsEqual(['private_key', 'public_key', 'public_key_ssh'],
                              settings['keys']['deployment'].keys())


class TestDeploymentParser(unittest.TestCase):
    def test_parser(self):
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
        parsed = cmdeps.Manager.plan(cmdep.Deployment(deployment),
                                     cmmid.RequestContext())
        del parsed['status']  # we expect this to get added
        del parsed['created']  # we expect this to get added
        self.assertDictEqual(original, parsed)

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
            parsed = cmdep.Deployment.parse_constraints(case['parse'])
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

    @mock.patch.object(utils, 'get_time_string')
    @mock.patch('checkmate.deployments.manager.db.get_driver')
    def test_deployer(self, mock_get_driver, mock_get_time_string):
        mock_db = self._mox.CreateMockAnything()
        mock_get_driver.return_value = mock_db
        mock_get_time_string.return_value = '2013-03-31 17:49:51 +0000'
        manager = cmdeps.Manager()
        mock_db.save_workflow(mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              mox.IgnoreArg(),
                              tenant_id=mox.IgnoreArg()).AndReturn(True)
        mock_db.save_deployment(
            mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg(),
            tenant_id=mox.IgnoreArg(), partial=False
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
        dep_class = cmdep.Deployment(deployment)
        parsed = manager.plan(dep_class, cmmid.RequestContext())
        operation = manager.deploy(parsed, cmmid.RequestContext())
        self._mox.VerifyAll()
        expected = {
            'created': '2013-03-31 17:49:51 +0000',
            'status': 'IN PROGRESS',
            'tasks': 2,
            'complete': 0,
            'estimated-duration': 0,
            'link': '/T1000/workflows/test',
            'last-change': None,
            'type': 'BUILD',
            'workflow-id': 'test'
        }
        operation['last-change'] = None  # skip comparing/mocking times

        self.assertDictEqual(expected, operation)
        self.assertEqual(parsed['status'], "PLANNED")


class TestDeploymentResourceGenerator(unittest.TestCase):
    def test_component_resource_generator(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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

        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase

        cmdeps.Manager.plan(deployment, cmmid.RequestContext())
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
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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

        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase

        parsed = cmdeps.Manager.plan(deployment, cmmid.RequestContext())
        resources = parsed['resources']
        self.assertIn("myResource", resources)
        expected = {
            'component': 'small_widget',
            #dns-name with a deployment name
            'dns-name': 'sharedwidget.checkmate.local',
            'index': 'myResource',
            'instance': {},
            'provider': 'base',
            'type': 'widget',
            'desired-state': {},
        }
        self.assertDictEqual(resources['myResource'], expected)

    def test_providerless_static_resource_generator(self):
        private, _ = keys.generate_key_pair()
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
        parsed = cmdeps.Manager.plan(deployment, cmmid.RequestContext())
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
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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

        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase

        parsed = cmdeps.Manager.plan(deployment, cmmid.RequestContext())
        expected_connections = {
            'balanced-front': {'interface': 'foo'},
            'allyourbase': {'interface': 'bar'},
        }
        self.assertDictEqual(parsed['resources']['connections'],
                             expected_connections)


class TestComponentSearch(unittest.TestCase):
    def test_component_find_by_type(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase
        cmdeps.Manager.plan(deployment, cmmid.RequestContext())
        self.assertEquals(deployment['resources'].values()[0]['component'],
                          'small_widget')

    def test_component_find_by_type_and_interface(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase
        cmdeps.Manager.plan(deployment, cmmid.RequestContext())
        components = [r['component'] for r in deployment['resources'].values()]
        self.assertIn('big_widget', components)
        self.assertIn('small_widget', components)

    def test_component_finding(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase
        cmdeps.Manager.plan(deployment, cmmid.RequestContext())
        components = [r['component'] for r in deployment['resources'].values()]
        self.assertIn('big_widget', components)
        self.assertIn('small_widget', components)

    def test_component_find_with_role(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase
        cmdeps.Manager.plan(deployment, cmmid.RequestContext())
        self.assertEquals(deployment['resources'].values()[0]['component'],
                          'small_widget')


class TestDeploymentSettings(unittest.TestCase):

    def test_get_setting(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
        deployment.update(utils.yaml_to_dict("""
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
        }, {
            'case': "Provider setting is used even with service param",
            'name': "size",
            'provider': "base",
            'service': 'web',
            'type': "widget",
            'expected': "big",
        }, {
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
        }, {
            'case': "Relation setting is used when relation passed in",
            'name': "algorithm",
            'type': 'compute',
            'relation': 'web',
            'service': 'wordpress',
            'expected': "round-robin",
        }, {
            'case': "Set in blueprint/providers",
            'name': "memory",
            'type': 'compute',
            'expected': "4 Gb",
        },
        ]

        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase
        parsed = cmdeps.Manager.plan(deployment, cmmid.RequestContext())
        # TODO(any): last case broken without env providers
        for case in cases[:-1]:
            value = parsed.get_setting(case['name'],
                                       service_name=case.get('service'),
                                       provider_key=case.get('provider'),
                                       resource_type=case.get('type'),
                                       relation=case.get('relation'))
            self.assertEquals(value, case['expected'], msg=case['case'])
            LOG.debug("Test '%s' success=%s", case['case'],
                      value == case['expected'])

        msg = "Coming from static resource constraint"
        value = parsed.get_setting("server_key", service_name="web",
                                   resource_type="compute")
        self.assertIn('-----BEGIN RSA PRIVATE KEY-----\n', value, msg=msg)

    def test_get_setting_static(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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

        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase

        parsed = cmdeps.Manager.plan(deployment, cmmid.RequestContext())
        resources = parsed['resources']
        self.assertIn("myResource", resources)
        self.assertIn("myUser", resources)
        self.assertEqual(resources['myUser']['instance']['name'], 'bar')
        self.assertEqual(deployment.get_setting('resources/myUser/name'),
                         'bar')

    def test_get_false_settings(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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

        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase
        parsed = cmdeps.Manager.plan(deployment, cmmid.RequestContext())
        # TODO(any): last case broken without env providers
        for case in cases[:-1]:
            value = parsed.get_setting(case['name'],
                                       service_name=case.get('service'),
                                       provider_key=case.get('provider'),
                                       resource_type=case.get('type'),
                                       relation=case.get('relation'))
            self.assertEquals(value, case['expected'], msg=case['case'])
            LOG.debug("Test '%s' success=%s", case['case'],
                      value == case['expected'])

    def test_get_input_provider_option(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
        self.assertRaises(exceptions.CheckmateValidationException,
                          cmdep.Deployment,
                          utils.yaml_to_dict("""
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
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase
        planned = cmdeps.Manager.plan(deployment, cmmid.RequestContext())
        # Use service and type
        value = planned.get_setting('username', service_name='single',
                                    resource_type='widget')
        self.assertEqual(value, 'john')
        # Use only type
        value = planned.get_setting('password', resource_type='widget')
        self.assertGreater(len(value), 0)

    def test_handle_missing_options(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase
        self.assertRaises(exceptions.CheckmateValidationException,
                          cmdeps.Manager.plan, deployment,
                          cmmid.RequestContext())

    def test_objectify(self):
        deployment = cmdep.Deployment({})
        msg = "Untyped option should remain unchanged"
        self.assertEqual(deployment._objectify({}, 0), 0, msg=msg)

        msg = "Typed, non-object option should remain unchanged"
        self.assertEqual(deployment._objectify({'type': 'string'}, 0), 0,
                         msg=msg)

        msg = "Typed option should return type"
        self.assertIsInstance(deployment._objectify({'type': 'url'},
                                                    'http://fqdn'),
                              cminp.Input, msg=msg)

    def test_apply_constraint_attribute(self):
        deployment = utils.yaml_to_dict("""
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
        deployment = cmdep.Deployment(deployment)
        option = deployment['blueprint']['options']['my_option']
        constraint = option['constrains'][0]
        self.assertRaises(exceptions.CheckmateException,
                          deployment._apply_constraint,
                          "my_option", constraint, option=option,
                          option_key="my_option")

    def test_handle_bad_call(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
                id: test
                environment:
                  providers: {}
                blueprint: {}
                inputs: {}
            """))
        self.assertRaises(exceptions.CheckmateValidationException,
                          deployment.get_setting, None)
        self.assertRaises(exceptions.CheckmateValidationException,
                          deployment.get_setting, '')


class TestDynamicValues(unittest.TestCase):

    def test_options_static(self):
        """Make syure simple, static check works."""
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
                    bar:
                      type: string
            """))
        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase
        with self.assertRaises(exceptions.CheckmateException):
            cmdep.validate_blueprint_options(deployment)

        deployment['blueprint']['options']['foo']['required'] = False
        cmdep.validate_blueprint_options(deployment)

    def test_options_required(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
                      required:
                        if:
                          value: inputs://blueprint/bar
                inputs:
                  blueprint:
                    bar: 1
            """))
        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase
        with self.assertRaises(exceptions.CheckmateException):
            cmdep.validate_blueprint_options(deployment)

        deployment['inputs']['blueprint']['bar'] = False
        cmdep.validate_blueprint_options(deployment)

    def test_constraints(self):
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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
                      constraints:
                      - check:
                          if:
                            exists: inputs://blueprint/absent
                inputs:
                  blueprint:
                    bar: 1
            """))
        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase
        with self.assertRaises(exceptions.CheckmateException):
            cmdep.validate_input_constraints(deployment)

        deployment['inputs']['blueprint']['absent'] = False
        cmdep.validate_input_constraints(deployment)


class TestDeploymentScenarios(unittest.TestCase):

    def test_deployment_scenarios(self):
        base.PROVIDER_CLASSES['test.base'] = base.ProviderBase

        data_dir = os.path.join(os.path.dirname(__file__), '../data')

        # No objects
        path = os.path.join(data_dir, "deployment - none objects.yaml")
        with file(path, 'r') as the_file:
            content = the_file.read()
        self.assertRaisesRegexp(exceptions.CheckmateValidationException,
                                "Blueprint not found. Nothing to do.",
                                self.plan_deployment, content)

    @staticmethod
    def plan_deployment(content):
        """Helper method to kick off plan deployment."""
        deployment = cmdep.Deployment(utils.yaml_to_dict(content))
        return cmdeps.Manager.plan(deployment, cmmid.RequestContext())


class TestCloneDeployments(unittest.TestCase):
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
        manager = cmdeps.Manager()
        self._mox.StubOutWithMock(manager, "get_deployment")
        manager.get_deployment('1234', tenant_id='T1000')\
            .AndReturn(self._deployment)

        self._mox.ReplayAll()
        try:
            manager.clone('1234', {}, tenant_id='T1000')
            self.fail("Expected exception not raised.")
        except exceptions.CheckmateBadState:
            pass

    def test_clone_deployment_happy_path(self):
        self._deployment['status'] = 'DELETED'

        manager = cmdeps.Manager()
        self._mox.StubOutWithMock(manager, "get_deployment")
        manager.get_deployment('1234', tenant_id='T1000')\
            .AndReturn(self._deployment)

        context = cmmid.RequestContext(simulation=False)
        self._mox.StubOutWithMock(manager, "deploy")
        manager.deploy(mox.IgnoreArg(), context)

        manager.get_deployment(mox.IgnoreArg(), tenant_id='T1000')\
            .AndReturn({'id': 'NEW'})
        self._mox.ReplayAll()
        manager.clone('1234', context, tenant_id='T1000')
        self._mox.VerifyAll()

    def test_clone_deployment_simulation(self):
        self._deployment['status'] = 'DELETED'

        manager = cmdeps.Manager()
        self._mox.StubOutWithMock(manager, "get_deployment")
        manager.get_deployment('1234', tenant_id='T1000')\
            .AndReturn(self._deployment)

        context = cmmid.RequestContext(simulation=True)
        self._mox.StubOutWithMock(manager, "deploy")
        manager.deploy(mox.IgnoreArg(), context)

        manager.get_deployment(mox.IgnoreArg(), tenant_id='T1000')\
            .AndReturn(self._deployment)

        self._mox.ReplayAll()
        manager.clone('1234', context, tenant_id='T1000')
        self._mox.VerifyAll()


class TestDeleteDeployments(unittest.TestCase):
    def __init__(self, methodName="runTest"):
        self._mox = mox.Mox()
        unittest.TestCase.__init__(self, methodName)

    def setUp(self):
        bottle.request.bind({})
        bottle.request.environ['context'] = cmmid.RequestContext()
        bottle.request.environ['context'].tenant = None
        self._deployment = {
            'id': '1234',
            'status': 'PLANNED',
            'tenantId': 'T1000',
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
        manager = self._mox.CreateMockAnything()
        router = cmdeps.Router(bottle.default_app(), manager)
        manager.get_deployment(
            '1234', with_secrets=True).AndReturn(self._deployment)
        manager.save_deployment('1234', mox.IgnoreArg(), tenant_id=None,
                                partial=False).AndReturn(None)

        self._mox.ReplayAll()
        try:
            router.plan_deployment('1234')
            self.fail("Attempt to change from PLANNED to NEW should fail.")
        except exceptions.CheckmateBadState as exc:
            self.assertIn("Deployment '1234' is in 'PLANNED' status and must "
                          "be in 'NEW' to be planned", str(exc))

    def test_not_found(self):
        manager = self._mox.CreateMockAnything()
        router = cmdeps.Router(bottle.default_app(), manager)
        manager.get_deployment('1234', tenant_id=None).AndReturn(None)
        self._mox.ReplayAll()
        try:
            router.delete_deployment('1234')
            self.fail("Delete deployment with not found did not raise "
                      "exception")
        except exceptions.CheckmateDoesNotExist as exc:
            self.assertEqual("No deployment with id 1234", str(exc))

    @mock.patch('checkmate.deployments.manager.db.get_driver')
    def test_happy_path(self, mock_get_driver):
        self._deployment['status'] = 'UP'
        self._deployment['created'] = utils.get_time_string()
        self._deployment['operation'] = {'status': 'IN PROGRESS'}
        mock_driver = self._mox.CreateMockAnything()
        mock_spec = self._mox.CreateMock(Workflow)
        mock_spiff_wf = self._mox.CreateMockAnything()
        mock_spiff_wf.attributes = {"id": "w_id"}
        manager = mock.Mock()
        manager.get_deployment.return_value = self._deployment
        router = cmdeps.Router(bottle.default_app(), manager)
        mock_get_driver.return_value = mock_driver

        self._mox.StubOutWithMock(workflow_spec.WorkflowSpec,
                                  "create_delete_dep_wf_spec")
        workflow_spec.WorkflowSpec.create_delete_dep_wf_spec(
            self._deployment, bottle.request.environ['context'])\
            .AndReturn(mock_spec)
        self._mox.StubOutWithMock(workflow,
                                  "create_workflow")
        workflow.create_workflow(mock_spec, self._deployment,
                                 bottle.request.environ['context'],
                                 driver=mock_driver,
                                 wf_type="DELETE")\
            .AndReturn(mock_spiff_wf)
        self._mox.StubOutWithMock(common_tasks, "update_operation")
        common_tasks.update_operation.delay('1234', '1234', action='PAUSE',
                                            driver=mock_driver)
        self._mox.StubOutWithMock(operations, "create")
        operations.create.delay('1234', 'w_id', 'DELETE', 'T1000')
        self._mox.StubOutWithMock(wf_tasks, "cycle_workflow")
        wf_tasks.cycle_workflow.delay(
            'w_id',
            bottle.request.environ['context'].get_queued_task_dict())\
            .AndReturn(4)

        self._mox.ReplayAll()
        router.delete_deployment('1234', tenant_id="T1000")
        self._mox.VerifyAll()

    @mock.patch('checkmate.deployments.manager.db.get_driver')
    def test_delete_deployment_task(self, mock_get_driver):
        self._deployment['tenantId'] = '4567'
        self._deployment['status'] = 'UP'
        self._deployment['operation'] = {'workflow-id': "w_id"}
        mock_driver = self._mox.CreateMockAnything()
        mock_driver.get_deployment('1234').AndReturn(self._deployment)
        mock_get_driver.return_value = mock_driver

        self._mox.StubOutWithMock(common_tasks.update_operation, "delay")
        common_tasks.update_operation.delay('1234', 'w_id', status="COMPLETE",
                                            deployment_status="DELETED",
                                            complete=0, driver=mock_driver
                                            ).AndReturn(True)
        self._mox.ReplayAll()
        cmdeps.delete_deployment_task('1234', driver=mock_driver)
        self._mox.VerifyAll()


class TestGetResourceStuff(unittest.TestCase):
    def setUp(self):
        self._mox = mox.Mox()
        bottle.request.bind({})
        bottle.request.environ['context'] = task.Context()
        bottle.request.environ['context'].tenant = None
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
                      'error-message': 'whoops'},
                '9': {'status-message': 'I have an unknown status'}
            }
        }
        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    @mock.patch('checkmate.deployments.manager.db.get_driver')
    def test_happy_resources(self, mock_get_driver):
        mock_db = self._mox.CreateMockAnything()
        mock_db.get_deployment('1234', with_secrets=False)\
            .AndReturn(self._deployment)
        mock_get_driver.return_value = mock_db
        manager = cmdeps.Manager()
        router = cmdeps.Router(bottle.default_app(), manager)
        self._mox.ReplayAll()
        ret = json.loads(router.get_deployment_resources('1234'))
        self.assertDictEqual(self._deployment.get('resources'), ret)

    @mock.patch('checkmate.deployments.manager.db.get_driver')
    def test_happy_status(self, mock_get_driver):
        mock_db = self._mox.CreateMockAnything()
        mock_db.get_deployment('1234', with_secrets=False)\
            .AndReturn(self._deployment)
        mock_get_driver.return_value = mock_db
        manager = cmdeps.Manager()
        router = cmdeps.Router(bottle.default_app(), manager)
        self._mox.ReplayAll()
        ret = json.loads(router.get_resources_statuses('1234'))
        self.assertNotIn('fake', ret)
        for key in ['1', '2', '3', '9']:
            self.assertIn(key, ret)
        self.assertEquals('A certain error happened',
                          ret.get('2', {}).get('error-message'))

    @mock.patch('checkmate.deployments.manager.db.get_driver')
    def test_no_resources(self, mock_get_driver):
        del self._deployment['resources']
        mock_db = self._mox.CreateMockAnything()
        mock_db.get_deployment('1234', with_secrets=False)\
            .AndReturn(self._deployment)
        mock_get_driver.return_value = mock_db
        manager = cmdeps.Manager()
        router = cmdeps.Router(bottle.default_app(), manager)

        self._mox.ReplayAll()
        self.assertRaisesRegexp(exceptions.CheckmateDoesNotExist,
                                "No resources found "
                                "for deployment 1234",
                                router.get_deployment_resources, '1234')

    @mock.patch('checkmate.deployments.manager.db.get_driver')
    def test_no_res_status(self, mock_get_driver):
        del self._deployment['resources']
        mock_db = self._mox.CreateMockAnything()
        mock_db.get_deployment('1234', with_secrets=False)\
            .AndReturn(self._deployment)

        mock_get_driver.return_value = mock_db
        manager = cmdeps.Manager()
        router = cmdeps.Router(bottle.default_app(), manager)
        self._mox.ReplayAll()
        self.assertRaisesRegexp(exceptions.CheckmateDoesNotExist,
                                "No resources found "
                                "for deployment 1234",
                                router.get_resources_statuses, '1234')

    @mock.patch('checkmate.deployments.manager.db.get_driver')
    def test_dep_404(self, mock_get_driver):
        mock_db = self._mox.CreateMockAnything()
        mock_db.get_deployment('1234', with_secrets=False).AndReturn(None)
        mock_get_driver.return_value = mock_db
        manager = cmdeps.Manager()
        router = cmdeps.Router(bottle.default_app(), manager)

        self._mox.ReplayAll()
        try:
            router.get_deployment_resources('1234')
            self.fail("get_deployment_resources with not found did not raise"
                      " exception")
        except exceptions.CheckmateDoesNotExist as exc:
            self.assertIn("No deployment with id 1234", str(exc))

    @mock.patch('checkmate.deployments.manager.db.get_driver')
    def test_dep_404_status(self, mock_get_driver):
        mock_db = self._mox.CreateMockAnything()
        mock_db.get_deployment('1234', with_secrets=False).AndReturn(None)
        mock_get_driver.return_value = mock_db
        manager = cmdeps.Manager()
        router = cmdeps.Router(bottle.default_app(), manager)

        self._mox.ReplayAll()
        try:
            router.get_resources_statuses('1234')
            self.fail("get_deployment_resources with not found did not raise"
                      " exception")
        except exceptions.CheckmateDoesNotExist as exc:
            self.assertIn("No deployment with id 1234", str(exc))


class TestPostbackHelpers(unittest.TestCase):
    def setUp(self):
        self._mox = mox.Mox()
        bottle.request.bind({})
        bottle.request.environ['context'] = cmmid.RequestContext()
        bottle.request.environ['context'].tenant = None
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
                      'error-trace': 'stacktrace',
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

    @mock.patch('checkmate.deployments.manager.db.get_driver')
    def test_provider_update(self, mock_get_driver):
        mock_db = self._mox.CreateMockAnything()
        manager = cmdeps.Manager()
        cmdeps.Router(bottle.default_app(), manager)
        mock_db.get_deployment('1234').AndReturn(self._deployment)
        mock_get_driver.return_value = mock_db
        self._mox.StubOutWithMock(cmdeps.tasks.resource_postback, "delay")
        cmdeps.tasks.resource_postback.delay(
            '1234', mox.IgnoreArg(), driver=mock_db).AndReturn(True)
        self._mox.ReplayAll()
        ret = cmdeps.update_all_provider_resources('foo', '1234', 'NEW',
                                                   message='I test u',
                                                   driver=mock_db)
        self.assertIn('instance:1', ret)
        self.assertIn('instance:9', ret)
        self.assertEquals('NEW', ret.get('instance:1', {}).get('status'))
        self.assertEquals('NEW', ret.get('instance:9', {}).get('status'))
        self.assertEquals('I test u', ret.get('instance:1',
                                              {}).get('status-message'))
        self.assertEquals('I test u', ret.get('instance:9',
                                              {}).get('status-message'))


class TestDeploymentAddNodes(unittest.TestCase):
    def setUp(self):
        self._mox = mox.Mox()
        bottle.request.bind({})
        bottle.request.environ['context'] = cmmid.RequestContext()
        bottle.request.environ['context'].tenant = None
        self._deployment = {
            'id': '1234',
            'status': 'PLANNED',
            'environment': {},
            'blueprint': {
                'meta-data': {
                    'schema-version': '0.7'
                }
            },
            'operation': {},
            'created': time.time()
        }
        unittest.TestCase.setUp(self)

    def test_happy_path(self):
        manager = self._mox.CreateMock(cmdeps.Manager)
        router = cmdeps.Router(bottle.default_app(), manager)

        manager.get_deployment('1234', tenant_id="T1000",
                               with_secrets=True).AndReturn(self._deployment)

        self._mox.StubOutWithMock(utils, "read_body")
        utils.read_body(bottle.request).AndReturn({
            'service_name': 'service_name',
            'count': '2'
        })

        manager.plan_add_nodes(self._deployment,
                               bottle.request.environ['context'],
                               "service_name", 2).AndReturn(self._deployment)
        manager.deploy_workflow(bottle.request.environ['context'],
                                self._deployment,
                                "T1000", "SCALE UP").AndReturn({'workflow-id':
                                                                'w_id'})
        self._mox.StubOutWithMock(wf_tasks, "cycle_workflow")
        wf_tasks.cycle_workflow.delay(
            'w_id',
            bottle.request.environ['context'].get_queued_task_dict())

        self._mox.ReplayAll()
        router.add_nodes("1234", tenant_id="T1000")

        self._mox.VerifyAll()

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)


class TestDeploymentDisplayOutputs(unittest.TestCase):
    def test_parse_source_uri_options(self):
        fxn = cmdep.Deployment.parse_source_uri
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
    def test_parse_source_uri_python24(self):
        """This seems to fail in python 2.7.1, but not 2.7.4

        2.7.1 parses ?type=compute as /?type=compute
        """
        fxn = cmdep.Deployment.parse_source_uri
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
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
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

    @mock.patch('checkmate.deployments.manager.db.get_driver')
    def test_resource_postback(self, mock_get_driver):
        mock_db = self.mox.CreateMockAnything()
        target = {
            'id': '1234',
            'tenantId': 'T1000',
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
        mock_db.get_deployment('1234', with_secrets=True).AndReturn(target)
        expected = {
            'resources': {
                '0': {
                    'instance': {
                        'field_name': 1,
                    }
                }
            }
        }
        mock_db.save_deployment('1234', expected, None, partial=True,
                                tenant_id='T1000').AndReturn(None)
        mock_get_driver.return_value = mock_db
        self.mox.ReplayAll()
        contents = {
            'instance:0': {
                'field_name': 1
            }
        }
        cmdeps.resource_postback('1234', contents, driver=mock_db)
        self.mox.VerifyAll()


if __name__ == '__main__':
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
