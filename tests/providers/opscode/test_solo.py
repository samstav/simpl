# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''Tests for chef-solo provider'''

import __builtin__
import hashlib
import json
import logging
import os
import shutil
import unittest
from urlparse import urlunparse
import uuid
import yaml

import mox
from mox import In, IsA, And, IgnoreArg, ContainsKeyValue, Not
from SpiffWorkflow.util import merge_dictionary  # HACK: used by transform

import checkmate
from checkmate.deployment import Deployment
from checkmate import deployments
from checkmate.middleware import RequestContext
from checkmate.providers import base, register_providers
from checkmate.providers.opscode import solo, knife
from checkmate import test
from checkmate import utils
from checkmate.workflow import init_spiff_workflow, create_workflow_spec_deploy


LOG = logging.getLogger(__name__)


class TestChefSoloProvider(test.ProviderTester):

    klass = solo.Provider

    def test_get_resource_prepared_maps(self):
        base.PROVIDER_CLASSES = {}
        register_providers([solo.Provider, test.TestProvider])
        deployment = Deployment(utils.yaml_to_dict('''
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
        chef_map = solo.ChefMap(raw='''
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
        deployments.Manager.plan(deployment, RequestContext())
        provider = deployment.environment().get_provider('chef-solo')

        # Check requirement map

        resource = deployment['resources']['0']  # one of the mysql clients
        result = provider.get_resource_prepared_maps(
            resource, deployment, map_file=chef_map)
        expected = [{'source': 'requirements://database:mysql/ip',
                     'targets': ['attributes://ip'],
                     'path': 'instance:2/interfaces/mysql',
                     'resource': '0',
                     }]
        self.assertListEqual(result, expected)

        # Check client maps

        resource = deployment['resources']['2']  # mysql database w/ 2 clients
        result = provider.get_resource_prepared_maps(
            resource, deployment, map_file=chef_map)
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
        '''Make sure defaults get evaluated correctly'''
        provider = solo.Provider({})
        deployment = Deployment(utils.yaml_to_dict('''
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
        chefmap = solo.ChefMap(raw='''
                id: test
                options:
                  password:
                    default: =generate_password()
                output:
                  component: {{ setting('password') }}
                  blueprint: {{ setting('bp_password') }}
            ''')
        provider.map_file = chefmap
        component = chefmap.components[0]

        self.mox.StubOutWithMock(provider, 'evaluate')
        provider.evaluate('generate_password()').AndReturn("RandomPass")

        self.mox.StubOutWithMock(solo.ProviderBase, 'evaluate')
        solo.ProviderBase.evaluate('generate_password()').AndReturn("randp2")

        resource = {
            'type': 'application',
            'service': 'foo',
            'provider': 'chef-solo',
        }
        self.mox.ReplayAll()
        context = provider.get_map_with_context(component=component,
                                                deployment=deployment,
                                                resource=resource)
        output = context.get_component_output_template("test")
        self.assertEqual(output['component'], "RandomPass")
        self.assertEqual(output['blueprint'], "randp2")
        self.mox.VerifyAll()


class TestCeleryTasks(unittest.TestCase):

    ''' Test Celery tasks '''

    def setUp(self):
        self.mox = mox.Mox()
        self.original_local_path = os.environ.get('CHECKMATE_CHEF_LOCAL_PATH')
        os.environ['CHECKMATE_CHEF_LOCAL_PATH'] = '/tmp/checkmate-chefmap'
        self.local_path = '/tmp/checkmate-chefmap'

    def tearDown(self):
        self.mox.UnsetStubs()
        if os.path.exists(self.local_path):
            shutil.rmtree('/tmp/checkmate-chefmap')
        if self.original_local_path:
            os.environ['CHECKMATE_CHEF_LOCAL_PATH'] = self.original_local_path

    def test_cook(self):
        '''Test that cook task picks up run_list and attributes'''
        root_path = os.environ['CHECKMATE_CHEF_LOCAL_PATH']
        environment_path = os.path.join(root_path, "env_test")
        kitchen_path = os.path.join(environment_path, "kitchen")
        node_path = os.path.join(kitchen_path, "nodes", "a.b.c.d.json")

        #Stub out checks for paths
        self.mox.StubOutWithMock(knife, '_get_root_environments_path')
        knife._get_root_environments_path(
            "env_test", None).AndReturn(root_path)
        self.mox.StubOutWithMock(os.path, 'exists')
        os.path.exists(kitchen_path).AndReturn(True)
        os.path.exists(node_path).AndReturn(True)

        #Stub out file access
        mock_file = self.mox.CreateMockAnything()
        mock_file.__enter__().AndReturn(mock_file)
        mock_file.__exit__(None, None, None).AndReturn(None)

        #Stub out file reads
        node = json.loads('{ "run_list": [] }')
        self.mox.StubOutWithMock(json, 'load')
        json.load(mock_file).AndReturn(node)

        #Stub out file write
        mock_file.__enter__().AndReturn(mock_file)
        self.mox.StubOutWithMock(json, 'dump')
        json.dump(
            And(
                ContainsKeyValue(
                    'run_list',
                    ['role[role1]', 'recipe[recipe1]']
                ),
                ContainsKeyValue('id', 1)
            ),
            mock_file
        ).AndReturn(None)
        mock_file.__exit__(None, None, None).AndReturn(None)

        #Stub out file opens
        self.mox.StubOutWithMock(__builtin__, 'file')
        __builtin__.file(node_path, 'r').AndReturn(mock_file)
        __builtin__.file(node_path, 'w').AndReturn(mock_file)

        #Stub out process call to knife
        params = ['knife', 'solo', 'cook', 'root@a.b.c.d',
                  '-c', os.path.join(kitchen_path, "solo.rb"),
                  '-p', '22']
        self.mox.StubOutWithMock(knife, '_run_kitchen_command')
        knife._run_kitchen_command(
            "env_test", kitchen_path, params).AndReturn("OK")

        #TODO: better test for postback?
        #Stub out call to resource_postback
        self.mox.StubOutWithMock(knife.resource_postback, 'delay')
        knife.resource_postback.delay(IgnoreArg(), IgnoreArg()).AndReturn(True)
        knife.resource_postback.delay(IgnoreArg(), IgnoreArg()).AndReturn(True)

        self.mox.ReplayAll()
        resource = {'index': 1234, 'hosted_on': 'rack cloud'}
        knife.cook(
            "a.b.c.d", "env_test", resource, roles=['role1'],
            recipes=['recipe1'], attributes={'id': 1}
        )
        self.mox.VerifyAll()


class TestMySQLMaplessWorkflow(test.StubbedWorkflowBase):

    '''

    Test that cookbooks can be used without a map file (only catalog)

    This test is done using the MySQL cookbook. This is a very commonly used
    cookbook.

    '''

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        register_providers([solo.Provider, test.TestProvider])
        self.deployment = Deployment(utils.yaml_to_dict('''
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
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)

    def test_workflow_task_generation(self):
        '''Verify workflow task creation'''
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        workflow_spec = create_workflow_spec_deploy(self.deployment, context)
        workflow = init_spiff_workflow(workflow_spec, self.deployment, context)

        task_list = workflow.spec.task_specs.keys()
        expected = ['Root',
                    'Start',
                    'Create Chef Environment',
                    'Create Resource 1',
                    'After Environment is Ready and Server 1 (db) is Up',
                    'Pre-Configure Server 1 (db)',
                    'Register Server 1 (db)',
                    'After server 1 (db) is registered and options are ready',
                    'Configure mysql: 0 (db)']
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)

    def test_workflow_completion(self):
        '''Verify workflow sequence and data flow'''

        expected = []

        # Create Chef Environment

        expected.append({
            # Use chef-solo tasks for now
            # Use only one kitchen. Call it "kitchen" like we used to
            'call': 'checkmate.providers.opscode.knife.create_environment',
            'args': [self.deployment['id'], 'kitchen'],
            'kwargs': And(
                ContainsKeyValue('private_key', IgnoreArg()),
                ContainsKeyValue('secret_key', IgnoreArg()),
                ContainsKeyValue(
                    'public_key_ssh',
                    IgnoreArg()
                ),
                ContainsKeyValue('source_repo', IgnoreArg())
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

        for key, resource in self.deployment['resources'].iteritems():
            if resource['type'] == 'compute':
                expected.append({
                    'call': 'checkmate.providers.test.create_resource',
                    'args': [IsA(dict), resource],
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
                    'call': 'checkmate.providers.opscode.knife.register_node',
                    'args': [
                        '4.4.4.1',
                        self.deployment['id'],
                        ContainsKeyValue('index', IgnoreArg())
                    ],
                    'kwargs': And(
                        In('password'),
                        ContainsKeyValue('omnibus_version', '10.24.0')
                    ),
                    'result': None,
                    'resource': key,
                })

                # build-essential (now just cook with bootstrap.json)

                expected.append({
                    'call': 'checkmate.providers.opscode.knife.cook',
                    'args': [
                        '4.4.4.1',
                        self.deployment['id'],
                        ContainsKeyValue('index', IgnoreArg())
                    ],
                    'kwargs': And(
                        In('password'),
                        Not(In('recipes')),
                        Not(In('roles')),
                        ContainsKeyValue(
                            'identity_file',
                            '/var/tmp/%s/private.pem' % self.deployment['id']
                        )
                    ),
                    'result': None,
                    'resource': key,
                })
            else:

                # Cook with cookbook (special mysql handling calls server role)

                expected.append({
                    'call': 'checkmate.providers.opscode.knife.cook',
                    'args': [
                        '4.4.4.1',
                        self.deployment['id'],
                        ContainsKeyValue('index', IgnoreArg())
                    ],
                    'kwargs': And(
                        In('password'),
                        ContainsKeyValue('recipes', ['mysql::server']),
                        ContainsKeyValue(
                            'identity_file',
                            '/var/tmp/%s/private.pem' % self.deployment['id']
                        )
                    ),
                    'result': None,
                    'resource': key,
                })

        self.workflow = self._get_stubbed_out_workflow(expected_calls=expected)

        self.mox.ReplayAll()

        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(),
                        'Workflow did not complete')

        self.mox.VerifyAll()


class TestMapfileWithoutMaps(test.StubbedWorkflowBase):

    '''Test that map file works without maps (was 'checkmate.json')'''

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        register_providers([solo.Provider, test.TestProvider])
        self.deployment = \
            Deployment(utils.yaml_to_dict('''
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
        '''Verify workflow sequence and data flow'''

        self.mox.StubOutWithMock(solo.ChefMap, "get_map_file")
        chefmap = solo.ChefMap(IgnoreArg())
        chefmap.get_map_file().AndReturn(self.map_file)

        self.mox.ReplayAll()

        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)

        workflow_spec = create_workflow_spec_deploy(self.deployment, context)
        workflow = init_spiff_workflow(workflow_spec, self.deployment, context)

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
        ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)

        self.mox.VerifyAll()


class TestMappedSingleWorkflow(test.StubbedWorkflowBase):
    '''

    Test workflow for a single service works

    We're looking to:
    - test using a map file to generate outputs (map and template)
    - tests that option defaults are picked up and sent to outputs.
    - test mysql cookbook and map with outputs
    - test routing data from requires (host/ip) to provides (mysql/host)
    - have a simple, one component test to test the basics if one of the more
      complex tests fails

    '''

    def setUp(self):
        self.maxDiff = 1000
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        register_providers([solo.Provider, test.TestProvider])
        self.deployment = \
            Deployment(utils.yaml_to_dict('''
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
        '''Verify workflow sequence and data flow'''

        self.mox.StubOutWithMock(solo.ChefMap, "get_map_file")
        chefmap = solo.ChefMap(IgnoreArg())
        chefmap.get_map_file().AndReturn(self.map_file)

        self.mox.ReplayAll()
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)
        workflow_spec = create_workflow_spec_deploy(self.deployment, context)
        workflow = init_spiff_workflow(workflow_spec, self.deployment, context)
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
                    ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)
        self.mox.VerifyAll()

        # Make sure hash value was generated
        resources = self.deployment['resources']
        self.assertIn("hash", resources['admin']['instance'])

    def test_workflow_execution(self):
        '''Verify workflow executes'''

        self.mox.StubOutWithMock(solo.ChefMap, "get_map_file")
        chefmap = solo.ChefMap(IgnoreArg())
        chefmap.get_map_file().AndReturn(self.map_file)

        self.mox.ReplayAll()
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)
        self.mox.VerifyAll()

        # Create new mox queue for running workflow

        self.mox.ResetAll()
        self.assertEqual(self.deployment.get('status'), 'PLANNED')
        expected_calls = [{
            # Create Chef Environment
            'call': 'checkmate.providers.opscode.knife.create_environment',
            'args': [self.deployment['id'], 'kitchen'],
            'kwargs': And(
                ContainsKeyValue('private_key', IgnoreArg()),
                ContainsKeyValue('secret_key', IgnoreArg()),
                ContainsKeyValue('public_key_ssh', IgnoreArg())
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
        }]
        for key, resource in self.deployment['resources'].iteritems():
            if resource.get('type') == 'compute':
                attributes = {
                    'username': 'u1',
                    'password': 'myPassW0rd',
                    'db_name': 'app_db',
                }
                expected_calls.extend([
                    {
                        # Create Server
                        'call': 'checkmate.providers.test.create_resource',
                        'args': [IsA(dict), IsA(dict)],
                        'kwargs': IgnoreArg(),
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
                        'checkmate.providers.opscode.knife.register_node',
                        'args': [
                            "4.4.4.4",
                            self.deployment['id'],
                            ContainsKeyValue('index', IgnoreArg())
                        ],
                        'kwargs': And(
                            In('password'),
                            ContainsKeyValue('attributes', attributes),
                            ContainsKeyValue('omnibus_version', '10.24.0')
                        ),
                        'result': None,
                        'resource': key,
                    },
                    {
                        # Prep host - bootstrap.json means no recipes passed in
                        'call': 'checkmate.providers.opscode.knife.cook',
                        'args': [
                            '4.4.4.4',
                            self.deployment['id'],
                            ContainsKeyValue('index', IgnoreArg())
                        ],
                        'kwargs': And(
                            In('password'),
                            Not(In('recipes')),
                            ContainsKeyValue(
                                'identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id']
                            )
                        ),
                        'result': None
                    }
                ])
            elif resource.get('type') == 'database':
                expected_calls.extend([{
                    # Cook mysql
                    'call': 'checkmate.providers.opscode.knife.cook',
                    'args': [
                        '4.4.4.4',
                        self.deployment['id'],
                        ContainsKeyValue('index', IgnoreArg())
                    ],
                    'kwargs': And(
                        In('password'),
                        ContainsKeyValue('recipes', ['mysql::server']),
                        ContainsKeyValue(
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
        print final.attributes
        self.assertDictEqual(final.attributes['instance:0'],
                             expected['instance:0'])


def do_nothing(self, my_task):
    call_me = 'dep.on_resource_postback(output_template) #'
    source = utils.get_source_body(solo.Transforms.collect_options)
    source = source.replace('postback.', call_me)
    tabbed_code = '\n    '.join(source.split('\n'))
    func_name = "trans_%s" % uuid.uuid4().hex[0:8]
    exec("def %s(self, my_task):\n    %s"
         "\n%s(self, my_task)" %
         (func_name, tabbed_code, func_name))


class TestMappedMultipleWorkflow(test.StubbedWorkflowBase):

    '''

    Test complex workflows

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

    '''

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        register_providers([solo.Provider, test.TestProvider])
        self.deployment = \
            Deployment(utils.yaml_to_dict('''
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
        '''Verify workflow sequence and data flow'''

        self.mox.StubOutWithMock(solo.ChefMap, "get_map_file")
        chefmap = solo.ChefMap(IgnoreArg())
        chefmap.get_map_file().AndReturn(self.map_file)

        self.mox.ReplayAll()
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)
        workflow_spec = create_workflow_spec_deploy(self.deployment, context)
        workflow = init_spiff_workflow(workflow_spec, self.deployment, context)
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

    def test_workflow_execution(self):
        '''Verify workflow executes'''

        self.mox.StubOutWithMock(solo.ChefMap, "get_map_file")
        chefmap = solo.ChefMap(IgnoreArg())
        chefmap.get_map_file().AndReturn(self.map_file)

        # Plan deployment
        self.mox.ReplayAll()
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)
        self.mox.VerifyAll()

        # Create new mox queue for running workflow
        self.mox.ResetAll()
        self.assertEqual(self.deployment.get('status'), 'PLANNED')

        expected_calls = [{
            # Create Chef Environment
            'call': 'checkmate.providers.opscode.knife.create_environment',
            'args': [self.deployment['id'], 'kitchen'],
            'kwargs': And(
                ContainsKeyValue('private_key', IgnoreArg()),
                ContainsKeyValue('secret_key', IgnoreArg()),
                ContainsKeyValue('public_key_ssh', IgnoreArg())
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
        }]
        for key, resource in self.deployment['resources'].iteritems():
            if resource.get('type') == 'compute':
                expected_calls.extend([
                    {
                        # Register foo - knife prepare
                        'call':
                        'checkmate.providers.opscode.knife.register_node',
                        'args': [
                            "4.4.4.4",
                            self.deployment['id'],
                            ContainsKeyValue('index', IgnoreArg())
                        ],
                        'kwargs': And(
                            In('password'),
                            ContainsKeyValue('omnibus_version', '10.24.0'),
                            ContainsKeyValue(
                                'attributes',
                                {'connections': 10, 'widgets': 10}
                            )
                        ),
                        'result': None,
                        'resource': key,
                    },
                    {
                        # Prep foo - bootstrap.json
                        'call': 'checkmate.providers.opscode.knife.cook',
                        'args': [
                            '4.4.4.4',
                            self.deployment['id'],
                            ContainsKeyValue('index', IgnoreArg())
                        ],
                        'kwargs': And(
                            In('password'),
                            Not(ContainsKeyValue('recipes', ['foo'])),
                            ContainsKeyValue(
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
                        'args': [IsA(dict), IsA(dict)],
                        'kwargs': IgnoreArg(),
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
                expected_calls.extend([
                    {
                        # Write foo databag item
                        'call':
                        'checkmate.providers.opscode.knife.write_databag',
                        'args': [
                            'DEP-ID-1000', 'app_bag', 'mysql',
                            {'db_name': 'foo-db'}, IgnoreArg()
                        ],
                        'kwargs': {
                            'merge': True,
                            'secret_file': 'certificates/chef.pem'
                        },
                        'result': None
                    },
                    {
                        # Write foo-master role
                        'call':
                        'checkmate.providers.opscode.knife.manage_role',
                        'args': ['foo-master', 'DEP-ID-1000', IgnoreArg()],
                        'kwargs': {
                            'run_list': ['recipe[apt]', 'recipe[foo::server]'],
                            'override_attributes': {'how-many': 2},
                            'kitchen_name': 'kitchen',
                        },
                        'result': None
                    },
                    {
                        # Cook foo - run using runlist
                        'call': 'checkmate.providers.opscode.knife.cook',
                        'args': [
                            '4.4.4.4',
                            self.deployment['id'],
                            ContainsKeyValue('index', IgnoreArg())
                        ],
                        'kwargs': And(
                            In('password'),
                            ContainsKeyValue(
                                'recipes',
                                ['something', 'something::role']
                            ),
                            ContainsKeyValue('roles', ['foo-master']),
                            ContainsKeyValue(
                                'attributes',
                                {
                                    'master': {'ip': '4.4.4.4'},
                                    'db': {'name': 'foo-db'},
                                }
                            ),
                            ContainsKeyValue(
                                'identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id']
                            ),
                        ),
                        'result': None
                    }
                ])
            elif resource.get('type') == 'database':
                expected_calls.extend([
                    {
                        # Cook bar
                        'call': 'checkmate.providers.opscode.knife.cook',
                        'args': [
                            None,
                            self.deployment['id'],
                            ContainsKeyValue('index', IgnoreArg())
                        ],
                        'kwargs': And(
                            In('password'),
                            ContainsKeyValue('recipes', ['bar']),
                            ContainsKeyValue(
                                'identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id']
                            )
                        ),
                        'result': None
                    },
                    {
                        # Re-cook bar
                        'call': 'checkmate.providers.opscode.knife.cook',
                        'args': [
                            None,
                            self.deployment['id'],
                            ContainsKeyValue('index', IgnoreArg())
                        ],
                        'kwargs': And(
                            In('password'),
                            ContainsKeyValue('recipes', ['bar']),
                            ContainsKeyValue(
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


class TestChefMap(unittest.TestCase):

    '''Test ChefMap Class'''

    def setUp(self):
        self.mox = mox.Mox()
        knife.CONFIG = self.mox.CreateMockAnything()
        knife.CONFIG.deployments_path = '/tmp/checkmate-chefmap'
        self.local_path = '/tmp/checkmate-chefmap'
        self.url = 'https://github.com/checkmate/app.git'
        self.cache_path = self.local_path + "/cache/blueprints/" + \
            hashlib.md5(self.url).hexdigest()
        self.fetch_head_path = os.path.join(self.cache_path, ".git",
                                            "FETCH_HEAD")
        self.chef_map_path = os.path.join(self.cache_path, "Chefmap")

        # Clean up from previous failed run
        if os.path.exists(self.local_path):
            shutil.rmtree(self.local_path)
            LOG.info("Removed '%s'", self.local_path)

    def tearDown(self):
        self.mox.UnsetStubs()
        if os.path.exists(self.local_path):
            shutil.rmtree('/tmp/checkmate-chefmap')

    def test_get_map_file_hit_cache(self):
        '''Test remote map file retrieval (cache hit)'''
        os.makedirs(os.path.join(self.cache_path, ".git"))
        LOG.info("Created '%s'", self.cache_path)

        # Create a dummy Chefmap and .git/FETCH_HEAD
        with file(self.fetch_head_path, 'a'):
            os.utime(self.fetch_head_path, None)
        with file(self.chef_map_path, 'a') as f:
            f.write(TEMPLATE)

        # Make sure cache_expire_time is set to something that
        # shouldn't cause a cache miss
        chefmap = solo.ChefMap()
        os.environ["CHECKMATE_BLUEPRINT_CACHE_EXPIRE"] = "3600"

        chefmap.url = self.url
        map_file = chefmap.get_map_file()

        def update_map(repo_dir=None, head=None):
            with open(self.chef_map_path, 'a') as f:
                f.write("new information")
        utils.git_pull = self.mox.CreateMockAnything()
        utils.git_pull(IgnoreArg(), IgnoreArg()).WithSideEffects(update_map)
        self.assertEqual(map_file, TEMPLATE)

        # Catch the exception that mox will throw when it doesn't get
        # the call to repository
        with self.assertRaises(mox.ExpectedMethodCallsError):
            self.mox.VerifyAll()

    def test_get_map_file_miss_cache(self):
        '''Test remote map file retrieval (cache miss)'''
        os.makedirs(os.path.join(self.cache_path, ".git"))
        LOG.info("Created '%s'", self.cache_path)

        # Create a dummy Chefmap and .git/FETCH_HEAD
        with file(self.fetch_head_path, 'a'):
            os.utime(self.fetch_head_path, None)
        self.chef_map_path = os.path.join(self.cache_path, "Chefmap")
        with file(self.chef_map_path, 'a') as f:
            f.write(TEMPLATE)

        chefmap = solo.ChefMap()
        # Make sure the expire time is set to something that WILL
        # cause a cache miss
        os.environ["CHECKMATE_BLUEPRINT_CACHE_EXPIRE"] = "0"

        def update_map(repo_dir=None, head=None):
            with open(self.chef_map_path, 'a') as f:
                f.write("new information")
        utils.git_tags = self.mox.CreateMockAnything()
        utils.git_tags(IgnoreArg()).AndReturn(["master"])
        utils.git_fetch = self.mox.CreateMockAnything()
        utils.git_fetch(IgnoreArg(), IgnoreArg())
        utils.git_checkout = self.mox.CreateMockAnything()
        utils.git_checkout(
            IgnoreArg(), IgnoreArg()).WithSideEffects(update_map)
        self.mox.ReplayAll()

        chefmap.url = self.url
        map_file = chefmap.get_map_file()

        self.assertNotEqual(map_file, TEMPLATE)
        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_get_map_file_no_cache(self):
        '''Test remote map file retrieval (not cached)'''
        chefmap = solo.ChefMap()

        def fake_clone(url=None, path=None, branch=None):
            os.makedirs(os.path.join(self.cache_path, ".git"))
            with file(self.fetch_head_path, 'a'):
                os.utime(self.fetch_head_path, None)
            with open(self.chef_map_path, 'w') as f:
                f.write(TEMPLATE)

        utils.git_clone = self.mox.CreateMockAnything()
        utils.git_clone(IgnoreArg(), IgnoreArg(), branch=IgnoreArg())\
            .WithSideEffects(fake_clone)
        utils.git_tags = self.mox.CreateMockAnything()
        utils.git_tags(IgnoreArg()).AndReturn(["master"])
        utils.git_checkout = self.mox.CreateMockAnything()
        utils.git_checkout(IgnoreArg(), IgnoreArg())
        self.mox.ReplayAll()

        chefmap.url = self.url
        map_file = chefmap.get_map_file()

        self.assertEqual(map_file, TEMPLATE)
        self.mox.VerifyAll()

    def test_get_map_file_local(self):
        '''Test local map file retrieval'''
        blueprint = os.path.join(self.local_path, "blueprint")
        os.makedirs(blueprint)

        # Create a dummy Chefmap
        with file(os.path.join(blueprint, "Chefmap"), 'a') as f:
            f.write(TEMPLATE)

        url = "file://" + blueprint
        chefmap = solo.ChefMap(url=url)
        map_file = chefmap.get_map_file()

        self.assertEqual(map_file, TEMPLATE)

    def test_map_URI_parser(self):
        fxn = solo.ChefMap.parse_map_URI
        cases = [
            {
                'name': 'requirement from short form',
                'scheme': 'requirements',
                'netloc': 'database:mysql',
                'path': 'username',
            },
            {
                'name': 'requirement from long form',
                'scheme': 'requirements',
                'netloc': 'my_name',
                'path': 'root/child',
            },
            {
                'name': 'databag',
                'scheme': 'databags',
                'netloc': 'my_dbag',
                'path': 'item/key',
            },
            {
                'name': 'encrypted databag',
                'scheme': 'encrypted-databags',
                'netloc': 'secrets',
                'path': 'item/key/with/long/path',
            },
            {
                'name': 'attributes',
                'scheme': 'attributes',
                'netloc': '',
                'path': 'item/key/with/long/path',
            },
            {
                'name': 'clients',
                'scheme': 'clients',
                'netloc': 'provides_key',
                'path': 'item/key/with/long/path',
            },
            {
                'name': 'roles',
                'scheme': 'roles',
                'netloc': 'role-name',
                'path': 'item/key/with/long/path',
            },
            {
                'name': 'output',
                'scheme': 'outputs',
                'netloc': '',
                'path': 'item/key/with/long/path',
            },
            {
                'name': 'path check for output',
                'scheme': 'outputs',
                'netloc': '',
                'path': 'only/path',
            },
            {
                'name': 'only path check for attributes',
                'scheme': 'attributes',
                'netloc': '',
                'path': 'only/path',
            }
        ]

        for case in cases:
            uri = urlunparse((case['scheme'],
                              case['netloc'],
                              case['path'],
                              None,
                              None,
                              None
                              )
                             )
            result = fxn(uri)
            for key, value in result.iteritems():
                self.assertEqual(value, case.get(key, ''), msg="'%s' got '%s' "
                                 "wrong in %s" % (case['name'], key, uri))

    def test_map_URI_parser_netloc(self):
        result = solo.ChefMap.parse_map_URI("attributes://only/path")
        self.assertEqual(result['path'], 'only/path')

        result = solo.ChefMap.parse_map_URI("attributes://only")
        self.assertEqual(result['path'], 'only')

        result = solo.ChefMap.parse_map_URI("outputs://only/path")
        self.assertEqual(result['path'], 'only/path')

        result = solo.ChefMap.parse_map_URI("outputs://only")
        self.assertEqual(result['path'], 'only')

    def test_has_mapping_positive(self):
        chef_map = solo.ChefMap(raw='''
                id: test
                maps:
                - source: 1
            ''')
        self.assertTrue(chef_map.has_mappings('test'))

    def test_has_mapping_negative(self):
        chef_map = solo.ChefMap(raw='''
                id: test
                maps: {}
            ''')
        self.assertFalse(chef_map.has_mappings('test'))

    def test_has_requirement_map_positive(self):
        chef_map = solo.ChefMap(raw='''
                id: test
                maps:
                - source: requirements://name/path
                - source: requirements://database:mysql/username
            ''')
        self.assertTrue(chef_map.has_requirement_mapping('test', 'name'))
        self.assertTrue(chef_map.has_requirement_mapping('test',
                                                         'database:mysql'))
        self.assertFalse(chef_map.has_requirement_mapping('test', 'other'))

    def test_has_requirement_mapping_negative(self):
        chef_map = solo.ChefMap(raw='''
                id: test
                maps: {}
            ''')
        self.assertFalse(chef_map.has_requirement_mapping('test', 'name'))

    def test_has_client_map_positive(self):
        chef_map = solo.ChefMap(raw='''
                id: test
                maps:
                - source: clients://name/path
                - source: clients://database:mysql/ip
            ''')
        self.assertTrue(chef_map.has_client_mapping('test', 'name'))
        self.assertTrue(chef_map.has_client_mapping('test', 'database:mysql'))
        self.assertFalse(chef_map.has_client_mapping('test', 'other'))

    def test_has_client_mapping_negative(self):
        chef_map = solo.ChefMap(raw='''
                id: test
                maps: {}
            ''')
        self.assertFalse(chef_map.has_client_mapping('test', 'name'))

    def test_get_attributes(self):
        chef_map = solo.ChefMap(raw='''
                id: foo
                maps:
                - value: 1
                  targets:
                  - attributes://here
                \n--- # component bar
                id: bar
                maps:
                - value: 1
                  targets:
                  - databags://mybag/there
            ''')
        self.assertDictEqual(chef_map.get_attributes('foo', None), {'here': 1})
        self.assertDictEqual(chef_map.get_attributes('bar', None), {})
        self.assertIsNone(chef_map.get_attributes('not there', None))

    def test_has_runtime_options(self):
        chef_map = solo.ChefMap(raw='''
                id: foo
                maps:
                - source: requirements://database:mysql/
                \n---
                id: bar
                maps: {}
                ''')
        self.assertTrue(chef_map.has_runtime_options('foo'))
        self.assertFalse(chef_map.has_runtime_options('bar'))
        self.assertFalse(chef_map.has_runtime_options('not there'))

    def test_filter_maps_by_schemes(self):
        maps = utils.yaml_to_dict('''
                - value: 1
                  targets:
                  - databags://bag/item
                - value: 2
                  targets:
                  - databags://bag/item
                  - roles://bag/item
                - value: 3
                  targets:
                  - attributes://id
                ''')
        expect = "Should detect all maps with databags target"
        ts = ['databags']
        result = solo.ChefMap.filter_maps_by_schemes(maps, target_schemes=ts)
        self.assertListEqual(result, maps[0:2], msg=expect)

        expect = "Should detect only map with roles target"
        ts = ['roles']
        result = solo.ChefMap.filter_maps_by_schemes(maps, target_schemes=ts)
        self.assertListEqual(result, [maps[1]], msg=expect)

        expect = "Should detect all maps once"
        ts = ['databags', 'attributes', 'roles']
        result = solo.ChefMap.filter_maps_by_schemes(maps, target_schemes=ts)
        self.assertListEqual(result, maps, msg=expect)

        expect = "Should return all maps"
        result = solo.ChefMap.filter_maps_by_schemes(maps)
        self.assertListEqual(result, maps, msg=expect)

        expect = "Should return all maps"
        result = solo.ChefMap.filter_maps_by_schemes(maps, target_schemes=[])
        self.assertListEqual(result, maps, msg=expect)


class TestTransform(unittest.TestCase):
    '''Test Transform functionality'''

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
        fxn = solo.Transforms.collect_options
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
        '''Test that an output template written as output'''
        output = utils.yaml_to_dict('''
                  'instance:0':
                    name: test
                    instance:
                      interfaces:
                        mysql:
                          database_name: db1
            ''')

        self.mox.StubOutWithMock(
            checkmate.deployments.resource_postback, "delay")
        fxn = solo.Transforms.collect_options
        task = self.mox.CreateMockAnything()
        spec = self.mox.CreateMockAnything()
        spec.get_property('chef_maps', []).AndReturn([])
        spec.get_property('chef_options', {}).AndReturn({})
        spec.get_property('chef_output').AndReturn(output or {})
        spec.get_property('deployment').AndReturn(1)
        checkmate.deployments.resource_postback.delay(
            IgnoreArg(), IgnoreArg()).AndReturn(None)
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
    '''Test ChefMap Mapping Evaluation'''
    def test_scalar_evaluation(self):
        chefmap = solo.ChefMap(parsed="")
        result = chefmap.evaluate_mapping_source({'value': 10}, None)
        self.assertEqual(result, 10)

    def test_requirement_evaluation(self):
        chefmap = solo.ChefMap(parsed="")
        mapping = {
            'source': 'requirements://host/ip',
            'path': 'instance:1'
        }
        data = {'instance:1': {'ip': '4.4.4.4'}}
        result = chefmap.evaluate_mapping_source(mapping, data)
        self.assertEqual(result, '4.4.4.4')

    def test_client_evaluation(self):
        chefmap = solo.ChefMap(parsed="")
        mapping = {
            'source': 'clients://host/ip',
            'path': 'instance:1'
        }
        data = {'instance:1': {'ip': '4.4.4.4'}}
        result = chefmap.evaluate_mapping_source(mapping, data)
        self.assertEqual(result, '4.4.4.4')


class TestChefMapApplier(unittest.TestCase):
    '''Test ChefMap Mapping writing to targets'''
    def test_output_writing(self):
        chefmap = solo.ChefMap(parsed="")
        mapping = {'targets': ['outputs://ip']}
        result = {}
        chefmap.apply_mapping(mapping, '4.4.4.4', result)
        self.assertEqual(result, {'outputs': {'ip': '4.4.4.4'}})


class TestChefMapResolver(unittest.TestCase):
    '''Test ChefMap Mapping writing to targets'''
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
        unresolved = solo.ChefMap.resolve_ready_maps(maps, data, result)
        expected = {'attributes:0': {'ready': 8, 'simple': 1}}
        self.assertDictEqual(result, expected)
        self.assertListEqual(unresolved, [maps[2]])


class TestTemplating(unittest.TestCase):
    '''Test that templating engine handles the use cases we need'''

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_remote_catalog_sourcing(self):
        '''Test source constraint picks up remote catalog'''

        provider = \
            solo.Provider(utils.yaml_to_dict('''
                vendor: opscode
                constraints:
                - source: git://gh.acme.com/user/repo.git#branch
                '''))
        self.mox.StubOutWithMock(solo.ChefMap, "get_map_file")
        chefmap = solo.ChefMap(IgnoreArg())
        chefmap.get_map_file().AndReturn(TEMPLATE)
        self.mox.ReplayAll()

        response = provider.get_catalog(RequestContext())

        self.assertListEqual(
            response.keys(), ['application', 'database'])
        self.assertListEqual(response['application'].keys(), ['webapp'])
        self.assertListEqual(response['database'].keys(), ['mysql'])
        self.mox.VerifyAll()

    def test_parsing_scalar(self):
        '''Test parsing with simple, scalar variables'''
        chef_map = solo.ChefMap('')
        chef_map._raw = '''
            {% set id = 'foo' %}
            id: {{ id }}
            maps:
            - value: {{ 1 }}
              targets:
              - attributes://{{ 'here' }}
        '''
        self.assertDictEqual(chef_map.get_attributes('foo', None), {'here': 1})

    def test_parsing_functions_parse_url(self):
        '''Test 'parse_url' function use in parsing'''
        chef_map = solo.ChefMap('')
        chef_map._raw = '''
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
        result = chef_map.get_attributes('bar', None)
        expected = {
            'scheme': 'http',
            'netloc': 'github.com',
            'fragment': 'master',
            'path': '/checkmate',
            'a': {'b': {'c': {'d': '/checkmate'}}}
        }
        self.assertDictEqual(result, expected)

    def test_parsing_functions_parse_url_Input(self):
        '''Test 'parse_url' function use in parsing of Inputs'''
        chef_map = solo.ChefMap('')
        chef_map._raw = '''
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
        chef_map.parse(chef_map.raw)
        result = chef_map.get_attributes('bar', None)
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
        '''Test 'parse_url' function use in parsing of Inputs'''
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
        deployment = Deployment({
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
        chef_map = solo.ChefMap('')
        chef_map._raw = '''
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
        result = chef_map.parse(chef_map.raw, deployment=deployment)
        data = yaml.safe_load(result)
        self.assertEqual(data['maps'][0]['value'], cert)

    def test_parsing_functions_hash(self):
        '''Test 'hash' function use in parsing'''
        chef_map = solo.ChefMap('')
        chef_map._raw = '''
            id: foo
            maps:
            - value: {{ hash('password', salt='ahem') }}
              targets:
              - attributes://here
        '''
        self.assertDictEqual(
            chef_map.get_attributes('foo', None),
            {
                'here':
                '$6$ahem$cf866f39224e26521d6ac5575225c0ac4933ec3d47bc'
                'ee136c3ceef8341343b4530858b8bca85e33e1e4ccf297f8b096'
                'fcebe978f5e0d6e8188445dc89cc66cf'
            }
        )

    def test_yaml_escaping_simple(self):
        '''Test parsing with simple strings that don't break YAML'''
        chef_map = solo.ChefMap('')
        template = "id: {{ setting('password') }}"
        deployment = Deployment({
            'inputs': {
                'password': "Password1",
            },
            'blueprint': {},
        })

        result = chef_map.parse(template, deployment=deployment)
        self.assertEqual(result, "id: Password1")
        data = yaml.safe_load(result)
        self.assertEqual(data, {'id': 'Password1'})

    def test_yaml_escaping_at(self):
        '''Test parsing with YAML-breaking values: @'''
        chef_map = solo.ChefMap('')
        template = "id: {{ setting('password') }}"
        deployment = Deployment({
            'inputs': {
                'password': "@W#$%$^D%F^UGY",
            },
            'blueprint': {},
        })

        result = chef_map.parse(template, deployment=deployment)
        self.assertEqual(result, "id: '@W#$%$^D%F^UGY'")
        data = yaml.safe_load(result)
        self.assertEqual(data, {'id': '@W#$%$^D%F^UGY'})


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
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
