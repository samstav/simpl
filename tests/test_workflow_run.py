#!/usr/bin/env python
import copy
import json
import logging
import os
from string import Template
import unittest2 as unittest
import uuid

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()

from celery.app import default_app
from celery.result import AsyncResult
import mox
from mox import IsA, In, And, Or, IgnoreArg, ContainsKeyValue, Func, \
        StrContains
from SpiffWorkflow.storage import DictionarySerializer
import yaml

from checkmate.deployments import Deployment
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

from checkmate.server import RequestContext  # also enables logging
from checkmate.deployments import plan, get_os_env_keys
from checkmate.providers.base import PROVIDER_CLASSES, ProviderBase
from checkmate.utils import resolve_yaml_external_refs, is_ssh_key
from checkmate.workflows import create_workflow

# Environment variables and safe alternatives
ENV_VARS = {
        'CHECKMATE_CLIENT_USERNAME': 'john.doe',
        'CHECKMATE_CLIENT_APIKEY': 'secret-api-key',
        'CHECKMATE_CLIENT_PUBLIC_KEY': """ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtjYYMFbpCJ/ND3izZ1DqNFQHlooXyNcDGWilAqNqcCfz9L+gpGjY2pQlZz/1Hir3R8fz0MS9VY32RYmP3wWygt85kNccEkOpVGGpGyV/aMFaQHZD0h6d0AT+haP0Iig+OrH1YBnpdgVPWx3SbU4eV/KYGpO9Mintj3P54of22lTK4dOwCNvID9P9w+T1kMfdVxGwhqsSL0RxVXnSSkozXQWCNvaZJMUmidm8YA009c5PoksyWjl3EE+rEzZ8ywvtUJf9DvnLCESfhF3hK5lAiEd8z7gyiQnBexn/dXzldGFiJYJgQ5HolYaNMtTF+AQY6R6Qt0okCPyEDJxHJUM7d""",
        'CHECKMATE_CLIENT_PRIVATE_KEY': 'mumble-code',
        'CHECKMATE_CLIENT_DOMAIN': 'test.local',
        'CHECKMATE_CLIENT_REGION': 'north'
    }

CATALOG = [{
                "endpoints": [
                    {
                        "publicURL": "https://monitoring.api.rackspacecloud.com/v1.0/T1000",
                        "tenantId": "T1000"
                    }
                ],
                "name": "cloudMonitoring",
                "type": "rax:monitor"
            },
            {
                "endpoints": [
                    {
                        "publicURL": "https://ord.loadbalancers.api.rackspacecloud.com/v1.0/T1000",
                        "region": "ORD",
                        "tenantId": "T1000"
                    },
                    {
                        "publicURL": "https://dfw.loadbalancers.api.rackspacecloud.com/v1.0/T1000",
                        "region": "DFW",
                        "tenantId": "T1000"
                    }
                ],
                "name": "cloudLoadBalancers",
                "type": "rax:load-balancer"
            },
            {
                "endpoints": [
                    {
                        "internalURL": "https://snet-storage101.ord1.clouddrive.com/v1/Mosso_T-2000",
                        "publicURL": "https://storage101.ord1.clouddrive.com/v1/Mosso_T-2000",
                        "region": "ORD",
                        "tenantId": "Mossos_T-2000"
                    }
                ],
                "name": "cloudFiles",
                "type": "object-store"
            },
            {
                "endpoints": [
                    {
                        "publicURL": "https://dfw.databases.api.rackspacecloud.com/v1.0/T1000",
                        "region": "DFW",
                        "tenantId": "T1000"
                    },
                    {
                        "publicURL": "https://ord.databases.api.rackspacecloud.com/v1.0/T1000",
                        "region": "ORD",
                        "tenantId": "T1000"
                    }
                ],
                "name": "cloudDatabases",
                "type": "rax:database"
            },
            {
                "endpoints": [
                    {
                        "publicURL": "https://servers.api.rackspacecloud.com/v1.0/T1000",
                        "tenantId": "T1000",
                        "versionId": "1.0",
                        "versionInfo": "https://servers.api.rackspacecloud.com/v1.0",
                        "versionList": "https://servers.api.rackspacecloud.com/"
                    }
                ],
                "name": "cloudServers",
                "type": "compute"
            },
            {
                "endpoints": [
                    {
                        "publicURL": "https://dfw.servers.api.rackspacecloud.com/v2/T1000",
                        "region": "DFW",
                        "tenantId": "T1000",
                        "versionId": "2",
                        "versionInfo": "https://dfw.servers.api.rackspacecloud.com/v2",
                        "versionList": "https://dfw.servers.api.rackspacecloud.com/"
                    }
                ],
                "name": "cloudServersOpenStack",
                "type": "compute"
            },
            {
                "endpoints": [
                    {
                        "publicURL": "https://dns.api.rackspacecloud.com/v1.0/T1000",
                        "tenantId": "T1000"
                    }
                ],
                "name": "cloudDNS",
                "type": "rax:dns"
            },
            {
                "endpoints": [
                    {
                        "publicURL": "https://cdn2.clouddrive.com/v1/Mosso_T-2000",
                        "region": "ORD",
                        "tenantId": "Mosso_T-2000"
                    }
                ],
                "name": "cloudFilesCDN",
                "type": "rax:object-cdn"
            }
        ]


class StubbedWorkflowBase(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()
        self.deployment = None

    def tearDown(self):
        self.mox.UnsetStubs()

    def result_postback(self, *args, **kwargs):
        """Simluates a postback from the called resource which updates the
        deployment data. The results will be appended to the simulated
        deployment results"""
        if args[0] == 'checkmate.providers.rackspace.database.'\
                'create_instance':
            args = kwargs['args']
            context = args[0]
            self.deployment.on_resource_postback(context['resource'],
                    {  # TODO: This is a copy of call results. Consolidate?
                        'id': 'db-inst-1',
                        'name': 'dbname.domain.local',
                        'status': 'BUILD',
                        'hostname': 'verylong.rackspaceclouddb.com',
                        'region': 'testonia'})

    def _get_stubbed_out_workflow(self):
        """Returns a workflow of self.deployment with mocks attached to all
        celery calls
        """
        assert isinstance(self.deployment, Deployment)
        context = RequestContext(auth_token="MOCK_TOKEN", username="MOCK_USER",
                catalog=CATALOG)
        plan(self.deployment, context)
        workflow = create_workflow(self.deployment, context)

        # Prepare expected call names, args, and returns for mocking
        def is_good_context(context):
            """Checks that call has all necessary context data"""
            for key in ['auth_token', 'username', 'catalog']:
                if key not in context:
                    LOG.warn("Context does not have a '%s'" % key)
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

        def is_good_data_bag(context):
            """Checks that we're writing everything we need to the chef databag
            for managed cloud cookbooks to work"""
            if context is None:
                return False
            for key in context:
                if key not in ['wordpress', 'user', 'lsyncd', 'mysql',
                        'apache']:
                        return False
            return True

        expected_calls = [{
                # Create Chef Environment
                'call': 'checkmate.providers.opscode.local.create_environment',
                'args': ['DEP-ID-1000'],
                'kwargs': And(ContainsKeyValue('private_key', IgnoreArg()),
                        ContainsKeyValue('secret_key', IgnoreArg()),
                        ContainsKeyValue('public_key_ssh', IgnoreArg())),
                'result': {'environment': '/var/tmp/DEP-ID-1000/',
                    'kitchen': '/var/tmp/DEP-ID-1000/kitchen',
                    'private_key_path': '/var/tmp/DEP-ID-1000/private.pem',
                    'public_key_path': '/var/tmp/DEP-ID-1000/checkmate.pub',
                    'public_key': ENV_VARS['CHECKMATE_CLIENT_PUBLIC_KEY']}
            },
            {
                # Create Load Balancer
                'call': 'checkmate.providers.rackspace.loadbalancer.'
                        'create_loadbalancer',
                'args': [Func(is_good_context), IsA(basestring), 'PUBLIC',
                        'HTTP', 80,  self.deployment.get_setting('region',
                                                        default='testonia')],
                'kwargs': IgnoreArg(),
                'result': {'id': 20001, 'vip': "200.1.1.1", 'lbid': 20001}
            }]

        if str(os.environ.get('CHECKMATE_CHEF_USE_DATA_BAGS', True)
                    ).lower() in ['true', '1', 'yes']:
            expected_calls.append({
                    'call': 'checkmate.providers.opscode.local.manage_databag',
                    'args': ['DEP-ID-1000', 'DEP-ID-1000',
                            'webapp_wordpress_%s' % self.deployment.get_setting('prefix'),
                            Func(is_good_data_bag)],
                    'kwargs': And(ContainsKeyValue('secret_file',
                            'certificates/chef.pem'), ContainsKeyValue('merge',
                            True)),
                    'result': None
                })
        else:
            expected_calls.append({
                    'call': 'checkmate.providers.opscode.local.manage_role',
                    'args': ['wordpress-web', 'DEP-ID-1000'],
                    'kwargs': {'override_attributes': {'wordpress': {'db': {
                            'host': 'verylong.rackspaceclouddb.com',
                            'password': IsA(basestring),
                            'user': os.environ['USER'],
                            'database': 'db1'}}}},
                    'result': None
                })
        # Add repetive calls (per resource)
        for key, resource in self.deployment.get('resources', {}).iteritems():
            if resource.get('type') == 'compute':
                if 'master' in resource['dns-name']:
                    id = 10000 + int(key)  # legacy format
                    role = 'master'
                    ip = 100
                else:
                    id = "10-uuid-00%s" % key  # Nova format
                    role = 'web'
                    ip = key
                name = resource['dns-name']
                flavor = resource['flavor']
                index = key
                image = resource['image']

                expected_calls.append({
                    # Create First Server
                    'call': 'checkmate.providers.rackspace.compute_legacy.'
                            'create_server',
                    'args': [Func(is_good_context),
                            StrContains(name)],
                    'kwargs': And(ContainsKeyValue('image', image),
                            ContainsKeyValue('flavor', flavor),
                            ContainsKeyValue('prefix', key),
                            ContainsKeyValue('ip_address_type', 'public')),
                    'result': {'id': id,
                            'ip': "4.4.4.%s" % ip,
                            'private_ip': "10.1.1.%s" % ip,
                            'password': "shecret",
                            '%s.id' % index: id,
                            '%s.ip' % index: "4.4.4.%s" % ip,
                            '%s.private_ip' % index: "10.1.1.%s" % ip,
                            '%s.password' % index: "shecret"}
                    })
                expected_calls.append({
                    # Wait for Server Build
                    'call': 'checkmate.providers.rackspace.compute_legacy.'
                            'wait_on_build',
                    'args': [Func(is_good_context), id],
                    'kwargs': And(In('password')),
                    'result': {
                            'status': "ACTIVE",
                            '%s.status' % index: "ACTIVE",
                            'ip': '4.4.4.%s' % ip,
                            '%s.ip' % index: '4.4.4.%s' % ip,
                            'private_ip': '10.1.2.%s' % ip,
                            '%s.private_ip' % index: '10.1.2.%s' % ip,
                            'addresses': {
                              'public': [
                                {
                                  "version": 4,
                                  "addr": "4.4.4.%s" % ip,
                                },
                                {
                                  "version": 6,
                                  "addr": "2001:babe::ff04:36c%s" % index,
                                }
                              ],
                              'private': [
                                {
                                  "version": 4,
                                  "addr": "10.1.2.%s" % ip,
                                }
                              ]
                            },
                            '%s.addresses' % index: {
                              'public': [
                                {
                                  "version": 4,
                                  "addr": "4.4.4.%s" % ip,
                                },
                                {
                                  "version": 6,
                                  "addr": "2001:babe::ff04:36c%s" % index,
                                }
                              ],
                              'private': [
                                {
                                  "version": 4,
                                  "addr": "10.1.2.%s" % ip,
                                }
                              ]
                            }
                        }
                    })
                # Bootstrap Server with Chef
                expected_calls.append({
                        'call': 'checkmate.providers.opscode.local.register_node',
                        'args': ["4.4.4.%s" % ip, 'DEP-ID-1000'],
                        'kwargs': In('password'),
                        'result': None
                    })
                # build-essential and then role
                expected_calls.append({
                        'call': 'checkmate.providers.opscode.local.cook',
                        'args': ["4.4.4.%s" % ip, 'DEP-ID-1000'],
                        'kwargs': And(In('password'), ContainsKeyValue('recipes',
                                ['build-essential']),
                                ContainsKeyValue('identity_file',
                                    '/var/tmp/DEP-ID-1000/private.pem')),
                        'result': None
                    })
                expected_calls.append(
                    {
                        'call': 'checkmate.providers.opscode.local.cook',
                        'args': ["4.4.4.%s" % ip, 'DEP-ID-1000'],
                        'kwargs': And(In('password'), ContainsKeyValue('roles',
                                ["wordpress-%s" % role]),
                                ContainsKeyValue('identity_file',
                                    '/var/tmp/DEP-ID-1000/private.pem')),
                        'result': None
                    })
                if role == 'master':
                    expected_calls.append({
                        'call': 'checkmate.providers.opscode.local.manage_databag',
                        'args': ['DEP-ID-1000', 'DEP-ID-1000',
                                'webapp_wordpress_%s' % self.deployment.get_setting('prefix'),
                                And(IsA(dict), In('lsyncd'))],
                        'kwargs': And(ContainsKeyValue('secret_file',
                                'certificates/chef.pem'), ContainsKeyValue('merge',
                                True)),
                        'result': None
                    })
                    expected_calls.append(
                        {
                            'call': 'checkmate.providers.opscode.local.cook',
                            'args': ["4.4.4.%s" % ip, 'DEP-ID-1000'],
                            'kwargs': And(In('password'), ContainsKeyValue('recipes',
                                    ['lsyncd::install']),
                                    ContainsKeyValue('identity_file',
                                        '/var/tmp/DEP-ID-1000/private.pem')),
                            'result': None
                        })

                else:
                    expected_calls.append(
                        {
                            'call': 'checkmate.providers.opscode.local.cook',
                            'args': ["4.4.4.%s" % ip, 'DEP-ID-1000'],
                            'kwargs': And(In('password'), ContainsKeyValue('recipes',
                                    ["lsyncd::install_keys"]),
                                    ContainsKeyValue('identity_file',
                                        '/var/tmp/DEP-ID-1000/private.pem')),
                            'result': None
                        })
                expected_calls.append({
                        'call': 'checkmate.providers.rackspace.loadbalancer.add_node',
                        'args': [Func(is_good_context), 20001, "10.1.2.%s" % ip,
                                80, self.deployment.get_setting('region', default='testonia')],
                        'kwargs': None,
                        'result': None
                    })
            elif resource.get('type') == 'database':
                username = self.deployment.get_setting('username',
                        resource_type=resource.get('type'),
                        provider_key=resource.get('provider'),
                        default='wp_user_db1')
                expected_calls.append({
                        # Create Database
                        'call': 'checkmate.providers.rackspace.database.'
                                'create_instance',
                        'args': [Func(is_good_context),
                                IsA(basestring),
                                1, 1, [{'name': 'db1'}],
                                 self.deployment.get_setting('region', default='testonia')],
                        'kwargs': IgnoreArg(),
                        'result': {
                                'id': 'db-inst-1',
                                'name': 'dbname.domain.local',
                                'status': 'BUILD',
                                'hostname': 'verylong.rackspaceclouddb.com',
                                'region': 'testonia'}
                    })
                expected_calls.append({
                        # Create Database User
                        'call': 'checkmate.providers.rackspace.database.add_user',
                        'args': [Func(is_good_context),
                                'db-inst-1', ['db1'], username,
                                IsA(basestring),
                                 self.deployment.get_setting('region', default='testonia')],
                        'kwargs': None,
                        'result': {'db_username': username, 'db_password': 'DbPxWd'}
                    })
                expected_calls.append({
                        'call': 'checkmate.providers.opscode.local.manage_databag',
                        'args': ['DEP-ID-1000', 'DEP-ID-1000',
                                'webapp_wordpress_%s' % self.deployment.get_setting('prefix'),
                                IsA(dict)],
                        'kwargs': And(ContainsKeyValue('secret_file',
                                'certificates/chef.pem'), ContainsKeyValue('merge',
                                True)),
                        'result': None
                    })

       #Mock out celery calls
        self.mock_tasks = {}
        self.mox.StubOutWithMock(default_app, 'send_task')
        self.mox.StubOutWithMock(default_app, 'AsyncResult')
        for call in expected_calls:
            async_mock = self.mox.CreateMock(AsyncResult)
            async_mock.task_id = "MOCK%s" % uuid.uuid4().hex
            async_mock.result = call['result']
            async_mock.state = 'SUCCESS'
            self.mock_tasks[async_mock.task_id] = async_mock

            # Task is called
            default_app.send_task(call['call'], args=call['args'],
                    kwargs=call['kwargs']).InAnyOrder()\
                    .WithSideEffects(self.result_postback).AndReturn(async_mock)

            # State is checked
            async_mock.ready().AndReturn(True)

            # Data is retrieved
            default_app.AsyncResult.__call__(async_mock.task_id).AndReturn(
                    async_mock)

        return workflow


class TestWorkflowStubbing(StubbedWorkflowBase):
    """ Test Basic Server code """
    def test_workflow_run(self):
        self.deployment = Deployment(yaml_to_dict("""
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
                """))

        workflow = self._get_stubbed_out_workflow()

        self.mox.ReplayAll()

        workflow.complete_all()
        self.assertTrue(workflow.is_completed())
        self.assertNotIn('resources', self.deployment)


class TestWorkflowLogic(StubbedWorkflowBase):
    """ Test Basic Workflow code """
    def test_workflow_resource_generation(self):
        self.deployment = Deployment(yaml_to_dict("""
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
        PROVIDER_CLASSES['test.base'] = ProviderBase

        workflow = self._get_stubbed_out_workflow()

        self.mox.ReplayAll()

        workflow.complete_all()
        self.assertTrue(workflow.is_completed())
        self.assertEqual(len(workflow.get_tasks()), 3)


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
        app['id'] = 'DEP-ID-1000'
        cls.deployment = Deployment(app)

    def setUp(self):
        StubbedWorkflowBase.setUp(self)
        # Parse app.yaml as a deployment
        self.deployment = TestWorkflow.deployment
        self.workflow = self._get_stubbed_out_workflow()

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
        app['id'] = 'DEP-ID-1000'

        # WordPress Settings
        inputs = yaml_to_dict("""
                client_public_key_ssh: %s
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
                      'os': Ubuntu 12.04 LTS
                      """ % ENV_VARS['CHECKMATE_CLIENT_PUBLIC_KEY'])
        app['inputs'] = inputs
        cls.deployment = Deployment(app)

    def setUp(self):
        StubbedWorkflowBase.setUp(self)
        # Parse app.yaml as a deployment
        self.deployment = TestWordpressWorkflow.deployment
        self.workflow = self._get_stubbed_out_workflow()

    def test_workflow_completion(self):
        """Verify workflow sequence and data flow"""

        self.mox.ReplayAll()

        def recursive_tree(task, indent):
            print ' ' * indent, task.id, "-", task.name
            for child in task.outputs:
                recursive_tree(child, indent + 1)

        def pp(workflow):
            print workflow.spec.name
            recursive_tree(workflow.spec.start, 1)

            for id, task in workflow.spec.task_specs.iteritems():
                if task.inputs:
                    print task.id, "-", id
                else:
                    print task.id, "-", id, "    >>>>  DICONNECTED!"

        #pp(self.workflow)

        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(), "Workflow did not "
                "complete")

        serializer = DictionarySerializer()
        simulation = self.workflow.serialize(serializer)
        simulation['id'] = 'simulate'


class TestDBWorkflow(StubbedWorkflowBase):
    """ Test MySQL and DBaaS Workflow """

    def setUp(self):
        StubbedWorkflowBase.setUp(self)
        self.deployment = Deployment(yaml_to_dict("""
                id: 'DEP-ID-1000'
                blueprint:
                  name: test db
                  services:
                    db:
                      component:
                        id: my_sql
                        is: database
                        type: database
                        requires:
                          "server":
                            relation: host
                            interface: 'linux'
                environment:
                  name: test
                  providers:
                    database:
                      vendor: rackspace
                      provides:
                      - database: mysql
                      catalog:  # override so we don't need a token to connect
                        database:
                          mysql_instance:
                            id: mysql_instance
                            is: database
                            provides:
                            - database: mysql
                        lists:
                          regions:
                            DFW: https://dfw.databases.api.rackspacecloud.com/v1.0/T1000
                            ORD: https://ord.databases.api.rackspacecloud.com/v1.0/T1000
                          sizes:
                            1:
                              memory: 512
                              name: m1.tiny
                            2:
                              memory: 1024
                              name: m1.small
                            3:
                              memory: 2048
                              name: m1.medium
                            4:
                              memory: 4096
                              name: m1.large
                    chef-local:
                      vendor: opscode
                      provides:
                      - database: mysql
                inputs:
                  blueprint:
                    region: DFW
            """))
        self.workflow = self._get_stubbed_out_workflow()

    def test_workflow_completion(self):
        """Verify workflow sequence and data flow"""

        self.mox.ReplayAll()

        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(), "Workflow did not "
                "complete")

        serializer = DictionarySerializer()
        simulation = self.workflow.serialize(serializer)
        simulation['id'] = 'simulate'


if __name__ == '__main__':
    # Run tests. Handle our paramsters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
