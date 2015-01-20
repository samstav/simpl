# pylint: disable=R0201,C0111,C0103,R0904,W0212
#
# Copyright (c) 2011-2015 Rackspace US, Inc.
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

from checkmate import exceptions
from checkmate.workflows.exception_handlers import automatic_reset_and_retry


class TestAutoResetExceptionHandlers(unittest.TestCase):

    __handler_class__ = automatic_reset_and_retry.AutomaticResetAndRetryHandler

    def test_can_handle_positive(self):
        exception = exceptions.CheckmateException(options=exceptions.CAN_RESET)
        mock_failed_task = mock.Mock()
        mock_failed_task.task_spec.get_property.return_value = 2
        self.assertTrue(self.__handler_class__.can_handle(mock_failed_task,
                                                          exception))

    def test_can_handle_negative(self):
        exception = exceptions.CheckmateException(options=exceptions.CAN_RESET)
        mock_failed_task = mock.Mock()
        mock_failed_task.task_spec.get_property.return_value = None
        self.assertFalse(self.__handler_class__.can_handle(mock_failed_task,
                                                           exception))

    def test_friendly_message(self):
        exception = exceptions.CheckmateException(options=exceptions.CAN_RESET)
        mock_failed_task = mock.Mock()
        mock_failed_task.task_spec.get_property.return_value = 1
        handler = self.__handler_class__(None, mock_failed_task, None, None)
        self.assertEqual(handler.friendly_message(exception),
                         "Retrying a failed task (1 attempts remaining)")

    def test_friendly_message_no_retry(self):
        exception = exceptions.CheckmateException(options=exceptions.CAN_RESET)
        mock_failed_task = mock.Mock()
        mock_failed_task.task_spec.get_property.return_value = None
        handler = self.__handler_class__(None, mock_failed_task, None, None)
        self.assertEqual(handler.friendly_message(exception),
                         "Retrying a failed task (No attempts remaining)")


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
