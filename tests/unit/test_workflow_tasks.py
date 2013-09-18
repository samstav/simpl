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

"""Tests for Workflow Tasks."""
import mock
import unittest

from SpiffWorkflow import specs
from SpiffWorkflow import Workflow

from checkmate.common import tasks as cmtasks
from checkmate.workflows import tasks


class TestWorkflowTasks(unittest.TestCase):
    @mock.patch('checkmate.workflow.update_workflow')
    @mock.patch('checkmate.workflows.tasks.revoke_task')
    @mock.patch('checkmate.workflow.find_tasks')
    @mock.patch.object(Workflow, 'deserialize')
    @mock.patch.object(cmtasks.update_operation, 'delay')
    @mock.patch('checkmate.db.get_driver')
    def test_pause_workflow_for_delete_operation(self, mock_driver,
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
            'operations-history': [
                {
                    'workflow-id': build_wf_id,
                    'type': 'BUILD',
                    'action': 'PAUSE',
                }
            ],
            'operation': {
                'type': 'DELETE',
            },
        }
        mock_task = mock.Mock()
        mock_task.task_spec = specs.Celery(specs.WorkflowSpec(), "name",
                                           "call")
        mock_task._get_internal_attribute.side_effect = [
            {"state": "WAITING"}, "task_id"
        ]
        driver.get_workflow.return_value = build_workflow
        driver.get_deployment.return_value = deployment
        mock_find_tasks.return_value = [mock_task]
        self.assertTrue(tasks.pause_workflow.run(build_wf_id))
        mock_revoke.delay.assert_called_with('ct_id')
        mock_revoke.assert_called_with('task_id', terminate=True)
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
