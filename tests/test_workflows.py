#!/usr/bin/env python
from celery.app import default_app
from celery.result import AsyncResult
import json
import logging
import mox
from mox import IsA, In, And, Or, IgnoreArg, ContainsKeyValue
import os
from SpiffWorkflow.specs import Celery as SpiffCelery
from SpiffWorkflow.storage import DictionarySerializer
from string import Template
import sys
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

from checkmate import server
from checkmate.deployments import plan_dict
from checkmate.workflows import create_workflow
from checkmate.utils import resolve_yaml_external_refs


class TestWorkflow(unittest.TestCase):
    """ Test Basic Server code """

    @classmethod
    def setUpClass(cls):
        # Load app.yaml, substitute variables
        path = os.path.join(os.path.dirname(__file__), '..', 'examples',
            'app.yaml')
        with file(path) as f:
            source = f.read().decode('utf-8')
        env = {
                'CHECKMATE_USERNAME': '1',
                'CHECKMATE_APIKEY': '2',
                'CHECKMATE_PUBLIC_KEY': '3',
                'CHECKMATE_PRIVATE_KEY': '4',
                'CHECKMATE_DOMAIN': '5',
                'CHECKMATE_REGION': '6'
            }
        t = Template(source)
        env.update(os.environ)
        parsed = t.safe_substitute(**env)
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
                'result': "mock-token"
            },
            {
                # Create First Server
                'call': 'stockton.server.distribute_create',
                'args': [IsA(dict), IsA(basestring)],
                'kwargs': And(ContainsKeyValue('image', 119),
                        ContainsKeyValue('flavor', 1),
                        ContainsKeyValue('ip_address_type', 'public')),
                'result': {'id': 10001, 'ip': "10.1.1.1",
                        'password': "shecret"}
            },
            {
                # Create Second Server
                'call': 'stockton.server.distribute_create',
                'args': [IsA(dict), IsA(basestring)],
                'kwargs': And(ContainsKeyValue('image', 119),
                        ContainsKeyValue('flavor', 1),
                        ContainsKeyValue('ip_address_type', 'public')),
                'result': {'id': 10002, 'ip': "10.1.1.2",
                        'password': "shecret"}
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
                # Create Database User
                'call': 'stockton.db.distribute_add_user',
                'args': [IsA(dict), 'db-inst-1', ['db1'], 'wp_user_db1',
                        IsA(basestring)],
                'kwargs': None,
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
            async_mock.id = "MOCK%s" % uuid.uuid4().hex
            async_mock.result = call['result']
            async_mock.state = 'SUCCESS'
            self.mock_tasks[async_mock.id] = async_mock

            # Task is called
            default_app.send_task(call['call'], args=call['args'],
                    kwargs=call['kwargs']).AndReturn(async_mock)

            # State is checked
            async_mock.ready().AndReturn(True)

            # Data is retrieved
            default_app.AsyncResult.__call__(async_mock.id).AndReturn(
                    async_mock)

        self.mox.ReplayAll()

        self.workflow.complete_all()

        serializer = DictionarySerializer()
        LOG.debug(json.dumps(self.workflow.serialize(serializer), indent=2))

    def tearDown(self):
        self.mox.UnsetStubs()

if __name__ == '__main__':
    unittest.main(verbosity=2)
