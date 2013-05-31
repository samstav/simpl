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
from SpiffWorkflow.Workflow import Workflow
from SpiffWorkflow.specs import WorkflowSpec, Simple
from SpiffWorkflow.storage import DictionarySerializer
from checkmate import workflow
import mox
import unittest2 as unittest
from checkmate.workflow import (
    get_failed_tasks,
    is_failed_task,
    update_workflow,
)


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

    def test_is_failed_task(self):
        task_with_error = self.mox.CreateMockAnything()
        task_without_error = self.mox.CreateMockAnything()

        task_with_error._get_internal_attribute('task_state').AndReturn({
            "info": "Error Information",
            "state": "FAILURE",
            "traceback": "Traceback"})
        task_without_error._get_internal_attribute('task_state').AndReturn({})
        self.mox.ReplayAll()

        self.assertTrue(is_failed_task(task_with_error))
        self.assertFalse(is_failed_task(task_without_error))

    def test_update_status_without_an_overriding_status_value(self):
        w_id = "1"
        tenant_id = "1001"

        serializer = DictionarySerializer()
        d_wf = self._create_spiff_workflow()
        d_wf.attributes["id"] = w_id

        self.mox.StubOutWithMock(workflow, 'update_workflow_status')
        workflow.update_workflow_status(d_wf)
        mock_driver = self.mox.CreateMockAnything()
        wf_serialize = d_wf.serialize(serializer)
        wf_serialize["tenantId"] = tenant_id
        wf_serialize["id"] = w_id
        mock_driver.save_workflow(w_id, wf_serialize,
                                  secrets=None)
        self.mox.ReplayAll()

        update_workflow(d_wf, tenant_id=tenant_id, status=None,
                        driver=mock_driver)

    def test_update_status_with_an_overriding_status_value(self):
        w_id = "1"
        tenant_id = "1001"

        serializer = DictionarySerializer()
        d_wf = self._create_spiff_workflow()
        d_wf.attributes["id"] = w_id
        d_wf.attributes["status"] = "COMPLETE"

        self.mox.StubOutWithMock(workflow, 'update_workflow_status')
        workflow.update_workflow_status(d_wf)
        mock_driver = self.mox.CreateMockAnything()
        wf_serialize = d_wf.serialize(serializer)
        wf_serialize["tenantId"] = tenant_id
        wf_serialize["id"] = w_id
        wf_serialize["attributes"] = {'status': 'PAUSED', 'id': w_id}
        mock_driver.save_workflow(w_id, wf_serialize,
                                  secrets=None)
        self.mox.ReplayAll()

        update_workflow(d_wf, tenant_id=tenant_id, status="PAUSED",
                        driver=mock_driver)

    def tearDown(self):
        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def _create_spiff_workflow(self):
        wf_spec = WorkflowSpec(name="Test")
        A = Simple(wf_spec, 'A')
        wf_spec.start.connect(A)
        return Workflow(wf_spec)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params

    run_with_params(sys.argv[:])
