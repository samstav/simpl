# pylint: disable=R0201,C0111,C0103,R0904,W0212
#
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
"""Tests for workflows/exception_handlers/automatic_reset_and_retry.py"""
import unittest

import mock

from checkmate import task
from checkmate.workflows import exception_handlers as cmexch
from checkmate.workflows.exception_handlers import automatic_reset_and_retry


class TestAutoResetExceptionHandlers(unittest.TestCase):

    @mock.patch.object(cmexch, 'HANDLERS')
    def test_select_handler(self, mock_handlers):
        handlers = [cmexch.AutomaticResetAndRetryHandler]
        mock_handlers.__iter__.return_value = handlers.__iter__()
        task_state = {
            "info": "CheckmateException('','', 4)",
        }
        mock_wf = mock.Mock()
        mock_context = mock.Mock()
        mock_driver = mock.Mock()

        mock_wf.get_task(100)._get_internal_attribute.return_value = task_state
        mock_wf.get_task(100).task_spec.get_property.return_value = 3
        handlers = cmexch.get_handlers(mock_wf, [100], mock_context,
                                       mock_driver)
        self.assertEquals(1, len(handlers))
        self.assertIsInstance(handlers[0],
                              cmexch.AutomaticResetAndRetryHandler)

    @mock.patch.object(automatic_reset_and_retry, 'AsyncResult')
    @mock.patch.object(automatic_reset_and_retry, 'workflow')
    @mock.patch.object(task, 'set_exception')
    def test_retries_with_message(self, mock_set, mock_workflow, mock_async):
        """Will retry if retries available (and publishes a clear message)."""
        task_state = {
            "info": "CheckmateException('BigUglyError()', 'Oops, Sorry!', 4)",
        }
        retry_count = 2

        mock_task = mock.Mock()
        mock_task.id = 100
        mock_task._get_internal_attribute.return_value = task_state
        mock_task.task_spec.get_property.return_value = retry_count

        mock_wf = mock.Mock()
        mock_wf.attributes = {}
        mock_wf.get_task.return_value = mock_task

        handler = cmexch.AutomaticResetAndRetryHandler(mock_wf, mock_task,
                                                       None, None)

        handler.handle()

        # Correct message to client
        mock_set.assert_has_calls((mock.ANY, mock.ANY))
        exception = mock_set.call_args[0][0]
        self.assertEqual(str(exception),
                         "Retrying a failed task (2 attempts remaining)")

        # Decrement retry count
        mock_wf.get_task(100).task_spec.get_property.\
            assert_called_with("auto_retry_count", 0)
        mock_wf.get_task(100).task_spec.set_property.\
            assert_called_with(auto_retry_count=retry_count-1)

    @mock.patch.object(automatic_reset_and_retry, 'AsyncResult')
    @mock.patch.object(automatic_reset_and_retry, 'workflow')
    @mock.patch.object(task, 'set_exception')
    def test_max_retries_uses_friendly_message(self, mock_set, mock_workflow,
                                               mock_async):
        """Maximum retries reached publishes a clear message."""
        task_state = {
            "info": "CheckmateException('BigUglyError()', 'Oops, Sorry!', 4)",
        }

        mock_task = mock.Mock()
        mock_task.id = 100
        mock_task._get_internal_attribute.return_value = task_state
        mock_task.task_spec.get_property.return_value = 0

        mock_wf = mock.Mock()
        mock_wf.attributes = {}
        mock_wf.get_task.return_value = mock_task

        handler = cmexch.AutomaticResetAndRetryHandler(mock_wf, mock_task,
                                                       None, None)

        handler.handle()

        # Correct message to client
        mock_set.assert_has_calls((mock.ANY, mock.ANY))
        exception = mock_set.call_args[0][0]
        self.assertEqual(str(exception),
                         "Oops, Sorry! (Maximum retries reached)")

        # Confirm not retried (we're out of retries)
        self.assertEqual(mock_wf.add_subworkflow.call_count, 0)


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
