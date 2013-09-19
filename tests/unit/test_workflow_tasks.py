# pylint: disable=C0103,W0212,R0913

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

"""Tests for Workflow Tasks."""
import mock
import unittest

from celery import exceptions
from SpiffWorkflow import specs
from SpiffWorkflow import Workflow

from checkmate.common import tasks as cmtasks
from checkmate.workflows import tasks
from checkmate.workflows.tasks import cycle_workflow, update_deployment


class TestWorkflowTasks(unittest.TestCase):
    @mock.patch('checkmate.workflow.update_workflow')
    @mock.patch('checkmate.workflows.tasks.revoke_task')
    @mock.patch('checkmate.workflow.find_tasks')
    @mock.patch.object(Workflow, 'deserialize')
    @mock.patch.object(cmtasks.update_operation, 'delay')
    @mock.patch('checkmate.db.get_driver')
    def test_pause_workflow_with_only_waiting_tasks(self, mock_driver,
                                                    mock_update_operation,
                                                    mock_deserialize,
                                                    mock_find_tasks,
                                                    mock_revoke,
                                                    mock_update_wf):
        mock_spiff_wf = mock_deserialize.return_value
        driver = mock_driver.return_value
        build_wf_id = "BUILD_WF_ID"
        build_workflow = {
            'attributes': {
                'deploymentId': 'DEP_ID'
            },
            'celery_task_id': 'ct_id',
            'tenantId': "tenant_id",
        }
        deployment = {
            'id': 'DEP_ID',
            'operation': {
                'workflow-id': build_wf_id,
                'type': 'BUILD',
                'action': 'PAUSE',
            },
        }
        mock_task = mock.Mock()
        mock_task.task_spec = specs.Celery(specs.WorkflowSpec(), "name",
                                           "call")
        mock_task.task_spec._clear_celery_task_data = mock.Mock()
        mock_task._get_internal_attribute.side_effect = [
            {"state": "WAITING"}, "task_id"
        ]
        driver.get_workflow.return_value = build_workflow
        driver.get_deployment.return_value = deployment
        mock_find_tasks.side_effect = [[], [mock_task]]
        self.assertTrue(tasks.pause_workflow.run(build_wf_id))
        mock_revoke.assert_any_call('ct_id')
        mock_revoke.assert_any_call('task_id', terminate=True)
        mock_task.task_spec._clear_celery_task_data.assert_called_with(
            mock_task)
        kwargs = {"action-response": "ACK"}
        mock_update_operation.assert_any_call("DEP_ID", build_wf_id,
                                              driver=driver, **kwargs)
        kwargs = {
            "action-completes-after": 0,
            'status': 'PAUSED',
            'action-response': None,
            'action': None,
        }
        mock_update_operation.assert_any_call("DEP_ID", build_wf_id,
                                              driver=driver, **kwargs)
        mock_update_wf.assert_called_with(mock_spiff_wf, "tenant_id",
                                          status="PAUSED",
                                          workflow_id=build_wf_id)

    @mock.patch('checkmate.db.get_driver')
    def test_pause_workflow_completed_operation(self, mock_driver):
        driver = mock_driver.return_value
        build_wf_id = "BUILD_WF_ID"
        build_workflow = {
            'attributes': {
                'deploymentId': 'DEP_ID'
            },
        }
        deployment = {
            'id': 'DEP_ID',
            'operations-history': [
                {
                    'workflow-id': build_wf_id,
                    'type': 'BUILD',
                    'status': 'COMPLETE',
                }
            ],
            'operation': {
                'type': 'DELETE',
            },
        }
        driver.get_workflow.return_value = build_workflow
        driver.get_deployment.return_value = deployment
        self.assertTrue(tasks.pause_workflow.run(build_wf_id))

    @mock.patch('checkmate.workflow.update_workflow')
    @mock.patch('checkmate.workflows.tasks.revoke_task')
    @mock.patch('checkmate.workflow.find_tasks')
    @mock.patch.object(Workflow, 'deserialize')
    @mock.patch.object(cmtasks.update_operation, 'delay')
    @mock.patch('checkmate.db.get_driver')
    def test_pause_workflow_with_create_tasks(self, mock_driver,
                                              mock_update_operation,
                                              mock_deserialize,
                                              mock_find_tasks,
                                              mock_revoke,
                                              mock_update_wf):
        mock_spiff_wf = mock_deserialize.return_value
        driver = mock_driver.return_value
        build_wf_id = "BUILD_WF_ID"
        build_workflow = {
            'attributes': {
                'deploymentId': 'DEP_ID'
            },
            'celery_task_id': 'ct_id',
            'tenantId': "tenant_id",
        }
        deployment = {
            'id': 'DEP_ID',
            'operation': {
                'workflow-id': build_wf_id,
                'type': 'BUILD',
                'action': 'PAUSE',
            },
        }
        mock_task = mock.Mock()
        mock_task.task_spec = specs.Celery(specs.WorkflowSpec(), "name",
                                           "call")
        mock_task.task_spec._update_state = mock.Mock()
        mock_task._has_state.return_value = True
        mock_task._get_internal_attribute.return_value = {"state": "WAITING"}
        driver.get_workflow.return_value = build_workflow
        driver.get_deployment.return_value = deployment
        mock_find_tasks.return_value = [mock_task]
        tasks.pause_workflow.retry = mock.Mock()

        self.assertIsNone(tasks.pause_workflow.run(build_wf_id))
        mock_revoke.assert_called_with('ct_id')
        kwargs = {"action-response": "ACK"}
        mock_update_operation.assert_any_call("DEP_ID", build_wf_id,
                                              driver=driver, **kwargs)
        kwargs = {"action-completes-after": 1}
        mock_update_operation.assert_any_call("DEP_ID", build_wf_id,
                                              driver=driver, **kwargs)
        mock_update_wf.assert_called_with(mock_spiff_wf, "tenant_id",
                                          workflow_id=build_wf_id)
        mock_task.task_spec._update_state.assert_called_with(mock_task)
        tasks.pause_workflow.retry.assert_called_with([build_wf_id], kwargs={
            'retry_counter': 0, 'driver': driver
        })

    @mock.patch('checkmate.db.get_driver')
    def test_pause_workflow_wait_for_pause_action_update(self, mock_driver):
        driver = mock_driver.return_value
        build_wf_id = "BUILD_WF_ID"
        build_workflow = {
            'attributes': {
                'deploymentId': 'DEP_ID'
            },
            'celery_task_id': 'ct_id',
            'tenantId': "tenant_id",
        }
        deployment = {
            'id': 'DEP_ID',
            'operation': {
                'workflow-id': build_wf_id,
                'type': 'BUILD',
            },
        }
        driver.get_workflow.return_value = build_workflow
        driver.get_deployment.return_value = deployment
        tasks.pause_workflow.retry = mock.Mock(
            side_effect=exceptions.RetryTaskError())

        self.assertRaises(exceptions.RetryTaskError, tasks.pause_workflow.run,
                          build_wf_id)
        tasks.pause_workflow.retry.assert_called_with([build_wf_id], kwargs={
            'retry_counter': 1, 'driver': driver
        })

    @mock.patch('checkmate.workflows.manager.Manager.get_workflow')
    @mock.patch('SpiffWorkflow.Workflow.deserialize')
    @mock.patch('checkmate.common.tasks.update_operation')
    def test_update_deployment_set_deployment_status_when_wf_complete(
            self, mock_update_operation, deserializer, get_workflow,
            driver):

        mock_driver = mock.MagicMock()
        driver.return_value = mock_driver
        get_workflow.return_value = {'id': 1001}

        mock_d_wf = mock.MagicMock()

        def attributes(*args):
            if args[0] == 'type':
                return "BUILD"
            return args[0]

        mock_d_wf.get_attribute.side_effect = attributes
        mock_d_wf.is_completed = mock.MagicMock(return_value=True)
        deserializer.return_value = mock_d_wf
        mock_update_operation.delay = mock.MagicMock(return_value=None)
        update_deployment(1001)

        driver.assert_called_once_with(api_id=1001)
        get_workflow.assert_called_once_with(1001)
        mock_d_wf.is_completed.assert_any_call()
        mock_update_operation.delay.assert_any_call("deploymentId", 1001,
                                                    driver=mock_driver,
                                                    deployment_status="UP",
                                                    status="status",
                                                    tasks="total",
                                                    complete="completed")

    @mock.patch('checkmate.db.get_driver')
    @mock.patch('checkmate.workflows.manager.Manager.get_workflow')
    @mock.patch('SpiffWorkflow.Workflow.deserialize')
    @mock.patch('checkmate.common.tasks.update_operation')
    def test_update_deployment_set_deployment_status_when_delete_wf_complete(
            self, mock_update_operation, deserializer, get_workflow,
            driver):

        mock_driver = mock.MagicMock()
        driver.return_value = mock_driver
        get_workflow.return_value = {'id': 1001}

        mock_d_wf = mock.MagicMock()

        def attributes(*args):
            if args[0] == 'type':
                return "DELETE"
            return args[0]

        mock_d_wf.get_attribute.side_effect = attributes
        mock_d_wf.is_completed = mock.MagicMock(return_value=True)
        deserializer.return_value = mock_d_wf
        mock_update_operation.delay = mock.MagicMock(return_value=None)
        update_deployment(1001)

        driver.assert_called_once_with(api_id=1001)
        get_workflow.assert_called_once_with(1001)
        mock_d_wf.is_completed.assert_any_call()
        mock_update_operation.delay.assert_called_once_with(
            "deploymentId", 1001, driver=mock_driver,
            deployment_status="DELETED", status="status", tasks="total",
            complete="completed")

    @mock.patch('checkmate.db.get_driver')
    @mock.patch('checkmate.workflows.manager.Manager.get_workflow')
    @mock.patch('SpiffWorkflow.Workflow.deserialize')
    @mock.patch('checkmate.common.tasks.update_operation')
    @mock.patch('checkmate.workflow.get_errors')
    @mock.patch('checkmate.workflow.get_status_info')
    def test_update_deployment_set_deployment_status_when_wf_incomplete(
            self, get_status_info, get_errors, mock_update_operation,
            deserializer, get_workflow,
            driver):

        mock_driver = mock.MagicMock()
        driver.return_value = mock_driver

        mock_d_wf = mock.MagicMock()

        def attributes(*args):
            if args[0] == 'type':
                return "BUILD"
            return args[0]

        mock_d_wf.get_attribute.side_effect = attributes
        mock_d_wf.is_completed = mock.MagicMock(return_value=False)
        deserializer.return_value = mock_d_wf
        mock_update_operation.delay = mock.MagicMock(return_value=None)
        get_errors.return_value = ["error1", "error2"]
        get_status_info.return_value = {'friendly_message': 'status-info'}
        update_deployment(1001)

        driver.assert_called_with(api_id=1001)
        get_workflow.assert_called_once_with(1001)
        mock_d_wf.is_completed.assert_any_call()
        mock_update_operation.delay.assert_called_once_with(
            "deploymentId",
            1001,
            driver=mock_driver,
            deployment_status="FAILED",
            status='status',
            tasks='total',
            complete='completed',
            friendly_message='status-info',
            errors=["error1", "error2"])

    @mock.patch('checkmate.utils.match_celery_logging')
    @mock.patch('checkmate.db.get_driver')
    @mock.patch('checkmate.workflows.manager.Manager.get_workflow')
    @mock.patch('SpiffWorkflow.Workflow.deserialize')
    @mock.patch('checkmate.workflow.update_workflow_status')
    @mock.patch('checkmate.workflows.manager.Manager.save_spiff_workflow')
    @mock.patch('checkmate.workflows.tasks.cycle_workflow.update_state')
    def test_cycle_workflow_when_workflow_complete(
            self, update_state, save_spiffworkflow, update_workflow_status,
            deserializer, get_workflow, get_driver, logging):

        mock_driver = mock.MagicMock()
        get_driver.return_value = mock_driver
        get_workflow.return_value = {'id': 1001}

        mock_d_wf = mock.MagicMock()
        deserializer.return_value = mock_d_wf
        update_workflow_status.side_effect = [
            {'completed': 5, 'errored': 0, 'total': 6},
            {'completed': 5, 'errored': 1, 'total': 6}]

        mock_d_wf.is_completed.return_value = True

        cycle_workflow.request.id = "1234"
        cycle_workflow.run(1001, None)
        self.assertFalse(update_state.called)
        save_spiffworkflow.assert_called_once_with(mock_d_wf,
                                                   celery_task_id="1234")

    @mock.patch('checkmate.utils.match_celery_logging')
    @mock.patch('checkmate.db.get_driver')
    @mock.patch('checkmate.workflows.manager.Manager.get_workflow')
    @mock.patch('SpiffWorkflow.Workflow.deserialize')
    @mock.patch('checkmate.workflow.update_workflow_status')
    @mock.patch('checkmate.workflows.manager.Manager.save_spiff_workflow')
    @mock.patch('checkmate.workflows.tasks.cycle_workflow.update_state')
    @mock.patch('checkmate.workflows.tasks.cycle_workflow.retry')
    def test_cycle_workflow_when_workflow_is_not_complete(
            self, workflow_retry, update_state, save_spiffworkflow,
            update_workflow_status, deserializer, get_workflow,
            get_driver, logging):

        mock_driver = mock.MagicMock()
        get_driver.return_value = mock_driver
        get_workflow.return_value = {'id': 1001}

        mock_d_wf = mock.MagicMock()
        deserializer.return_value = mock_d_wf
        update_workflow_status.side_effect = [
            {'completed': 5, 'errored': 0, 'total': 6},
            {'completed': 5, 'errored': 1, 'total': 6}]

        mock_d_wf.is_completed.return_value = False

        cycle_workflow.request.id = "1234"
        cycle_workflow.run(1001, None)
        update_state.assert_called_once_with(
            state="PROGRESS",
            meta={'complete': 5, 'total': 6})

        #Also tests that apply_callbacks are defaulted to 'true'
        workflow_retry.assert_called_once_with(
            [1001, None],
            kwargs={'wait': 1, 'apply_callbacks': True},
            countdown=1)
        save_spiffworkflow.assert_called_once_with(mock_d_wf,
                                                   celery_task_id="1234")

    @mock.patch('checkmate.utils.match_celery_logging')
    @mock.patch('checkmate.db.get_driver')
    @mock.patch('checkmate.workflows.manager.Manager.get_workflow')
    @mock.patch('SpiffWorkflow.Workflow.deserialize')
    @mock.patch('checkmate.workflow.update_workflow_status')
    @mock.patch('checkmate.workflows.manager.Manager.save_spiff_workflow')
    @mock.patch('checkmate.workflows.tasks.cycle_workflow.update_state')
    @mock.patch('checkmate.workflows.tasks.cycle_workflow.retry')
    def test_workflow_run_without_callbacks(
            self, workflow_retry, update_state, save_spiffworkflow,
            update_workflow_status, deserializer, get_workflow,
            get_driver, logging):

        apply_callbacks = False

        mock_driver = mock.MagicMock()
        get_driver.return_value = mock_driver
        get_workflow.return_value = {'id': 1001}

        mock_d_wf = mock.MagicMock()
        deserializer.return_value = mock_d_wf
        update_workflow_status.side_effect = [
            {'completed': 5, 'errored': 0, 'total': 6},
            {'completed': 5, 'errored': 1, 'total': 6}]

        mock_d_wf.is_completed.return_value = False

        cycle_workflow.request.id = "1234"
        cycle_workflow.run(1001, None, apply_callbacks=apply_callbacks)
        update_state.assert_called_once_with(
            state="PROGRESS",
            meta={'complete': 5, 'total': 6})
        workflow_retry.assert_called_once_with([1001, None],
                                               kwargs={'wait': 1,
                                                       'apply_callbacks':
                                                       apply_callbacks},
                                               countdown=1)
        save_spiffworkflow.assert_called_once_with(mock_d_wf,
                                                   celery_task_id="1234")

    @mock.patch('checkmate.utils.match_celery_logging')
    @mock.patch('checkmate.db.get_driver')
    @mock.patch('checkmate.workflows.manager.Manager.get_workflow')
    @mock.patch('SpiffWorkflow.Workflow.deserialize')
    @mock.patch('checkmate.workflow.update_workflow_status')
    @mock.patch('checkmate.workflows.manager.Manager.save_spiff_workflow')
    @mock.patch('checkmate.workflows.tasks.cycle_workflow.update_state')
    @mock.patch('checkmate.workflows.tasks.cycle_workflow.retry')
    def test_workflow_when_it_makes_no_progress(
            self, workflow_retry, update_state, save_spiffworkflow,
            update_workflow_status, deserializer,
            get_workflow, get_driver, logging):

        initial_wait = 5

        mock_driver = mock.MagicMock()
        get_driver.return_value = mock_driver
        get_workflow.return_value = {'id': 1001}

        mock_d_wf = mock.MagicMock()
        deserializer.return_value = mock_d_wf
        # To indicate that the workflow made no progress:
        update_workflow_status.side_effect = [
            {'completed': 5, 'errored': 0, 'total': 6},
            {'completed': 5, 'errored': 0, 'total': 6}]

        mock_d_wf.is_completed.return_value = False

        cycle_workflow.run(1001, None, wait=initial_wait)
        self.assertFalse(update_state.called)
        workflow_retry.assert_called_once_with([1001, None],
                                               kwargs={
                                                   'wait': (initial_wait + 1),
                                                   'apply_callbacks': True
                                               },
                                               countdown=(initial_wait + 1))
        self.assertFalse(save_spiffworkflow.called)

    @mock.patch('checkmate.utils.match_celery_logging')
    @mock.patch('checkmate.db.get_driver')
    @mock.patch('checkmate.workflows.manager.Manager.get_workflow')
    @mock.patch('SpiffWorkflow.Workflow.deserialize')
    @mock.patch('checkmate.workflow.update_workflow_status')
    @mock.patch('checkmate.workflows.exception_handlers.get_handlers')
    @mock.patch('checkmate.workflows.manager.Manager.save_spiff_workflow')
    @mock.patch('checkmate.workflows.tasks.cycle_workflow.update_state')
    @mock.patch('checkmate.workflows.tasks.cycle_workflow.retry')
    @mock.patch('checkmate.workflows.tasks.cycle_workflow.apply_async')
    def test_run_of_subworkflows(
            self, apply_async, workflow_retry, update_state,
            save_spiffworkflow, get_handlers, update_workflow_status,
            deserializer, get_workflow, get_driver, logging):

        mock_driver = mock.MagicMock()
        get_driver.return_value = mock_driver
        get_workflow.return_value = {'id': 1001}

        mock_d_wf = mock.MagicMock()
        deserializer.return_value = mock_d_wf
        update_workflow_status.side_effect = [
            {'completed': 5, 'errored': 0, 'total': 6},
            {'completed': 5, 'errored': 0, 'total': 6, 'errored_tasks': [1]}]

        get_handlers.return_value = [mock.MagicMock(handle=mock.MagicMock(
            return_value=[2743]))]

        mock_d_wf.is_completed.return_value = True

        cycle_workflow.request.id = "1234"
        cycle_workflow.run(1001, None)
        self.assertFalse(update_state.called)
        self.assertFalse(workflow_retry.called)
        apply_async.assert_call_once_with(args=[2743, None],
                                          kwargs={'apply_callbacks': False},
                                          task_id=2743)
        save_spiffworkflow.assert_called_once_with(mock_d_wf,
                                                   celery_task_id="1234")
