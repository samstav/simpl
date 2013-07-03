# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''

import unittest

import mox

from checkmate import operations


class TestOperations(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_update_operation(self):
        db = self.mox.CreateMockAnything()
        db.get_deployment('1234', with_secrets=True).AndReturn({'operation': {
            'status': 'NEW'}})
        db.save_deployment('1234', {'operation': {'status': 'NEW'}},
                           partial=True).AndReturn(None)
        self.mox.ReplayAll()
        operations.update_operation('1234', status='NEW', driver=db)
        self.mox.VerifyAll()

    def test_update_operation_with_deployment_status(self):
        db = self.mox.CreateMockAnything()
        db.get_deployment('1234', with_secrets=True).AndReturn({'operation': {
            'status': 'NEW'}})
        db.save_deployment('1234', {'operation': {'status': 'NEW'},
                                    'status': "PLANNED"},
                           partial=True).AndReturn(None)
        self.mox.ReplayAll()
        operations.update_operation('1234', status='NEW',
                                    deployment_status="PLANNED", driver=db)
        self.mox.VerifyAll()

    def test_update_operation_with_operation_marked_complete(self):
        db = self.mox.CreateMockAnything()
        db.get_deployment('1234', with_secrets=True).AndReturn({'operation': {
            'status': 'COMPLETE'}})
        self.mox.ReplayAll()
        operations.update_operation('1234', status='NEW',
                                    deployment_status="PLANNED", driver=db)
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
            'status-message': "1. OverLimit Message\n2. RateLimit Message\n",
            'retry-link': "/tenantId/workflows/workflowId/+retry-failed-tasks",
            'retriable': True
        }
        self.assertDictEqual(info, expected)

    def test_status_info_with_no_retriable_and_resumable_errors(self):
        errors = [
            {"error-type": "OverLimit", "error-message": "OverLimit Message",
             "action-required": True},
            {"error-type": "OverLimit", "error-message": "OverLimit Message",
             "action-required": True},
            {"error-type": "RateLimit", "error-message": "RateLimit Message",
             "action-required": True},
        ]
        info = operations.get_status_info(errors, "tenantId", "workflowId")
        expected = {
            'status-message': "1. OverLimit Message\n2. RateLimit Message\n",
        }
        self.assertDictEqual(info, expected)

    def test_status_info_with_resumable_errors(self):
        errors = [
            {"error-type": "OverLimit", "error-message": "OverLimit Message",
             "action-required": True,},
            {"error-type": "SomeError", "error-message": "SomeError Message",
             "action-required": True, "resumable": True},
        ]
        info = operations.get_status_info(errors, "tenantId", "workflowId")
        expected = {
            'status-message': "1. OverLimit Message\n2. SomeError Message\n",
            'resume-link': "/tenantId/workflows/workflowId/"
                           "+resume-failed-tasks",
            'resumable': True
        }
        self.assertDictEqual(info, expected)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
