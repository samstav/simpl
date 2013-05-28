# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method
'''
import mox
import unittest2 as unittest
from checkmate.workflow import get_failed_tasks


class TestWorkflow(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_get_failed_tasks(self):
        workflow = self.mox.CreateMockAnything()
        task_with_error = self.mox.CreateMockAnything()
        task_without_error = self.mox.CreateMockAnything()
        task_with_error._get_internal_attribute('task_state').AndReturn({
            "info": "Error Information",
            "state": "FAILURE",
            "traceback": "Traceback"})
        task_without_error._get_internal_attribute('task_state').AndReturn({})
        workflow.get_tasks().AndReturn([task_with_error, task_without_error])
        self.mox.ReplayAll()

        failed_tasks = get_failed_tasks(workflow)

        self.mox.VerifyAll()
        self.assertEqual(1, len(failed_tasks))
        self.assertDictEqual({"error_message": "Error Information",
                              "error_traceback": "Traceback"},
                             failed_tasks[0])


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params

    run_with_params(sys.argv[:])
