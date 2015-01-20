# pylint: disable=C0103,R0904,W0201

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

"""Tests for Workflows Manager."""
import mock
import unittest

from checkmate import workflows


class TestManager(unittest.TestCase):
    @mock.patch('checkmate.db.get_lock_db_driver')
    def test_workflow_lock(self, mock_driver):
        mock_lock = mock_driver().lock
        manager = workflows.Manager()
        manager.workflow_lock("WF_ID")
        mock_lock.assert_called_with("async_wf_writer:WF_ID", 5)
