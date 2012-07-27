#!/usr/bin/env python
"""File with testing primitives for use in tests and external providers"""
import json
import logging
import os
import unittest2 as unittest
import uuid

from celery.app import default_app
from celery.result import AsyncResult
import mox
from mox import IsA, In, And, IgnoreArg, ContainsKeyValue, Func, StrContains

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate.common import schema
from checkmate.deployments import Deployment

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
from checkmate.deployments import plan
from checkmate.utils import is_ssh_key, merge_dictionary
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
        self.outcome = {}  # store results and end state as simulation runs

    def tearDown(self):
        self.mox.UnsetStubs()

    def result_postback(self, *args, **kwargs):
        """Simulates a postback from the called resource which updates the
        deployment data. The results will be appended to the simulated
        deployment results"""
        # If we need to get the calling task, use inspect. The call stack is
        # self->mock->method->class (so 3 in a zero-based index)
        # import inspect
        # obj = inspect.stack()[3][0].f_locals['self']
        # print obj.name

        if args[0] == 'checkmate.providers.rackspace.database.'\
                'create_instance':
            args = kwargs['args']
            context = args[0]
            self.deployment.on_resource_postback(context['resource'],
                    {
                        'id': 'db-inst-1',
                        'instance':  {
                            'id': 'db-inst-1',
                            'name': 'dbname.domain.local',
                            'status': 'BUILD',
                            'region': 'testonia',
                            'interfaces': {
                                'mysql': {
                                    'host': 'verylong.rackspaceclouddb'
                                            '.com',
                                    },
                                },
                            'databases': {}
                            },
                    })
        elif args[0] == 'checkmate.providers.rackspace.database.'\
                'create_database':
            args = kwargs['args']
            context = args[0]
            self.deployment.on_resource_postback(context['resource'],
                    {
                            'instance': {
                                    'name': 'db1',
                                    'host_instance': 'db-inst-1',
                                    'host_region': self.deployment.get_setting(
                                            'region', default='testonia'),
                                    'interfaces': {
                                            'mysql': {
                                                    'host': 'verylong.rackspaceclouddb.com',
                                                    'database_name': 'db1',
                                                },
                                        },
                                },
                        })
        elif args[0] == 'checkmate.providers.rackspace.database.add_user':
            args = kwargs['args']
            context = args[0]
            self.deployment.on_resource_postback(context['resource'],
                    dict(instance=schema.translate_dict({  # TODO: This is a copy of call results. Consolidate?
                        'username': args[3],
                        'password': args[4]})))
        elif args[0] == 'checkmate.providers.opscode.local.manage_databag':
            args = kwargs['args']
            bag_name = args[1]
            item_name = args[2]
            contents = args[3]
            if 'data_bags' not in self.outcome:
                self.outcome['data_bags'] = {}
            if bag_name not in self.outcome['data_bags']:
                self.outcome['data_bags'][bag_name] = {}
            if kwargs.get('merge', False) == True or \
                    item_name not in self.outcome['data_bags'][bag_name]:
                self.outcome['data_bags'][bag_name][item_name] = contents
            else:
                merge_dictionary(self.outcome['data_bags'][bag_name]
                        [item_name], contents)

    def _get_stubbed_out_workflow(self, expected_calls=None):
        """Returns a workflow of self.deployment with mocks attached to all
        celery calls
        """
        assert isinstance(self.deployment, Deployment)
        context = RequestContext(auth_token="MOCK_TOKEN", username="MOCK_USER",
                catalog=CATALOG)
        plan(self.deployment, context)
        print json.dumps(self.deployment['resources'], indent=2)

        workflow = create_workflow(self.deployment, context)

        if not expected_calls:
            expected_calls = self._get_expected_calls()

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
                    .WithSideEffects(self.result_postback).AndReturn(
                            async_mock)

            # State is checked
            async_mock.ready().AndReturn(True)

            # Data is retrieved
            default_app.AsyncResult.__call__(async_mock.task_id).AndReturn(
                    async_mock)

        return workflow

    def _get_expected_calls(self):

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
                'args': [self.deployment['id']],
                'kwargs': And(ContainsKeyValue('private_key', IgnoreArg()),
                        ContainsKeyValue('secret_key', IgnoreArg()),
                        ContainsKeyValue('public_key_ssh', IgnoreArg())),
                'result': {
                    'environment': '/var/tmp/%s/' % self.deployment['id'],
                    'kitchen': '/var/tmp/%s/kitchen' % self.deployment['id'],
                    'private_key_path': '/var/tmp/%s/private.pem' %
                            self.deployment['id'],
                    'public_key_path': '/var/tmp/%s/checkmate.pub' %
                            self.deployment['id'],
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
                    'args': [self.deployment['id'],
                            self.deployment['id'],
                            'webapp_wordpress_%s' %
                                    self.deployment.get_setting('prefix'),
                            Func(is_good_data_bag)],
                    'kwargs': And(ContainsKeyValue('secret_file',
                            'certificates/chef.pem'), ContainsKeyValue('merge',
                            True)),
                    'result': None
                })
        else:
            expected_calls.append({
                    'call': 'checkmate.providers.opscode.local.manage_role',
                    'args': ['wordpress-web', self.deployment['id']],
                    'kwargs': {'override_attributes': {'wordpress': {'db': {
                            'host': 'verylong.rackspaceclouddb.com',
                            'password': IsA(basestring),
                            'user': os.environ['USER'],
                            'database': 'db1'}}}},
                    'result': None
                })
        # Add repetive calls (per resource)
        for key, resource in self.deployment.get('resources', {}).iteritems():
            if resource.get('type') == 'compute' and 'image' in resource:
                if 'master' in resource['dns-name']:
                    id = 10000 + int(key)  # legacy format
                    role = 'master'
                    ip = 100
                else:
                    id = "10-uuid-00%s" % key  # Nova format
                    role = 'web'
                    ip = int(key) + 1
                name = resource['dns-name']
                flavor = resource['flavor']
                index = key
                image = resource['image']

                expected_calls.append({
                    # Create Server
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
                        'call': 'checkmate.providers.opscode.local.'
                                'register_node',
                        'args': ["4.4.4.%s" % ip, self.deployment['id']],
                        'kwargs': In('password'),
                        'result': None
                    })
                # build-essential and then role
                expected_calls.append({
                        'call': 'checkmate.providers.opscode.local.cook',
                        'args': ["4.4.4.%s" % ip, self.deployment['id']],
                        'kwargs': And(In('password'),
                                        ContainsKeyValue('recipes',
                                            ['build-essential']),
                                        ContainsKeyValue('identity_file',
                                                '/var/tmp/%s/private.pem' %
                                                self.deployment['id'])),
                        'result': None
                    })
                expected_calls.append(
                    {
                        'call': 'checkmate.providers.opscode.local.cook',
                        'args': ["4.4.4.%s" % ip, self.deployment['id']],
                        'kwargs': And(In('password'), ContainsKeyValue('roles',
                                ["wordpress-%s" % role]),
                                ContainsKeyValue('identity_file',
                                        '/var/tmp/%s/private.pem' %
                                        self.deployment['id'])),
                        'result': None
                    })
                if role == 'master':
                    expected_calls.append({
                        'call': 'checkmate.providers.opscode.local.'
                                'manage_databag',
                        'args': [self.deployment['id'],
                                self.deployment['id'],
                                'webapp_wordpress_%s' %
                                        self.deployment.get_setting('prefix'),
                                And(IsA(dict), In('lsyncd'))],
                        'kwargs': And(ContainsKeyValue('secret_file',
                                        'certificates/chef.pem'),
                                        ContainsKeyValue('merge', True)),
                        'result': None
                    })
                    expected_calls.append(
                        {
                            'call': 'checkmate.providers.opscode.local.cook',
                            'args': ["4.4.4.%s" % ip, self.deployment['id']],
                            'kwargs': And(In('password'),
                                    ContainsKeyValue('recipes',
                                    ['lsyncd::install']),
                                    ContainsKeyValue('identity_file',
                                            '/var/tmp/%s/private.pem' %
                                            self.deployment['id'])),
                            'result': None
                        })

                else:
                    expected_calls.append(
                        {
                            'call': 'checkmate.providers.opscode.local.cook',
                            'args': ["4.4.4.%s" % ip, self.deployment['id']],
                            'kwargs': And(In('password'),
                                    ContainsKeyValue('recipes',
                                    ["lsyncd::install_keys"]),
                                    ContainsKeyValue('identity_file',
                                            '/var/tmp/%s/private.pem' %
                                            self.deployment['id'])),
                            'result': None
                        })
                expected_calls.append({
                        'call': 'checkmate.providers.rackspace.loadbalancer.'
                                'add_node',
                        'args': [Func(is_good_context),
                                20001,
                                "10.1.2.%s" % ip,
                                80,
                                self.deployment.get_setting('region',
                                        default='testonia')],
                        'kwargs': None,
                        'result': None
                    })
            elif resource.get('type') == 'compute' and 'disk' in resource:
                expected_calls.append({
                        # Create Instance
                        'call': 'checkmate.providers.rackspace.database.'
                                'create_instance',
                        'args': [Func(is_good_context),
                                IsA(basestring),
                                1,
                                '1',
                                None,
                                self.deployment.get_setting('region',
                                        default='testonia')],
                        'kwargs': IgnoreArg(),
                        'result': {
                                'id': 'db-inst-1',
                                'instance':  {
                                    'id': 'db-inst-1',
                                    'name': 'dbname.domain.local',
                                    'status': 'BUILD',
                                    'region': self.deployment.get_setting(
                                            'region', default='testonia'),
                                    'interfaces': {
                                        'mysql': {
                                            'host': 'verylong.rackspaceclouddb'
                                                    '.com',
                                            },
                                        },
                                    'databases': {}
                                    },
                            }
                    })
            elif resource.get('type') == 'database':
                username = self.deployment.get_setting('username',
                        resource_type=resource.get('type'),
                        provider_key=resource.get('provider'),
                        default='wp_user_db1')
                expected_calls.append({
                        # Create Database
                        'call': 'checkmate.providers.rackspace.database.'
                                'create_database',
                        'args': [Func(is_good_context),
                                'db1',
                                self.deployment.get_setting('region',
                                        default='testonia'),
                                ],
                        'kwargs': ContainsKeyValue('instance_id', 'db-inst-1'),
                        'result': {
                                'instance': {
                                    'name': 'db1',
                                    'host_instance': 'db-inst-1',
                                    'host_region': self.deployment.get_setting(
                                            'region', default='testonia'),
                                    'interfaces': {
                                        'mysql': {
                                            'host': 'verylong.'
                                                    'rackspaceclouddb'
                                                    '.com',
                                            'database_name': 'db1',
                                            },
                                        }
                                    }
                                },
                    })
                expected_calls.append({
                        # Create Database User
                        'call': 'checkmate.providers.rackspace.database.'
                                'add_user',
                        'args': [Func(is_good_context),
                                'db-inst-1',
                                ['db1'],
                                username,
                                IsA(basestring),
                                self.deployment.get_setting('region',
                                        default='testonia')],
                        'kwargs': None,
                        'result': {'username': username, 'password': 'DbPxWd'}
                    })
                expected_calls.append({
                        'call': 'checkmate.providers.opscode.local.'
                                'manage_databag',
                        'args': [self.deployment['id'],
                                self.deployment['id'],
                                'webapp_wordpress_%s' %
                                        self.deployment.get_setting('prefix'),
                                IsA(dict)],
                        'kwargs': And(ContainsKeyValue('secret_file',
                                'certificates/chef.pem'),
                                ContainsKeyValue('merge', True)),
                        'result': None
                    })
        return expected_calls
