# pylint: disable=C0302,R0904,C0103,R0903
# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

#!/usr/bin/env python

"""File with testing primitives for use in tests and external providers."""

import json
import logging
import os
import sys
import unittest
import uuid

import bottle
from celery.app import default_app
from celery.result import AsyncResult
import mock
import mox
from SpiffWorkflow import specs

from checkmate.deployment import Deployment
from checkmate import deployments
from checkmate import workflow_spec

os.environ['CHECKMATE_DATA_PATH'] = os.path.join(os.path.dirname(__file__),
                                                 'data')

from checkmate.common import schema
from checkmate import exceptions
from checkmate import middleware
from checkmate.providers import base
from checkmate import utils
from checkmate.workflow import init_spiff_workflow

# Environment variables and safe alternatives
ENV_VARS = {
    'CHECKMATE_CLIENT_USERNAME': 'john.doe',
    'CHECKMATE_CLIENT_APIKEY': 'secret-api-key',
    'CHECKMATE_CLIENT_PUBLIC_KEY': """ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAA\
ABAQDtjYYMFbpCJ/ND3izZ1DqNFQHlooXyNcDGWilAqNqcCfz9L+gpGjY2pQlZz/1Hir\
3R8fz0MS9VY32RYmP3wWygt85kNccEkOpVGGpGyV/aMFaQHZD0h6d0AT+haP0Iig+OrH\
1YBnpdgVPWx3SbU4eV/KYGpO9Mintj3P54of22lTK4dOwCNvID9P9w+T1kMfdVxGwhqs\
SL0RxVXnSSkozXQWCNvaZJMUmidm8YA009c5PoksyWjl3EE+rEzZ8ywvtUJf9DvnLCES\
fhF3hK5lAiEd8z7gyiQnBexn/dXzldGFiJYJgQ5HolYaNMtTF+AQY6R6Qt0okCPyEDJx\
HJUM7d""",
    'CHECKMATE_PUBLIC_KEY': """ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtj\
YYMFbpCJ/ND3izZ1DqNFQHlooXyNcDGWilAqNqcCfz9L+gpGjY2pQlZz/1Hir3R8fz0M\
S9VY32RYmP3wWygt85kNccEkOpVGGpGyV/aMFaQHZD0h6d0AT+haP0Iig+OrH1YBnpdg\
VPWx3SbU4eV/KYGpO9Mintj3P54of22lTK4dOwCNvID9P9w+T1kMfdVxGwhqsSL0RxVX\
nSSkozXQWCNvaZJMUmidm8YA009c5PoksyWjl3EE+rEzZ8ywvtUJf9DvnLCESfhF3hK5\
lAiEd8z7gyiQnBexn/dXzldGFiJYJgQ5HolYaNMtTF+AQY6R6Qt0okCPyEDJxHJUM7d""",
    'CHECKMATE_CLIENT_PRIVATE_KEY': 'mumble-code',
    'CHECKMATE_CLIENT_DOMAIN': 'test.local',
    'CHECKMATE_CLIENT_REGION': 'chicago'
}

CATALOG = [
    {
        "endpoints": [{
            "publicURL":
            "https://monitoring.api.rackspacecloud.com/v1.0/T1000",
            "tenantId": "T1000"
        }],
        "name": "cloudMonitoring",
        "type": "rax:monitor"
    },
    {
        "endpoints": [
            {
                "publicURL":
                "https://ord.loadbalancers.api.rackspacecloud.com/v1.0/T1000",
                "region": "ORD",
                "tenantId": "T1000"
            },
            {
                "publicURL":
                "https://dfw.loadbalancers.api.rackspacecloud.com/v1.0/T1000",
                "region": "DFW",
                "tenantId": "T1000"
            }
        ],
        "name": "cloudLoadBalancers",
        "type": "rax:load-balancer"
    },
    {
        "endpoints": [{
            "internalURL":
            "https://snet-storage101.ord1.clouddrive.com/v1/Mosso_T-2000",
            "publicURL":
            "https://storage101.ord1.clouddrive.com/v1/Mosso_T-2000",
            "region": "ORD",
            "tenantId": "Mossos_T-2000"
        }],
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
                "publicURL": "https://servers.api.rackspacecloud.com/v1.0/T100\
0",
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
                "publicURL": "https://dfw.servers.api.rackspacecloud.com/v2/T1\
00",
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
LOG = logging.getLogger(__name__)


def mock_object(test_self, target, method_name):
    """Helper function to mock objects in a setUp() method of a test class.

    :param test_self: the test_self of the unittest.TestCase instance
    :param target: the object to mock
    """
    patcher = mock.patch.object(target, method_name)
    the_mock = patcher.start()
    test_self.addCleanup(the_mock.stop)
    return the_mock


def register():
    """Register TestProviders.

    This makes this module behave like a real provider package.
    """
    base.register_providers([TestProvider])


def run_with_params(args=None):
    """Helper method that handles command line arguments.

    Having command line parameters passed on to checkmate is handy
    for troubleshooting issues. This helper method encapsulates
    this logic so it can be used in any test.

    :param args: will use sys.argv[:] if not passed in
    """
    if args is None:
        args = sys.argv[:]

    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)


class StubbedWorkflowBase(unittest.TestCase):

    """Base class that stubbs out a workflow so it does not call live APIs."""

    def setUp(self):
        self.mox = mox.Mox()
        self.deployment = None
        self.outcome = {}  # store results and end state as simulation runs
        self.expected_calls = None
        self.mock_tasks = None

    def tearDown(self):
        self.mox.UnsetStubs()

    def result_postback(self, *args, **kwargs):
        """Simulates a postback from the called resource.

        This updates the deployment data. The results will be appended to the
        simulated deployment results.
        """
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

        if args[0] == ('checkmate.providers.opscode.solo.tasks'
                       '.write_databag_v2'):
            args = kwargs['args']
            bag_name = args[2]
            item_name = args[3]
            contents = args[4]
            if 'data_bags' not in self.outcome:
                self.outcome['data_bags'] = {}
            if bag_name not in self.outcome['data_bags']:
                self.outcome['data_bags'][bag_name] = {}
            if item_name not in self.outcome['data_bags'][bag_name]:
                self.outcome['data_bags'][bag_name][item_name] = contents
            else:
                utils.merge_dictionary(self.outcome['data_bags'][bag_name]
                                       [item_name], contents)
        else:
            LOG.debug("No postback for %s", args[0])

    def _get_stubbed_out_workflow(self, expected_calls=None, context=None):
        """Return a self.deployment workflow with all celery calls mocked."""
        assert isinstance(self.deployment, Deployment)
        if not context:
            context = middleware.RequestContext(auth_token="MOCK_TOKEN",
                                                tenant='TMOCK',
                                                username="MOCK_USER",
                                                catalog=CATALOG,
                                                base_url='http://MOCK')
        if self.deployment.get('status') == 'NEW':
            deployments.Manager.plan(self.deployment, context)
        LOG.debug(json.dumps(self.deployment.get('resources', {}), indent=2))
        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(context,
                                                               self.deployment)
        workflow = init_spiff_workflow(wf_spec, self.deployment,
                                       context, "w_id", "BUILD")

        if not expected_calls:
            expected_calls = self._get_expected_calls()
        self.expected_calls = expected_calls
        if not expected_calls:
            raise exceptions.CheckmateException("Unable to identify expected "
                                                "calls which is needed to run "
                                                "a simulated workflow")

        # Mock out celery calls
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
            # default_app.AsyncResult.__call__(async_mock.task_id).AndReturn(
            #        async_mock)

        return workflow

    def _get_expected_calls(self):
        """Prepare expected call names, args, and returns for mocking."""

        def is_good_context(context):
            """Checks that call has all necessary context data."""
            for key in ['auth_token', 'username', 'catalog']:
                if key not in context:
                    LOG.warn("Context does not have a '%s'", key)
                    return False
            return True

        def is_good_data_bag(context):
            """True if all managed cloud cookbook needs are in the databag."""
            if context is None:
                return False
            for key in context:
                if key not in [
                        'wordpress', 'user', 'lsyncd', 'mysql', 'apache']:
                    return False
            return True

        expected_calls = [{
            # Create Chef Environment
            'call': 'checkmate.providers.opscode.solo.tasks'
                    '.create_environment',
            'args': [mox.IgnoreArg(), self.deployment['id'], mox.IgnoreArg()],
            'kwargs': mox.And(
                mox.ContainsKeyValue('private_key', mox.IgnoreArg()),
                mox.ContainsKeyValue('secret_key', mox.IgnoreArg()),
                mox.ContainsKeyValue('public_key_ssh', mox.IgnoreArg())
            ),
            'result': {
                'environment': '/var/tmp/%s/' % self.deployment['id'],
                'kitchen': '/var/tmp/%s/kitchen' % self.deployment['id'],
                'private_key_path': '/var/tmp/%s/private.pem' % (
                    self.deployment['id']),
                'public_key_path': '/var/tmp/%s/checkmate.pub' % (
                    self.deployment['id']),
                'public_key': ENV_VARS['CHECKMATE_CLIENT_PUBLIC_KEY']}
        }]

        use_data_bags = os.environ.get('CHECKMATE_CHEF_USE_DATA_BAGS', 'true')
        if str(use_data_bags).lower() in ['true', '1', 'yes']:
            expected_calls.append({
                'call': 'checkmate.providers.opscode.solo.tasks'
                        '.write_databag',
                'args': [
                    mox.IgnoreArg(),
                    self.deployment['id'],
                    self.deployment['id'],
                    self.deployment.settings().get('app_id'),
                    mox.Func(is_good_data_bag)
                ],
                'kwargs': mox.And(
                    mox.ContainsKeyValue('secret_file',
                                         'certificates/chef.pem'),
                    mox.ContainsKeyValue('merge', True)
                ),
                'result': None
            })
        else:
            expected_calls.append({
                'call': 'checkmate.providers.opscode.solo.tasks.manage_role',
                'args': [mox.IgnoreArg(), 'wordpress-web',
                         self.deployment['id']],
                'kwargs': {
                    'override_attributes': {
                        'wordpress': {
                            'db': {
                                'host': 'verylong.rackspaceclouddb.com',
                                'password': mox.IsA(basestring),
                                'user': os.environ['USER'],
                                'database': 'db1'
                            }
                        }
                    }
                },
                'result': None
            })
        # Add repetitive calls (per resource)
        for key, resource in self.deployment.get('resources', {}).iteritems():
            desired = resource.get('desired-state')
            if resource.get('type') == 'compute' and desired.get('image'):
                if 'master' in resource['dns-name']:
                    fake_id = 10000 + int(key)  # legacy format
                    role = 'master'
                    fake_ip = 100
                else:
                    fake_id = "10-uuid-00%s" % key  # Nova format
                    role = 'web'
                    fake_ip = int(key) + 1
                name = resource['dns-name']
                flavor = desired['flavor']
                index = key
                image = desired['image']
                if resource.get('provider') == 'nova':
                    expected_calls.append({
                        # Create Server
                        'call': 'checkmate.providers.rackspace.compute.tasks.'
                                'create_server',
                        'args': [
                            mox.Func(is_good_context),
                            mox.StrContains(name)
                        ],
                        'kwargs': mox.And(
                            mox.ContainsKeyValue('image', image),
                            mox.ContainsKeyValue('flavor', flavor)
                        ),
                        'result': {
                            'resources': {
                                str(key): {
                                    'instance': {
                                        'id': fake_id,
                                        'password': "shecret",
                                    }
                                }
                            }
                        },
                        'post_back_result': True,
                        'resource': str(key),
                    })
                    expected_calls.append({
                        # Wait for Server Build
                        'call': 'checkmate.providers.rackspace.compute.tasks'
                                '.wait_on_build',
                        'args': [
                            mox.Func(is_good_context),
                            fake_id,
                        ],
                        'kwargs': mox.And(mox.In('password')),
                        'result': {
                            'resources': {
                                str(key): {
                                    'status': "ACTIVE",
                                    'instance': {
                                        'status': "ACTIVE",
                                        'ip': '4.4.4.%s' % fake_ip,
                                        'private_ip': '10.1.2.%s' % fake_ip,
                                        'addresses': {
                                            'public': [
                                                {
                                                    "version": 4,
                                                    "addr": ("4.4.4.%s" %
                                                             fake_ip),
                                                },
                                                {
                                                    "version": 6,
                                                    "addr":
                                                    "2001:babe::ff04:36c%s" %
                                                    index,
                                                }
                                            ],
                                            'private': [
                                                {
                                                    "version": 4,
                                                    "addr": ("10.1.2.%s" %
                                                             fake_ip),
                                                }
                                            ]
                                        }
                                    }
                                }
                            }
                        },
                        'post_back_result': True,
                        'resource': str(key),
                    })
                else:
                    expected_calls.append({
                        # Create Server
                        'call': 'checkmate.providers.rackspace.compute_legacy.'
                                'create_server',
                        'args': [mox.Func(is_good_context),
                                 mox.StrContains(name)],
                        'kwargs': mox.And(
                            mox.ContainsKeyValue('image', image),
                            mox.ContainsKeyValue('flavor', flavor),
                            mox.ContainsKeyValue('ip_address_type', 'public')
                        ),
                        'result': {
                            'resources': {
                                str(key): {
                                    'instance': {
                                        'id': fake_id,
                                        'ip': "4.4.4.%s" % fake_ip,
                                        'private_ip': "10.1.1.%s" % fake_ip,
                                        'password': "shecret",
                                    }
                                }
                            }
                        },
                        'post_back_result': True,
                        'resource': key,
                    })
                    expected_calls.append({
                        # Wait for Server Build
                        'call': 'checkmate.providers.rackspace.compute_legacy'
                                '.wait_on_build',
                        'args': [mox.Func(is_good_context), fake_id],
                        'kwargs': mox.And(mox.In('password')),
                        'result': {
                            'resources': {
                                str(key): {
                                    'status': "ACTIVE",
                                    'instance': {
                                        'ip': '4.4.4.%s' % fake_ip,
                                        'private_ip': '10.1.2.%s' % fake_ip,
                                        'addresses': {
                                            'public': [
                                                {
                                                    "version": 4,
                                                    "addr": ("4.4.4.%s" %
                                                             fake_ip),
                                                },
                                                {
                                                    "version": 6,
                                                    "addr":
                                                    "2001:babe::ff04:36c%s" %
                                                    index,
                                                }
                                            ],
                                            'private': [
                                                {
                                                    "version": 4,
                                                    "addr": ("10.1.2.%s" %
                                                             fake_ip),
                                                }
                                            ]
                                        }
                                    }
                                }
                            }
                        },
                        'post_back_result': True,
                        'resource': key,
                    })
                # Bootstrap Server with Chef
                expected_calls.append({
                    'call': 'checkmate.providers.opscode.solo.tasks'
                            'register_node_v2',
                    'args': [mox.IgnoreArg(), "4.4.4.%s" % fake_ip,
                             self.deployment['id']],
                    'kwargs': mox.In('password'),
                    'result': None,
                    'resource': key,
                })

                # build-essential (now just cook with bootstrap.json)
                expected_calls.append({
                    'call': 'checkmate.providers.opscode.solo.tasks.cook_v2',
                    'args': [mox.IgnoreArg(), "4.4.4.%s" % fake_ip,
                             self.deployment['id']],
                    'kwargs': mox.And(
                        mox.In('password'), mox.Not(mox.In('recipes')),
                        mox.Not(mox.In('roles')),
                        mox.ContainsKeyValue(
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
                        'call': 'checkmate.providers.opscode.solo.tasks'
                                '.cook_v2',
                        'args': [mox.IgnoreArg(), "4.4.4.%s" % fake_ip,
                                 self.deployment['id']],
                        'kwargs': mox.And(
                            mox.In('password'),
                            mox.ContainsKeyValue(
                                'roles', ["wordpress-%s" % role]),
                            mox.ContainsKeyValue(
                                'identity_file',
                                '/var/tmp/%s/private.pem' % (
                                    self.deployment['id']))
                        ),
                        'result': None,
                        'resource': key,
                    })
                if role == 'master':
                    expected_calls.append({
                        'call': 'checkmate.providers.opscode.'
                                'solo.tasks.write_databag',
                        'args': [
                            mox.IgnoreArg(),
                            self.deployment['id'],
                            self.deployment['id'],
                            'webapp_wordpress_%s' % (
                                self.deployment.get_setting('prefix')),
                            mox.And(mox.IsA(dict), mox.In('lsyncd'))
                        ],
                        'kwargs': mox.And(
                            mox.ContainsKeyValue(
                                'secret_file', 'certificates/chef.pem'),
                            mox.ContainsKeyValue('merge', True)),
                        'result': None,
                        'resource': key,
                    })
                    expected_calls.append(
                        {
                            'call': 'checkmate.providers.opscode.solo.tasks'
                                    '.cook_v2',
                            'args': [mox.IgnoreArg(), "4.4.4.%s" % fake_ip,
                                     self.deployment['id']],
                            'kwargs': mox.And(
                                mox.In('password'),
                                mox.ContainsKeyValue(
                                    'recipes',
                                    ['lsyncd::install']
                                ),
                                mox.ContainsKeyValue(
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
                            'call': 'checkmate.providers.opscode.solo.tasks'
                                    '.cook_v2',
                            'args': [mox.IgnoreArg(), "4.4.4.%s" % fake_ip,
                                     self.deployment['id']],
                            'kwargs': mox.And(
                                mox.In('password'),
                                mox.ContainsKeyValue(
                                    'recipes',
                                    ["lsyncd::install_keys"]),
                                mox.ContainsKeyValue(
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
                        mox.Func(is_good_context),
                        20001,
                        "10.1.2.%s" % fake_ip,
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
            elif (resource.get('provider') == 'database' and
                     resource.get('type') == 'compute' and
                     'disk' in resource['desired-state']):
                expected_calls.extend([{
                    # Create Instance
                    'call': 'checkmate.providers.rackspace.database.tasks.'
                            'create_instance',
                    'args': [
                        mox.Func(is_good_context),
                        mox.IsA(basestring),
                        resource['desired-state'],
                    ],
                    'kwargs': mox.IgnoreArg(),
                    'result': {
                        'resources': {
                            str(key): {
                                'instance': {
                                    'id': 'db-inst-1',
                                    'name': 'dbname.domain.local',
                                    'status': 'BUILD',
                                    'region': self.deployment.get_setting(
                                        'region', default='testonia'),
                                    'interfaces': {
                                        'mysql': {
                                            'host':
                                            'verylong.rackspaceclouddb.com',
                                        },
                                    },
                                    'databases': {}
                                }
                            }
                        },
                    },
                    'post_back_result': True,
                    'resource': key,
                }, {  # wait_on_build
                    'call': 'checkmate.providers.rackspace.database.tasks.'
                            'wait_on_build',
                    'args': [
                        mox.Func(is_good_context),
                    ],
                    'kwargs': mox.IgnoreArg(),
                    'result': {
                        'resources': {
                            str(key): {
                                'status': 'ACTIVE',
                                'instance': {
                                    'id': 'db-inst-1'
                                }
                            }
                        },
                    },
                    'post_back_result': True,
                    'resource': key,
                }])
            elif (resource.get('provider') == 'database' and
                     resource.get('type') == 'cache'):
                expected_calls.extend([{
                    # Create Instance
                    'call': 'checkmate.providers.rackspace.database.tasks.'
                            'create_instance',
                    'args': [
                        mox.Func(is_good_context),
                        mox.IsA(basestring),
                        resource['desired-state'],
                    ],
                    'kwargs': mox.IgnoreArg(),
                    'result': {
                        'resources': {
                            str(key): {
                                'instance': {
                                    'id': 'db-inst-1',
                                    'name': 'dbname.domain.local',
                                    'status': 'BUILD',
                                    'region': self.deployment.get_setting(
                                        'region', default='testonia'),
                                    'interfaces': {
                                        'redis': {
                                            'host':
                                            'verylong.rackspaceclouddb.com',
                                        },
                                    }
                                }
                            }
                        },
                    },
                    'post_back_result': True,
                    'resource': key,
                }, {  # wait_on_build
                    'call': 'checkmate.providers.rackspace.database.tasks.'
                            'wait_on_build',
                    'args': [
                        mox.Func(is_good_context),
                    ],
                    'kwargs': mox.IgnoreArg(),
                    'result': {
                        'resources': {
                            str(key): {
                                'status': 'ACTIVE',
                                'instance': {
                                    'id': 'db-inst-1',
                                }
                            }
                        },
                    },
                    'post_back_result': True,
                    'resource': key,
                }])
            elif resource.get('provider') == 'block':
                expected_calls.extend([{
                    # Create Block Device
                    'call': 'checkmate.providers.rackspace.block.tasks.'
                            'create_volume',
                    'args': [
                        mox.Func(is_good_context),
                        desired['region'],
                        desired['size']
                    ],
                    'kwargs': mox.ContainsKeyValue(
                        'tags', {'RAX-CHECKMATE': mox.IgnoreArg()}
                    ),
                    'result': {
                        'resources': {
                            str(key): {
                                'instance': {
                                    'id': 'cbs%s' % key,
                                    'region': desired['region'],
                                }
                            }
                        }
                    },
                    'post_back_result': True,
                    'resource': str(key),
                }, {
                    # Wait on Block Device
                    'call': 'checkmate.providers.rackspace.block.tasks.'
                            'wait_on_build',
                    'args': [
                        mox.Func(is_good_context),
                        desired['region'],
                        'cbs%s' % key
                    ],
                    'kwargs': {},
                    'result': {
                        'status': 'ACTIVE'
                    },
                    'post_back_result': True,
                    'resource': str(key),
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
                    'call': 'checkmate.providers.rackspace.database.tasks.'
                            'create_database',
                    'args': mox.IgnoreArg(),
                    'kwargs': mox.IgnoreArg(),
                    'result': {
                        'resources': {
                            str(key): {
                                'instance': {
                                    'name': 'db1',
                                    'host_instance': 'db-inst-1',
                                    'host_region': self.deployment.get_setting(
                                        'region', default='testonia'),
                                    'interfaces': {
                                        'mysql': {
                                            'host':
                                            'verylong.rackspaceclouddb.com',
                                            'database_name': 'db1',
                                        },
                                    }
                                }
                            }
                        }
                    },
                    'post_back_result': True,
                    'resource': key,
                })
                expected_calls.append({
                    # Create Database User
                    'call':
                    'checkmate.providers.rackspace.database.tasks.add_user',
                    'args': [
                        mox.Func(is_good_context),
                        'db-inst-1',
                        ['db1'],
                        username,
                        mox.IsA(basestring),
                        self.deployment.get_setting(
                            'region',
                            default='testonia'
                        )
                    ],
                    'kwargs': None,
                    'result': {
                        'resources': {
                            str(key): {
                                'instance': {
                                    'username': username,
                                    'password': 'DbPxWd',
                                    'interfaces': {
                                        'mysql': {
                                            'username': username,
                                            'password': 'DbPxWd',
                                        }
                                    }
                                }
                            }
                        }
                    },
                    'post_back_result': True,
                    'resource': key,
                })
                expected_calls.append({
                    'call': 'checkmate.providers.opscode.solo.tasks'
                            '.write_databag',
                    'args': [
                        mox.IgnoreArg(),
                        self.deployment['id'],
                        self.deployment['id'],
                        'webapp_wordpress_%s' % (
                            self.deployment.get_setting('prefix')),
                        mox.IsA(dict)
                    ],
                    'kwargs': mox.And(
                        mox.ContainsKeyValue(
                            'secret_file', 'certificates/chef.pem'),
                        mox.ContainsKeyValue('merge', True)),
                    'result': None,
                    'resource': key,
                })
            elif resource.get('type') == 'load-balancer':
                region = self.deployment.get_setting('region',
                                                     default='testonia')
                expected_calls.append({
                    # Create Load Balancer
                    'call': 'checkmate.providers.rackspace.loadbalancer.'
                            'create_loadbalancer',
                    'args': [
                        mox.Func(is_good_context), mox.IsA(basestring),
                        'PUBLIC',
                        'HTTP',
                        80,
                        region
                    ],
                    'kwargs': mox.ContainsKeyValue(
                        'tag', {'RAX-CHECKMATE': mox.IgnoreArg()}
                    ),
                    'result': {
                        'resources': {
                            str(key): {
                                'instance': {
                                    'id': 20001, 'vip': "200.1.1.1",
                                    'lbid': 20001,
                                    'region': region,
                                }
                            }
                        }
                    },
                    'post_back_result': True,
                    'resource': key,
                })
        return expected_calls


class TestProvider(base.ProviderBase):

    """Provider that returns mock responses for testing.

    Defers to ProviderBase for most functionality, but implements
    prep_environment, add_connection_tasks and add_resource_tasks
    """

    name = "base"
    vendor = "test"

    def prep_environment(self, wfspec, deployment, context):
        pass

    def add_resource_tasks(self, resource, key, wfspec,
                           deployment, context, wait_on=None):
        wait_on, _, _ = self._add_resource_tasks_helper(
            resource, key, wfspec, deployment, context, wait_on)

        create_instance_task = specs.Celery(
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
        root = wfspec.wait_for(create_instance_task, wait_on)
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
                raise exceptions.CheckmateException("No host")

        # Get the definition of the interface
        interface_schema = schema.INTERFACE_SCHEMA.get(interface) or {}
        # Get the fields this interface defines
        fields = interface_schema.get('options', {}).keys()
        if not fields:
            LOG.debug(
                "No options defined for interface '%s', so nothing "
                "to do for connection '%s'", interface, relation_key)
            return  # nothing to do

        # Build full path to 'resources/:id/interfaces/:interface/:field_name'
        fields_with_path = []
        for field in fields:
            fields_with_path.append('resources/%s/interfaces/%s/%s' % (
                relation['target'], interface, field))

        # Get the final task for the target
        target_final = wfspec.find_task_specs(
            provider=target['provider'],
            resource=relation['target'],
            tag='final'
        )
        if not target_final:
            raise exceptions.CheckmateException("Relation final task not "
                                                "found")
        if len(target_final) > 1:
            raise exceptions.CheckmateException(
                "Multiple relation final tasks "
                "found: %s" % [t.name for t in target_final]
            )
        target_final = target_final[0]

        def get_fields_code(my_task):  # Holds code for the task
            """Write the task to get the values."""
            fields = my_task.get_property('options', [])
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
                    LOG.warn("Field %s not found", field,
                             extra=dict(data=my_task.attributes))
            utils.merge_dictionary(my_task.attributes, data)

        compile_override = specs.Transform(
            wfspec,
            "Get %s values for %s" % (relation_key, key),
            transforms=[utils.get_source_body(get_fields_code)],
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
        wfspec.wait_for(compile_override, [target_final])
        # Provide data to 'final' task
        tasks = wfspec.find_task_specs(provider=resource['provider'],
                                       resource=key, tag='final')
        if tasks:
            for task in tasks:
                wfspec.wait_for(task, [compile_override])


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
        override = utils.yaml_to_dict("""
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
        context = {'region': 'test_region'}
        self.assertListEqual(provider.provides(None), override['provides'])
        self.assertDictEqual(provider.get_catalog(context),
                             override['catalog'])

    def test_provider_loads_unregistered(self):
        """Check that provider loads without registration."""
        if not isinstance(self.klass, TestProvider):
            self.assertIs(base.get_provider_class(self.klass.vendor,
                                                  self.klass.name), self.klass)

    def test_provider_loads_registered(self):
        """Check that provider loads."""
        base.PROVIDER_CLASSES = {}
        base.register_providers([self.klass])
        self.assertTrue(issubclass(base.get_provider_class(self.klass.vendor,
                                                           self.klass.name),
                                   base.ProviderBase))

    def test_provider_registration(self):
        """Check that provider class registers."""
        base.PROVIDER_CLASSES = {}
        base.register_providers([self.klass])
        key = self.klass({}).key
        self.assertIn(key, base.PROVIDER_CLASSES)
        self.assertIs(base.PROVIDER_CLASSES[key], self.klass)

    def test_translate_status(self):
        """Tests that provider status is translated."""
        expected = 'UNDEFINED'
        results = self.klass.translate_status('DOESNOTEXIST')
        self.assertEqual(expected, results)

    def tearDown(self):
        self.mox.UnsetStubs()


class MockContext(dict):

    """Used to mock RequestContext."""

    is_admin = False
    tenant = None
    username = "Ziad"
    simulation = False


class MockAttribContext(object):

    """Used to mock context in Rackspace py modules."""

    def __init__(self, region, tenant, auth_token):
        self.region = region
        self.tenant = tenant
        self.auth_token = auth_token


class MockWsgiFilters(object):

    """Used to mock Context, Extension, and Tenant Middleware."""

    def __init__(self, app):
        self.app = app
        self.context = MockContext()

    def __call__(self, environ, start_response):
        """Add context, strip out tenant if not already mocked."""
        environ['context'] = self.context
        bottle.request.accept = 'application/json'
        path = environ['PATH_INFO']
        if path and not self.context.tenant:
            parts = path.strip('/').split('/')
            if parts[0] != 'admin':
                self.context.tenant = parts[0]
                environ['PATH_INFO'] = '/%s' % '/'.join(parts[1:])
        return self.app(environ, start_response)
