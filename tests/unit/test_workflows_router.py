# pylint: disable=C0103,E1101,R0904,W0201,W0212

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

"""Tests for Deployments Router."""
import mock
import unittest

import bottle
import webtest

from checkmate import workflows
from checkmate import test


class TestWorkflowsRouter(unittest.TestCase):
    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.app = webtest.TestApp(self.filters)

        self.manager = mock.Mock()
        self.deployments_manager = mock.Mock()
        self.router = workflows.Router(self.root_app, self.manager,
                                       self.deployments_manager)

    @mock.patch.object(workflows.router, 'cycle_workflow')
    def test_execute_workflow_for_already_executing_workflow(self,
                                                             cycle_workflow):
        self.manager.get_workflow.return_value = {'celery_task_id': 'task_id'}
        mock_async_result = cycle_workflow.AsyncResult.return_value
        mock_async_result.ready.return_value = False
        res = self.app.post("/T1000/workflows/W_ID/+execute",
                            content_type='application/json',
                            expect_errors=True)
        self.assertEqual(res.status, '406 Not Acceptable')

    @mock.patch.object(workflows.router, 'cycle_workflow')
    def test_execute_workflow_for_new_workflow(self, cycle_workflow):
        self.manager.get_workflow.return_value = {'workflow': {}}
        self.filters.context.get_queued_task_dict = mock.Mock()
        self.filters.context.get_queued_task_dict.return_value = {}

        res = self.app.post("/T1000/workflows/W_ID/+execute",
                            content_type='application/json')
        self.assertEqual(res.status, '200 OK')
        cycle_workflow.delay.assert_called_once_with("W_ID", {})
