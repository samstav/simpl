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

#pylint: disable=R0201,C0111,C0103

import mock
import unittest

from celery.result import AsyncResult

from checkmate.workflows import exception_handlers


class TestRetryTaskTreeExceptionHandler(unittest.TestCase):

    @mock.patch("checkmate.workflow.get_subworkflow")
    @mock.patch.object(AsyncResult, 'ready')
    @mock.patch("checkmate.workflow.create_reset_failed_task_wf")
    @mock.patch("checkmate.workflow.add_subworkflow")
    def test_should_retry_a_failed_task(self, mock_add_subwf, mock_create_wf,
                                        mock_async_result, mock_get_subwf):
        mock_context = mock.Mock()
        mock_workflow = mock.Mock()
        mock_driver = mock.Mock()

        mock_failed_task = mock_workflow.get_task("task_id")

        mock_task_spec = mock_failed_task.task_spec
        mock_task_spec.get_property.return_value = 1

        mock_get_subwf.return_value = 1001
        mock_async_result.return_value = True

        mock_reset_wf = mock.Mock()
        mock_reset_wf.get_attribute.return_value = "1111"

        mock_workflow.get_attribute.return_value = "DEP_ID"
        mock_create_wf.return_value = mock_reset_wf

        mock_set_property = mock_task_spec.set_property

        handler = exception_handlers.ResetTaskTreeExceptionHandler(
            mock_workflow, "task_id", mock_context, mock_driver)
        reset_wf = handler.handle()

        self.assertEqual("1111", reset_wf)
        mock_task_spec.get_property.assert_called_with(
            "task_retry_count", default=0)
        mock_get_subwf.assert_called_with(mock_workflow, "task_id")
        self.assertTrue(mock_async_result.called)
        mock_workflow.get_attribute.assert_called_with("deploymentId")
        mock_create_wf.assert_called_with(mock_workflow, "DEP_ID",
                                          mock_context,
                                          mock_failed_task,
                                          driver=mock_driver)
        mock_reset_wf.get_attribute.assert_called_with("id")
        mock_add_subwf.assert_called_with(mock_workflow, "1111", "task_id")
        mock_set_property.assert_called_with(task_retry_count=2)

    def test_max_retries_limit(self):
        mock_workflow = mock.Mock()

        mock_workflow.get_task(
            "task_id").task_spec.get_property.return_value = (
                exception_handlers.ResetTaskTreeExceptionHandler
                .MAX_RETRIES_FOR_TASK + 1)
        mock_workflow.get_attribute.return_value = 1

        handler = exception_handlers.ResetTaskTreeExceptionHandler(
            mock_workflow, "task_id", None, None)
        handler.handle()
        mock_workflow.get_task(
            "task_id").task_spec.get_property.assert_called_with(
                "task_retry_count", default=0)
        mock_workflow.get_attribute.assert_called_with('id')

    @mock.patch("checkmate.workflow.get_subworkflow")
    @mock.patch.object(AsyncResult, 'ready')
    def test_running_workflow_status_validation(self,
                                                mock_async_result,
                                                mock_get_wf):
        mock_workflow = mock.Mock()

        mock_workflow.get_task(
            "task_id").task_spec.get_property.return_value = 1

        mock_get_wf.return_value = 1000
        mock_async_result.return_value = False
        mock_workflow.get_attribute.return_value = 1

        handler = exception_handlers.ResetTaskTreeExceptionHandler(
            mock_workflow, "task_id", None, None)
        handler.handle()
        mock_workflow.get_task(
            "task_id").task_spec.get_property.assert_called_with(
                "task_retry_count", default=0)
        mock_workflow.get_attribute.assert_called_with('id')
        self.assertTrue(mock_async_result.called)
