# pylint: disable=C0103

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

"""Tests for Operations."""
import unittest

import mox
from SpiffWorkflow import specs
from SpiffWorkflow import Workflow

from checkmate import operations


class TestOperations(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_create_add_nodes(self):
        wf_spec = specs.WorkflowSpec(name="Add Nodes")
        wf_spec.start.connect(specs.Simple(wf_spec, "end"))
        wflow = Workflow(wf_spec)
        expected_operation = {"foo": "bar", 'type': "ADD_NODES"}
        deployment = {}
        self.mox.StubOutWithMock(operations, "init_operation")
        operations.init_operation(wflow, tenant_id="TENANT_ID").AndReturn(
            {"foo": "bar"})
        self.mox.ReplayAll()
        operations.add(deployment, wflow, "ADD_NODES", "TENANT_ID")
        self.assertDictEqual(deployment['operation'], expected_operation)

    def test_update_operation(self):
        mock_db = self.mox.CreateMockAnything()
        mock_db.get_deployment('1234', with_secrets=True).AndReturn({
            'id': '1234', 'operation': {
            'status': 'NEW'}})
        mock_db.save_deployment('1234', {'operation': {'status': 'NEW'}},
                                partial=True).AndReturn(None)
        self.mox.ReplayAll()
        operations.update_operation(
            '1234', '1234', status='NEW', driver=mock_db)
        self.mox.VerifyAll()

    def test_update_operation_when_operation_in_operations_history(self):
        mock_db = self.mox.CreateMockAnything()
        mock_db.get_deployment('1234', with_secrets=True).AndReturn({
            'id': '1234', 'operation': {
            'status': 'NEW'},
            'operations-history': [{'workflow-id': 'w_id', 'status': 'BUILD'}]
        })
        mock_db.save_deployment('1234', {'operations-history': [{'status':
                                                                 'PAUSE'}],
                                         'display-outputs': {}},
                                partial=True).AndReturn(None)
        self.mox.ReplayAll()
        operations.update_operation(
            '1234', 'w_id', status='PAUSE', driver=mock_db)
        self.mox.VerifyAll()

    def test_update_operation_with_deployment_status(self):
        mock_db = self.mox.CreateMockAnything()
        mock_db.get_deployment('1234', with_secrets=True).AndReturn(
            {'id': '1234', 'operation': {'status': 'NEW'}})
        mock_db.save_deployment('1234', {'operation': {'status': 'NEW'},
                                         'status': "PLANNED"},
                                partial=True).AndReturn(None)
        self.mox.ReplayAll()
        operations.update_operation('1234', '1234', status='NEW',
                                    deployment_status="PLANNED",
                                    driver=mock_db)
        self.mox.VerifyAll()

    def test_update_operation_with_operation_marked_complete(self):
        mock_db = self.mox.CreateMockAnything()
        mock_db.get_deployment('1234', with_secrets=True).AndReturn(
            {'id': '1234', 'operation': {'status': 'COMPLETE'}})
        self.mox.ReplayAll()
        operations.update_operation('1234', '1234', status='NEW',
                                    deployment_status="PLANNED",
                                    driver=mock_db)
        self.mox.VerifyAll()

    def test_add_operation(self):
        deployment = {}
        operations.add_operation(deployment, 'TEST', status='NEW')
        expected = {'operation': {'type': 'TEST', 'status': 'NEW'}}
        self.assertDictEqual(deployment, expected)

    def test_add_operation_first_history(self):
        deployment = {'operation': {'type': 'OLD', 'status': 'COMPLETE'}}
        operations.add_operation(deployment, 'TEST', status='NEW')
        expected = {
            'operation': {'type': 'TEST', 'status': 'NEW'},
            'operations-history': [
                {'type': 'OLD', 'status': 'COMPLETE'}
            ],
        }
        self.assertDictEqual(deployment, expected)

    def test_add_operation_existing_history(self):
        deployment = {
            'operation': {'type': 'RECENT', 'status': 'COMPLETE'},
            'operations-history': [
                {'type': 'OLD', 'status': 'COMPLETE'}
            ],
        }
        operations.add_operation(deployment, 'TEST', status='NEW')
        expected = {
            'operation': {'type': 'TEST', 'status': 'NEW'},
            'operations-history': [
                {'type': 'RECENT', 'status': 'COMPLETE'},  # at top
                {'type': 'OLD', 'status': 'COMPLETE'}
            ],
        }
        self.assertDictEqual(deployment, expected)

    def test_get_status_message_from_all_friendly_error_messages(self):
        errors = [
            {"friendly-message": "Message 1", "error-type": "Type 1"},
            {"friendly-message": "Message 2", "error-type": "Type 2"}
        ]
        info = operations.get_status_info(errors, "tenantId", "workflowId")
        expected = {
            "status-message": "1. Message 1\n2. Message 2\n"
        }

        self.assertDictEqual(info, expected)

    def test_generic_message_if_no_status(self):
        errors = [
            {"error-message": 'Complicated Error message'},
            {"error-message": 'Another Complicated error'},
        ]
        info = operations.get_status_info(errors, "tenantId", "workflowId")
        expected = {
            "status-message": "Multiple errors have occurred. Please contact "
                              "support"
        }
        self.assertDictEqual(info, expected)

    def test_get_status_info_when_there_are_both_frndly_non_frndly_errs(self):
        errors = [
            {"error-message": 'Complicated Error message'},
            {"error-message": 'Another Complicated error'},
            {"friendly-message": 'A friendly message'},
        ]

        info = operations.get_status_info(errors, "tenantId", "workflowId")
        expected = {
            "status-message": "Multiple errors have occurred. Please contact "
                              "support"
        }
        self.assertDictEqual(info, expected)

    def test_get_status_message_with_grouping_based_on_error_type(self):
        errors = [
            {"friendly-message": 'I am a friendly error message',
             'error-type': 'Overlimit'},
            {"friendly-message": 'I am a friendly error message',
             'error-type': 'Overlimit'},
            {"friendly-message": 'Another friendly error message',
             'error-type': 'RandomException'},
            {"friendly-message": 'I am a friendly error message',
             'error-type': 'Overlimit'},
        ]
        info = operations.get_status_info(errors, "tenantId", "workflowId")
        expected = {
            "status-message": "1. I am a friendly error message\n2. Another "
                              "friendly error message\n"
        }
        self.assertDictEqual(info, expected)

    def test_status_info_with_retriable_errors(self):
        errors = [
            {"error-type": "OverLimit", "error-message": "OverLimit Message",
             "action-required": True, "retriable": True},
            {"error-type": "OverLimit", "error-message": "OverLimit Message",
             "action-required": True},
            {"error-type": "RateLimit", "error-message": "RateLimit Message",
             "action-required": True},
            {"error-type": "RandomError", "error-message": "Random Message",
             "action-required": False},
            {"error-type": "RandomError", "error-message": "Random Message"},
        ]
        info = operations.get_status_info(errors, "tenantId", "workflowId")
        expected = {
            'status-message': "Multiple errors have occurred. Please contact "
                              "support",
            'retry-link': "/tenantId/workflows/workflowId/+retry-failed-tasks",
            'retriable': True
        }
        self.assertDictEqual(info, expected)

    def test_status_info_with_resumable_errors(self):
        errors = [
            {"error-type": "OverLimit", "error-message": "OverLimit Message",
             "action-required": True},
            {"error-type": "SomeError", "error-message": "SomeError Message",
             "action-required": True, "resumable": True},
        ]
        info = operations.get_status_info(errors, "tenantId", "workflowId")
        expected = {
            'status-message': "Multiple errors have occurred. Please contact "
                              "support",
            'resume-link': "/tenantId/workflows/workflowId/"
                           "+resume-failed-tasks",
            'resumable': True
        }
        self.assertDictEqual(info, expected)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
