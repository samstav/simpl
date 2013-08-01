# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest
import mox

from SpiffWorkflow import Workflow as SpiffWorkflow
from SpiffWorkflow.storage import DictionarySerializer
from SpiffWorkflow.specs import Simple, Merge

from checkmate import workflow
from checkmate.workflows import WorkflowSpec


class TestWorkflowTools(unittest.TestCase):
    def test_simple_wait_for(self):
        """Test that adding a wait_for task works"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        B = Simple(wf_spec, 'B')

        wf_spec.wait_for(A, [B])
        self.assertListEqual(A.inputs, [B])

    def test_insert_wait_for(self):
        """Test that adding a wait_for task maintains inputs"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        B = Simple(wf_spec, 'B')
        wf_spec.start.connect(A)
        wf_spec.wait_for(A, [B])
        wf_spec.start.connect(B)
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
        self.assertIn(wf_spec.start, A.ancestors())
        self.assertIn(B, A.ancestors())

    def test_inject_wait_for(self):
        """Test that adding a wait_for to a task sharing ancestors that the
        result acts as an insertion"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        B = Simple(wf_spec, 'B')
        wf_spec.start.connect(A)
        wf_spec.start.connect(B)

        wf_spec.wait_for(A, [B])
        spiff_wf = SpiffWorkflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
    3/0: Task of B State: FUTURE Children: 1
      4/0: Task of After 1,3 run 2 State: FUTURE Children: 1
        5/0: Task of A State: FUTURE Children: 0"""
        self.assertEqual(spiff_wf.get_dump(), expected.strip())
        self.assertIn(wf_spec.start, A.ancestors())
        self.assertIn(B, A.ancestors())
        self.assertNotIn(wf_spec.start, A.inputs)

    def test_wait_for_chain(self):
        """Test that adding a single wait_for task works"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        B = Simple(wf_spec, 'B')
        wf_spec.start.connect(wf_spec.wait_for(B, [A]))

        spiff_wf = SpiffWorkflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
    3/0: Task of A State: FUTURE Children: 1
      4/0: Task of B State: FUTURE Children: 0"""
        self.assertEqual(spiff_wf.get_dump(), expected.strip())

    def test_wait_for_none(self):
        """Test that adding a no wait_for returns task"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        wf_spec.start.connect(wf_spec.wait_for(A, None))

        spiff_wf = SpiffWorkflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
    3/0: Task of A State: FUTURE Children: 0"""
        self.assertEqual(spiff_wf.get_dump(), expected.strip())

    def test_insert_wait_for_many(self):
        """Test that adding a wait_for task works"""
        wf_spec = WorkflowSpec()
        A1 = Simple(wf_spec, 'A1')
        A2 = Simple(wf_spec, 'A2')
        A3 = Simple(wf_spec, 'A3')
        wf_spec.start.connect(A1)
        wf_spec.start.connect(A2)
        wf_spec.start.connect(A3)
        B = Simple(wf_spec, 'B')
        wf_spec.wait_for(B, [A1, A2, A3])

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
        """Test that adding a wait_for task works"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        B = Simple(wf_spec, 'B')
        C = Simple(wf_spec, 'C')
        M = Merge(wf_spec, 'M')
        wf_spec.start.connect(M)
        A.follow(M)
        B.connect(M)

        wf_spec.wait_for(A, [C])
        self.assertListEqual(A.inputs, [M])


class TestWorkflow(unittest.TestCase):
    """Test Checkmate Workflow class"""
    mox = mox.Mox()

    def test_instantiation(self):
        wf = workflow.Workflow()
        self.assertDictEqual(wf._data, {})

    def test_SpiffSerialization(self):
        wf_spec = WorkflowSpec(name="Test")
        A = Simple(wf_spec, 'A')
        wf_spec.start.connect(A)
        wf = SpiffWorkflow(wf_spec)

        # Serialize into Checkmate Workflow (dict)
        serializer = DictionarySerializer()
        wf = workflow.Workflow(wf.serialize(serializer))
        expected_keys = ['wf_spec', 'last_task', 'success', 'workflow',
                         'attributes', 'task_tree']
        self.assertListEqual(wf._data.keys(), expected_keys)

        # Deserialize from Checkmate Workflow (dict)
        new = SpiffWorkflow.deserialize(serializer, wf)
        self.assertIsInstance(new, SpiffWorkflow)

    def test_workflow_error(self):
        wf_spec = WorkflowSpec(name="Test")
        A = Simple(wf_spec, 'A')
        wf_spec.start.connect(A)
        spiff_wf = SpiffWorkflow(wf_spec)

        self.mox.StubOutWithMock(workflow, "get_errors")
        workflow.get_errors(spiff_wf, None).AndReturn([{}, {}])

        self.mox.ReplayAll()
        workflow.update_workflow_status(spiff_wf, tenant_id=None)
        self.mox.UnsetStubs()
        self.mox.VerifyAll()

        assert spiff_wf.attributes['status'] == 'FAILED'


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
