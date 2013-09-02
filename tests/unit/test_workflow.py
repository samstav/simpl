# pylint: disable=C0103,W0212

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

"""Tests for Workflow class."""
import re
import unittest

import mox
from SpiffWorkflow import specs
from SpiffWorkflow import storage
from SpiffWorkflow.Workflow import Workflow

from checkmate import deployment as cmdep
from checkmate import deployments
from checkmate import middleware as cmmid
from checkmate import providers as cmprov
from checkmate.providers import base
from checkmate.providers.rackspace import loadbalancer
from checkmate import test
from checkmate import utils
from checkmate import workflow
from checkmate import workflows
from checkmate.workflows import WorkflowSpec as cm_wfspec


class TestWorkflow(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()
        self.mocked_workflow = self.mox.CreateMockAnything()
        self.task_with_error = self.mox.CreateMockAnything()
        self.task_without_error = self.mox.CreateMockAnything()
        self.tenant_id = "tenant_id"
        self.task_with_error.id = "task_id"
        base.PROVIDER_CLASSES = {}
        cmprov.register_providers([loadbalancer.Provider, test.TestProvider])

    def tearDown(self):
        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_get_errored_tasks(self):
        failed_task_state = {
            'state': 'FAILURE',
        }
        self.task_with_error._get_internal_attribute("task_state").AndReturn(
            failed_task_state)
        self.task_without_error._get_internal_attribute(
            "task_state").AndReturn(None)
        self.mocked_workflow.get_tasks().AndReturn([self.task_with_error,
                                                    self.task_without_error])
        self.mox.ReplayAll()
        self.assertEquals(workflow.get_errored_tasks(self.mocked_workflow),
                          ['task_id'])

    def test_reset_failed_tasks_when_retry_count_is_under_threshold(self):
        context = self.mox.CreateMock(cmmid.RequestContext)
        deployment = cmdep.Deployment({"id":"DEP_ID"})
        driver = self.mox.CreateMockAnything()
        task_state = {
            "info": "CheckmateResetTaskTreeException()",
            "state": "FAILURE",
        }

        driver.get_deployment(deployment["id"], with_secrets=False)\
            .AndReturn(deployment)

        self.mocked_workflow.get_task("task_id").AndReturn(
            self.task_with_error)
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)

        mock_taskspec = self.mox.CreateMockAnything()
        self.task_with_error.task_spec = mock_taskspec
        mock_taskspec.get_property("task_retry_count", default=0).AndReturn(2)
        resource_key = 1
        mock_taskspec.get_property("resource").AndReturn(resource_key)
        self.mox.StubOutWithMock(cm_wfspec,
                                 "create_workflow_for_resource_deletion")
        spec = self.mox.CreateMock(specs.WorkflowSpec)
        cm_wfspec.create_reset_failed_resources_spec(context, deployment,
                                                        resource_key).\
            AndReturn(spec)
        self.mox.StubOutWithMock(workflow, "reset_task_tree")
        workflow.reset_task_tree(self.task_with_error)
        self.mox.StubOutWithMock(workflow, "create_workflow")
        workflow.create_workflow(spec, deployment, context, driver=driver)
        mock_taskspec.set_property(task_retry_count=3)
        self.mox.ReplayAll()
        workflow.try_create_reset_failed_tasks_workflow(self.mocked_workflow, deployment["id"],
                                    context, ["task_id"], driver)

    def test_reset_failed_tasks_when_retry_count_above_threshold(self):
        context = self.mox.CreateMock(cmmid.RequestContext)
        deployment = cmdep.Deployment({"id":"DEP_ID"})
        driver = self.mox.CreateMockAnything()
        task_state = {
            "info": "CheckmateResetTaskTreeException()",
            "state": "FAILURE",
        }

        driver.get_deployment(deployment["id"], with_secrets=False)\
            .AndReturn(deployment)
        self.mocked_workflow.get_task("task_id").AndReturn(
            self.task_with_error)

        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        mock_task_spec = self.mox.CreateMockAnything()
        self.task_with_error.task_spec = mock_task_spec
        mock_task_spec.get_property("task_retry_count", default=0).AndReturn(
            workflow.TASK_RETRY_MAX_LIMIT + 1)
        self.mox.ReplayAll()
        workflow.try_create_reset_failed_tasks_workflow(self.mocked_workflow, deployment["id"],
                                    context,["task_id"], driver)

    def test_convert_exc_to_dict_with_retriable_exception(self):
        info = "CheckmateRetriableException('foo', 'Exception', " \
               "'exception_message', 'error-help')"
        error = workflow.convert_exc_to_dict(info, "task_id", "tenant_id",
                                             "wf_id", "Traceback")
        expected_error = {
            "error-message": "foo",
            "error-help": "error-help",
            "retriable": True,
            "retry-link": "/tenant_id/workflows/wf_id/tasks/task_id/"
                          "+reset-task-tree",
            "error-type": "Exception",
            "task-id": "task_id",
            "error-traceback": "Traceback",
            "friendly-message": "exception_message"
        }
        self.assertDictEqual(expected_error, error)

    def test_convert_exc_to_dict_with_checkmate_user_exception(self):
        info = "CheckmateUserException('foo', 'Exception', " \
               "'exception_message', 'error-help')"
        error = workflow.convert_exc_to_dict(info, "task_id", "tenant_id",
                                             "wf_id", "Traceback")
        expected_error = {
            "error-message": "foo",
            "error-help": "error-help",
            "error-type": "Exception",
            "task-id": "task_id",
            "error-traceback": "Traceback",
            "friendly-message": "exception_message"
        }
        self.assertDictEqual(expected_error, error)

    def test_convert_exc_to_dict_with_resumable_exception(self):
        info = "CheckmateResumableException('foo', 'Exception', " \
               "'friendly_message', 'error-help')"
        error = workflow.convert_exc_to_dict(info, "task_id", "tenant_id",
                                             "wf_id", "Traceback")
        expected_error = {
            "error-message": "foo",
            "error-help": "error-help",
            "resumable": True,
            "resume-link": "/tenant_id/workflows/wf_id/tasks/task_id/+execute",
            "error-type": "Exception",
            "task-id": "task_id",
            "error-traceback": "Traceback",
            "friendly-message": 'friendly_message'
        }
        self.assertDictEqual(expected_error, error)

    def test_convert_exc_to_dict_with_max_retries_exceeded_error(self):
        info = "MaxRetriesExceededError()"
        error = workflow.convert_exc_to_dict(info, "task_id", "tenant_id",
                                             "wf_id", "Traceback")
        expected_error = {
            "error-message": "The maximum amount of permissible retries for "
                             "workflow wf_id has elapsed. Please re-execute "
                             "the workflow",
            "error-help": "",
            "retriable": True,
            "retry-link": "/tenant_id/workflows/wf_id/+execute",
            "error-type": "MaxRetriesExceededError",
            "friendly-message": 'There was a timeout while executing the '
                                'deployment'
        }
        self.assertDictEqual(expected_error, error)

    def test_convert_exc_to_dict_with_generic_exception(self):
        info = "Exception('This is an exception')"
        error = workflow.convert_exc_to_dict(info, "task_id", "tenant_id",
                                             "wf_id", "Traceback")
        expected_error = {"error-message": "This is an exception",
                          "error-type": "Exception",
                          "error-traceback": "Traceback"}
        self.assertDictEqual(expected_error, error)

    def test_convert_exc_to_dict_with_no_exception(self):
        info = "C"
        self.assertRaises(NameError, workflow.convert_exc_to_dict, info,
                          "task_id", "tenant_id", "wf_id", "Traceback")

    def test_get_failed_tasks_with_no_exception(self):
        task_state = {
            "info": "C",
            "state": "FAILURE",
            "traceback": "Traceback"
        }
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.task_with_error._get_internal_attribute('task_state').AndReturn(
            task_state)
        self.mocked_workflow.get_tasks().AndReturn([self.task_with_error])
        self.mocked_workflow.get_attribute('id').AndReturn("wf_id")
        self.mox.ReplayAll()

        failed_tasks = workflow.get_errors(self.mocked_workflow,
                                           self.tenant_id)

        self.mox.VerifyAll()
        self.assertEqual(1, len(failed_tasks))
        expected_error = {"error-message": "C",
                          "error-traceback": "Traceback"}
        self.assertDictEqual(expected_error,
                             failed_tasks[0])

    def test_get_failed_tasks_with_valid_exception(self):
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
        self.mocked_workflow.get_attribute('id').AndReturn("wf_id")
        self.mox.ReplayAll()

        failed_tasks = workflow.get_errors(self.mocked_workflow,
                                           self.tenant_id)

        self.mox.VerifyAll()
        self.assertEqual(1, len(failed_tasks))
        expected_error = {"error-message": "This is an exception",
                          "error-type": "Exception",
                          "error-traceback": "Traceback"}
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

        self.assertTrue(workflow.is_failed_task(task_with_error))
        self.assertFalse(workflow.is_failed_task(task_without_error))

    def test_update_status_without_an_overriding_status_value(self):
        w_id = "1"
        tenant_id = "1001"

        serializer = storage.DictionarySerializer()
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

        workflow.update_workflow(d_wf, tenant_id=tenant_id, status=None,
                                 driver=mock_driver, workflow_id=w_id)

    def test_update_status_with_an_overriding_status_value(self):
        w_id = "1"
        tenant_id = "1001"

        serializer = storage.DictionarySerializer()
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

        workflow.update_workflow(d_wf, tenant_id=tenant_id, status="PAUSED",
                                 driver=mock_driver, workflow_id=w_id)

    def test_create_delete_workflow_with_incomplete_operation(self):
        context = cmmid.RequestContext(auth_token='MOCK_TOKEN',
                                       username='MOCK_USER')
        deployment_with_lb_provider = cmdep.Deployment(utils.yaml_to_dict("""
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
        workflow_spec = workflows.WorkflowSpec.create_delete_dep_wf_spec(
            deployment_with_lb_provider, context)
        test_workflow = workflow.init_spiff_workflow(
            workflow_spec, deployment_with_lb_provider, context, "w_id",
            "DELETE")
        workflow_dump = re.sub(r"\s", "", test_workflow.get_dump())
        expected_dump = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
      3/0: Task of Pause BUILD Workflow DEP-ID-1000 State: FUTURE
      Children: 1
        4/0: Task of Delete Loadbalancer (0) State: FUTURE Children: 1
          5/0: Task of Wait for Loadbalancer (0) delete State: FUTURE
      Children: 0"""

        expected_dump = re.sub(r"\s", "", expected_dump)
        self.assertEqual(expected_dump.strip(), workflow_dump.strip())

    def test_create_delete_workflow_with_complete_operation(self):
        context = cmmid.RequestContext(auth_token='MOCK_TOKEN',
                                       username='MOCK_USER')
        deployment_with_lb_provider = cmdep.Deployment(utils.yaml_to_dict("""
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
        workflow_spec = workflows.WorkflowSpec\
            .create_delete_dep_wf_spec(
                deployment_with_lb_provider, context)
        test_workflow = workflow.init_spiff_workflow(
            workflow_spec, deployment_with_lb_provider, context, "w_id",
            "DELETE")
        workflow_dump = re.sub(r"\s", "", test_workflow.get_dump())
        expected_dump = """
1/0: Task of Root State: COMPLETED Children: 1
  2/0: Task of Start State: READY Children: 1
    3/0: Task of Delete Loadbalancer (0) State: FUTURE Children: 1
      4/0: Task of Wait for Loadbalancer (0) delete State: FUTURE
      Children: 0"""

        expected_dump = re.sub(r"\s", "", expected_dump)
        self.assertEqual(expected_dump.strip(), workflow_dump.strip())

    def _create_spiff_workflow(self):
        """Helper method to create a Spiff Workflow."""
        wf_spec = specs.WorkflowSpec(name="Test")
        wf_a = specs.Simple(wf_spec, 'A')
        wf_spec.start.connect(wf_a)
        return Workflow(wf_spec)

    def test_format_resources_for_path_attrib(self):
        actual = workflow.format({"1": {"instance": {"id": "1000",
                                                     "foo": "bar"}}})
        expected = {"instance:1": {"id": "1000",
                                   "foo": "bar"}}
        self.assertDictEqual(actual, expected)

        actual = workflow.format({"1": {"index": "1"}})
        expected = {"instance:1": {}}

        self.assertDictEqual(actual, expected)

if __name__ == '__main__':
    import sys

    test.run_with_params(sys.argv[:])
