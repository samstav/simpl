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
from checkmate.utils import yaml_to_dict

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
        deployment = yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services: {}
                environment:
                  name: environment
                  providers:
                    common:
                      credentials:
                      - password: secret
                        username: tester
                """)
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
        deployment = yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      components:
                        id: widget
                    two:
                      components:
                        id: widget
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      - widget: bar
                      vendor: test
                    common:
                      credentials:
                      - password: secret
                        username: tester
            """)
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


class TestWordpressWorkflow(StubbedWorkflowBase):
    """ Test WordPress Workflow """

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

        # WordPress Settings
        inputs = yaml_to_dict("""
                client_public_key_ssh: ssh-rsa AAAAB3NzaC1...
                environment_private_key: |
                    -----BEGIN RSA PRIVATE KEY-----
                    MIIEpAIBAAKCAQEAvQYtPZCP+5SVD68nf9OzEEE7itZlfynbf/XRQ6YggOa0t1U5
                    XRqdHPnmG7nYtxdMQLZkMYJtyML8u56p11DrpQCF9p9VISrnjSS4CmO2Y6vLbd2H
                    yntKeV57repsAnhqkE788rWQ5bm15bYyYLa52qhpYxy3R7O/Nif3B1wQzq0+KYbD
                    MqoHs7dOGErKXxRcqO1f1WZe6gBfat2qDY/XUJe+VQXNSGl7e19KSr9FZXMTQBOs
                    sGvleL0mDy0Gn9NKp9V3haKmAMPW0ZAMA14TqwBfHaELPuRLrCDRt6YtDLGg4V+w
                    vgZdGkzwoEAAAuKheu+5TwEBrD9wO4fE/C8sBwIDAQABAoIBAGzHaDOcxO9f82Ri
                    RRXv64V4NN7SQPisSvBZs4L90Ii9u9QhjHCDB1WMjpr4GbpMAwreq8w+JhW5+J20
                    UkNiAyoiofVqfiAnQ7fbILqB5Y14aQqhySqCRzqPYBeW52+IgrLncfPu/yLk+8Pl
                    VRqJLW2jK3rpJKRz0Z9F4ohuuBFnbjsGtjknivH+Xd6KR9022mzNiBinjD/R8R+K
                    GW75buDzquvuaQ12mHub4uQ59hhyp2a/jrwy6ez0lbXu3zqIyzPzhHk95WLMmrDv
                    AeyzqkjcbuJ1VBv8ko8enp56m9CQvoPnmYHW8xI53I4yCzp6yymd9/mgFj6CoSyv
                    Z/NUIJkCgYEA2A9ibxjvNVF/s6lKhb8WGRhSlQZoZT3u360ok8JzPDWwEOyEEUy2
                    OFJDJ8gtJ6PelQD2b9xaz+dGWEfZU2CGL68KtiRmO5uDD5BmJ02UmjfBUl/7uipl
                    BhtZLDexj1vORZQMrhSrxt7n1VfEgpX42n0WR/EU4aoWSX1CAIG2AksCgYEA3/de
                    YCuHYjEscDbkee0CSqBfdg/u01+HRE+fQ8AesNLC1ZZv7h5OfCfrZvM925Kk+0tm
                    ex8IdMfnuGaF3E25mkAshDeQQO5kj14KcJ8GD9z3qG6iiWOcTJtFw8CNkbPe9SfT
                    9FmYPZbvXGeIQvj6b9dEVRJOcI+4WsoiMgOeh7UCgYEAqhmSmXy79vIu47dIYHvM
                    Xf10JrdgwTQ9OAQPiiTwrFpoPyq13xjR7Q12qX9DbY3p0s1rNy34oO2nyCDozGeV
                    vTzF5hhKFGueh0Zb5l2BvNhgbwX6HNr7pg8p6VH/jKnuf4DLatIDWxJq2t+6akTA
                    IuOQAxueIPvTiBABQnzcWnkCgYAtWHNGO2n0yon5ylNmEEOXgnLxf3ZWW5ASl6Bi
                    YkKUgIesIQJWjtJLNvXlaThL/ZvjuTdtlDHtGxBieHd/zEjY30dkGa/eRaYclOi+
                    NqROj+mgs427DWz24bU1VgYTyvxIXKEAZyd4yNd7uQaQsMJb5JTUOJmjFqY305cq
                    0yrExQKBgQCB2Be1RFBkLa+7VGpK+kT7OVHhmMAMjr9apL4XI6WYQzeS+JN6elG3
                    hEN1X4K28pVFgiQKqoUZhTjo9MGJsiA8TJ8QX4fLqfyhzitV98zTvPar4i/3bATc
                    /lQOh9JeTc7pCXHX9A2sVT0A7XNR2riT+zoof5edWIBK0UFSA8u0Vw==
                    -----END RSA PRIVATE KEY-----
                blueprint:
                  "prefix": TEST-BLOG
                  "domain": testing.local
                  "path": '/test_blog'
                  "username": tester
                  "password": test_password
                  "ssl": true
                  "ssl_certificate": SSLCERT
                  "ssl_private_key": SSLKEY
                  "region": testonia
                  "high-availability": true
                  "requests-per-second": 60
                services:
                  "backend":
                    'database':
                      'memory': 1024 Mb
                  "web":
                    'compute':
                      'memory': 2048 Mb
                      'count': 2
                providers:
                  'legacy':
                    'compute':
                      'os': Ubuntu 12.04
                      """)
        deployment['inputs'] = inputs

    def setUp(self):
        StubbedWorkflowBase.setUp(self)
        # Parse app.yaml as a deployment
        result = self._get_stubbed_out_workflow(TestWordpressWorkflow.deployment)
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


if __name__ == '__main__':
    unittest.main()
