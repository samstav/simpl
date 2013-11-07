# pylint: disable=C0103,E1101,E1103,R0904,W0212,W0613

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

"""Tests for Chef Solo."""
import logging
import unittest
import uuid

import mox
from SpiffWorkflow import specs
import yaml

from checkmate.common import templating
from checkmate import deployment as cm_dep
from checkmate import deployments
from checkmate import middleware
from checkmate import providers
from checkmate.providers.opscode import solo
from checkmate.providers.opscode.solo import chef_map
from checkmate.providers.opscode.solo import transforms
from checkmate import test
from checkmate import utils
from checkmate import workflow as cm_wf
from checkmate import workflow_spec

LOG = logging.getLogger(__name__)


class TestChefSoloProvider(test.ProviderTester):

    klass = solo.Provider

    def test_get_resource_prepared_maps(self):
        providers.base.PROVIDER_CLASSES = {}
        providers.register_providers([solo.Provider, test.TestProvider])
        deployment = cm_dep.Deployment(utils.yaml_to_dict('''
                id: 'DEP-ID-1000'
                blueprint:
                  name: test app
                  services:
                    frontend:
                      component:
                        id: foo
                      constraints:
                      - count: 2
                      relations:
                        backend: mysql
                    backend:
                      component:
                        id: bar
                environment:
                  name: test
                  providers:
                    chef-solo:
                      vendor: opscode
                      catalog:
                        application:
                          foo:
                            is: application
                            requires:
                            - database: mysql
                        database:
                          bar:
                            is: database
                            provides:
                            - database: mysql
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            id: linux_instance
                            is: compute
                            provides:
                            - compute: linux
            '''))
        map = chef_map.ChefMap(raw='''
            \n--- # foo component
                id: foo
                requires:
                - database: mysql
                maps:
                - source: requirements://database:mysql/ip
                  targets:
                  - attributes://ip
            \n--- # bar component
                id: bar
                provides:
                - database: mysql
                maps:
                - source: clients://database:mysql/ip
                  targets:
                  - attributes://clients
            ''')
        deployments.Manager.plan(deployment, middleware.RequestContext())
        solo_provider = deployment.environment().get_provider('chef-solo')

        # Check requirement map

        resource = deployment['resources']['0']  # one of the mysql clients
        result = solo_provider.get_resource_prepared_maps(
            resource, deployment, map_file=map)
        expected = [{'source': 'requirements://database:mysql/ip',
                     'targets': ['attributes://ip'],
                     'path': 'instance:2/interfaces/mysql',
                     'resource': '0',
                     }]
        self.assertListEqual(result, expected)

        # Check client maps

        resource = deployment['resources']['2']  # mysql database w/ 2 clients
        result = solo_provider.get_resource_prepared_maps(
            resource, deployment, map_file=map)
        expected = [
            {
                'source': 'clients://database:mysql/ip',
                'targets': ['attributes://clients'],
                'resource': '2',
                'path': 'instance:1',
            },
            {
                'source': 'clients://database:mysql/ip',
                'targets': ['attributes://clients'],
                'resource': '2',
                'path': 'instance:0',
            },
        ]
        self.assertListEqual(result, expected)

    def test_get_map_with_context_defaults(self):
        solo_provider = solo.Provider({})
        deployment = cm_dep.Deployment(utils.yaml_to_dict('''
                id: 'DEP-ID-1000'
                blueprint:
                  name: Test
                  services:
                    foo:
                      component:
                        id: test
                  options:
                    bp_password:
                      default: =generate_password()
                      constrains:
                      - service: foo
                        setting: bp_password
                environment:
                  name: test
                  providers:
                    chef-solo:
                      vendor: opscode
                      constraint:
                      - source: dummy
            '''))
        chefmap = chef_map.ChefMap(raw='''
                id: test
                options:
                  password:
                    default: =generate_password()
                output:
                  component: {{ setting('password') }}
                  blueprint: {{ setting('bp_password') }}
            ''')
        solo_provider.map_file = chefmap
        component = chefmap.components[0]

        self.mox.StubOutWithMock(utils, 'evaluate')
        utils.evaluate('generate_password()').AndReturn("RandomPass")
        utils.evaluate('generate_password()').AndReturn("randp2")

        resource = {
            'type': 'application',
            'service': 'foo',
            'provider': 'chef-solo',
        }
        self.mox.ReplayAll()
        context = solo_provider.get_map_with_context(component=component,
                                                     deployment=deployment,
                                                     resource=resource)
        output = context.get_component_output_template("test")
        self.assertEqual(output['component'], "RandomPass")
        self.assertEqual(output['blueprint'], "randp2")
        self.mox.VerifyAll()

    def test_cleanup_environment(self):
        wf_spec = workflow_spec.WorkflowSpec()
        solo_provider = solo.Provider({})
        cleanup_result = solo_provider.cleanup_environment(
            wf_spec, {'id': 'DEP1'})
        cleanup_task_spec = cleanup_result['root']
        self.assertIsInstance(cleanup_task_spec, specs.Celery)
        self.assertEqual(cleanup_task_spec.args, ['DEP1'])
        defines = {'provider': solo_provider.key, 'resource': 'workspace'}
        properties = {
            'estimated_duration': 1,
            'task_tags': ['cleanup'],
        }
        properties.update(defines)
        self.assertDictEqual(cleanup_task_spec.defines, defines)
        self.assertDictEqual(cleanup_task_spec.properties, properties)
        self.assertEqual(
            cleanup_task_spec.call, 'checkmate.providers.opscode.solo.tasks'
                                    '.delete_environment')

    def test_cleanup_temp_files(self):
        wf_spec = workflow_spec.WorkflowSpec()
        self.mox.StubOutWithMock(wf_spec, "find_task_specs")
        self.mox.StubOutWithMock(wf_spec, "wait_for")
        mock_task_spec = self.mox.CreateMock(specs.TaskSpec)
        mock_final_task_spec = self.mox.CreateMock(specs.TaskSpec)
        solo_provider = solo.Provider({})
        wf_spec.find_task_specs(
            provider=solo_provider.key,
            tag='client-ready').AndReturn([mock_task_spec])
        wf_spec.find_task_specs(
            provider=solo_provider.key,
            tag='final').AndReturn([mock_final_task_spec])
        wf_spec.task_specs = dict()
        defines = {'provider': solo_provider.key, 'resource': 'workspace'}
        wf_spec.wait_for(mox.IgnoreArg(), [mock_task_spec,
                                           mock_final_task_spec],
                         name="Wait before deleting cookbooks",
                         defines=defines)
        self.mox.ReplayAll()
        result = solo_provider.cleanup_temp_files(wf_spec, {'id': 'DEP1'})
        cleanup_task_spec = result['final']
        self.assertIsInstance(cleanup_task_spec, specs.Celery)
        self.assertEqual(cleanup_task_spec.args, ['DEP1', 'kitchen'])
        properties = {
            'estimated_duration': 1,
        }
        properties.update(defines)
        self.assertDictEqual(cleanup_task_spec.defines, defines)
        self.assertDictEqual(cleanup_task_spec.properties, properties)
        self.assertEqual(
            cleanup_task_spec.call, 'checkmate.providers.opscode.solo.tasks'
                                    '.delete_cookbooks')


class TestMySQLMaplessWorkflow(test.StubbedWorkflowBase):
    """Test that cookbooks can be used without a map file (only catalog)

    This test is done using the MySQL cookbook. This is a very commonly used
    cookbook.
    """
    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        providers.base.PROVIDER_CLASSES = {}
        providers.register_providers([solo.Provider, test.TestProvider])
        self.deployment = cm_dep.Deployment(utils.yaml_to_dict('''
                id: 'DEP-ID-1000'
                blueprint:
                  name: MySQL Database
                  services:
                    db:
                      component:
                        resource_type: database
                        interface: mysql
                environment:
                  name: test
                  providers:
                    chef-solo:
                      vendor: opscode
                      catalog:
                        database:
                          mysql:
                            provides:
                            - database: mysql
                            requires:
                            - host: 'linux'
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            provides:
                            - compute: linux
            '''))
        self.deployment['tenantId'] = 'tenantId'
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)

    def test_workflow_task_generation(self):
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(context,
                                                               self.deployment)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, self.deployment, context, "w_id", "BUILD")

        task_list = workflow.spec.task_specs.keys()
        expected = ['Root',
                    'Start',
                    'Create Chef Environment',
                    'Create Resource 1',
                    'After Environment is Ready and Server 1 (db) is Up',
                    'Pre-Configure Server 1 (db)',
                    'Register Server 1 (db)',
                    'After server 1 (db) is registered and options are ready',
                    'Configure mysql: 0 (db)',
                    'Delete Cookbooks']
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)

    def test_workflow_completion(self):
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        expected = []

        # Create Chef Environment
        expected.append({
            # Use chef-solo tasks for now
            # Use only one kitchen. Call it "kitchen" like we used to
            'call': 'checkmate.providers.opscode.solo.tasks'
                    '.create_environment',
            'args': [context.get_queued_task_dict(
                    deployment_id=self.deployment['id']),
                self.deployment['id'], 'kitchen'],
            'kwargs': mox.And(
                mox.ContainsKeyValue('private_key', mox.IgnoreArg()),
                mox.ContainsKeyValue('secret_key', mox.IgnoreArg()),
                mox.ContainsKeyValue(
                    'public_key_ssh',
                    mox.IgnoreArg()
                ),
                mox.ContainsKeyValue('source_repo', mox.IgnoreArg())
            ),
            'result': {
                'environment': '/var/tmp/%s/' % self.deployment['id'],
                'kitchen': '/var/tmp/%s/kitchen' % self.deployment['id'],
                'private_key_path':
                '/var/tmp/%s/private.pem' % self.deployment['id'],
                'public_key_path':
                '/var/tmp/%s/checkmate.pub' % self.deployment['id'],
                'public_key': test.ENV_VARS['CHECKMATE_CLIENT_PUBLIC_KEY'],
            },
        })
        expected.append({
            'call': 'checkmate.providers.opscode.solo.tasks.delete_cookbooks',
            'args': [self.deployment['id'], 'kitchen'],
            'result': None,
            'kwargs': None
        })

        for key, resource in self.deployment['resources'].iteritems():
            if resource['type'] == 'compute':
                context_dict = context.get_queued_task_dict(
                    deployment_id=self.deployment['id'],
                    resource_key=resource.get('hosts')[0])
                expected.append({
                    'call': 'checkmate.providers.test.create_resource',
                    'args': [mox.IsA(dict), resource],
                    'kwargs': None,
                    'result': {
                        'instance:%s' % key: {
                            'status': 'ACTIVE',
                            'ip': '4.4.4.1',
                            'private_ip': '10.1.2.1',
                            'addresses': {
                                'public': [
                                    {'version': 4, 'addr': '4.4.4.1'},
                                    {
                                        'version': 6,
                                        'addr': '2001:babe::ff04:36c1'
                                    }
                                ],
                                'private': [{
                                    'version': 4,
                                    'addr': '10.1.2.1'
                                }]
                            },
                        }
                    },
                    'post_back_result': True,
                })
                expected.append({
                    'call': 'checkmate.providers.opscode.solo.tasks'
                            '.register_node_v2',
                    'args': [
                        context_dict,
                        '4.4.4.1',
                        self.deployment['id'],
                    ],
                    'kwargs': mox.And(
                        mox.In('password'),
                        mox.ContainsKeyValue('bootstrap_version', '10.24.0')
                    ),
                    'result': None,
                    'resource': key,
                })

                # build-essential (now just cook with bootstrap.json)
                expected.append({
                    'call': 'checkmate.providers.opscode.solo.tasks.cook_v2',
                    'args': [
                        context_dict,
                        '4.4.4.1',
                        self.deployment['id'],
                    ],
                    'kwargs': mox.And(
                        mox.In('password'),
                        mox.Not(mox.In('recipes')),
                        mox.Not(mox.In('roles')),
                        mox.ContainsKeyValue(
                            'identity_file',
                            '/var/tmp/%s/private.pem' % self.deployment['id']
                        )
                    ),
                    'result': None,
                    'resource': key,
                })
            else:
                # Cook with cookbook (special mysql handling calls server role)
                context_dict = context.get_queued_task_dict(
                    deployment_id=self.deployment['id'],
                    resource_key=key)

                expected.append({
                    'call': 'checkmate.providers.opscode.solo.tasks.cook_v2',
                    'args': [
                        context_dict,
                        '4.4.4.1',
                        self.deployment['id'],
                    ],
                    'kwargs': mox.And(
                        mox.In('password'),
                        mox.ContainsKeyValue('recipes', ['mysql::server']),
                        mox.ContainsKeyValue(
                            'identity_file',
                            '/var/tmp/%s/private.pem' % self.deployment['id']
                        )
                    ),
                    'result': None,
                    'resource': key,
                })

        self.workflow = self._get_stubbed_out_workflow(
            expected_calls=expected, context=context)
        self.mox.ReplayAll()
        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(),
                        'Workflow did not complete')
        self.mox.VerifyAll()


class TestMapfileWithoutMaps(test.StubbedWorkflowBase):
    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        providers.base.PROVIDER_CLASSES = {}
        providers.register_providers([solo.Provider, test.TestProvider])
        self.deployment = \
            cm_dep.Deployment(utils.yaml_to_dict('''
                id: 'DEP-ID-1000'
                blueprint:
                  name: test app
                  services:
                    frontend:
                      component:
                        id: foo
                      relations:
                        backend: mysql
                    backend:
                      component:
                        id: bar
                environment:
                  name: test
                  providers:
                    chef-solo:
                      vendor: opscode
                      constraints:
                      - source: http://mock_url
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            id: linux_instance
                            is: compute
                            provides:
                            - compute: linux
            '''))
        self.deployment['tenantId'] = 'tenantId'
        self.map_file = \
            '''
            \n--- # foo component
                id: foo
                requires:
                - database: mysql
            \n--- # bar component
                id: bar
                provides:
                - database: mysql
                maps: {}  # blank map should be ignored as well
            '''

    def test_workflow_task_generation(self):
        self.mox.StubOutWithMock(chef_map.ChefMap, "get_map_file")
        chefmap = chef_map.ChefMap(mox.IgnoreArg())
        chefmap.get_map_file().AndReturn(self.map_file)

        self.mox.ReplayAll()

        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)

        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(context,
                                                               self.deployment)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, self.deployment, context, "w_id", "BUILD")

        task_list = workflow.spec.task_specs.keys()
        self.assertNotIn('Collect Chef Data for 0', task_list,
                         msg="Should not have a Collect task when no mappings "
                             "exist in the map file")
        expected = [
            'Root',
            'Start',
            'Create Chef Environment',
            'Configure bar: 1 (backend)',
            'Configure foo: 0 (frontend)',
            'Wait before deleting cookbooks',
            'Delete Cookbooks',
        ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)

        self.mox.VerifyAll()


class TestMappedSingleWorkflow(test.StubbedWorkflowBase):
    """Test workflow for a single service works

    We're looking to:
    - test using a map file to generate outputs (map and template)
    - tests that option defaults are picked up and sent to outputs.
    - test mysql cookbook and map with outputs
    - test routing data from requires (host/ip) to provides (mysql/host)
    - have a simple, one component test to test the basics if one of the more
      complex tests fails
    """
    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        providers.base.PROVIDER_CLASSES = {}
        providers.register_providers([solo.Provider, test.TestProvider])
        self.deployment = \
            cm_dep.Deployment(utils.yaml_to_dict('''
                id: 'DEP-ID-1000'
                blueprint:
                  name: test db
                  services:
                    db:
                      component:
                        id: mysql
                        constraints:
                        - password: myPassW0rd  # test constraints work
                  resources:
                    admin:
                      type: user
                environment:
                  name: test
                  providers:
                    chef-solo:
                      vendor: opscode
                      constraints:
                      - source: http://mock_url
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            id: linux_instance
                            provides:
                            - compute: linux
                inputs:
                  blueprint:
                    username: u1  # test that this gets used
                    # test that database_name gets provided from defaults
            '''))
        self.deployment['tenantId'] = 'tenantId'
        self.map_file = \
            '''
                id: mysql
                is: database
                requires:
                - host: linux
                options:
                  database_name:
                    required: true
                    default: app_db
                  username:
                    required: true
                    default: root
                  password:
                    type: password
                    default: =generate_password()
                    required: false
                maps:
                # Take inputs and provide them as output using map
                - value: {{ setting('database_name') }}
                  targets:
                  #TODO: find out if users would like writing to attributes
                  #      to happen by default (not needing this next line)
                  - attributes://db_name
                  - outputs://instance:{{resource.index}}/instance/\
interfaces/mysql/database_name
                - value: {{ setting('username') or 'root' }}
                  targets:
                  - attributes://username
                - value: {{ setting('password') or 'password' }}
                  targets:
                  - attributes://password
                # We can route data from requires to provides
                - source: requirements://host:linux/ip
                  targets:
                  - outputs://instance:{{resource.index}}/instance/\
interfaces/mysql/host
                output:
                  instance:{{resource.index}}:
                    name: {{ setting('database_name') }}
                    instance:
                      interfaces:
                        mysql:
                          password: {{ setting('password') }}
                          username: {{ setting('username') }}
            '''

    def test_workflow_task_creation(self):
        self.mox.StubOutWithMock(chef_map.ChefMap, "get_map_file")
        chefmap = chef_map.ChefMap(mox.IgnoreArg())
        chefmap.get_map_file().AndReturn(self.map_file)

        self.mox.ReplayAll()
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)
        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(context,
                                                               self.deployment)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, self.deployment, context, "w_id", "BUILD")
        task_list = workflow.spec.task_specs.keys()
        expected = ['Root',
                    'Start',
                    'Create Chef Environment',
                    'Create Resource 1',
                    'After Environment is Ready and Server 1 (db) is Up',
                    'Register Server 1 (db)',
                    'Pre-Configure Server 1 (db)',
                    'Collect Chef Data for 0',
                    'Configure mysql: 0 (db)',
                    'Delete Cookbooks',
                    ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)
        self.mox.VerifyAll()

        # Make sure hash value was generated
        resources = self.deployment['resources']
        self.assertIn("hash", resources['admin']['instance'])

    def test_workflow_execution(self):
        self.mox.StubOutWithMock(chef_map.ChefMap, "get_map_file")
        chefmap = chef_map.ChefMap(mox.IgnoreArg())
        chefmap.get_map_file().AndReturn(self.map_file)

        self.mox.ReplayAll()
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)
        self.mox.VerifyAll()

        # Create new mox queue for running workflow

        self.mox.ResetAll()
        self.assertEqual(self.deployment.get('status'), 'PLANNED')
        expected_calls = [{
            # Create Chef Environment
            'call': 'checkmate.providers.opscode.solo.tasks'
                    '.create_environment',
            'args': [
                context.get_queued_task_dict(
                    deployment_id=self.deployment['id']),
                self.deployment['id'], 'kitchen'],
            'kwargs': mox.And(
                mox.ContainsKeyValue('private_key', mox.IgnoreArg()),
                mox.ContainsKeyValue('secret_key', mox.IgnoreArg()),
                mox.ContainsKeyValue('public_key_ssh', mox.IgnoreArg())
            ),
            'result': {
                'environment': '/var/tmp/%s/' % self.deployment['id'],
                'kitchen': '/var/tmp/%s/kitchen',
                'private_key_path':
                '/var/tmp/%s/private.pem' % self.deployment['id'],
                'public_key_path':
                '/var/tmp/%s/checkmate.pub' % self.deployment['id'],
                'public_key':
                test.ENV_VARS['CHECKMATE_CLIENT_PUBLIC_KEY']
            }
        }, {
            'call': 'checkmate.providers.opscode.solo.tasks.delete_cookbooks',
            'args': [self.deployment['id'], 'kitchen'],
            'result': None,
            'kwargs': None
        },
        ]
        for key, resource in self.deployment['resources'].iteritems():
            if resource.get('type') == 'compute':
                context_dict = context.get_queued_task_dict(
                    deployment_id=self.deployment['id'],
                    resource_key=resource.get('hosts')[0])
                attributes = {
                    'username': 'u1',
                    'password': 'myPassW0rd',
                    'db_name': 'app_db',
                }
                expected_calls.extend([
                    {
                        # Create Server
                        'call': 'checkmate.providers.test.create_resource',
                        'args': [mox.IsA(dict), mox.IsA(dict)],
                        'kwargs': mox.IgnoreArg(),
                        'result': {
                            'instance:%s' % key: {
                                'id': '1',
                                'password': "shecret",
                                'ip': '4.4.4.4',
                                'instance': {
                                    'interfaces': {
                                        'linux': {
                                            'ip': '4.4.4.4'
                                        }
                                    }
                                }
                            }
                        },
                        'post_back_result': True,
                        'resource': key,
                    },
                    {
                        # Register host - knife prepare
                        'call':
                        'checkmate.providers.opscode.solo.tasks'
                        '.register_node_v2',
                        'args': [
                            context_dict,
                            "4.4.4.4",
                            self.deployment['id'],
                        ],
                        'kwargs': mox.And(
                            mox.In('password'),
                            mox.ContainsKeyValue('attributes', attributes),
                            mox.ContainsKeyValue('bootstrap_version',
                                                 '10.24.0')
                        ),
                        'result': None,
                        'resource': key,
                    },
                    {
                        # Prep host - bootstrap.json means no recipes passed in
                        'call': 'checkmate.providers.opscode.solo.tasks'
                                '.cook_v2',
                        'args': [
                            context_dict,
                            '4.4.4.4',
                            self.deployment['id'],
                        ],
                        'kwargs': mox.And(
                            mox.In('password'),
                            mox.Not(mox.In('recipes')),
                            mox.ContainsKeyValue(
                                'identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id']
                            )
                        ),
                        'result': None
                    }
                ])
            elif resource.get('type') == 'database':
                context_dict = context.get_queued_task_dict(
                    deployment_id=self.deployment['id'],
                    resource_key=key)
                expected_calls.extend([{
                    # Cook mysql
                    'call': 'checkmate.providers.opscode.solo.tasks.cook_v2',
                    'args': [
                        context_dict,
                        '4.4.4.4',
                        self.deployment['id'],
                    ],
                    'kwargs': mox.And(
                        mox.In('password'),
                        mox.ContainsKeyValue('recipes', ['mysql::server']),
                        mox.ContainsKeyValue(
                            'identity_file',
                            '/var/tmp/%s/private.pem' % self.deployment['id']
                        )
                    ),
                    'result': None
                }])
        workflow = self._get_stubbed_out_workflow(
            context=context, expected_calls=expected_calls)

        # Hack to hijack postback in Transform which is called as a string in
        # exec(), so cannot be easily mocked.
        # We make the call hit our deployment directly
        transmerge = workflow.spec.task_specs['Collect Chef Data for 0']
        transmerge.set_property(deployment=self.deployment)
        transmerge.function_name = "tests.providers.opscode.test_solo."\
                                   "do_nothing"

        self.mox.ReplayAll()
        workflow.complete_all()
        self.assertTrue(workflow.is_completed(), msg=workflow.get_dump())
        self.assertDictEqual(self.outcome, {})
        self.mox.VerifyAll()

        final = workflow.get_tasks()[-1]
        expected = utils.yaml_to_dict('''
                chef_options:
                instance:0:
                    name: app_db
                    instance:
                      interfaces:
                        mysql:
                          database_name: app_db      # from mapfile defaults
                          password: myPassW0rd       # from constraints
                          username: u1               # from blueprint settings
                          host: 4.4.4.4              # from host requirement
                    interfaces:                      # add this for v3.0 compat
                      mysql:
                        database_name: app_db
                        password: myPassW0rd
                        username: u1
                        host: 4.4.4.4
            ''')
        self.assertDictEqual(final.attributes['instance:0'],
                             expected['instance:0'])


def do_nothing(self, my_task):
    """Mock method."""
    call_me = 'dep.on_resource_postback(output_template) #'
    source = utils.get_source_body(transforms.Transforms.collect_options)
    source = source.replace('postback.', call_me)
    tabbed_code = '\n    '.join(source.split('\n'))
    func_name = "trans_%s" % uuid.uuid4().hex[0:8]
    exec("def %s(self, my_task):\n    %s"
         "\n%s(self, my_task)" %
         (func_name, tabbed_code, func_name))


class TestMappedMultipleWorkflow(test.StubbedWorkflowBase):
    """Test complex workflows

    We're looking to test:
    - workflows with multiple service that all use map files
    - map file outputs being delivered to dependent components
    - write to databags
    - write to attributes
    - write to roles
    - use run-list
    - multiple components in one service (count>1)
    - use conceptual (foo, bar, widget, etc) catalog, not mysql
    - check client mappings
    """
    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        providers.base.PROVIDER_CLASSES = {}
        providers.register_providers([solo.Provider, test.TestProvider])
        self.deployment = \
            cm_dep.Deployment(utils.yaml_to_dict('''
                id: 'DEP-ID-1000'
                blueprint:
                  name: test app
                  services:
                    frontend:
                      component:
                        id: foo
                      relations:
                        backend: mysql
                    backend:
                      component:
                        id: bar
                environment:
                  name: test
                  providers:
                    chef-solo:
                      vendor: opscode
                      constraints:
                      - source: http://mock_url
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            is: compute
                            provides:
                            - compute: linux
            '''))
        self.deployment['tenantId'] = 'tenantId'
        self.map_file = \
            '''
            \n--- # foo component
                id: foo
                is: application
                requires:
                - database: mysql
                - host: linux
                maps:
                # Simple scalar to attribute
                - value: 10
                  targets:
                  - attributes://widgets
                  - attributes://connections
                # Host requirement resolved at run-time
                - source: requirements://host:linux/ip
                  targets:
                  - attributes://master/ip
                  - outputs://instance:{{resource.index}}/instance/ip
                - source: requirements://host:linux/private_ip
                  targets:
                  - outputs://instance:{{resource.index}}/instance/private_ip
                - source: requirements://host:linux/public_ip
                  targets:
                  - outputs://instance:{{resource.index}}/instance/public_ip
                # Relation requirement resolved at run-time
                - source: requirements://database:mysql/database_name
                  targets:
                  - attributes://db/name
                  - encrypted-databags://app_bag/mysql/db_name
                # Test writing into a role
                - value: 2
                  targets:
                  - roles://foo-master/how-many
                chef-roles:
                  foo-master:
                    recipes:
                    - apt
                    - foo::server
                run-list:
                  roles:
                  - foo-master
                  recipes:
                  - something
                  - something::role
            \n--- # bar component
                id: bar
                is: database
                provides:
                - database: mysql
                maps:
                - value: foo-db
                  targets:
                  - outputs://instance:{{resource.index}}/instance/\
interfaces/mysql/database_name
                - source: clients://database:mysql/ip
                  targets:
                  - attributes://connections
            '''

    def test_workflow_task_creation(self):
        self.mox.StubOutWithMock(chef_map.ChefMap, "get_map_file")
        chefmap = chef_map.ChefMap(mox.IgnoreArg())
        chefmap.get_map_file().AndReturn(self.map_file)

        self.mox.ReplayAll()
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)
        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(context,
                                                               self.deployment)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, self.deployment, context, "w_id", "BUILD")
        collect_task = workflow.spec.task_specs['Collect Chef Data for 0']
        ancestors = collect_task.ancestors()
        host_done = workflow.spec.task_specs['Configure bar: 2 (backend)']
        self.assertIn(host_done, ancestors)
        task_list = workflow.spec.task_specs.keys()
        expected = [
            'Root',
            'Start',
            'Create Chef Environment',
            'Create Resource 1',
            'After Environment is Ready and Server 1 (frontend) is Up',
            'Register Server 1 (frontend)',
            'Pre-Configure Server 1 (frontend)',
            'Collect Chef Data for 2',
            'Configure bar: 2 (backend)',
            'Collect Chef Data for 0',
            'Write Data Bag for 0',
            'Write Role foo-master for 0',
            'Configure foo: 0 (frontend)',
            'Reconfig Chef Data for 2',
            'Reconfigure bar: client ready',
            'Wait before deleting cookbooks',
            'Delete Cookbooks',
        ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)
        self.mox.VerifyAll()

        # Make sure maps are correct
        transmerge = workflow.spec.task_specs['Collect Chef Data for 0']
        expected = {
            'resource': '0',
            'deployment': 'DEP-ID-1000',
            'provider': 'chef-solo',
            'task_tags': ['collect'],
            'extend_lists': True,
            'chef_options': {
                'roles': {
                    'foo-master': {'how-many': 2}}},
            'chef_output': None,
            'chef_maps': [
                {
                    'source': 'requirements://host:linux/ip',
                    'targets': ['attributes://master/ip',
                                'outputs://instance:0/instance/ip'],
                    'path': 'instance:1',
                    'resource': '0',
                },
                {
                    'source': 'requirements://host:linux/private_ip',
                    'targets': ['outputs://instance:0/instance/private_ip'],
                    'path': 'instance:1',
                    'resource': '0',
                },
                {
                    'source': 'requirements://host:linux/public_ip',
                    'targets': ['outputs://instance:0/instance/public_ip'],
                    'path': 'instance:1',
                    'resource': '0',
                },
                {
                    'source': 'requirements://database:mysql/database_name',
                    'targets': ['attributes://db/name',
                                'encrypted-databags://app_bag/mysql/db_name'],
                    'path': 'instance:2/interfaces/mysql',
                    'resource': '0',
                }
            ]
        }
        self.assertDictEqual(transmerge.properties, expected)

        transmerge = workflow.spec.task_specs['Collect Chef Data for 2']
        expected = {
            'resource': '2',
            'deployment': 'DEP-ID-1000',
            'provider': 'chef-solo',
            'task_tags': ['collect', 'options-ready'],
            'extend_lists': True,
            'chef_options': {
                'outputs': {
                    'instance:2': {
                        'instance': {
                            'interfaces': {
                                'mysql': {
                                    'database_name': 'foo-db'
                                }
                            }
                        }
                    }
                }
            },
            'chef_output': None,
            'chef_maps': [{
                'path': 'instance:0',
                'resource': '2',
                'source': 'clients://database:mysql/ip',
                'targets': ['attributes://connections']
            }]
        }
        self.assertDictEqual(transmerge.properties, expected)

        # Make sure plan-time data is correct
        register = workflow.spec.task_specs['Register Server 1 (frontend)']
        expected = {
            'resource': '0',
            'provider': 'chef-solo',
            'relation': 'host',
            'estimated_duration': 120
        }
        self.assertDictEqual(register.properties, expected)
        self.assertDictEqual(register.kwargs['attributes'], {'connections': 10,
                                                             'widgets': 10})

        # Make sure role is being created
        role = workflow.spec.task_specs['Write Role foo-master for 0']
        expected = ['recipe[apt]', 'recipe[foo::server]']
        self.assertListEqual(role.kwargs['run_list'], expected)

    def test_cook_tasks_should_have_merge_results_set_to_true(self):
        self.mox.StubOutWithMock(chef_map.ChefMap, "get_map_file")
        chefmap = chef_map.ChefMap(mox.IgnoreArg())
        chefmap.get_map_file().AndReturn(self.map_file)

        self.mox.ReplayAll()
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)
        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(context,
                                                               self.deployment)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, self.deployment, context, "w_id", "BUILD")

        self.assertTrue(workflow.spec.task_specs[
            "Pre-Configure Server 1 (frontend)"].merge_results)
        self.assertTrue(workflow.spec.task_specs[
            "Configure bar: 2 (backend)"].merge_results)
        self.assertTrue(workflow.spec.task_specs[
            "Configure foo: 0 (frontend)"].merge_results)
        self.assertTrue(workflow.spec.task_specs[
            "Reconfigure bar: client ready"].merge_results)

    def test_workflow_execution(self):
        self.mox.StubOutWithMock(chef_map.ChefMap, "get_map_file")
        chefmap = chef_map.ChefMap(mox.IgnoreArg())
        chefmap.get_map_file().AndReturn(self.map_file)

        # Plan deployment
        self.mox.ReplayAll()
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)
        self.mox.VerifyAll()

        # Create new mox queue for running workflow
        self.mox.ResetAll()
        self.assertEqual(self.deployment.get('status'), 'PLANNED')

        expected_calls = [{
            # Create Chef Environment
            'call': 'checkmate.providers.opscode.solo.tasks'
                    '.create_environment',
            'args': [
                context.get_queued_task_dict(
                    deployment_id=self.deployment['id']),
                self.deployment['id'], 'kitchen'],
            'kwargs': mox.And(
                mox.ContainsKeyValue('private_key', mox.IgnoreArg()),
                mox.ContainsKeyValue('secret_key', mox.IgnoreArg()),
                mox.ContainsKeyValue('public_key_ssh', mox.IgnoreArg())
            ),
            'result': {
                'environment': '/var/tmp/%s/' % self.deployment['id'],
                'kitchen': '/var/tmp/%s/kitchen',
                'private_key_path':
                '/var/tmp/%s/private.pem' % self.deployment['id'],
                'public_key_path':
                '/var/tmp/%s/checkmate.pub' % self.deployment['id'],
                'public_key':
                test.ENV_VARS['CHECKMATE_CLIENT_PUBLIC_KEY']
            }
        }, {
            'call': 'checkmate.providers.opscode.solo.tasks.delete_cookbooks',
            'args': [self.deployment['id'], 'kitchen'],
            'result': None,
            'kwargs': None
        },
        ]
        for key, resource in self.deployment['resources'].iteritems():
            if resource.get('type') == 'compute':
                context_dict = context.get_queued_task_dict(
                    deployment_id=self.deployment['id'],
                    resource_key=resource.get('hosts')[0])
                expected_calls.extend([
                    {
                        'call':
                        'checkmate.providers.opscode.solo.tasks'
                        '.register_node_v2',
                        'args': [
                            context_dict,
                            "4.4.4.4",
                            self.deployment['id'],
                        ],
                        'kwargs': mox.And(
                            mox.In('password'),
                            mox.ContainsKeyValue('bootstrap_version',
                                                 '10.24.0'),
                            mox.ContainsKeyValue(
                                'attributes',
                                {'connections': 10, 'widgets': 10}
                            )
                        ),
                        'result': None,
                        'resource': key,
                    },
                    {
                        # Prep foo - bootstrap.json
                        'call': 'checkmate.providers.opscode.solo.tasks'
                                '.cook_v2',
                        'args': [
                            context_dict,
                            '4.4.4.4',
                            self.deployment['id'],
                        ],
                        'kwargs': mox.And(
                            mox.In('password'),
                            mox.Not(mox.ContainsKeyValue('recipes', ['foo'])),
                            mox.ContainsKeyValue(
                                'identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id']
                            )
                        ),
                        'result': None
                    },
                    {
                        # Create Server
                        'call': 'checkmate.providers.test.create_resource',
                        'args': [mox.IsA(dict), mox.IsA(dict)],
                        'kwargs': mox.IgnoreArg(),
                        'result': {
                            'instance:%s' % key: {
                                'id': '1',
                                'password': "shecret",
                                'ip': '4.4.4.4',
                                'instance': {
                                    'interfaces': {
                                        'linux': {
                                            'password': "shecret",
                                            'ip': '4.4.4.4',
                                        }
                                    }
                                }
                            }
                        },
                        'post_back_result': True,
                        'resource': key,
                    }
                ])
            elif resource.get('type') == 'application':
                context_dict = context.get_queued_task_dict(
                    deployment_id=self.deployment['id'],
                    resource_key=key)
                expected_calls.extend([
                    {
                        # Write foo databag item
                        'call':
                        'checkmate.providers.opscode.solo.tasks'
                        '.write_databag_v2',
                        'args': [
                            context_dict, 'DEP-ID-1000', 'app_bag', 'mysql',
                            {'db_name': 'foo-db'}
                        ],
                        'kwargs': {
                            'secret_file': 'certificates/chef.pem'
                        },
                        'result': None
                    },
                    {
                        # Write foo-master role
                        'call':
                        'checkmate.providers.opscode.solo.tasks.'
                        'manage_role_v2',
                        'args': [context_dict, 'foo-master', 'DEP-ID-1000'],
                        'kwargs': {
                            'run_list': ['recipe[apt]', 'recipe[foo::server]'],
                            'override_attributes': {'how-many': 2},
                            'kitchen_name': 'kitchen',
                        },
                        'result': None
                    },
                    {
                        # Cook foo - run using runlist
                        'call': 'checkmate.providers.opscode.solo.tasks'
                                '.cook_v2',
                        'args': [
                            context_dict,
                            '4.4.4.4',
                            self.deployment['id'],
                        ],
                        'kwargs': mox.And(
                            mox.In('password'),
                            mox.ContainsKeyValue(
                                'recipes',
                                ['something', 'something::role']
                            ),
                            mox.ContainsKeyValue('roles', ['foo-master']),
                            mox.ContainsKeyValue(
                                'attributes',
                                {
                                    'master': {'ip': '4.4.4.4'},
                                    'db': {'name': 'foo-db'},
                                }
                            ),
                            mox.ContainsKeyValue(
                                'identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id']
                            ),
                        ),
                        'result': None
                    }
                ])
            elif resource.get('type') == 'database':
                context_dict = context.get_queued_task_dict(
                    deployment_id=self.deployment['id'],
                    resource_key=key)
                expected_calls.extend([
                    {
                        # Cook bar
                        'call': 'checkmate.providers.opscode.solo.tasks'
                                '.cook_v2',
                        'args': [
                            context_dict,
                            None,
                            self.deployment['id'],
                        ],
                        'kwargs': mox.And(
                            mox.In('password'),
                            mox.ContainsKeyValue('recipes', ['bar']),
                            mox.ContainsKeyValue(
                                'identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id']
                            )
                        ),
                        'result': None
                    },
                    {
                        # Re-cook bar
                        'call': 'checkmate.providers.opscode.solo.tasks'
                                '.cook_v2',
                        'args': [
                            context_dict,
                            None,
                            self.deployment['id'],
                        ],
                        'kwargs': mox.And(
                            mox.In('password'),
                            mox.ContainsKeyValue('recipes', ['bar']),
                            mox.ContainsKeyValue(
                                'identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id']
                            )
                        ),
                        'result': None
                    }
                ])
        workflow = self._get_stubbed_out_workflow(
            context=context, expected_calls=expected_calls)

        # Hack to hijack postback in Transform which is called as a string in
        # exec(), so cannot be easily mocked.
        # We make the call hit our deployment directly
        for task_name in [
            'Collect Chef Data for 0',
            'Collect Chef Data for 2',
            'Reconfig Chef Data for 2',
        ]:
            transmerge = workflow.spec.task_specs[task_name]
            transmerge.set_property(deployment=self.deployment)
            transmerge.function_name = "tests.providers.opscode.test_solo." \
                                       "do_nothing"

        self.mox.ReplayAll()
        workflow.complete_all()
        self.assertTrue(workflow.is_completed(), msg=workflow.get_dump())
        expected = {'data_bags': {'app_bag': {'mysql': {'db_name': 'foo-db'}}}}
        self.assertDictEqual(self.outcome, expected)

        found = False
        for task in workflow.get_tasks():
            if task.get_name() == "Reconfig Chef Data for 2":
                connections = (
                    task.attributes.get('chef_options', {}).get(
                        'attributes:2', {}).get('connections')
                )
                if connections == ['4.4.4.4']:
                    found = True
                self.assertNotEqual(connections, 10, "Foo attribute written "
                                                     "to Bar")
        self.assertTrue(found, "Client IPs expected in 'connecitons' for bar")

        for task in workflow.get_tasks():
            if task.get_name() == "Collect Chef Data for 0":
                connections = (
                    task.attributes.get('chef_options', {}).get(
                        'attributes:0', {}).get('connections')
                )
                self.assertNotEqual(connections, ['4.4.4.4'],
                                    "Bar attribute written to Foo")

        register = workflow.spec.task_specs["Register Server 1 (frontend)"]
        connections = (register.kwargs.get('attributes', {}).
                       get('connections'))
        self.assertEqual(connections, 10,
                         "Foo attribute not written")

        self.mox.VerifyAll()


class TestTransform(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_write_attribute(self):
        maps = utils.yaml_to_dict('''
                # Simple scalar to attribute
                - value: 10
                  targets:
                  - attributes://widgets
                  resource: '0'
            ''')
        fxn = transforms.Transforms.collect_options
        task = self.mox.CreateMockAnything()
        spec = self.mox.CreateMockAnything()
        spec.get_property('chef_maps', []).AndReturn(maps)
        spec.get_property('chef_options', {}).AndReturn({})
        spec.get_property('chef_output').AndReturn({})
        results = {}
        task.attributes = results
        self.mox.ReplayAll()
        result = fxn(spec, task)
        self.mox.VerifyAll()
        self.assertTrue(result)  # task completes
        expected = {'chef_options': {'attributes:0': {'widgets': 10}}}
        self.assertDictEqual(results, expected)

    def test_write_output_template(self):
        output = utils.yaml_to_dict('''
                  'instance:0':
                    name: test
                    instance:
                      interfaces:
                        mysql:
                          database_name: db1
            ''')

        self.mox.StubOutWithMock(deployments.resource_postback, "delay")
        fxn = transforms.Transforms.collect_options
        task = self.mox.CreateMockAnything()
        spec = self.mox.CreateMockAnything()
        spec.get_property('chef_maps', []).AndReturn([])
        spec.get_property('chef_options', {}).AndReturn({})
        spec.get_property('chef_output').AndReturn(output or {})
        spec.get_property('deployment').AndReturn(1)
        deployments.resource_postback.delay(mox.IgnoreArg(),
                                            mox.IgnoreArg()).AndReturn(None)
        results = {}
        task.attributes = results
        self.mox.ReplayAll()
        result = fxn(spec, task)
        self.mox.VerifyAll()
        self.assertTrue(result)  # task completes
        expected = utils.yaml_to_dict('''
                  'instance:0':
                    name: test
                    instance:
                      interfaces:
                        mysql:
                          database_name: db1
            ''')
        self.assertDictEqual(results, expected)


class TestChefMapEvaluator(unittest.TestCase):
    def test_scalar_evaluation(self):
        chefmap = chef_map.ChefMap(parsed="")
        result = chefmap.evaluate_mapping_source({'value': 10}, None)
        self.assertEqual(result, 10)

    def test_requirement_evaluation(self):
        chefmap = chef_map.ChefMap(parsed="")
        mapping = {
            'source': 'requirements://host/ip',
            'path': 'instance:1'
        }
        data = {'instance:1': {'ip': '4.4.4.4'}}
        result = chefmap.evaluate_mapping_source(mapping, data)
        self.assertEqual(result, '4.4.4.4')

    def test_client_evaluation(self):
        chefmap = chef_map.ChefMap(parsed="")
        mapping = {
            'source': 'clients://host/ip',
            'path': 'instance:1'
        }
        data = {'instance:1': {'ip': '4.4.4.4'}}
        result = chefmap.evaluate_mapping_source(mapping, data)
        self.assertEqual(result, '4.4.4.4')


class TestChefMapApplier(unittest.TestCase):
    def test_output_writing(self):
        chefmap = chef_map.ChefMap(parsed="")
        mapping = {'targets': ['outputs://ip']}
        result = {}
        chefmap.apply_mapping(mapping, '4.4.4.4', result)
        self.assertEqual(result, {'outputs': {'ip': '4.4.4.4'}})


class TestChefMapResolver(unittest.TestCase):
    def test_resolve_ready_maps(self):
        maps = utils.yaml_to_dict('''
                - value: 1
                  resource: '0'
                  targets:
                  - attributes://simple
                - source: requirements://key/path/value
                  path: instance:1/location
                  resource: '0'
                  targets:
                  - attributes://ready
                - source: requirements://key/path/value
                  path: instance:2/location
                  resource: '0'
                  targets:
                  - attributes://not
                ''')
        data = utils.yaml_to_dict('''
                instance:1:
                  location:
                    path:
                      value: 8
                ''')
        result = {}
        unresolved = chef_map.ChefMap.resolve_ready_maps(maps, data, result)
        expected = {'attributes:0': {'ready': 8, 'simple': 1}}
        self.assertDictEqual(result, expected)
        self.assertListEqual(unresolved, [maps[2]])


class TestCatalog(unittest.TestCase):
    """Test catalog functionality (remote)."""
    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_remote_catalog_sourcing(self):
        solo_provider = \
            solo.Provider(utils.yaml_to_dict('''
                vendor: opscode
                constraints:
                - source: git://gh.acme.com/user/repo.git#branch
                '''))
        self.mox.StubOutWithMock(chef_map.ChefMap, "get_map_file")
        chefmap = chef_map.ChefMap(mox.IgnoreArg())
        chefmap.get_map_file().AndReturn(TEMPLATE)
        self.mox.ReplayAll()

        response = solo_provider.get_catalog(middleware.RequestContext())

        self.assertListEqual(
            response.keys(), ['application', 'database'])
        self.assertListEqual(response['application'].keys(), ['webapp'])
        self.assertListEqual(response['database'].keys(), ['mysql'])
        self.mox.VerifyAll()


class TestMapTemplating(unittest.TestCase):
    """Chef maps with templating work correctly."""
    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_parsing_scalar(self):
        map = chef_map.ChefMap('')
        map._raw = '''
            {% set id = 'foo' %}
            id: {{ id }}
            maps:
            - value: {{ 1 }}
              targets:
              - attributes://{{ 'here' }}
        '''
        self.assertDictEqual(map.get_attributes('foo', None), {'here': 1})

    def test_parsing_functions_parse_url(self):
        map = chef_map.ChefMap('')
        map._raw = '''
            id: foo
            maps:
            - value: {{ 1 }}
              targets:
              - attributes://here
            \n--- # component bar
            id: bar
            maps:
            - value: {{ parse_url('http://github.com').scheme }}
              targets:
              - attributes://scheme
            - value: {{ parse_url('http://github.com').netloc }}
              targets:
              - attributes://netloc
            - value: {{ parse_url('http://github.com/checkmate').path }}
              targets:
              - attributes://path
              - attributes://{{ parse_url('http://local/a/b/c/d').path }}
            - value: {{ parse_url('http://github.com/#master').fragment }}
              targets:
              - attributes://fragment
        '''
        result = map.get_attributes('bar', None)
        expected = {
            'scheme': 'http',
            'netloc': 'github.com',
            'fragment': 'master',
            'path': '/checkmate',
            'a': {'b': {'c': {'d': '/checkmate'}}}
        }
        self.assertDictEqual(result, expected)

    def test_parsing_functions_parse_url_Input(self):
        map = chef_map.ChefMap('')
        map._raw = '''
            id: foo
            maps:
            - value: {{ 1 }}
              targets:
              - attributes://here
            \n--- # component bar
            id: bar
            maps:
            - value: {{ parse_url({'url': 'http://github.com', 'certificate': \
'TEST_CERT'}).certificate }}
              targets:
              - attributes://cert_target/certificate
            - value: {{ parse_url({'url': 'http://github.com', 'certificate': \
'TEST_CERT'}).protocol }}
              targets:
              - attributes://protocol_target/scheme
        '''
        result = map.get_attributes('bar', None)
        expected = {
            'protocol_target': {
                'scheme': 'http',
            },
            'cert_target': {
                'certificate': 'TEST_CERT',
            },
        }
        self.assertDictEqual(result, expected)

    def test_parsing_functions_url_certificate(self):
        cert = """-----BEGIN CERTIFICATE-----
MIICkjCCAfsCAgXeMA0GCSqGSIb3DQEBBQUAMIG2MQswCQYDVQQGEwJVUzEOMAwG
A1UECBMFVGV4YXMxFDASBgNVBAcTC1NhbiBBbnRvbmlvMRIwEAYDVQQKEwlSYWNr
c3BhY2UxHjAcBgNVBAsTFVN5c3RlbSBBZG1pbmlzdHJhdGlvbjEjMCEGA1UEAxMa
UmFja3NwYWNlIEludGVybmFsIFJvb3QgQ0ExKDAmBgkqhkiG9w0BCQEWGVNlcnZp
Y2VEZXNrQHJhY2tzcGFjZS5jb20wHhcNMTMwNTE2MDYxMDQ3WhcNMTQwNTE2MDYx
MDQ3WjBrMQswCQYDVQQGEwJVUzEOMAwGA1UECBMFVGV4YXMxEjAQBgNVBAoTCVJh
Y2tzcGFjZTEVMBMGA1UECxMMWmlhZCBTYXdhbGhhMSEwHwYDVQQDExhjaGVja21h
dGUuY2xvdWQuaW50ZXJuYWwwgZ8wDQYJKoZIhvcNAQEBBQADgY0AMIGJAoGBALin
K4gUwoQVt6mapFqmFBHAL1YUqabjWeyQNGD4Vt7L9XVgh6l1k+uqdzOKP7vlKh+T
diUnDh/VTpq8HZ+bHI8HhDLLIXG61+3LDa+CkgRi4RuwgWIUUY7rs9rUCnJ2HeYa
gRR+moptp+OK9rIwPv0k4O2Q29efBnZaL5Yyk3dPAgMBAAEwDQYJKoZIhvcNAQEF
BQADgYEAYxnk0LCk+kZB6M93Cr4Br0brE/NvNguJVoep8gb1sHI0bbnKY9yAfwvF
0qrcpuTvCS7ggfg1nCtXteJiYsRxZaleQeQSXBswXT3s3ZrUR9RSRPfGqJ9XiGlz
/YrPhnGGC24lpqLV8lBZkLsdnnoKwQfI+aRGbg0x2pi+Zh22H8U=
-----END CERTIFICATE-----
"""
        deployment = cm_dep.Deployment({
            'inputs': {
                'blueprint': {
                    'url': {
                        'url': 'http://github.com',
                        'certificate': cert,
                    },
                },
            },
            'blueprint': {},
        })
        map = chef_map.ChefMap('')
        map._raw = '''
            id: foo
            maps:
            - value: |
                {{ parse_url(setting('url')).certificate  | indent(16) }}
              targets:
              - attributes://cert_target/certificate
            - value: {{ parse_url(setting('url')).protocol }}
              targets:
              - attributes://protocol_target/scheme
        '''
        result = templating.parse(map.raw, deployment=deployment)
        data = yaml.safe_load(result)
        self.assertEqual(data['maps'][0]['value'], cert)

    def test_parsing_functions_hash(self):
        map = chef_map.ChefMap('')
        map._raw = '''
            id: foo
            maps:
            - value: {{ hash('password', salt='ahem1234') }}
              targets:
              - attributes://here
        '''
        self.assertDictEqual(
            map.get_attributes('foo', None),
            {
                'here':
                '$6$rounds=60000$ahem1234$6SJb7IPwxFdrqAKZIK4Q3yAxkHc'
                'VCGXgwE2Onzrxwgzsb3LANHxMdrGlS05MYjT/ncgo6xIH1Pm1dqS'
                'tJWqoY/'
            }
        )


TEMPLATE = \
    """# vim: set filetype=yaml syntax=yaml:
# Global function
{% set app_id = deployment.id + '_app' %}

--- # first component
id: webapp
provides:
- application: http
requires:
- host: linux
- database: mysql
options:
  "site_name":
    type: string
    sample: "Bob's tire shop"
    required: false
run-list:
  recipes:
  - first
maps:
- value: {{ setting('site_name') }}
  targets:
  - attributes://webapp/site/name
- source: requirements://database:mysql/database_name
  targets:
  - attributes://webapp/db/name
- source: requirements://database:mysql/username
  targets:
  - attributes://webapp/db/user
- source: requirements://database:mysql/host
  targets:
  - attributes://webapp/db/host
- source: requirements://database:mysql/password
  targets:
  - attributes://webapp/db/password
- source: requirements://database:mysql/root_password
  targets:
  - attributes://mysql/server_root_password

--- # second component map
id: mysql
is: database
provides:
- database: mysql
requires:
- host: linux
options:
  "database_name":
    type: string
    default: db1
    required: true
  "database_user":
    type: string
    default: db_user
    required: true
  "database_password":
    type: password
    default: =generate_password()
    required: true
chef-roles:
  mysql-master:
    create: true
    recipes:
    - apt
    - mysql::server
    - holland
    - holland::common
    - holland::mysqldump
maps:
- value: {{ setting('server_root_password') }}
  targets:
  - encrypted-databag://{{app_id}}/mysql/server_root_password
  - output://{{resource.index}}/instance/interfaces/mysql/root_password
- source: requirements://database/hostname  # database is defined in component
  targets:
  - encrypted-databag://{{deployment.id}}//{{app_id}}/mysql/host
- source: requirements://host/instance/ip
  targets:
  - output://{{resource.index}}/instance/interfaces/mysql/host
- source: requirements://database:mysql/database_user
  targets:
  - encrypted-databag://{{app_id}}/mysql/username
  - output://{{resource.index}}/instance/interfaces/mysql/username
- value: {{ setting('database_password') }}
  targets:
  - encrypted-databag://{{app_id}}/mysql/password
  - output://{{resource.index}}/instance/interfaces/mysql/password
- value: {{ deployment.id }} # Deployment ID needs to go to Node Attribute
  targets:
  - attributes://deployment/id
output:
  '{{resource.index}}':
    name: {{ setting('database_name') }}
    instance:
      interfaces:
        mysql:
          database_name: {{ setting('database_name') }}
"""


if __name__ == '__main__':
    test.run_with_params()
