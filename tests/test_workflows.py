import unittest2 as unittest

from SpiffWorkflow import Workflow
from SpiffWorkflow.specs import WorkflowSpec, Simple

from checkmate.workflows import wait_for


class TestWorkflowTools(unittest.TestCase):
    def test_insert_wait_for(self):
        """Test that adding a wait_for task works"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        B = Simple(wf_spec, 'B')
        wf_spec.start.connect(A)

        wait_for(wf_spec, A, [B])
        wf_spec.start.connect(B)
        workflow = Workflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 2
    3/0: Task of After 3,1 run 2 State: FUTURE Children: 1
      5/0: Task of A State: FUTURE Children: 0
    4/0: Task of B State: FUTURE Children: 1
      6/0: Task of After 3,1 run 2 State: FUTURE Children: 1
        7/0: Task of A State: FUTURE Children: 0"""
        self.assertEqual(workflow.get_dump(), expected.strip())

    def test_wait_for_chain(self):
        """Test that adding a single wait_for task works"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        B = Simple(wf_spec, 'B')
        wf_spec.start.connect(wait_for(wf_spec, B, [A]))

        workflow = Workflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
    3/0: Task of A State: FUTURE Children: 1
      4/0: Task of B State: FUTURE Children: 0"""
        self.assertEqual(workflow.get_dump(), expected.strip())

    def test_wait_for_none(self):
        """Test that adding a no wait_for returns task"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        wf_spec.start.connect(wait_for(wf_spec, A, None))

        workflow = Workflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
    3/0: Task of A State: FUTURE Children: 0"""
        self.assertEqual(workflow.get_dump(), expected.strip())

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
        wait_for(wf_spec, B, [A1, A2, A3])

        workflow = Workflow(wf_spec)
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
        self.assertEqual(workflow.get_dump(), expected.strip())

if __name__ == '__main__':
    unittest.main()
