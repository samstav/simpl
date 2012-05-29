#!/usr/bin/env python
from celery.app import default_app
from celery.result import AsyncResult
import copy
import json
import logging
import mox
from mox import IsA, In, And, Or, IgnoreArg, ContainsKeyValue, Func, \
        StrContains
import os
from SpiffWorkflow.storage import DictionarySerializer
from string import Template
import unittest2 as unittest
import yaml
import uuid

LOG = logging.getLogger(__name__)

os.environ['CHECKMATE_DATA_PATH'] = os.path.join(os.path.dirname(__file__),
                                              'data')
os.environ['BROKER_USERNAME'] = os.environ.get('BROKER_USERNAME', 'checkmate')
os.environ['BROKER_PASSWORD'] = os.environ.get('BROKER_PASSWORD', 'password')
os.environ['BROKER_HOST'] = os.environ.get('BROKER_HOST', 'localhost')
os.environ['BROKER_PORT'] = os.environ.get('BROKER_PORT', '5672')

from checkmate import server  # enables logging
from checkmate.deployments import plan_dict
from checkmate.utils import resolve_yaml_external_refs, is_ssh_key
from checkmate.workflows import get_os_env_keys

# Environment variables and safe alternatives
ENV_VARS = {
        'CHECKMATE_USERNAME': 'john.doe',
        'CHECKMATE_APIKEY': 'secret-api-key',
        'CHECKMATE_PUBLIC_KEY': 'ssh-rsa AAAAB3NzaC1...',
        'CHECKMATE_PRIVATE_KEY': 'mumble-code',
        'CHECKMATE_DOMAIN': 'test.local',
        'CHECKMATE_REGION': 'north'
    }


class TestWorkflow(unittest.TestCase):
    """ Test Basic Server code """

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
        self.mox = mox.Mox()
        # Parse app.yaml as a deployment
        result = plan_dict(TestWorkflow.deployment)
        self.deployment = result['deployment']
        self.workflow = result['workflow']

    def test_workflow_completion(self):
        """Verify workflow sequence and data flow"""
        # Prepare expected call names, args, and returns for mocking
        def context_has_server_settings(context):
            """Checks that server_create call has all necessary settings"""
            if not is_ssh_key(context['keys']['checkmate']['public_key']):
                LOG.warn("Create server call did not get checkmate key")
                return False
            if not context['keys']['environment']['public_key'] == \
                    'ssh-rsa AAAAB3NzaC1...':
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
                'call': 'stockton.auth.distribute_get_token',
                'args': [And(Or(In('apikey'), In('password')),
                        In('username'))],
                'kwargs': None,
                'result': "mock-token"
            },
            {
                # Create Chef Environment
                'call': 'stockton.cheflocal.distribute_create_environment',
                'args': IgnoreArg(),
                'kwargs': None,
                'result': {'environment': '/var/tmp/DEP-ID-1000/',
                    'private_key_path': '/var/tmp/DEP-ID-1000/private.pem',
                    'public_key_path': '/var/tmp/DEP-ID-1000/checkmate.pub',
                    'public_key': 'ssh-rsa AAAAB3NzaC1...'}
            },
            {
                # Create Database
                'call': 'stockton.db.distribute_create_instance',
                'args': [And(ContainsKeyValue('db_name', 'db1'),
                        In('db_password'), ContainsKeyValue('db_username',
                                'wp_user_db1')), IsA(basestring),
                        1, 1, [{'name': 'db1'}]],
                'kwargs': IgnoreArg(),
                'result': {'id': 'db-inst-1', 'name': 'dbname.domain.local',
                        'status': 'BUILD', 'hostname':
                        'verylong.rackclouddb.com'}
            },
            {
                # Create Load Balancer
                'call': 'stockton.lb.distribute_create_loadbalancer',
                'args': [IsA(dict), IsA(basestring), 'PUBLIC', 'HTTP', 80],
                'kwargs': IgnoreArg(),
                'result': {'id': 20001, 'vip': "200.1.1.1"}
            },
            {
                # Create Database User
                'call': 'stockton.db.distribute_add_user',
                'args': [IsA(dict), 'db-inst-1', ['db1'], 'wp_user_db1',
                        IsA(basestring)],
                'kwargs': None,
                'result': True
            },
            {
                # Create First Server
                'call': 'stockton.server.distribute_create',
                'args': [Func(context_has_server_settings),
                        StrContains('web1')],
                'kwargs': And(ContainsKeyValue('image', 119),
                        ContainsKeyValue('flavor', 1),
                        ContainsKeyValue('ip_address_type', 'public')),
                'result': {'id': 10001, 'ip': "10.1.1.1",
                        'password': "shecret"}
            },
            {
                # Create Second Server
                'call': 'stockton.server.distribute_create',
                'args': [Func(context_has_server_settings),
                        StrContains('web2')],
                'kwargs': And(ContainsKeyValue('image', 119),
                        ContainsKeyValue('flavor', 1),
                        ContainsKeyValue('ip_address_type', 'public')),
                'result': {'id': 10002, 'ip': "10.1.1.2",
                        'password': "shecret"}
            },
            {
                # Wait for First Server Build
                'call': 'stockton.server.distribute_wait_on_build',
                'args': [IsA(dict), 10001],
                'kwargs': And(In('password')),
                'result': True
            },
            {
                # Wait for Second Server Build
                'call': 'stockton.server.distribute_wait_on_build',
                'args': [IsA(dict), 10002],
                'kwargs': And(In('password')),
                'result': True
            },
            {
                # Bootstrap Server 1 with Chef
                'call': 'stockton.cheflocal.distribute_register_node',
                'args': ['10.1.1.1', 'DEP-ID-1000'],
                'kwargs': In('password'),
                'result': None
            },
            {
                # Bootstrap Server 2 with Chef
                'call': 'stockton.cheflocal.distribute_register_node',
                'args': ['10.1.1.2', 'DEP-ID-1000'],
                'kwargs': In('password'),
                'result': None
            },
            {
                'call': 'stockton.cheflocal.distribute_manage_role',
                'args': ['wordpress-web', 'DEP-ID-1000'],
                'kwargs': {'override_attributes': {'wordpress': {'db': {
                        'host': 'verylong.rackclouddb.com',
                        'password': IsA(basestring),
                        'user': 'wp_user_db1',
                        'database': 'db1'}}}},
                'result': None
            },
            {
                'call': 'stockton.cheflocal.distribute_cook',
                'args': ['10.1.1.1', 'DEP-ID-1000'],
                'kwargs': And(In('password'), ContainsKeyValue('roles',
                        ['build-ks', 'wordpress-web'])),
                'result': None
            },
            {
                'call': 'stockton.lb.distribute_add_node',
                'args': [IsA(dict), 20001, '10.1.1.1', 80],
                'kwargs': None,
                'result': None
            },
            {
                'call': 'stockton.cheflocal.distribute_cook',
                'args': ['10.1.1.2', 'DEP-ID-1000'],
                'kwargs': And(In('password'), ContainsKeyValue('roles',
                        ['build-ks', 'wordpress-web'])),
                'result': None
            },
            {
                'call': 'stockton.lb.distribute_add_node',
                'args': [IsA(dict), 20001, '10.1.1.2', 80],
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

        self.mox.ReplayAll()

        self.workflow.complete_all()

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
                            ENV_VARS['CHECKMATE_PUBLIC_KEY'])
                if 'public_key_path' in value:
                    result = result.replace(value['public_key_path'],
                            '/var/tmp/DEP-ID-1000/key.pub')
                if 'private_key' in value:
                    result = result.replace(value['private_key'][0:-1],
                            ENV_VARS['CHECKMATE_PUBLIC_KEY'])
                if 'private_key_path' in value:
                    result = result.replace(value['private_key_path'],
                            '/var/tmp/DEP-ID-1000/key.pem')
        try:
            with file(simulator_file_path, 'w') as f:
                f.write(result)
        except:
            pass

    def tearDown(self):
        self.mox.UnsetStubs()

if __name__ == '__main__':
    unittest.main()
