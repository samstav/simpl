# pylint: disable=W0212
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
# pylint: disable=R0903

"""Task module Tests - for Task class helper methods."""

import mock
import unittest

from checkmate.exceptions import CheckmateException
from checkmate import task as cmtsk


class TestTask(unittest.TestCase):
    """Tests for Tasks helper methods."""
    def test_is_failed_task(self):
        task_with_error = mock.MagicMock(
            _get_internal_attribute=mock.MagicMock())
        task_without_error = mock.MagicMock(
            _get_internal_attribute=mock.MagicMock())

        task_with_error._get_internal_attribute.return_value = {
            "info": "Error Information",
            "state": "FAILURE",
            "traceback": "Traceback"}

        task_without_error._get_internal_attribute.return_value = {}

        self.assertTrue(cmtsk.is_failed(task_with_error))
        self.assertFalse(cmtsk.is_failed(task_without_error))

    def test_get_exception_on_task(self):
        task = mock.MagicMock()
        task._get_internal_attribute = mock.MagicMock()
        task._get_internal_attribute.return_value = {
            "info": "CheckmateException('', 'Server build failed')"
        }
        exception = cmtsk.get_exception(task)
        task._get_internal_attribute.assert_called_once_with("task_state")
        self.assertTrue(isinstance(exception, CheckmateException))

    def test_set_exception_on_task(self):
        task = mock.MagicMock()
        task._get_internal_attribute = mock.MagicMock()
        task._get_internal_attribute.return_value = {
            "info": "CheckmateException('','')"
        }
        new_exception = Exception("This replaces the old exception")
        cmtsk.set_exception(new_exception, task)
        exception = cmtsk.get_exception(task)
        task._get_internal_attribute.assert_called_with("task_state")
        self.assertTrue(isinstance(exception, Exception))
