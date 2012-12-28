#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Tests for chef-solo provider"""

import __builtin__
import copy
import json
import logging
import os
import unittest2 as unittest
from urlparse import urlunparse

import mox
from mox import In, IsA, And, IgnoreArg, ContainsKeyValue, Not

# Init logging before we load the database, 3rd party, and 'noisy' modules

from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import test, utils
from checkmate.deployments import Deployment, plan
from checkmate.middleware import RequestContext
from checkmate.providers import base, register_providers
from checkmate.providers.opscode import solo, local
from checkmate.workflows import create_workflow_deploy


class TestChefSolo(test.ProviderTester):

    klass = solo.Provider


class TestChefSoloTasks(unittest.TestCase):
    def setUp(self):
        os.environ['CHECKMATE_CHEF_LOCAL_PATH'] = '/test/checkmate'
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_cook(self):
        """Test that cook task picks up run_list and attributes"""
        root_path = os.environ['CHECKMATE_CHEF_LOCAL_PATH']
        environment_path = os.path.join(root_path, "env_test")
        kitchen_path = os.path.join(environment_path, "kitchen")
        node_path = os.path.join(kitchen_path, "nodes", "a.b.c.d.json")

        #Stub out checks for paths
        self.mox.StubOutWithMock(local, '_get_root_environments_path')
        local._get_root_environments_path(None).AndReturn(root_path)
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
        json.dump(And(
                      ContainsKeyValue('run_list',
                                       ['role[role1]', 'recipe[recipe1]']),
                      ContainsKeyValue('id', 1)
                      ),
                  mock_file).AndReturn(None)
        mock_file.__exit__(None, None, None).AndReturn(None)

        #Stub out file opens
        self.mox.StubOutWithMock(__builtin__, 'file')
        __builtin__.file(node_path, 'r').AndReturn(mock_file)
        __builtin__.file(node_path, 'w').AndReturn(mock_file)

        #Stub out process call to knife
        params = ['knife', 'cook', 'root@a.b.c.d',
                  '-c', os.path.join(kitchen_path, "solo.rb"),
                  '-p', '22']
        self.mox.StubOutWithMock(local, '_run_kitchen_command')
        local._run_kitchen_command(kitchen_path, params).AndReturn("OK")

        self.mox.ReplayAll()
        solo.cook("a.b.c.d", "env_test", roles=['role1'], recipes=['recipe1'],
                  attributes={'id': 1})
        self.mox.VerifyAll()


class TestDBWorkflow(test.StubbedWorkflowBase):

    """ Test MySQL Resource Creation Workflow """

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        register_providers([solo.Provider, test.TestProvider])
        self.deployment = Deployment(utils.yaml_to_dict("""
                id: 'DEP-ID-1000'
                blueprint:
                  name: test db
                  services:
                    db:
                      component:
                        id: mysql
                environment:
                  name: test
                  providers:
                    chef-solo:
                      vendor: opscode
                      catalog:
                        database:
                          mysql:
                            id: mysql
                            provides:
                            - database: mysql
                            requires:
                            - host: 'linux'
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
                    region: DFW
            """))
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        plan(self.deployment, context)

        expected = []

        # Create Chef Environment

        expected.append({  # Use chef-solo tasks for now
                           # Use only one kitchen. Call it "kitchen" like we
                           # used to
            'call': 'checkmate.providers.opscode.local.create_environment',
            'args': [self.deployment['id'], 'kitchen'],
            'kwargs': And(ContainsKeyValue('private_key', IgnoreArg()),
                          ContainsKeyValue('secret_key', IgnoreArg()),
                          ContainsKeyValue('public_key_ssh',
                          IgnoreArg()), ContainsKeyValue('source_repo',
                          IgnoreArg())),
            'result': {
                'environment': '/var/tmp/%s/' % self.deployment['id'],
                'kitchen': '/var/tmp/%s/kitchen' % self.deployment['id'
                        ],
                'private_key_path': '/var/tmp/%s/private.pem'
                    % self.deployment['id'],
                'public_key_path': '/var/tmp/%s/checkmate.pub'
                    % self.deployment['id'],
                'public_key': test.ENV_VARS['CHECKMATE_CLIENT_PUBLIC_KEY'
                        ],
                },
            })

        for key, resource in self.deployment['resources'].iteritems():
            if resource['type'] == 'compute':
                expected.append({
                        'call': 'checkmate.providers.test.create_resource',
                        'args': [IsA(dict), resource],
                        'kwargs': None,
                        'result': {'instance:%s' % key: {
                            'status': 'ACTIVE',
                            'ip': '4.4.4.1',
                            'private_ip': '10.1.2.1',
                            'addresses': {'public': [{'version': 4,
                                          'addr': '4.4.4.1'}, {'version': 6,
                                          'addr': '2001:babe::ff04:36c1'}],
                                          'private': [{'version': 4,
                                          'addr': '10.1.2.1'}]},
                            }},
                        'post_back_result': True,
                        })
                expected.append({
                    'call': 'checkmate.providers.opscode.local.register_node',
                    'args': ['4.4.4.1', self.deployment['id']],
                    'kwargs': In('password'),
                    'result': None,
                    'resource': key,
                    })

                # build-essential (now just cook with bootstrap.json)

                expected.append({
                    'call': 'checkmate.providers.opscode.solo.cook',
                    'args': ['4.4.4.1', self.deployment['id']],
                    'kwargs': And(In('password'),
                                  Not(In('recipes')),
                                  Not(In('roles')),
                                  ContainsKeyValue('identity_file',
                                        '/var/tmp/%s/private.pem'
                                        % self.deployment['id'])
                                 ),
                    'result': None,
                    'resource': key,
                    })
            else:

                # Cook with role

                expected.append({
                    'call': 'checkmate.providers.opscode.solo.cook',
                    'args': ['4.4.4.1', self.deployment['id']],
                    'kwargs': And(In('password'), ContainsKeyValue('recipes',
                                  ['mysql::server']),
                                  ContainsKeyValue('identity_file',
                                  '/var/tmp/%s/private.pem'
                                  % self.deployment['id'])),
                    'result': None,
                    'resource': key,
                    })
        expected.append({
            'call': 'checkmate.providers.opscode.local.manage_databag',
            'args': [self.deployment['id'], self.deployment['id'],
                     None, None],
            'kwargs': And(ContainsKeyValue('secret_file',
                          'certificates/chef.pem'),
                          ContainsKeyValue('merge', True)),
            'result': None,
            })
        self.workflow = self._get_stubbed_out_workflow(expected_calls=expected)

    def test_workflow_completion(self):
        """Verify workflow sequence and data flow"""

        self.mox.ReplayAll()

        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(),
                        'Workflow did not complete')


class TestMapWorkflowTasks(test.StubbedWorkflowBase):

    """Test that map file tasks are created"""

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        register_providers([solo.Provider, test.TestProvider])
        self.deployment = \
            Deployment(utils.yaml_to_dict("""
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
            """))
        self.map_file = \
            """
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
                # Host requirement resolved at run-time
                - source: requirements://host/ip
                  targets:
                  - attributes://master/ip
                # Relation requirement resolved at run-time
                - source: requirements://database:mysql/database_name
                  targets:
                  - attributes://db/name
            \n--- # bar component
                id: bar
                is: database
                provides:
                - database: mysql
            """

        # Mock out remote catalog calls
        self.mox.StubOutWithMock(solo, 'httplib')
        connection_class_mock = self.mox.CreateMockAnything()
        solo.httplib.HTTPConnection = connection_class_mock
        connection_mock = self.mox.CreateMockAnything()
        response_mock = self.mox.CreateMockAnything()

        connection_class_mock.__call__(IgnoreArg(),
                IgnoreArg()).AndReturn(connection_mock)

        connection_mock.request('GET', IgnoreArg(),
                                headers=IgnoreArg()).AndReturn(True)
        connection_mock.getresponse().AndReturn(response_mock)

        response_mock.read().AndReturn(self.map_file)
        connection_mock.close().AndReturn(True)
        response_mock.status = 200

    def test_workflow_task_creation(self):
        """Verify workflow sequence and data flow"""

        self.mox.ReplayAll()
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        plan(self.deployment, context)
        workflow = create_workflow_deploy(self.deployment, context)
        print workflow.get_dump()
        collect_task = workflow.spec.task_specs['Collect Chef Data for 0']
        ancestors = collect_task.ancestors()
        # inputs = collect_task.inputs
        host_done = workflow.spec.task_specs['Configure bar: 2 (backend)']
        self.assertIn(host_done, ancestors)
        task_list = list(set(t.get_name() for t in workflow.get_tasks()))
        expected = list(set([
                    'Root',
                    'Start',
                    'Create Chef Environment',
                    'Create Resource 1',
                    'After Environment is Ready and Server 1 (frontend) is Up',
                    'Register Server 1 (frontend)',
                    'Pre-Configure Server 1 (frontend)',
                    'Get frontend-backend values for 1',
                    'After 1,10 run 4',
                    'Collect Chef Data for 0',
                    'Configure foo: 0 (frontend)',
                    'Configure bar: 2 (backend)',
                    ]))
        self.assertListEqual(task_list, expected, msg=task_list)
        self.mox.VerifyAll()

    def test_workflow_execution(self):
        """Verify workflow executes"""

        # Plan deployment
        self.mox.ReplayAll()
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        plan(self.deployment, context)
        self.mox.VerifyAll()

        # Create new mox queue for running workflow
        self.mox.ResetAll()
        self.assertEqual(self.deployment.get('status'), 'PLANNED')
        expected_calls = [{
                # Create Chef Environment
                'call': 'checkmate.providers.opscode.local.create_environment',
                'args': [self.deployment['id'], 'kitchen'],
                'kwargs': And(ContainsKeyValue('private_key', IgnoreArg()),
                        ContainsKeyValue('secret_key', IgnoreArg()),
                        ContainsKeyValue('public_key_ssh', IgnoreArg())),
                'result': {
                        'environment': '/var/tmp/%s/' %
                                self.deployment['id'],
                        'kitchen': '/var/tmp/%s/kitchen',
                        'private_key_path': '/var/tmp/%s/private.pem' %
                                self.deployment['id'],
                        'public_key_path': '/var/tmp/%s/checkmate.pub' %
                                self.deployment['id'],
                        'public_key':
                                test.ENV_VARS['CHECKMATE_CLIENT_PUBLIC_KEY']}
            }]
        for key, resource in self.deployment['resources'].iteritems():
            if resource.get('type') == 'compute':
                expected_calls.extend([{
                        # Register foo - knife prepare
                        'call': 'checkmate.providers.opscode.local.'
                                'register_node',
                        'args': ["4.4.4.4", self.deployment['id']],
                        'kwargs': And(In('password'),
                                      ContainsKeyValue('attributes',
                                {'widgets': 10})),
                        'result': None,
                        'resource': key,
                    },  {
                        # Prep foo - bootstrap.json
                        'call': 'checkmate.providers.opscode.solo.cook',
                        'args': ['4.4.4.4', self.deployment['id']],
                        'kwargs': And(In('password'),
                                      Not(ContainsKeyValue('recipes',
                                                           ['foo'])),
                                ContainsKeyValue('identity_file',
                                        '/var/tmp/%s/private.pem' %
                                        self.deployment['id'])),
                        'result': None
                    }, {
                        # Create Server
                        'call': 'checkmate.providers.test.create_resource',
                        'args': [IsA(dict), IsA(dict)],
                        'kwargs': IgnoreArg(),
                        'result': {
                                'instance:%s' % key: {
                                    'id': '1',
                                    'password': "shecret",
                                    'ip': '4.4.4.4'
                                    }
                                },
                        'post_back_result': True,
                        'resource': key,
                    }])
            elif 'type' in resource:
                expected_calls.extend([{
                        # Cook foo - run recipes
                        'call': 'checkmate.providers.opscode.solo.cook',
                        'args': ['4.4.4.4', self.deployment['id']],
                        'kwargs': And(In('password'),
                                      ContainsKeyValue('recipes',
                                                        ['foo']),
                                      ContainsKeyValue('attributes',
                                            {'master': {'ip': '4.4.4.4'}}),
                                      ContainsKeyValue('identity_file',
                                            '/var/tmp/%s/private.pem' %
                                            self.deployment['id'])),
                        'result': None
                    }, {
                        # Cook bar
                        'call': 'checkmate.providers.opscode.solo.cook',
                        'args': [None, self.deployment['id']],
                        'kwargs': And(In('password'),
                                        ContainsKeyValue('recipes', ['bar']),
                                        ContainsKeyValue('identity_file',
                                                '/var/tmp/%s/private.pem' %
                                                self.deployment['id'])),
                        'result': None
                    }])
        workflow = self._get_stubbed_out_workflow(context=context,
                expected_calls=expected_calls)
        task_list = list(set(t.get_name() for t in workflow.get_tasks()))
        expected = list(set([
                    'Root',
                    'Start',
                    'Create Chef Environment',
                    'Create Resource 1',
                    'After Environment is Ready and Server 1 (frontend) is Up',
                    'Register Server 1 (frontend)',
                    'Pre-Configure Server 1 (frontend)',
                    'Get frontend-backend values for 1',
                    'After 1,10 run 4',
                    'Collect Chef Data for 0',
                    'Configure foo: 0 (frontend)',
                    'Configure bar: 2 (backend)',
                    ]))
        self.assertListEqual(task_list, expected, msg=task_list)
        self.mox.ReplayAll()
        workflow.complete_all()
        self.assertTrue(workflow.is_completed(), msg=workflow.get_dump())
        self.assertDictEqual(self.outcome, {})
        self.mox.VerifyAll()


class TestMaplessWorkflowTasks(test.StubbedWorkflowBase):

    """Test that workflow works without maps"""

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        register_providers([solo.Provider, test.TestProvider])
        self.deployment = \
            Deployment(utils.yaml_to_dict("""
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
            """))
        self.map_file = \
            """
            \n--- # foo component
                id: foo
                requires:
                - database: mysql
            \n--- # bar component
                id: bar
                provides:
                - database: mysql
                maps: {}  # blank map should be ignored as well
            """

    def test_workflow_tasks(self):
        """Verify workflow sequence and data flow"""

        self.mox.StubOutWithMock(solo, 'httplib')
        connection_class_mock = self.mox.CreateMockAnything()
        solo.httplib.HTTPConnection = connection_class_mock
        connection_mock = self.mox.CreateMockAnything()
        response_mock = self.mox.CreateMockAnything()
        for i in range(1):  # will be called twice; planning and workflow
                            # creation
            connection_class_mock.__call__(IgnoreArg(),
                    IgnoreArg()).AndReturn(connection_mock)

            connection_mock.request('GET', IgnoreArg(),
                                    headers=IgnoreArg()).AndReturn(True)
            connection_mock.getresponse().AndReturn(response_mock)

            response_mock.read().AndReturn(self.map_file)
            connection_mock.close().AndReturn(True)
            response_mock.status = 200

        self.mox.ReplayAll()

        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        plan(self.deployment, context)

        workflow = create_workflow_deploy(self.deployment, context)

        task_list = workflow.spec.task_specs.keys()
        self.assertNotIn('Collect Chef Data for 0', task_list,
                         msg="Should not have a Collect task when no mappings "
                             "exist in the map file")
        expected = ['Root',
                    'Start',
                    'Create Chef Environment',
                    'Configure bar: 1 (backend)',
                    'Configure foo: 0 (frontend)',
                   ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)

        self.mox.VerifyAll()


class TestChefMap(unittest.TestCase):

    """Test ChefMap Class"""

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_remote_url_parser(self):
        map_class = solo.ChefMap
        cases = [
            {
                'name': 'github file',
                'url': 'http://github.com/user/repo',
                'file': 'test.yaml',
                'expected': 'http://github.com/user/repo/raw/master/test.yaml',
                },
            {
                'name': 'github path',
                'url': 'http://github.com/user/repo/',
                'file': 'dir/file.txt',
                'expected':
                        'http://github.com/user/repo/raw/master/dir/file.txt',
                },
            {
                'name': 'with branch',
                'url': 'http://github.com/user/repo#myBranch',
                'file': 'file.txt',
                'expected':
                        'http://github.com/user/repo/raw/myBranch/file.txt',
                },
            {
                'name': 'with .git extension',
                'url': 'http://github.com/user/repo.git',
                'file': 'file.txt',
                'expected': 'http://github.com/user/repo/raw/master/file.txt',
                },
            {
                'name': 'enterprise https',
                'url': 'https://gh.acme.com/user/repo#a-branch',
                'file': 'file.txt',
                'expected':
                        'https://gh.acme.com/user/repo/raw/a-branch/file.txt',
                },
            {
                'name': 'git protocol',
                'url': 'git://github.com/user/repo/',
                'file': 'dir/file.txt',
                'expected':
                        'https://github.com/user/repo/raw/master/dir/file.txt',
                },
            ]

        for case in cases:
            result = map_class.get_remote_raw_url(case['url'],
                    case['file'])
            self.assertEqual(result, case['expected'], msg=case['name'])

    def test_get_remote_map_file(self):
        """Test remote map file retrieval"""

        map_file = '---\nid: mysql'
        self.mox.StubOutWithMock(solo, 'httplib')
        connection_class_mock = self.mox.CreateMockAnything()
        solo.httplib.HTTPSConnection = connection_class_mock

        connection_mock = self.mox.CreateMockAnything()
        connection_class_mock.__call__(IgnoreArg(),
                IgnoreArg()).AndReturn(connection_mock)

        response_mock = self.mox.CreateMockAnything()
        connection_mock.request('GET', IgnoreArg(),
                                headers=IgnoreArg()).AndReturn(True)
        connection_mock.getresponse().AndReturn(response_mock)

        response_mock.read().AndReturn(map_file)
        connection_mock.close().AndReturn(True)
        response_mock.status = 200
        self.mox.ReplayAll()
        chef_map = solo.ChefMap('https://github.com/checkmate/app.git')
        self.assertEqual(chef_map.raw, map_file)
        self.mox.VerifyAll()

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
                'name': 'roles',
                'scheme': 'roles',
                'netloc': 'role-name',
                'path': 'item/key/with/long/path',
                },
            {
                'name': 'output',
                'scheme': 'output',
                'netloc': '',
                'path': 'item/key/with/long/path',
            }, {
                'name': 'path check for output',
                'scheme': 'output',
                'netloc': '',
                'path': 'only/path',
            }, {
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

    def test_has_mapping_positive(self):
        chef_map = solo.ChefMap('')
        chef_map._raw = """
            id: test
            maps:
            - source: 1
        """
        self.assertTrue(chef_map.has_mappings())

    def test_has_mapping_negative(self):
        chef_map = solo.ChefMap('')
        chef_map._raw = """
            id: test
            maps: {}
        """
        self.assertFalse(chef_map.has_mappings())

    def test_has_requirement_map_positive(self):
        chef_map = solo.ChefMap('')
        chef_map._raw = """
            id: test
            maps:
            - source: requirements://name/path
            - source: requirements://database:mysql/username
        """
        self.assertTrue(chef_map.has_requirement_mapping('test', 'name'))
        self.assertTrue(chef_map.has_requirement_mapping('test',
                                                          'database:mysql'))
        self.assertFalse(chef_map.has_requirement_mapping('test', 'other'))

    def test_has_requirement_mapping_negative(self):
        chef_map = solo.ChefMap('')
        chef_map._raw = """
            id: test
            maps: {}
        """
        self.assertFalse(chef_map.has_requirement_mapping('test', 'name'))

    def test_has_databag_mapping_positive(self):
        chef_map = solo.ChefMap('')
        chef_map._raw = """
            id: test
            maps:
            - source: 1
            - source: 'string'
            - source: databags://test
            """
        self.assertTrue(chef_map.has_databag_mappings())

    def test_has_databag_mapping_positive_encrypted(self):
        chef_map = solo.ChefMap('')
        chef_map._raw = """
            id: test
            maps:
            - source: 1
            - source: 'string'
            - source: encrypted-databags://enc-test
            """
        self.assertTrue(chef_map.has_databag_mappings())

    def test_has_databag_mapping_negative(self):
        chef_map = solo.ChefMap('')
        chef_map._raw = """
            id: test
            maps: {}
        """
        self.assertFalse(chef_map.has_databag_mappings())

    def test_get_attributes(self):
        chef_map = solo.ChefMap('')
        chef_map._raw = """
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
        """
        self.assertDictEqual(chef_map.get_attributes('foo', None), {'here': 1})
        self.assertDictEqual(chef_map.get_attributes('bar', None), {})
        self.assertIsNone(chef_map.get_attributes('not there', None))

    def test_has_runtime_options(self):
        chef_map = solo.ChefMap('')
        chef_map._raw = """
            id: foo
            maps:
            - source: requirements://database:mysql/
            \n---
            id: bar
            maps: {}
            """
        self.assertTrue(chef_map.has_runtime_options('foo'))
        self.assertFalse(chef_map.has_runtime_options('bar'))
        self.assertFalse(chef_map.has_runtime_options('not there'))


class TestTemplating(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_remote_catalog_sourcing(self):
        """Test source constraint picks up remote catalog"""

        provider = \
            solo.Provider(utils.yaml_to_dict("""
                vendor: opscode
                constraints:
                - source: git://gh.acme.com/user/repo.git#branch
                """))
        self.mox.StubOutWithMock(solo, 'httplib')
        connection_class_mock = self.mox.CreateMockAnything()
        solo.httplib.HTTPSConnection = connection_class_mock

        connection_mock = self.mox.CreateMockAnything()
        connection_class_mock.__call__(IgnoreArg(),
                IgnoreArg()).AndReturn(connection_mock)

        response_mock = self.mox.CreateMockAnything()
        connection_mock.request('GET', IgnoreArg(),
                                headers=IgnoreArg()).AndReturn(True)
        connection_mock.getresponse().AndReturn(response_mock)

        response_mock.read().AndReturn(TEMPLATE)
        connection_mock.close().AndReturn(True)
        response_mock.status = 200
        self.mox.ReplayAll()

        response = provider.get_catalog(RequestContext())

        self.assertListEqual(response.keys(), ['application', 'database'
                             ])
        self.assertListEqual(response['application'].keys(), ['webapp'])
        self.assertListEqual(response['database'].keys(), ['mysql'])
        self.mox.VerifyAll()

    def test_parsing_scalar(self):
        """Test parsing with simple, scalar variables"""
        chef_map = solo.ChefMap('')
        chef_map._raw = """
            {% set id = 'foo' %}
            id: {{ id }}
            maps:
            - value: {{ 1 }}
              targets:
              - attributes://{{ 'here' }}
        """
        self.assertDictEqual(chef_map.get_attributes('foo', None), {'here': 1})

    def test_parsing_functions_parse_url(self):
        """Test 'parse_url' function use in parsing"""
        chef_map = solo.ChefMap('')
        chef_map._raw = """
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
        """
        result = chef_map.get_attributes('bar', None)
        expected = {
            'scheme': 'http',
            'netloc': 'github.com',
            'fragment': 'master',
            'path': '/checkmate',
            'a': {'b': {'c': {'d': '/checkmate'}}}
            }
        self.assertDictEqual(result, expected)

    def test_parsing_functions_hash(self):
        """Test 'hash' function use in parsing"""
        chef_map = solo.ChefMap('')
        chef_map._raw = """
            id: foo
            maps:
            - value: {{ hash('password', salt='ahem') }}
              targets:
              - attributes://here
        """
        self.assertDictEqual(chef_map.get_attributes('foo', None),
                {'here': '$6$ahem$cf866f39224e26521d6ac5575225c0ac4933ec3d47bc'
                         'ee136c3ceef8341343b4530858b8bca85e33e1e4ccf297f8b096'
                         'fcebe978f5e0d6e8188445dc89cc66cf'})


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

    # Run tests. Handle our parameters separately

    import sys
    args = sys.argv[:]

    # Our --debug means --verbose for unitest

    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
