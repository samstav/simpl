import mock
import unittest

from checkmate.deployments import planner


class TestDeploymentsPlanner(unittest.TestCase):
    def setUp(self):
        self.deployment = mock.Mock()
        self.depl_planner = planner.Planner(self.deployment)


class TestAddCustomResources(TestDeploymentsPlanner):
    def setUp(self):
        super(TestAddCustomResources, self).setUp()
        self.inputs = {}
        self.deployment.inputs = mock.Mock(return_value=self.inputs)
        self.depl_planner.resources = {}

    def test_adds_custom_resources_to_planner_resources_in_order(self):
        self.inputs['custom_resources'] = [{'id': 'r1'}, {'id': 'r2'}]
        self.depl_planner.add_custom_resources()
        self.assertEqual(len(self.depl_planner.resources), 2)
        self.assertEqual(self.depl_planner.resources['0']['id'], 'r1')
        self.assertEqual(self.depl_planner.resources['1']['id'], 'r2')

    def test_adds_index_to_resources(self):
        self.inputs['custom_resources'] = [{'id': 'r1'}, {'id': 'r2'}]
        self.depl_planner.add_custom_resources()
        self.assertEqual(len(self.depl_planner.resources), 2)
        self.assertEqual(self.depl_planner.resources['0']['index'], '0')
        self.assertEqual(self.depl_planner.resources['1']['index'], '1')

    def test_handles_no_custom_resources(self):
        self.depl_planner.add_custom_resources()
        self.assertEqual(self.depl_planner.resources, {})


if __name__ == '__main__':
    import sys
    from checkmate import test
    test.run_with_params(sys.argv[:])
