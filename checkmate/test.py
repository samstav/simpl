#!/usr/bin/env python
"""File with testing primitives for use in tests and external providers"""
import json
import logging
import os
import unittest2 as unittest
import uuid

import bottle
from celery.app import default_app  # @UnresolvedImport
from celery.result import AsyncResult  # @UnresolvedImport
import mox
from mox import (IsA, In, And, IgnoreArg, ContainsKeyValue, Func, StrContains,
                 Not)
from SpiffWorkflow.specs import Celery, Transform

LOG = logging.getLogger(__name__)

from checkmate.deployment import Deployment
from checkmate import deployments

os.environ['CHECKMATE_DATA_PATH'] = os.path.join(os.path.dirname(__file__),
                                                 'data')

from checkmate.common import schema
from checkmate.exceptions import CheckmateException
from checkmate.providers import base, register_providers, get_provider_class
from checkmate.providers.base import ProviderBase
from checkmate.middleware import RequestContext  # also enables logging
from checkmate.utils import is_ssh_key, get_source_body, merge_dictionary, \
    yaml_to_dict
from checkmate.workflow import (
    create_workflow,
    create_workflow_spec_deploy,
    wait_for,
)

# Environment variables and safe alternatives
ENV_VARS = {
    'CHECKMATE_CLIENT_USERNAME': 'john.doe',
    'CHECKMATE_CLIENT_APIKEY': 'secret-api-key',
    'CHECKMATE_CLIENT_PUBLIC_KEY': ("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAA"
    "ABAQDtjYYMFbpCJ/ND3izZ1DqNFQHlooXyNcDGWilAqNqcCfz9L+gpGjY2pQlZz/1Hir"
    "3R8fz0MS9VY32RYmP3wWygt85kNccEkOpVGGpGyV/aMFaQHZD0h6d0AT+haP0Iig+OrH"
    "1YBnpdgVPWx3SbU4eV/KYGpO9Mintj3P54of22lTK4dOwCNvID9P9w+T1kMfdVxGwhqs"
    "SL0RxVXnSSkozXQWCNvaZJMUmidm8YA009c5PoksyWjl3EE+rEzZ8ywvtUJf9DvnLCES"
    "fhF3hK5lAiEd8z7gyiQnBexn/dXzldGFiJYJgQ5HolYaNMtTF+AQY6R6Qt0okCPyEDJx"
    "HJUM7d"),
    'CHECKMATE_PUBLIC_KEY': "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtj"
    "YYMFbpCJ/ND3izZ1DqNFQHlooXyNcDGWilAqNqcCfz9L+gpGjY2pQlZz/1Hir3R8fz0M"
    "S9VY32RYmP3wWygt85kNccEkOpVGGpGyV/aMFaQHZD0h6d0AT+haP0Iig+OrH1YBnpdg"
    "VPWx3SbU4eV/KYGpO9Mintj3P54of22lTK4dOwCNvID9P9w+T1kMfdVxGwhqsSL0RxVX"
    "nSSkozXQWCNvaZJMUmidm8YA009c5PoksyWjl3EE+rEzZ8ywvtUJf9DvnLCESfhF3hK5"
    "lAiEd8z7gyiQnBexn/dXzldGFiJYJgQ5HolYaNMtTF+AQY6R6Qt0okCPyEDJxHJUM7d",
    'CHECKMATE_CLIENT_PRIVATE_KEY': 'mumble-code',
    'CHECKMATE_CLIENT_DOMAIN': 'test.local',
    'CHECKMATE_CLIENT_REGION': 'chicago'
}

CATALOG = [{
    "endpoints": [{
        "publicURL": "https://monitoring.api.rackspacecloud.com/v1.0/T1000",
        "tenantId": "T1000"
    }],
    "name": "cloudMonitoring",
    "type": "rax:monitor"
},
{
    "endpoints": [
        {
            "publicURL": "https://ord.loadbalancers.api.rackspacecloud.com"
            "/v1.0/T1000",
            "region": "ORD",
            "tenantId": "T1000"
        },
        {
            "publicURL": "https://dfw.loadbalancers.api.rackspacecloud.com"
            "/v1.0/T1000",
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
            "internalURL": "https://snet-storage101.ord1.clouddrive.com"
            "/v1/Mosso_T-2000",
            "publicURL":
            "https://storage101.ord1.clouddrive.com/v1/Mosso_T-2000",
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
            "publicURL":
            "https://dfw.databases.api.rackspacecloud.com/v1.0/T1000",
            "region": "DFW",
            "tenantId": "T1000"
        },
        {
            "publicURL":
            "https://ord.databases.api.rackspacecloud.com/v1.0/T1000",
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


def register():
    register_providers([TestProvider])


def run_with_params(args):
    '''Helper method that handles command line arguments:

    Having command line parameters passed on to checkmate is handy
    for troubleshooting issues. This helper method encapsulates
    this logic so it can be used in any test.

    '''
    import unittest

    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)


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

        for call in self.expected_calls:
            if args[0] == call['call']:
                if 'resource' in call and isinstance(kwargs['args'][0], dict):
                    if call['resource'] != kwargs['args'][0]['resource']:
                        continue
                if 'post_back' in call:
                    self.deployment.on_resource_postback(call['post_back'])
                    return
                elif 'post_back_result' in call:
                    assert call['result']
                    self.deployment.on_resource_postback(call['result'])
                    return

        if args[0] == 'checkmate.providers.opscode.knife.write_databag':
            args = kwargs['args']
            bag_name = args[1]
            item_name = args[2]
            contents = args[3]
            if 'data_bags' not in self.outcome:
                self.outcome['data_bags'] = {}
            if bag_name not in self.outcome['data_bags']:
                self.outcome['data_bags'][bag_name] = {}
            if (
                kwargs.get('merge', False) is True or
                item_name not in self.outcome['data_bags'][bag_name]
            ):
                self.outcome['data_bags'][bag_name][item_name] = contents
            else:
                merge_dictionary(self.outcome['data_bags'][bag_name]
                                 [item_name], contents)
        else:
            LOG.debug("No postback for %s" % args[0])

    def _get_stubbed_out_workflow(self, expected_calls=None, context=None):
        """Returns a workflow of self.deployment with mocks attached to all
        celery calls
        """
        assert isinstance(self.deployment, Deployment)
        if not context:
            context = RequestContext(auth_token="MOCK_TOKEN",
                                     tenant='TMOCK',
                                     username="MOCK_USER", catalog=CATALOG,
                                     base_url='http://MOCK')
        if self.deployment.get('status') == 'NEW':
            deployments.Manager.plan(self.deployment, context)
        LOG.debug(json.dumps(self.deployment.get('resources', {}), indent=2))
        workflow_spec = create_workflow_spec_deploy(self.deployment, context)
        workflow = create_workflow(workflow_spec, self.deployment, context)

        if not expected_calls:
            expected_calls = self._get_expected_calls()
        self.expected_calls = expected_calls
        if not expected_calls:
            raise CheckmateException("Unable to identify expected calls "
                                     "which is needed to run a simulated "
                                     "workflow")

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
            default_app.send_task(
                call['call'], args=call['args'],
                kwargs=call['kwargs']
            ).InAnyOrder().WithSideEffects(
                self.result_postback
            ).AndReturn(async_mock)

            # State is checked
            async_mock.ready().AndReturn(True)

            # To Mock data retrieval - but this has been commented out
            # since SpiffWorkflow only calls this when rehydrating a workflow
            #
            #default_app.AsyncResult.__call__(async_mock.task_id).AndReturn(
            #        async_mock)

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
                LOG.warn(
                    "Create server files has %s keys, which is less than 2" %
                    len(entries)
                )
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
                if key not in [
                    'wordpress', 'user', 'lsyncd', 'mysql', 'apache'
                ]:
                    return False
            return True

        expected_calls = [{
            # Create Chef Environment
            'call': 'checkmate.providers.opscode.knife.create_environment',
            'args': [self.deployment['id'], IgnoreArg()],
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
        }]

        if str(os.environ.get(
            'CHECKMATE_CHEF_USE_DATA_BAGS',
            True)
        ).lower() in ['true', '1', 'yes']:
            expected_calls.append({
                'call': 'checkmate.providers.opscode.knife.write_databag',
                'args': [self.deployment['id'],
                        self.deployment['id'],
                        self.deployment.settings().get('app_id'),
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
                if resource.get('provider') == 'nova':
                    expected_calls.append({
                        # Create Server
                        'call': 'checkmate.providers.rackspace.compute.'
                                'create_server',
                        'args': [
                            Func(is_good_context),
                            StrContains(name),
                            self.deployment.get_setting(
                                'region',
                                default='testonia'
                            )
                        ],
                        'kwargs': And(
                            ContainsKeyValue('image', image),
                            ContainsKeyValue('flavor', flavor)
                        ),
                        'result': {
                            'instance:%s' % key: {
                                'id': id,
                                'password': "shecret",
                            }
                        },
                        'post_back_result': True,
                        'resource': key,
                    })
                    expected_calls.append({
                        # Wait for Server Build
                        'call': 'checkmate.providers.rackspace.compute'
                                '.wait_on_build',
                        'args': [
                            Func(is_good_context), id,
                            self.deployment.get_setting(
                                'region', default='testonia')
                        ],
                        'kwargs': And(In('password')),
                        'result': {
                            'instance:%s' % key: {
                                'status': "ACTIVE",
                                'ip': '4.4.4.%s' % ip,
                                'private_ip': '10.1.2.%s' % ip,
                                'addresses': {
                                    'public': [
                                        {
                                            "version": 4,
                                            "addr": "4.4.4.%s" % ip,
                                        },
                                        {
                                            "version": 6,
                                            "addr":
                                            "2001:babe::ff04:36c%s" % index,
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
                        },
                        'post_back_result': True,
                        'resource': key,
                    })
                else:
                    expected_calls.append({
                        # Create Server
                        'call': 'checkmate.providers.rackspace.compute_legacy.'
                                'create_server',
                        'args': [Func(is_good_context),
                                StrContains(name)],
                        'kwargs': And(ContainsKeyValue('image', image),
                                ContainsKeyValue('flavor', flavor),
                                ContainsKeyValue('ip_address_type', 'public')),
                        'result': {
                                'instance:%s' % key: {
                                    'id': id,
                                    'ip': "4.4.4.%s" % ip,
                                    'private_ip': "10.1.1.%s" % ip,
                                    'password': "shecret",
                                }
                        },
                        'post_back_result': True,
                        'resource': key,
                    })
                    expected_calls.append({
                        # Wait for Server Build
                        'call': 'checkmate.providers.rackspace.compute_legacy'
                                '.wait_on_build',
                        'args': [Func(is_good_context), id],
                        'kwargs': And(In('password')),
                        'result': {
                            'instance:%s' % key: {
                                'status': "ACTIVE",
                                'ip': '4.4.4.%s' % ip,
                                'private_ip': '10.1.2.%s' % ip,
                                'addresses': {
                                    'public': [
                                        {
                                            "version": 4,
                                            "addr": "4.4.4.%s" % ip,
                                        },
                                        {
                                            "version": 6,
                                            "addr":
                                            "2001:babe::ff04:36c%s" % index,
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
                        },
                        'post_back_result': True,
                        'resource': key,
                    })
                # Bootstrap Server with Chef
                expected_calls.append({
                    'call': 'checkmate.providers.opscode.local.'
                            'register_node',
                    'args': ["4.4.4.%s" % ip, self.deployment['id']],
                    'kwargs': In('password'),
                    'result': None,
                    'resource': key,
                })

                # build-essential (now just cook with bootstrap.json)
                expected_calls.append({
                    'call': 'checkmate.providers.opscode.knife.cook',
                    'args': ["4.4.4.%s" % ip, self.deployment['id']],
                    'kwargs': And(
                        In('password'), Not(In('recipes')),
                        Not(In('roles')),
                        ContainsKeyValue(
                            'identity_file',
                            '/var/tmp/%s/private.pem' %
                            self.deployment['id']
                        )
                    ),
                    'result': None,
                    'resource': key,
                })
                # Cook with role
                expected_calls.append(
                    {
                        'call': 'checkmate.providers.opscode.knife.cook',
                        'args': ["4.4.4.%s" % ip, self.deployment['id']],
                        'kwargs': And(In('password'), ContainsKeyValue(
                            'roles',
                            ["wordpress-%s" % role]),
                            ContainsKeyValue(
                                'identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id'])),
                        'result': None,
                        'resource': key,
                    })
                if role == 'master':
                    expected_calls.append({
                        'call': 'checkmate.providers.opscode.'
                                'knife.write_databag',
                        'args': [self.deployment['id'],
                                self.deployment['id'],
                                'webapp_wordpress_%s' %
                                self.deployment.get_setting('prefix'),
                                And(IsA(dict), In('lsyncd'))],
                        'kwargs': And(
                            ContainsKeyValue('secret_file',
                                'certificates/chef.pem'),
                            ContainsKeyValue('merge', True)),
                        'result': None,
                        'resource': key,
                    })
                    expected_calls.append(
                        {
                            'call': 'checkmate.providers.opscode.knife.cook',
                            'args': ["4.4.4.%s" % ip, self.deployment['id']],
                            'kwargs': And(
                                In('password'),
                                ContainsKeyValue(
                                    'recipes',
                                    ['lsyncd::install']
                                ),
                                ContainsKeyValue(
                                    'identity_file',
                                    '/var/tmp/%s/private.pem' %
                                    self.deployment['id']
                                )
                            ),
                            'result': None,
                            'resource': key,
                        })

                else:
                    expected_calls.append(
                        {
                            'call': 'checkmate.providers.opscode.knife.cook',
                            'args': ["4.4.4.%s" % ip, self.deployment['id']],
                            'kwargs': And(
                                In('password'),
                                ContainsKeyValue(
                                    'recipes',
                                    ["lsyncd::install_keys"]),
                                ContainsKeyValue(
                                    'identity_file',
                                    '/var/tmp/%s/private.pem' %
                                    self.deployment['id']
                                )
                            ),
                            'result': None,
                            'resource': key,
                        })
                expected_calls.append({
                    'call':
                    'checkmate.providers.rackspace.loadbalancer.'
                    'add_node',
                    'args':
                    [
                        Func(is_good_context),
                        20001,
                        "10.1.2.%s" % ip,
                        80,
                        self.deployment.get_setting(
                            'region',
                            default='testonia'
                        )
                    ],
                    'kwargs': None,
                    'result': None,
                    'resource': key,
                })
            elif resource.get('type') == 'compute' and 'disk' in resource:
                expected_calls.extend([{
                    # Create Instance
                    'call': 'checkmate.providers.rackspace.database.'
                            'create_instance',
                    'args': [
                        Func(is_good_context),
                        IsA(basestring),
                        '1',
                        1,
                        None,
                        self.deployment.get_setting(
                            'region',
                            resource_type='compute',
                            service_name=resource['service'],
                            provider_key=resource['provider'],
                            default='testonia'
                        )
                    ],
                    'kwargs': IgnoreArg(),
                    'result': {
                        #'id': 'db-inst-1',
                        'instance:%s' % key: {
                            'id': 'db-inst-1',
                            'name': 'dbname.domain.local',
                            'status': 'BUILD',
                            'region': self.deployment.get_setting(
                                    'region', default='testonia'),
                            'interfaces': {
                                'mysql': {
                                    'host': 'verylong.rackspaceclouddb.com',
                                },
                            },
                            'databases': {}
                        },
                    },
                    'post_back_result': True,
                    'resource': key,
                }, {  # wait_on_build
                    'call': 'checkmate.providers.rackspace.database.'
                            'wait_on_build',
                    'args': [
                        Func(is_good_context),
                        IgnoreArg(),
                        self.deployment.get_setting(
                            'region',
                            resource_type='compute',
                            service_name=resource['service'],
                            provider_key=resource['provider'],
                            default='testonia'
                        )
                    ],
                    'kwargs': IgnoreArg(),
                    'result': {
                        #'id': 'db-inst-1',
                        'instance:%s' % key: {
                            'id': 'db-inst-1',
                            'status': 'ACTIVE'
                        },
                    },
                    'post_back_result': True,
                    'resource': key,
                }])
            elif resource.get('type') == 'database':
                username = self.deployment.get_setting(
                    'username',
                    resource_type=resource.get('type'),
                    provider_key=resource.get('provider'),
                    default='wp_user_db1'
                )
                expected_calls.append({
                    # Create Database
                    'call': 'checkmate.providers.rackspace.database.'
                            'create_database',
                    'args': IgnoreArg(),
                    'kwargs': IgnoreArg(),
                    'result': {
                        'instance:%s' % key: {
                            'name': 'db1',
                            'host_instance': 'db-inst-1',
                            'host_region': self.deployment.get_setting(
                                'region', default='testonia'),
                            'interfaces': {
                                'mysql': {
                                    'host': 'verylong.rackspaceclouddb.com',
                                    'database_name': 'db1',
                                },
                            }
                        }
                    },
                    'post_back_result': True,
                    'resource': key,
                })
                expected_calls.append({
                    # Create Database User
                    'call':
                    'checkmate.providers.rackspace.database.add_user',
                    'args': [
                        Func(is_good_context),
                        'db-inst-1',
                        ['db1'],
                        username,
                        IsA(basestring),
                        self.deployment.get_setting(
                            'region',
                            default='testonia'
                        )
                    ],
                    'kwargs': None,
                    'result': {
                        'instance:%s' % key: {
                            'username': username,
                            'password': 'DbPxWd',
                            'interfaces': {
                                'mysql': {
                                    'username': username,
                                    'password': 'DbPxWd',
                                }
                            }
                        }
                    },
                    'post_back_result': True,
                    'resource': key,
                })
                expected_calls.append({
                    'call': 'checkmate.providers.opscode.knife.write_databag',
                    'args': [
                        self.deployment['id'],
                        self.deployment['id'],
                        'webapp_wordpress_%s' %
                            self.deployment.get_setting('prefix'),
                            IsA(dict)],
                    'kwargs': And(ContainsKeyValue('secret_file',
                        'certificates/chef.pem'),
                        ContainsKeyValue('merge', True)),
                    'result': None,
                    'resource': key,
                })
            elif resource.get('type') == 'load-balancer':
                expected_calls.append({
                    # Create Load Balancer
                    'call': 'checkmate.providers.rackspace.loadbalancer.'
                            'create_loadbalancer',
                    'args': [
                        Func(is_good_context), IsA(basestring),
                        'PUBLIC',
                        'HTTP', 80,
                        self.deployment.get_setting(
                            'region',
                            default='testonia')],
                        'kwargs': ContainsKeyValue(
                            tag, {'RAX-CHECKMATE': IgnoreArg()}
                        ),
                    'result': {
                        'instance:%s' % key: {
                            'id': 20001, 'vip': "200.1.1.1",
                            'lbid': 20001
                        }
                    },
                    'post_back_result': True,
                    'resource': key,
                })
        return expected_calls


class TestProvider(ProviderBase):
    """Provider that returns mock responses for testing

    Defers to ProviderBase for most functionality, but implements
    prep_environment, add_connection_tasks and add_resource_tasks
    """
    name = "base"
    vendor = "test"

    def prep_environment(self, wfspec, deployment, context):
        pass

    def add_resource_tasks(self, resource, key, wfspec,
                           deployment, context, wait_on=None):
        wait_on, service_name, component = self._add_resource_tasks_helper(
            resource, key, wfspec, deployment, context, wait_on)

        create_instance_task = Celery(
            wfspec,
            'Create Resource %s' % key,
            'checkmate.providers.test.create_resource',
            call_args=[
                context.get_queued_task_dict(
                    deployment=deployment['id'],
                    resource=key
                ),
                resource,
            ],
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['create', 'final']
            )
        )
        root = wait_for(wfspec, create_instance_task, wait_on)
        if 'task_tags' in root.properties:
            root.properties['task_tags'].append('root')
        else:
            root.properties['task_tags'] = ['root']
        return dict(root=root, final=create_instance_task)

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        target = deployment['resources'][relation['target']]
        interface = relation['interface']

        if relation_key == 'host':
            # Wait on host to be ready
            wait_on = self.get_host_ready_tasks(
                resource,
                wfspec,
                deployment
            )
            if not wait_on:
                raise CheckmateException("No host")

        # Get the definition of the interface
        interface_schema = schema.INTERFACE_SCHEMA.get(interface, {})
        # Get the fields this interface defines
        fields = interface_schema.get('fields', {}).keys()
        if not fields:
            LOG.debug(
                "No fields defined for interface '%s', so nothing "
                "to do for connection '%s'" % (interface, relation_key)
            )
            return  # nothing to do

        # Build full path to 'instance:id/interfaces/:interface/:field_name'
        fields_with_path = []
        for field in fields:
            fields_with_path.append('instance:%s/interfaces/%s/%s' % (
                relation['target'], interface, field))

        # Get the final task for the target
        target_final = self.find_tasks(
            wfspec,
            provider=target['provider'],
            resource=relation['target'],
            tag='final'
        )
        if not target_final:
            raise CheckmateException("Relation final task not found")
        if len(target_final) > 1:
            raise CheckmateException(
                "Multiple relation final tasks "
                "found: %s" % [t.name for t in target_final]
            )
        target_final = target_final[0]

        # Write the task to get the values
        def get_fields_code(my_task):  # Holds code for the task
            fields = my_task.get_property('fields', [])
            data = {}
            # Get fields by navigating path
            for field in fields:
                parts = field.split('/')
                current = my_task.attributes
                for part in parts:
                    if part not in current:
                        current = None
                        break
                    current = current[part]
                if current:
                    data[field.split('/')[-1]] = current
                else:
                    LOG.warn(
                        "Field %s not found" % field,
                        extra=dict(data=my_task.attributes)
                    )
            merge_dictionary(my_task.attributes, data)

        compile_override = Transform(
            wfspec,
            "Get %s values for %s" % (relation_key, key),
            transforms=[get_source_body(get_fields_code)],
            description="Get all the variables we need (like database name "
            "and password) and compile them into JSON",
            defines=dict(
                relation=relation_key,
                provider=self.key,
                resource=key,
                fields=fields_with_path,
                task_tags=['final'])
        )
        # When target is ready, compile data
        wait_for(wfspec, compile_override, [target_final])
        # Provide data to 'final' task
        tasks = self.find_tasks(
            wfspec,
            provider=resource['provider'],
            resource=key, tag='final'
        )
        if tasks:
            for task in tasks:
                wait_for(wfspec, task, [compile_override])


class ProviderTester(unittest.TestCase):
    """Basic Provider Test Suite

    To use this, load it in the provider tests and set the override the klass
    property with the provider class to test:

        from checkmate import test

        class TestMe(test.ProviderTests):
            klass = module.MyProviderClass

    """

    klass = TestProvider

    def setUp(self):
        self.mox = mox.Mox()

    def test_provider_key(self):
        provider = self.klass({})
        self.assertEqual(provider.key, '%s.%s' % (self.klass.vendor,
                                                  self.klass.name))

    def test_provider_key_override(self):
        provider = self.klass({}, key="custom.value")
        self.assertEqual(provider.key, "custom.value")

    def test_provider_override(self):
        """Test that an injected catalog and config gets applied"""
        override = yaml_to_dict("""
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
            """)
        provider = self.klass(override)
        self.assertListEqual(provider.provides(None), override['provides'])
        self.assertDictEqual(provider.get_catalog(None), override['catalog'])

    def test_provider_loads_unregistered(self):
        """Check that provider loads without registration"""
        if not isinstance(self.klass, TestProvider):
            self.assertIs(get_provider_class(self.klass.vendor,
                                             self.klass.name), self.klass)

    def test_provider_loads_registered(self):
        """Check that provider loads"""
        base.PROVIDER_CLASSES = {}
        register_providers([self.klass])
        self.assertTrue(issubclass(get_provider_class(self.klass.vendor,
                                                      self.klass.name),
                                   ProviderBase))

    def test_provider_registration(self):
        """Check that provider class registers"""
        base.PROVIDER_CLASSES = {}
        register_providers([self.klass])
        key = self.klass({}).key
        self.assertIn(key, base.PROVIDER_CLASSES)
        self.assertIs(base.PROVIDER_CLASSES[key], self.klass)

    def test_translate_status(self):
        '''Tests that provider status is translated'''
        expected = 'UNDEFINED'
        results = self.klass.translate_status('DOESNOTEXIST')
        self.assertEqual(expected, results)

    def tearDown(self):
        self.mox.UnsetStubs()


class MockContext(dict):
    '''Used to mock RequestContext'''
    is_admin = False
    tenant = None
    username = "Ziad"
    simulation = False


class MockWsgiFilters(object):
    '''Used to mock Context, Extension, and Tenant Middleware'''

    def __init__(self, app):
        self.app = app
        self.context = MockContext()

    def __call__(self, environ, start_response):
        '''Add context, strip out tenant if not already mocked'''
        bottle.request.context = self.context
        bottle.request.accept = 'application/json'
        path = environ['PATH_INFO']
        if path and not self.context.tenant:
            parts = path.strip('/').split('/')
            if parts[0] != 'admin':
                self.context.tenant = parts[0]
                environ['PATH_INFO'] = '/%s' % '/'.join(parts[1:])
        return self.app(environ, start_response)
