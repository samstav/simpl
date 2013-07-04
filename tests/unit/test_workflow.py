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
import re

import mox
import unittest

from SpiffWorkflow.specs import WorkflowSpec, Simple
from SpiffWorkflow.storage import DictionarySerializer
from SpiffWorkflow.Workflow import Workflow

from checkmate import workflow, deployments, test
from checkmate import utils
from checkmate.deployment import Deployment
from checkmate.middleware import RequestContext
from checkmate.providers import base, register_providers
from checkmate.providers.rackspace import loadbalancer
from checkmate.workflow import (
    get_errors,
    is_failed_task,
    update_workflow,
    create_delete_deployment_workflow_spec,
    create_workflow,
)


class TestWorkflow(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()
        self.mocked_workflow = self.mox.CreateMockAnything()
        self.task_with_error = self.mox.CreateMockAnything()
        self.task_without_error = self.mox.CreateMockAnything()
        self.tenant_id = "tenant_id"
        self.task_with_error.id = "task_id"
        base.PROVIDER_CLASSES = {}
        register_providers([loadbalancer.Provider, test.TestProvider])

    def tearDown(self):
        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_get_failed_tasks_evaluates_only_failed_tasks(self):
        task_state = {"info": "Error Information", "state": "FAILURE",
                      "traceback": "Traceback"}
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.task_without_error._get_internal_attribute(
            'task_state').AndReturn({})
        self.mocked_workflow.get_tasks().AndReturn([self.task_with_error,
                                                    self.task_without_error])
        self.mox.ReplayAll()

        failed_tasks = get_errors(self.mocked_workflow, self.tenant_id)

        self.assertEqual(1, len(failed_tasks))
        self.assertDictEqual({"error-message": "Error Information"},
                             failed_tasks[0])

    def test_get_failed_tasks_with_retriable_exception(self):
        task_state = {
            "info": "CheckmateRetriableException('exception_message', "
                    "'error-help', 'error-type', True)",
            "state": "FAILURE",
            "traceback": "Traceback"
        }
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.mocked_workflow.get_tasks().AndReturn([self.task_with_error])
        self.mocked_workflow.attributes = {"id": "wf_id"}
        self.mox.ReplayAll()

        failed_tasks = get_errors(self.mocked_workflow, self.tenant_id)

        self.mox.VerifyAll()
        self.assertEqual(1, len(failed_tasks))
        expected_error = {
            "error-message": "exception_message",
            "error-help": "error-help",
            "retriable": True,
            "retry-link": "/tenant_id/workflows/wf_id/tasks/task_id/"
                          "+reset-task-tree",
            "error-type": "error-type",
            "action-required": True,
            "task-id": "task_id"
        }
        self.assertDictEqual(expected_error,
                             failed_tasks[0])

    def test_get_failed_tasks_with_resumable_exception(self):
        task_state = {
            "info": "CheckmateResumableException('exception_message', "
                    "'error-help', 'error-type', True)",
            "state": "FAILURE",
            "traceback": "Traceback"
        }
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.mocked_workflow.get_tasks().AndReturn([self.task_with_error])
        self.mocked_workflow.attributes = {"id": "wf_id"}
        self.mox.ReplayAll()

        failed_tasks = get_errors(self.mocked_workflow, self.tenant_id)

        self.mox.VerifyAll()
        self.assertEqual(1, len(failed_tasks))
        expected_error = {
            "error-message": "exception_message",
            "error-help": "error-help",
            "resumable": True,
            "resume-link": "/tenant_id/workflows/wf_id/tasks/task_id/+execute",
            "error-type": "error-type",
            "action-required": True,
            "task-id": "task_id"
        }
        self.assertDictEqual(expected_error,
                             failed_tasks[0])

    def test_get_failed_tasks_with_generic_exception(self):
        task_state = {
            "info": "Exception('This is an exception')",
            "state": "FAILURE",
            "traceback": "Traceback"
        }
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.mocked_workflow.get_tasks().AndReturn([self.task_with_error])
        self.mox.ReplayAll()

        failed_tasks = get_errors(self.mocked_workflow, self.tenant_id)

        self.mox.VerifyAll()
        self.assertEqual(1, len(failed_tasks))
        expected_error = {"error-message": "This is an exception",
                          "error-type": "Exception"}
        self.assertDictEqual(expected_error,
                             failed_tasks[0])

    def test_get_failed_tasks_with_no_exception(self):
        task_state = {
            "info": "This is a exception message",
            "state": "FAILURE",
            "traceback": "Traceback"
        }
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.mocked_workflow.get_tasks().AndReturn([self.task_with_error])
        self.mox.ReplayAll()

        failed_tasks = get_errors(self.mocked_workflow, self.tenant_id)

        self.mox.VerifyAll()
        self.assertEqual(1, len(failed_tasks))
        expected_error = {"error-message": "This is a exception message"}
        self.assertDictEqual(expected_error,
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
        workflow.update_workflow_status(d_wf, workflow_id=w_id)
        mock_driver = self.mox.CreateMockAnything()
        wf_serialize = d_wf.serialize(serializer)
        wf_serialize["tenantId"] = tenant_id
        wf_serialize["id"] = w_id
        mock_driver.save_workflow(w_id, wf_serialize,
                                  secrets=None)
        self.mox.ReplayAll()

        update_workflow(d_wf, tenant_id=tenant_id, status=None,
                        driver=mock_driver, workflow_id=w_id)

    def test_update_status_with_an_overriding_status_value(self):
        w_id = "1"
        tenant_id = "1001"

        serializer = DictionarySerializer()
        d_wf = self._create_spiff_workflow()
        d_wf.attributes["id"] = w_id
        d_wf.attributes["status"] = "COMPLETE"

        self.mox.StubOutWithMock(workflow, 'update_workflow_status')
        workflow.update_workflow_status(d_wf, workflow_id=w_id)

        mock_driver = self.mox.CreateMockAnything()
        wf_serialize = d_wf.serialize(serializer)
        wf_serialize["tenantId"] = tenant_id
        wf_serialize["id"] = w_id
        wf_serialize["attributes"] = {'status': 'PAUSED', 'id': w_id}
        mock_driver.save_workflow(w_id, wf_serialize,
                                  secrets=None)
        self.mox.ReplayAll()

        update_workflow(d_wf, tenant_id=tenant_id, status="PAUSED",
                        driver=mock_driver, workflow_id=w_id)

    def test_create_delete_workflow_with_incomplete_operation(self):
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        deployment_with_lb_provider = Deployment(utils.yaml_to_dict("""
                id: 'DEP-ID-1000'
                tenantId: '1000'
                blueprint:
                  name: LB Test
                  services:
                    lb:
                      component:
                        resource_type: load-balancer
                        interface: http
                        constraints:
                          - region: North
                      relations:
                        server: http
                    server:
                      component:
                        resource_type: compute
                operation:
                  status: IN PROGRESS
                  type: BUILD
                environment:
                  name: test
                  providers:
                    load-balancer:
                      vendor: rackspace
                      catalog:
                        load-balancer:
                          rsCloudLB:
                            provides:
                            - load-balancer: http
                            requires:
                            - application: http
                            options:
                              protocol:
                                type: list
                                choice: [http]
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            provides:
                            - application: http
                            - compute: linux
            """))
        deployments.Manager.plan(deployment_with_lb_provider, context)
        deployment_with_lb_provider['resources']['0']['instance'] = {
            'id': 'lbid'}
        workflow_spec = create_delete_deployment_workflow_spec(
            deployment_with_lb_provider, context)
        workflow = create_workflow(workflow_spec, deployment_with_lb_provider,
                                   context)
        workflow_dump = re.sub("\s", "", workflow.get_dump())
        expected_dump = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
      3/0: Task of Pause BUILD Workflow DEP-ID-1000 State: FUTURE
      Children: 1
        4/0: Task of Delete Loadbalancer (0) State: FUTURE Children: 1
          5/0: Task of Wait for Loadbalancer (0) delete State: FUTURE
      Children: 0"""

        expected_dump = re.sub("\s", "", expected_dump)
        self.assertEqual(expected_dump.strip(), workflow_dump.strip())

    def test_create_delete_workflow_with_complete_operation(self):
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        deployment_with_lb_provider = Deployment(utils.yaml_to_dict("""
                id: 'DEP-ID-1000'
                tenantId: '1000'
                blueprint:
                  name: LB Test
                  services:
                    lb:
                      component:
                        resource_type: load-balancer
                        interface: http
                        constraints:
                          - region: North
                      relations:
                        server: http
                    server:
                      component:
                        resource_type: compute
                operation:
                  status: COMPLETE
                  type: BUILD
                environment:
                  name: test
                  providers:
                    load-balancer:
                      vendor: rackspace
                      catalog:
                        load-balancer:
                          rsCloudLB:
                            provides:
                            - load-balancer: http
                            requires:
                            - application: http
                            options:
                              protocol:
                                type: list
                                choice: [http]
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            provides:
                            - application: http
                            - compute: linux
            """))
        deployments.Manager.plan(deployment_with_lb_provider, context)
        deployment_with_lb_provider['resources']['0']['instance'] = {
            'id': 'lbid'}
        workflow_spec = create_delete_deployment_workflow_spec(
            deployment_with_lb_provider, context)
        workflow = create_workflow(workflow_spec, deployment_with_lb_provider,
                                   context)
        workflow_dump = re.sub("\s", "", workflow.get_dump())
        print workflow.get_dump()
        expected_dump = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
    3/0: Task of Delete Loadbalancer (0) State: FUTURE Children: 1
      4/0: Task of Wait for Loadbalancer (0) delete State: FUTURE
      Children: 0"""

        expected_dump = re.sub("\s", "", expected_dump)
        self.assertEqual(expected_dump.strip(), workflow_dump.strip())

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
