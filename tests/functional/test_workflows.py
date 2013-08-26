# pylint: disable=R0904,W0212

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

"""Test for Workflow Tools."""
import mock
import unittest

from SpiffWorkflow import specs
from SpiffWorkflow import storage
from SpiffWorkflow import Workflow as SpiffWorkflow

from checkmate import workflow
from checkmate import workflows as cmwfs


class TestWorkflowTools(unittest.TestCase):
    def test_simple_wait_for(self):
        wf_spec = cmwfs.WorkflowSpec()
        wf_a = specs.Simple(wf_spec, 'A')
        wf_b = specs.Simple(wf_spec, 'B')

        wf_spec.wait_for(wf_a, [wf_b])
        self.assertListEqual(wf_a.inputs, [wf_b])

    def test_insert_wait_for(self):
        wf_spec = cmwfs.WorkflowSpec()
        wf_a = specs.Simple(wf_spec, 'A')
        wf_b = specs.Simple(wf_spec, 'B')
        wf_spec.start.connect(wf_a)
        wf_spec.wait_for(wf_a, [wf_b])
        wf_spec.start.connect(wf_b)
        spiff_wf = SpiffWorkflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 2
    3/0: Task of After 1,3 run 2 State: FUTURE Children: 1
      5/0: Task of A State: FUTURE Children: 0
    4/0: Task of B State: FUTURE Children: 1
      6/0: Task of After 1,3 run 2 State: FUTURE Children: 1
        7/0: Task of A State: FUTURE Children: 0"""
        self.assertEqual(spiff_wf.get_dump(), expected.strip())
        self.assertIn(wf_spec.start, wf_a.ancestors())
        self.assertIn(wf_b, wf_a.ancestors())

    def test_inject_wait_for(self):
        wf_spec = cmwfs.WorkflowSpec()
        wf_a = specs.Simple(wf_spec, 'A')
        wf_b = specs.Simple(wf_spec, 'B')
        wf_spec.start.connect(wf_a)
        wf_spec.start.connect(wf_b)

        wf_spec.wait_for(wf_a, [wf_b])
        spiff_wf = SpiffWorkflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
    3/0: Task of B State: FUTURE Children: 1
      4/0: Task of After 1,3 run 2 State: FUTURE Children: 1
        5/0: Task of A State: FUTURE Children: 0"""
        self.assertEqual(spiff_wf.get_dump(), expected.strip())
        self.assertIn(wf_spec.start, wf_a.ancestors())
        self.assertIn(wf_b, wf_a.ancestors())
        self.assertNotIn(wf_spec.start, wf_a.inputs)

    def test_wait_for_chain(self):
        wf_spec = cmwfs.WorkflowSpec()
        wf_a = specs.Simple(wf_spec, 'A')
        wf_b = specs.Simple(wf_spec, 'B')
        wf_spec.start.connect(wf_spec.wait_for(wf_b, [wf_a]))

        spiff_wf = SpiffWorkflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
    3/0: Task of A State: FUTURE Children: 1
      4/0: Task of B State: FUTURE Children: 0"""
        self.assertEqual(spiff_wf.get_dump(), expected.strip())

    def test_wait_for_none(self):
        wf_spec = cmwfs.WorkflowSpec()
        wf_a = specs.Simple(wf_spec, 'A')
        wf_spec.start.connect(wf_spec.wait_for(wf_a, None))

        spiff_wf = SpiffWorkflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
    3/0: Task of A State: FUTURE Children: 0"""
        self.assertEqual(spiff_wf.get_dump(), expected.strip())

    def test_insert_wait_for_many(self):
        wf_spec = cmwfs.WorkflowSpec()
        wf_a1 = specs.Simple(wf_spec, 'A1')
        wf_a2 = specs.Simple(wf_spec, 'A2')
        wf_a3 = specs.Simple(wf_spec, 'A3')
        wf_spec.start.connect(wf_a1)
        wf_spec.start.connect(wf_a2)
        wf_spec.start.connect(wf_a3)
        wf_b = specs.Simple(wf_spec, 'B')
        wf_spec.wait_for(wf_b, [wf_a1, wf_a2, wf_a3])

        spiff_wf = SpiffWorkflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 3
    3/0: Task of A1 State: FUTURE Children: 1
      6/0: Task of After 2,3,4 run 5 State: FUTURE Children: 1
        7/0: Task of B State: FUTURE Children: 0
    4/0: Task of A2 State: FUTURE Children: 1
      8/0: Task of After 2,3,4 run 5 State: FUTURE Children: 1
        9/0: Task of B State: FUTURE Children: 0
    5/0: Task of A3 State: FUTURE Children: 1
      10/0: Task of After 2,3,4 run 5 State: FUTURE Children: 1
        11/0: Task of B State: FUTURE Children: 0"""
        self.assertEqual(spiff_wf.get_dump(), expected.strip())

    def test_wait_for_merge_exists(self):
        wf_spec = cmwfs.WorkflowSpec()
        wf_a = specs.Simple(wf_spec, 'A')
        wf_b = specs.Simple(wf_spec, 'B')
        wf_c = specs.Simple(wf_spec, 'C')
        wf_m = specs.Merge(wf_spec, 'M')
        wf_spec.start.connect(wf_m)
        wf_a.follow(wf_m)
        wf_b.connect(wf_m)

        wf_spec.wait_for(wf_a, [wf_c])
        self.assertListEqual(wf_a.inputs, [wf_m])


class TestWorkflow(unittest.TestCase):
    def test_instantiation(self):
        wflow = workflow.Workflow()
        self.assertDictEqual(wflow._data, {})

    def test_spiff_serialization(self):
        wf_spec = cmwfs.WorkflowSpec(name="Test")
        wf_a = specs.Simple(wf_spec, 'A')
        wf_spec.start.connect(wf_a)
        spiff_wf = SpiffWorkflow(wf_spec)

        # Serialize into Checkmate Workflow (dict)
        serializer = storage.DictionarySerializer()
        wflow = workflow.Workflow(spiff_wf.serialize(serializer))
        expected_keys = ['wf_spec', 'last_task', 'success', 'workflow',
                         'attributes', 'task_tree']
        self.assertListEqual(wflow._data.keys(), expected_keys)

        # Deserialize from Checkmate Workflow (dict)
        new = SpiffWorkflow.deserialize(serializer, wflow)
        self.assertIsInstance(new, SpiffWorkflow)

    @mock.patch.object(workflow, 'get_errors')
    def test_workflow_error(self, mock_get_errors):
        wf_spec = cmwfs.WorkflowSpec(name="Test")
        wf_a = specs.Simple(wf_spec, 'A')
        wf_spec.start.connect(wf_a)
        spiff_wf = SpiffWorkflow(wf_spec)

        mock_get_errors.return_value = [{}, {}]

        workflow.update_workflow_status(spiff_wf, tenant_id=None)
        mock_get_errors.assert_called_with(spiff_wf, None)

        assert spiff_wf.attributes['status'] == 'FAILED'


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
