# pylint: disable=E1103

# Copyright (c) 2011-2013 Rackspace Hosting
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

"""Tests for workflow spec."""
import mock
import mox
import unittest

from checkmate import deployment as cmdep
from checkmate import workflow_spec


class TestWorkflowSpec(unittest.TestCase):
    def setUp(self):
        self._mox = mox.Mox()
        self.resource1 = {
            'relations': {
                'relation-1': {'source': '3'},
                'host': {'source': '99'}
            },
            'provider': 'chef-solo',
            'status': 'ACTIVE',
            'hosted_on': "2",
        }
        self.resource2 = {
            'provider': 'nova',
            'status': 'ACTIVE'
        }
        self.resource3 = {
            'provider': 'rsCloudLb',
            'status': 'ACTIVE'
        }

        self.deployment = cmdep.Deployment({
            'id': 'TEST',
            'blueprint': {
                'name': 'Deployment for test',
            },
            'resources': {
                '1': self.resource1,
                '2': self.resource2,
                '3': self.resource3
            }
        })

    def tearDown(self):
        self._mox.UnsetStubs()

    def test_create_delete_node_spec(self):
        context = self._mox.CreateMockAnything()
        mock_environment = self._mox.CreateMockAnything()
        lb_provider = self._mox.CreateMockAnything()
        chef_solo_provider = self._mox.CreateMockAnything()
        nova_provider = self._mox.CreateMockAnything()
        self._mox.StubOutWithMock(self.deployment, "environment")
        self.deployment.environment().AndReturn(mock_environment)
        mock_environment.get_provider("rsCloudLb").AndReturn(lb_provider)
        lb_provider.add_delete_connection_tasks(mox.IgnoreArg(),
                                                context,
                                                self.deployment,
                                                self.resource3,
                                                self.resource1)
        self.deployment.environment().AndReturn(mock_environment)
        mock_environment.get_provider("chef-solo").AndReturn(
            chef_solo_provider)
        chef_solo_provider.delete_resource_tasks(mox.IgnoreArg(), context,
                                                 "TEST", self.resource1, "1")
        self.deployment.environment().AndReturn(mock_environment)
        mock_environment.get_provider("nova").AndReturn(nova_provider)
        nova_provider.delete_resource_tasks(mox.IgnoreArg(), context, "TEST",
                                            self.resource2, "2")
        self._mox.ReplayAll()
        workflow_spec.WorkflowSpec.create_delete_node_spec(self.deployment,
                                                           ["1"], context)
        self._mox.VerifyAll()

    def test_create_resource_offline_spec(self):
        context = mock.Mock()
        source_resource = {'provider': 'load-balancer'}
        dest_resource = {
            'relations': {
                'lb-web-0': {
                    'source': '0'
                }
            }
        }
        deployment = cmdep.Deployment({
            'id': 'TEST',
            'blueprint': {
                'name': 'Deployment for test',
            },
            'resources': {
                '0': source_resource,
                '1': dest_resource,
            },
        })
        mock_task_spec = mock.Mock()
        deployment.environment = mock.Mock()
        mock_environment = deployment.environment.return_value
        mock_provider = mock_environment.get_provider.return_value
        mock_provider.disable_connection_tasks.return_value = {
            'root': mock_task_spec}

        wf_spec = workflow_spec.WorkflowSpec.create_resource_offline_spec(
            deployment, "1", context)
        self.assertListEqual(wf_spec.start.outputs, [mock_task_spec])
        mock_environment.get_provider.assert_called_once_with('load-balancer')
        mock_provider.disable_connection_tasks.assert_called_once_with(
            mock.ANY, context, source_resource, dest_resource)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
