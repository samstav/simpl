# pylint: disable=C0103,W0212,R0904

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

"""Tests for Rackspace Block Storage provider."""

import logging
import unittest

import mock
import mox

from checkmate import deployment
from checkmate import middleware
from checkmate.providers import base
from checkmate.providers.rackspace.block import provider
from checkmate import test
from checkmate import utils
from checkmate import workflow as cm_wf
from checkmate import workflow_spec

LOG = logging.getLogger(__name__)


class TestBlock(test.ProviderTester):

    def setUp(self):
        self.mox = mox.Mox()
        self.deployment = self.mox.CreateMockAnything()

    def test_template_generation_database(self):
        self.deployment.get_setting('domain', default='checkmate.local',
                                    provider_key='rackspace.block',
                                    resource_type='volume',
                                    service_name='master'). \
            AndReturn("test.checkmate")
        self.deployment._constrained_to_one('master').AndReturn(True)

        self.deployment.get_setting('size', default=100,
                                    provider_key='rackspace.block',
                                    resource_type='volume',
                                    service_name='master'). \
            AndReturn(102)

        self.deployment.get_setting('region',
                                    provider_key='rackspace.block',
                                    resource_type='volume',
                                    service_name='master'). \
            AndReturn('North')

        cbsprovider = provider.Provider({})

        # Mock Base Provider, context and deployment
        context = self.mox.CreateMockAnything()
        context.kwargs = {}

        expected = [{
            'instance': {},
            'dns-name': 'master.test.checkmate',
            'type': 'volume',
            'provider': cbsprovider.key,
            'service': 'master',
            'desired-state': {
                'size': 102,
                'region': 'North',
            },
        }]

        self.mox.ReplayAll()
        results = cbsprovider.generate_template(self.deployment, 'volume',
                                                'master', context, 100,
                                                cbsprovider.key, None, None)

        self.assertItemsEqual(results, expected)
        self.mox.VerifyAll()

    @staticmethod
    def verify_limits():
        """Helper method to verify limits."""
        context = middleware.RequestContext()
        resources = [
            {
                'component': 'rax:block_volume',
                'dns-name': 'backend01.wordpress.cldsrvr.com',
                'hosted_on': '6',
                'index': '5',
                'instance': {},
                'provider': 'other',
                'service': 'backend',
                'status': 'PLANNED',
                'type': 'database',
                'desired-state': {},
            },
            {
                'component': 'rax:block_volume',
                'dns-name': 'backend01.wordpress.cldsrvr.com',
                'hosts': ['5'],
                'index': '6',
                'instance': {},
                'provider': 'block',
                'service': 'backend',
                'status': 'NEW',
                'type': 'volume',
                'desired-state': {
                    'size': 1,
                    'region': 'ORD',
                },
            }
        ]
        cbsprovider = provider.Provider({})
        result = cbsprovider.verify_limits(context, resources)
        return result

    @mock.patch.object(provider.cbs, 'list_volumes')
    def test_verify_limits_negative(self, mock_list):
        instance1 = {'size': 1000}
        instance2 = {'size': 100}
        mock_list.return_value = [instance1, instance2]
        result = self.verify_limits()  # Will be 200 total (2 instances)
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")

    @mock.patch.object(provider.cbs, 'list_volumes')
    def test_verify_limits_positive(self, mock_list):
        instance1 = {'size': 10}
        instance2 = {'size': 10}
        mock_list.return_value = [instance1, instance2]
        result = self.verify_limits()
        self.assertEqual(result, [])

    def test_verify_access_positive(self):
        context = middleware.RequestContext()
        context.roles = 'identity:user-admin'
        cbsprovider = provider.Provider({})
        result = cbsprovider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'cbs:admin'
        result = cbsprovider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'cbs:creator'
        result = cbsprovider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')

    def test_verify_access_negative(self):
        context = middleware.RequestContext()
        context.roles = 'cbs:observer'
        cbsprovider = provider.Provider({})
        result = cbsprovider.verify_access(context)
        self.assertEqual(result['type'], 'NO-ACCESS')


class TestBlockWorkflow(test.StubbedWorkflowBase):

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        base.register_providers([provider.Provider])
        self.deployment = deployment.Deployment(utils.yaml_to_dict("""
id: 'DEP-ID-1000'
blueprint:
  name: test db
  services:
    db:
      component:
        resource_type: volume
        interface: iscsi
        constraints:
        - size: 101
        - region: North
environment:
  name: test
  providers:
    block:
      vendor: rackspace

"""))
        self.deployment['tenantId'] = 'tenantId'
        expected_calls = [{
            # Create Load Balancer
            'call': 'checkmate.providers.rackspace.block.tasks.'
                    'create_volume',
            'args': [
                mox.IgnoreArg(),
                'North',
                101
            ],
            'kwargs': mox.ContainsKeyValue(
                'tags', {'RAX-CHECKMATE': mox.IgnoreArg()}
            ),
            'result': {
                'resources': {
                    '0': {
                        'instance': {
                            'id': 'cbs',
                            'region': 'North',
                        }
                    }
                }
            },
            'post_back_result': True,
            'resource': '0',
        }, {
            # Wait on Block Device
            'call': 'checkmate.providers.rackspace.block.tasks.'
                    'wait_on_build',
            'args': [
                mox.IgnoreArg(),
                'North',
                'cbs'
            ],
            'kwargs': None,
            'result': {
                'status': 'ACTIVE'
            },
            'post_back_result': True,
            'resource': '0',
        }]
        self.workflow = self._get_stubbed_out_workflow(
            expected_calls=expected_calls)

    def test_workflow_task_generation(self):
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(context,
                                                               self.deployment)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, self.deployment, context, "w_id", "BUILD")

        task_list = workflow.spec.task_specs.keys()
        expected = [
            'Root',
            'Start',
            'Wait for Volume 0 (db) build',
            'Create Volume 0',
        ]
        self.assertItemsEqual(task_list, expected, msg=task_list)
        last_args = workflow.spec.task_specs['Create Volume 0'].args[1:3]
        self.assertEqual(last_args, ['North', 101])

    def test_workflow_completion(self):
        self.mox.ReplayAll()
        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(), "Workflow did not "
                        "complete")


class TestCatalog(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_generation(self):
        cbsprovider = provider.Provider({})
        context = self.mox.CreateMockAnything()

        context.catalog = [{
            "endpoints": [
                {
                    "publicURL": "https://north.blockstorage.com/v1/55BB",
                    "region": "North",
                    "tenantId": "55BB"
                },
                {
                    "publicURL": "https://south.blockstorage.com/v1/55BB",
                    "region": "South",
                    "tenantId": "55BB"
                }
            ],
            "name": "cloudBlockStorage",
            "type": "volume"
        }]
        context.auth_token = "DUMMY_TOKEN"
        context.region = None
        expected = {
            'volume': {
                'rax:block_volume': {
                    'is': 'volume',
                    'id': 'rax:block_volume',
                    'provides': [{'volume': 'iscsi'}],
                    'options': {
                        'type': {
                            'default': 'SSD',
                            'display-hints': {
                                'choice': ['SATA', 'SSD']
                            },
                            'type': 'string'
                        },
                        'size': {
                            'default': 50,
                            'type': 'integer'
                        }
                    }
                }
            }
        }

        self.mox.ReplayAll()
        results = cbsprovider.get_catalog(context)
        self.assertEqual(expected, results, results)
        self.mox.VerifyAll()

if __name__ == '__main__':
    import sys
    test.run_with_params(sys.argv[:])
