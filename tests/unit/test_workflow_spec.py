# pylint: disable=C0103,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
"""Tests for workflow spec."""
import mox
import unittest

from checkmate.deployment import Deployment
from checkmate.workflows import WorkflowSpec


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

        self.deployment = Deployment({
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
        WorkflowSpec.create_delete_node_spec(self.deployment, ["1"],
                                             context)
        self._mox.VerifyAll()
