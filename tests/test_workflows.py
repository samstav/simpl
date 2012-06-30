#!/usr/bin/env python
import copy
import json
import logging
import os
from string import Template
import unittest2 as unittest
import uuid

import mox
from mox import IsA, In, And, Or, IgnoreArg, ContainsKeyValue, Func, \
        StrContains
from celery.app import default_app
from celery.result import AsyncResult
from SpiffWorkflow.storage import DictionarySerializer
import yaml

LOG = logging.getLogger(__name__)

os.environ['CHECKMATE_DATA_PATH'] = os.path.join(os.path.dirname(__file__),
                                              'data')
os.environ['CHECKMATE_BROKER_USERNAME'] = os.environ.get(
        'CHECKMATE_BROKER_USERNAME', 'checkmate')
os.environ['CHECKMATE_BROKER_PASSWORD'] = os.environ.get(
        'CHECKMATE_BROKER_PASSWORD', 'password')
os.environ['CHECKMATE_BROKER_HOST'] = os.environ.get('CHECKMATE_BROKER_HOST',
        'localhost')
os.environ['CHECKMATE_BROKER_PORT'] = os.environ.get('CHECKMATE_BROKER_PORT',
        '5672')

from checkmate import server  # enables logging
from checkmate.deployments import plan_dict, get_os_env_keys
from checkmate.providers.base import PROVIDER_CLASSES, ProviderBase
from checkmate.utils import resolve_yaml_external_refs, is_ssh_key

# Environment variables and safe alternatives
ENV_VARS = {
        'CHECKMATE_CLIENT_USERNAME': 'john.doe',
        'CHECKMATE_CLIENT_APIKEY': 'secret-api-key',
        'CHECKMATE_CLIENT_PUBLIC_KEY': 'ssh-rsa AAAAB3NzaC1...',
        'CHECKMATE_CLIENT_PRIVATE_KEY': 'mumble-code',
        'CHECKMATE_CLIENT_DOMAIN': 'test.local',
        'CHECKMATE_CLIENT_REGION': 'north'
    }


class StubbedWorkflowBase(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def _get_stubbed_out_workflow(self, deployment):
        result = plan_dict(deployment)

        # Prepare expected call names, args, and returns for mocking
        def context_has_server_settings(context):
            """Checks that server_create call has all necessary settings"""
            if not is_ssh_key(context['keys']['client']['public_key_ssh']):
                LOG.warn("Create server call did not get client key")
                return False
            if not (context['keys']['environment']['public_key_ssh'] == \
                    'ssh-rsa AAAAB3NzaC1...' or
                    is_ssh_key(context['keys']['environment']['public_key_ssh']
                    )):
                LOG.warn("Create server call did not get environment key")
                return False
            return True

        def server_got_keys(files):
            """Checks that server_create call has all needed keys"""
            path = '/root/.ssh/authorized_keys'
            if not files:
                LOG.warn("Create server call got blank files")
                return False
            if path not in files:
                LOG.warn("Create server files don't have keys")
                return False
            entries = files[path].strip().split('\n')
            if len(entries) < 2:
                LOG.warn("Create server files has %s keys, which is less than "
                        " 2" % len(entries))
                return False
            for entry in entries:
                if not (entry == 'ssh-rsa AAAAB3NzaC1...'
                        or is_ssh_key(entry)):
                    return False
            return True

        calls = [{
                # Authenticate first
                'call': 'checkmate.providers.rackspace.identity.get_token',
                'args': [And(Or(In('apikey'), In('password')),
                        In('username'))],
                'kwargs': None,
                'result': "mock-token"
            },
            {
                # Create Chef Environment
                'call': 'checkmate.providers.opscode.local.create_environment',
                'args': IsA(list),
                'kwargs': And(ContainsKeyValue('private_key', IgnoreArg()),
                        ContainsKeyValue('secrets_key', IgnoreArg()),
                        ContainsKeyValue('public_key_ssh', IgnoreArg())),
                'result': {'environment': '/var/tmp/DEP-ID-1000/',
                    'kitchen': '/var/tmp/DEP-ID-1000/kitchen',
                    'private_key_path': '/var/tmp/DEP-ID-1000/private.pem',
                    'public_key_path': '/var/tmp/DEP-ID-1000/checkmate.pub',
                    'public_key': 'ssh-rsa AAAAB3NzaC1...'}
            },
            {
                # Create Database
                'call': 'checkmate.providers.rackspace.database.'
                        'create_instance',
                'args': [And(ContainsKeyValue('db_name', 'db1'),
                        In('db_password'), ContainsKeyValue('db_username',
                                'wp_user_db1')), IsA(basestring),
                        1, 1, [{'name': 'db1'}]],
                'kwargs': IgnoreArg(),
                'result': {
                        'id': 'db-inst-1',
                        'name': 'dbname.domain.local',
                        'status': 'BUILD',
                        'hostname': 'verylong.rackspaceclouddb.com'}
            },
            {
                # Create Load Balancer
                'call': 'checkmate.providers.rackspace.loadbalancer.'
                        'create_loadbalancer',
                'args': [IsA(dict), IsA(basestring), 'PUBLIC', 'HTTP', 80],
                'kwargs': IgnoreArg(),
                'result': {'id': 20001, 'vip': "200.1.1.1"}
            },
            {
                # Create Database User
                'call': 'checkmate.providers.rackspace.database.add_user',
                'args': [IsA(dict), 'db-inst-1', ['db1'], 'wp_user_db1',
                        IsA(basestring)],
                'kwargs': None,
                'result': None
            },
            {
                # Create First Server
                'call': 'checkmate.providers.rackspace.compute_legacy.'
                        'create_server',
                'args': [Func(context_has_server_settings),
                        StrContains('web1')],
                'kwargs': And(ContainsKeyValue('image', 119),
                        ContainsKeyValue('flavor', 2),
                        ContainsKeyValue('prefix', '0'),
                        ContainsKeyValue('ip_address_type', 'public')),
                'result': {'id': 10001, 'ip': "4.4.4.1",
                        'private_ip': "10.1.1.1",
                        'password': "shecret",
                        '0.id': 10001, '0.ip': "4.4.4.1",
                        '0.private_ip': "10.1.1.1",
                        '0.password': "shecret"}
            },
            {
                # Create Second Server (Nova format)
                'call': 'checkmate.providers.rackspace.compute_legacy.'
                        'create_server',
                'args': [Func(context_has_server_settings),
                        StrContains('web2')],
                'kwargs': And(ContainsKeyValue('image', 119),
                        ContainsKeyValue('flavor', 2),
                        ContainsKeyValue('prefix', '1'),
                        ContainsKeyValue('ip_address_type', 'public')),
                'result': {'id': "10-uuid-002", 'password': "shecret",
                        '1.id': "10-uuid-002", '1.password': "shecret"}
            },
            {
                # Wait for First Server Build (Legacy format)
                'call': 'checkmate.providers.rackspace.compute_legacy.'
                        'wait_on_build',
                'args': [IsA(dict), 10001],
                'kwargs': And(In('password')),
                'result': {
                        'status': "ACTIVE",
                        '0.status': "ACTIVE",
                        'ip': '4.4.4.1',
                        '0.ip': '4.4.4.1',
                        'private_ip': '10.1.2.1',
                        '0.private_ip': '10.1.2.1',
                        'addresses': {
                          'public': [
                            {
                              "version": 4,
                              "addr": "4.4.4.1"
                            },
                            {
                              "version": 6,
                              "addr": "2001:babe::ff04:36c1"
                            }
                          ],
                          'private': [
                            {
                              "version": 4,
                              "addr": "10.1.2.1"
                            }
                          ]
                        },
                        '0.addresses': {
                          'public': [
                            {
                              "version": 4,
                              "addr": "4.4.4.1"
                            },
                            {
                              "version": 6,
                              "addr": "2001:babe::ff04:36c1"
                            }
                          ],
                          'private': [
                            {
                              "version": 4,
                              "addr": "10.1.2.1"
                            }
                          ]
                        }
                    }
            },
            {
                # Wait for Second Server Build (Nova format)
                'call': 'checkmate.providers.rackspace.compute_legacy.'
                        'wait_on_build',
                'args': [IsA(dict), "10-uuid-002"],
                'kwargs': And(In('password')),
                'result': {
                        'status': "ACTIVE",
                        '1.status': "ACTIVE",
                        'ip': '4.4.4.2',
                        '1.ip': '4.4.4.2',
                        'private_ip': '10.1.2.2',
                        '1.private_ip': '10.1.2.2',
                        'addresses': {
                          'public': [
                            {
                              "version": 4,
                              "addr": "4.4.4.2"
                            },
                            {
                              "version": 6,
                              "addr": "2001:babe::ff04:36c2"
                            }
                          ],
                          'private': [
                            {
                              "version": 4,
                              "addr": "10.1.2.2"
                            }
                          ]
                        },
                        '1.addresses': {
                          'public': [
                            {
                              "version": 4,
                              "addr": "4.4.4.2"
                            },
                            {
                              "version": 6,
                              "addr": "2001:babe::ff04:36c2"
                            }
                          ],
                          'private': [
                            {
                              "version": 4,
                              "addr": "10.1.2.2"
                            }
                          ]
                        }
                    }
            },
            {
                # Bootstrap Server 1 with Chef
                'call': 'checkmate.providers.opscode.local.register_node',
                'args': ['4.4.4.1', 'DEP-ID-1000'],
                'kwargs': In('password'),
                'result': None
            },
            {
                # Bootstrap Server 2 with Chef
                'call': 'checkmate.providers.opscode.local.register_node',
                'args': ['4.4.4.2', 'DEP-ID-1000'],
                'kwargs': In('password'),
                'result': None
            },
            {
                'call': 'checkmate.providers.opscode.local.manage_role',
                'args': ['wordpress-web', 'DEP-ID-1000'],
                'kwargs': {'override_attributes': {'wordpress': {'db': {
                        'host': 'verylong.rackspaceclouddb.com',
                        'password': IsA(basestring),
                        'user': 'wp_user_db1',
                        'database': 'db1'}}}},
                'result': None
            },
            {
                'call': 'checkmate.providers.opscode.local.manage_databag',
                'args': ['DEP-ID-1000', 'DEP-ID-1000', 'webapp_wordpress_A',
                        IsA(dict)],
                'kwargs': ContainsKeyValue('secret_file',
                        'certificates/chef.pem'),
                'result': None
            },
            {
                'call': 'checkmate.providers.opscode.local.cook',
                'args': ['4.4.4.1', 'DEP-ID-1000'],
                'kwargs': And(In('password'), ContainsKeyValue('recipes',
                        ['build-essential']),
                        ContainsKeyValue('identity_file',
                            '/var/tmp/DEP-ID-1000/private.pem')),
                'result': None
            },
            {
                'call': 'checkmate.providers.opscode.local.cook',
                'args': ['4.4.4.1', 'DEP-ID-1000'],
                'kwargs': And(In('password'), ContainsKeyValue('roles',
                        ['build-ks', 'wordpress-web']),
                        ContainsKeyValue('identity_file',
                            '/var/tmp/DEP-ID-1000/private.pem')),
                'result': None
            },
            {
                'call': 'checkmate.providers.rackspace.loadbalancer.add_node',
                'args': [IsA(dict), 20001, '10.1.2.1', 80],
                'kwargs': None,
                'result': None
            },
            {
                'call': 'checkmate.providers.opscode.local.cook',
                'args': ['4.4.4.2', 'DEP-ID-1000'],
                'kwargs': And(In('password'), ContainsKeyValue('recipes',
                        ['build-essential']),
                        ContainsKeyValue('identity_file',
                            '/var/tmp/DEP-ID-1000/private.pem')),
                'result': None
            },
            {
                'call': 'checkmate.providers.opscode.local.cook',
                'args': ['4.4.4.2', 'DEP-ID-1000'],
                'kwargs': And(In('password'), ContainsKeyValue('roles',
                        ['build-ks', 'wordpress-web']),
                        ContainsKeyValue('identity_file',
                            '/var/tmp/DEP-ID-1000/private.pem')),
                'result': None
            },
            {
                'call': 'checkmate.providers.rackspace.loadbalancer.add_node',
                'args': [IsA(dict), 20001, '10.1.2.2', 80],
                'kwargs': None,
                'result': None
            }
            ]

       #Mock out celery calls
        self.mock_tasks = {}
        self.mox.StubOutWithMock(default_app, 'send_task')
        self.mox.StubOutWithMock(default_app, 'AsyncResult')
        for call in calls:
            async_mock = self.mox.CreateMock(AsyncResult)
            async_mock.task_id = "MOCK%s" % uuid.uuid4().hex
            async_mock.result = call['result']
            async_mock.state = 'SUCCESS'
            self.mock_tasks[async_mock.task_id] = async_mock

            # Task is called
            default_app.send_task(call['call'], args=call['args'],
                    kwargs=call['kwargs']).InAnyOrder().AndReturn(async_mock)

            # State is checked
            async_mock.ready().AndReturn(True)

            # Data is retrieved
            default_app.AsyncResult.__call__(async_mock.task_id).AndReturn(
                    async_mock)

        return result


class TestWorkflowStubbing(StubbedWorkflowBase):
    """ Test Basic Server code """
    def test_workflow_run(self):
        deployment = {
                'id': 'test',
                'blueprint': {
                    'name': 'test bp',
                    'services': {},
                    },
                'environment': {
                    'name': 'environment',
                    'providers': {
                        'common': {
                            'credentials': [
                                {
                                    'username': 'tester',
                                    'password': 'secret',
                                }]
                        }
                    },
                    },
                }
        data = self._get_stubbed_out_workflow(deployment)
        deployment = data['deployment']
        workflow = data['workflow']

        self.mox.ReplayAll()

        workflow.complete_all()
        self.assertTrue(workflow.is_completed())
        self.assertNotIn('resources', deployment)


class TestWorkflowLogic(StubbedWorkflowBase):
    """ Test Basic Workflow code """
    def test_workflow_resource_generation(self):
        deployment = {
                'id': 'test',
                'blueprint': {
                    'name': 'test bp',
                    'services': {
                        'one': {
                            'components': dict(id='widget')
                        },
                        'two': {
                            'components': dict(id='widget')
                            },
                        },
                    },
                'environment': {
                    'name': 'environment',
                    'providers': {
                        'base': {
                            'vendor': 'test',
                            'provides': [
                                {'widget': 'foo'},
                                {'widget': 'bar'}
                                ],
                            },
                        'common': {
                            'credentials': [
                                {
                                    'username': 'tester',
                                    'password': 'secret',
                                }]
                            }
                        },
                    },
                }
        PROVIDER_CLASSES['test.base'] = ProviderBase
        data = self._get_stubbed_out_workflow(deployment)
        deployment = data['deployment']
        workflow = data['workflow']

        self.mox.ReplayAll()

        workflow.complete_all()
        self.assertTrue(workflow.is_completed())
        self.assertEqual(len(workflow.get_tasks()), 4)  # until we remove auth


class TestWorkflow(StubbedWorkflowBase):
    """ Test Basic Workflow Stubbing works """

    @classmethod
    def setUpClass(cls):
        # Load app.yaml, substitute variables
        path = os.path.join(os.path.dirname(__file__), '..', 'examples',
            'app.yaml')
        with file(path) as f:
            source = f.read().decode('utf-8')

        t = Template(source)
        combined = copy.copy(ENV_VARS)
        combined.update(os.environ)
        parsed = t.safe_substitute(**combined)
        app = yaml.safe_load(yaml.emit(resolve_yaml_external_refs(parsed),
                         Dumper=yaml.SafeDumper))
        deployment = app['deployment']
        deployment['id'] = 'DEP-ID-1000'
        cls.deployment = deployment

    def setUp(self):
        StubbedWorkflowBase.setUp(self)
        # Parse app.yaml as a deployment
        result = self._get_stubbed_out_workflow(TestWorkflow.deployment)
        self.deployment = result['deployment']
        self.workflow = result['workflow']

    def test_workflow_completion(self):
        """Verify workflow sequence and data flow"""

        self.mox.ReplayAll()

        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed())

        serializer = DictionarySerializer()
        simulation = self.workflow.serialize(serializer)
        simulation['id'] = 'simulate'
        result = json.dumps(simulation, indent=2)
        LOG.debug(result)

        # Update simulator (since this test was successful)
        simulator_file_path = os.path.join(os.path.dirname(__file__),
                'data', 'simulator.json')

        # Scrub data
        for var_name, safe_value in ENV_VARS.iteritems():
            if var_name in os.environ:
                result = result.replace(os.environ[var_name], safe_value)
        keys = get_os_env_keys()
        if keys:
            for key, value in keys.iteritems():
                if 'public_key' in value:
                    result = result.replace(value['public_key'][0:-1],
                            "-----BEGIN PUBLIC KEY-----\n...\n"
                            "-----END PUBLIC KEY-----\n")
                if 'public_key_ssh' in value:
                    result = result.replace(value['public_key_ssh'][0:-1],
                            ENV_VARS['CHECKMATE_PUBLIC_KEY'])
                if 'public_key_path' in value:
                    result = result.replace(value['public_key_path'],
                            '/var/tmp/DEP-ID-1000/key.pub')
                if 'private_key' in value:
                    result = result.replace(value['private_key'][0:-1],
                            "-----BEGIN RSA PRIVATE KEY-----\n...\n"
                            "-----END RSA PRIVATE KEY-----")
                if 'private_key_path' in value:
                    result = result.replace(value['private_key_path'],
                            '/var/tmp/DEP-ID-1000/key.pem')
        try:
            with file(simulator_file_path, 'w') as f:
                f.write(result)
        except:
            pass


if __name__ == '__main__':
    unittest.main()
