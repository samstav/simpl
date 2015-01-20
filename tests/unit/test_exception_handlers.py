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
"""Test for workflows/exception_handlers.py"""
import unittest

import mock

from checkmate.workflows import exception_handlers as cmexch
from checkmate.workflows.exception_handlers import base


class PositiveHandler(base.ExceptionHandlerBase):
    """Always reports itself as capable of handing a task."""
    @staticmethod
    def can_handle(failed_task, exception):
        return True


class NegativeHandler(base.ExceptionHandlerBase):
    """Does not report itself as capable of handing anything."""
    @staticmethod
    def can_handle(failed_task, exception):
        return False


class TestExceptionHandlersBase(unittest.TestCase):

    def test_no_handlers(self):
        task_state = {
            "info": "CheckmateException('','')",
        }
        mock_wf = mock.Mock()
        mock_context = mock.Mock()
        mock_driver = mock.Mock()

        mock_wf.get_task(100)._get_internal_attribute\
            .return_value = task_state
        mock_wf.get_task(100).task_spec.get_property.return_value = None
        handlers = cmexch.get_handlers(mock_wf, [100], mock_context,
                                       mock_driver)
        self.assertEqual(0, len(handlers))

    @mock.patch.object(cmexch, 'HANDLERS')
    def test_select_handlers(self, mock_handlers):
        handlers = [PositiveHandler, NegativeHandler]
        mock_handlers.__iter__.return_value = handlers.__iter__()
        task_state = {
            "info": "CheckmateException('','')",
        }
        mock_wf = mock.Mock()
        mock_context = mock.Mock()
        mock_driver = mock.Mock()

        mock_wf.get_task(100)._get_internal_attribute\
            .return_value = task_state
        mock_wf.get_task(100).task_spec.get_property.return_value = None
        handlers = cmexch.get_handlers(mock_wf, [100], mock_context,
                                       mock_driver)
        self.assertEqual(1, len(handlers))
        self.assertIsInstance(handlers[0], PositiveHandler)


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
