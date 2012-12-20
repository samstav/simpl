#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Tests for chef-solo provider"""

import copy
import logging
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
from checkmate.providers.opscode import solo
from checkmate.workflows import create_workflow_deploy


class TestChefSolo(test.ProviderTester):

    klass = solo.Provider


class TestDBWorkflow(test.StubbedWorkflowBase):

    """ Test MySQL Resource Creation Workflow """

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        register_providers([solo.Provider, test.TestProvider])
        self.deployment = \
            Deployment(utils.yaml_to_dict("""
                id: 'DEP-ID-1000'
                blueprint:
                  name: test db
                  services:
                    db:
                      component:
                        id: mysql
                        is: database
                        type: database
                environment:
                  name: test
                  providers:
                    chef-solo:
                      vendor: opscode
                      provides:
                      - database: mysql
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
                      provides:
                      - compute: linux
                      catalog:
                        compute:
                          linux_instance:
                            id: linux_instance
                            is: compute
                            provides:
                            - compute: linux
                inputs:
                  blueprint:
                    region: DFW
            """))
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
        expected.append({
            'call': 'checkmate.providers.test.create_resource',
            'args': [IsA(dict), {
                'index': '0',
                'component': 'linux_instance',
                'dns-name': 'CM-DEP-ID--db1.checkmate.local',
                'instance': {},
                'hosts': ['1'],
                'provider': 'base',
                'type': 'compute',
                'service': 'db',
                }],
            'kwargs': None,
            'result': {'instance:0': {
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
            'resource': '1',
            })

        # build-essential (now just cook with bootstrap.json)

        expected.append({
            'call': 'checkmate.providers.opscode.local.cook',
            'args': ['4.4.4.1', self.deployment['id']],
            'kwargs': And(In('password'), Not(In('recipes')),
                          Not(In('roles')),
                          ContainsKeyValue('identity_file',
                          '/var/tmp/%s/private.pem'
                          % self.deployment['id'])),
            'result': None,
            'resource': '1',
            })

        # Cook with role

        expected.append({
            'call': 'checkmate.providers.opscode.local.cook',
            'args': ['4.4.4.1', self.deployment['id']],
            'kwargs': And(In('password'), ContainsKeyValue('recipes',
                          ['mysql::server']),
                          ContainsKeyValue('identity_file',
                          '/var/tmp/%s/private.pem'
                          % self.deployment['id'])),
            'result': None,
            'resource': '1',
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
        self.workflow = \
            self._get_stubbed_out_workflow(expected_calls=expected)

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
                maps:
                # Simple scalar to attribute
                - value: 10
                  targets:
                  - attributes://widgets
            \n--- # bar component
                id: bar
                provides:
                - database: mysql
            """

    def test_workflow_task_creation(self):
        """Verify workflow sequence and data flow"""

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

        self.mox.ReplayAll()

        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        plan(self.deployment, context)
        workflow = create_workflow_deploy(self.deployment, context)

        task_list = [t.get_name() for t in workflow.get_tasks()]
        expected = ['Root',
                    'Start',
                    'Create Chef Environment',
                    'Configure bar: 1 (backend)',
                    'Configure foo: 0 (frontend)',
                    ]
        self.assertListEqual(task_list, expected)
        self.mox.VerifyAll()

    def test_workflow_execution(self):
        """Verify workflow executes"""

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

        self.mox.ReplayAll()

        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        plan(self.deployment, context)
        self.mox.VerifyAll()

        # New mox queue starts here
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
            },  {
                'call': 'checkmate.providers.opscode.local.cook',
                'args': [None, self.deployment['id']],
                'kwargs': And(In('password'), ContainsKeyValue('recipes',
                        ['foo']),
                        ContainsKeyValue('identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id'])),
                'result': None
            }, {
                'call': 'checkmate.providers.opscode.local.cook',
                'args': [None, self.deployment['id']],
                'kwargs': And(In('password'), ContainsKeyValue('recipes',
                        ['bar']),
                        ContainsKeyValue('identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id'])),
                'result': None
            }]
        workflow = self._get_stubbed_out_workflow(context=context,
                expected_calls=expected_calls)
        task_list = [t.get_name() for t in workflow.get_tasks()]
        expected = ['Root',
                    'Start',
                    'Create Chef Environment',
                    'Configure bar: 1 (backend)',
                    'Configure foo: 0 (frontend)',
                    ]
        self.assertListEqual(task_list, expected)

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

        task_list = [t.get_name() for t in workflow.get_tasks()]
        expected = ['Root',
                    'Start',
                    'Create Chef Environment',
                    'Configure bar: 1 (backend)',
                    'Configure foo: 0 (frontend)',
                    ]
        self.assertListEqual(task_list, expected)

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
                },
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
                self.assertEqual(value, case.get(key, ''), msg="%s' got '%s' "
                                 "wrong in %s" % (case['name'], key, uri))

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
