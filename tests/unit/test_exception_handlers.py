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
# pylint: disable=R0201,C0111,C0103,R0904

import mock
import unittest

from checkmate.workflows import exception_handlers as cmexch


class TestExceptionHandlers(unittest.TestCase):

    def test_get_handlers(self):
        task_state = {
            "info": "CheckmateRetriableException('','','','')",
        }
        mock_wf = mock.Mock()
        mock_context = mock.Mock()
        mock_driver = mock.Mock()

        mock_wf.get_task(1001)._get_internal_attribute\
            .return_value = \
            task_state
        mock_wf.get_task(1001).task_spec.get_property.return_value = 3
        handlers = cmexch.get_handlers(mock_wf, [1001], mock_context,
                                       mock_driver)
        self.assertIsInstance(handlers[0],
                              cmexch.AutomaticResetAndRetryHandler)
        mock_wf.get_task(1001).task_spec.get_property.\
            assert_called_with("auto_retry_count")

    def test_should_not_get_handler_when_property_is_not_set(self):
        task_state = {
            "info": "CheckmateRetriableException('','','','')",
        }
        mock_wf = mock.Mock()
        mock_context = mock.Mock()
        mock_driver = mock.Mock()

        mock_wf.get_task(1001)._get_internal_attribute\
            .return_value = \
            task_state
        mock_wf.get_task(1001).task_spec.get_property.return_value = None
        handlers = cmexch.get_handlers(mock_wf, [1001], mock_context,
                                       mock_driver)
        self.assertEquals(0, len(handlers))
        mock_wf.get_task(1001).task_spec.get_property.\
            assert_called_with("auto_retry_count")
