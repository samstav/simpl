#!/usr/bin/env python
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from SpiffWorkflow import Workflow as SpiffWorkflow
from SpiffWorkflow.storage import DictionarySerializer
from SpiffWorkflow.specs import WorkflowSpec, Simple, Merge, Join

from checkmate.workflows import wait_for, Workflow


class TestWorkflowTools(unittest.TestCase):
    def test_simple_wait_for(self):
        """Test that adding a wait_for task works"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        B = Simple(wf_spec, 'B')

        wait_for(wf_spec, A, [B])
        self.assertListEqual(A.inputs, [B])

    def test_insert_wait_for(self):
        """Test that adding a wait_for task maintains inputs"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        B = Simple(wf_spec, 'B')
        wf_spec.start.connect(A)

        wait_for(wf_spec, A, [B])
        wf_spec.start.connect(B)
        workflow = SpiffWorkflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 2
    3/0: Task of After 3,1 run 2 State: FUTURE Children: 1
      5/0: Task of A State: FUTURE Children: 0
    4/0: Task of B State: FUTURE Children: 1
      6/0: Task of After 3,1 run 2 State: FUTURE Children: 1
        7/0: Task of A State: FUTURE Children: 0"""
        self.assertEqual(workflow.get_dump(), expected.strip())
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

        wait_for(wf_spec, A, [B])
        workflow = SpiffWorkflow(wf_spec)
        expected = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
    3/0: Task of B State: FUTURE Children: 1
      4/0: Task of After 3,1 run 2 State: FUTURE Children: 1
        5/0: Task of A State: FUTURE Children: 0"""
        self.assertEqual(workflow.get_dump(), expected.strip())
        self.assertIn(wf_spec.start, A.ancestors())
        self.assertIn(B, A.ancestors())
        self.assertNotIn(wf_spec.start, A.inputs)

    def test_wait_for_chain(self):
        """Test that adding a single wait_for task works"""
        wf_spec = WorkflowSpec()
        A = Simple(wf_spec, 'A')
        B = Simple(wf_spec, 'B')
        wf_spec.start.connect(wait_for(wf_spec, B, [A]))

        workflow = SpiffWorkflow(wf_spec)
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

        workflow = SpiffWorkflow(wf_spec)
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

        workflow = SpiffWorkflow(wf_spec)
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

        wait_for(wf_spec, A, [C])
        self.assertListEqual(A.inputs, [M])


class TestWorkflow(unittest.TestCase):
    """Test Checkmate Workflow class"""
    def test_instantiation(self):
        workflow = Workflow()
        self.assertDictEqual(workflow._data, {})

    def test_SpiffSerialization(self):
        wf_spec = WorkflowSpec(name="Test")
        A = Simple(wf_spec, 'A')
        wf_spec.start.connect(A)
        wf = SpiffWorkflow(wf_spec)

        # Serialize into Checkmate Workflow (dict)
        serializer = DictionarySerializer()
        workflow = Workflow(wf.serialize(serializer))
        expected_keys = ['wf_spec', 'last_task', 'success', 'workflow',
                         'attributes', 'task_tree']
        self.assertListEqual(workflow._data.keys(), expected_keys)

        # Deserialize from Checkmate Workflow (dict)
        new = SpiffWorkflow.deserialize(serializer, workflow)
        self.assertIsInstance(new, SpiffWorkflow)


if __name__ == '__main__':
    # Run tests. Handle our paramsters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
