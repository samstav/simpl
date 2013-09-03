# pylint: disable=C0103,R0201,R0904,W0212

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
import mock
import unittest

#from SpiffWorkflow import specs
#from SpiffWorkflow import Workflow

from checkmate import exceptions as cmexc
from checkmate import operations


class TestOperations(unittest.TestCase):
    @mock.patch.object(operations.SpiffWorkflow, 'deserialize')
    @mock.patch.object(operations, 'add')
    @mock.patch('checkmate.operations.db.get_driver')
    def test_operations_create(self, mock_get_db, mock_add, mock_deserialize):
        mock_get_db.return_value = mock_db = mock.Mock()

        operations._create('depid', 'wfid', 'test', '123456')

        mock_get_db.assert_called_once_with(api_id='depid')
        mock_db.get_deployment.assert_called_once_with('depid',
                                                       with_secrets=False)
        mock_db.get_workflow.assert_called_once_with('wfid',
                                                     with_secrets=False)
        mock_deserialize.assert_called_once_with(mock.ANY, mock.ANY)
        mock_add.assert_called_once_with(mock.ANY, mock.ANY, 'test',
                                         tenant_id='123456')
        mock_db.save_deployment.assert_called_once_with('depid',
                                                        mock.ANY,
                                                        secrets=None,
                                                        tenant_id='123456',
                                                        partial=False)

    @mock.patch.object(operations, 'add_operation')
    @mock.patch.object(operations, 'init_operation')
    def test_add_called_successfully(self, mock_init, mock_add):
        mock_init.return_value = {'data': 'item'}
        operations.add('deployment', 'spiff_wf', 'op_type')
        mock_init.assert_called_once_with('spiff_wf', tenant_id=None)
        mock_add.assert_called_once_with('deployment', 'op_type', data='item')


class TestOperationsAddOperation(unittest.TestCase):
    def test_op_type_is_added_to_operation(self):
        deployment = {}
        result = operations.add_operation(deployment, 'op_type')
        self.assertEqual({'type': 'op_type'}, result)

    def test_no_previous_operations_history(self):
        """Test the deployment gets an operations history."""
        deployment = {'operation': 'new-op'}
        operations.add_operation(deployment, 'op_type')
        self.assertEqual(['new-op'], deployment.get('operations-history'))

    def test_with_previous_operations_history(self):
        """Test the deployment's operations history is updated."""
        deployment = {'operation': 'new-op', 'operations-history': ['old-op']}
        operations.add_operation(deployment, 'op_type')
        self.assertEqual(
            ['new-op', 'old-op'], deployment['operations-history'])

    def test_no_operation_in_deployment(self):
        deployment = {}
        operations.add_operation(deployment, 'op_type')
        self.assertEqual(None, deployment.get('operations-history'))

    def test_passed_in_kwarg_added_to_operation(self):
        deployment = {}
        result = operations.add_operation(
            deployment, 'op_type', op_kwarg='op_stuff')
        self.assertEqual('op_stuff', result['op_kwarg'])


class TestOperationsUpdateOperation(unittest.TestCase):
    @mock.patch('checkmate.operations.db.get_driver')
    def test_do_nothing_if_no_kwargs(self, mock_get_db):
        operations.update_operation('depid', 'wfid', driver='Mock')
        assert not mock_get_db.called

    @mock.patch('checkmate.operations.db.get_driver')
    def test_db_driver_passed_in(self, mock_get_db):
        mock_get_db.return_value = mock_db = mock.Mock()
        mock_db.get_deployment.return_value = {}
        operations.update_operation('depid', 'wfid', driver=mock_db,
                                    test_kwarg='test')
        assert not mock_get_db.called
        mock_db.get_deployment.assert_called_once_with('depid',
                                                       with_secrets=True)

    @mock.patch('checkmate.operations.db.get_driver')
    def test_db_driver_not_passed_in(self, mock_get_driver):
        mock_get_driver.return_value = mock_db = mock.Mock()
        mock_db.get_deployment.return_value = {}
        operations.update_operation('depid', 'wfid', test_kwarg='test')
        mock_db.get_deployment.assert_called_once_with('depid',
                                                       with_secrets=True)

    @mock.patch.object(operations, 'get_operation',
                       side_effect=cmexc.CheckmateInvalidParameterError)
    @mock.patch('checkmate.operations.db.get_driver')
    def test_no_operation_found(self, mock_get_driver, mock_getop):
        mock_get_driver.return_value = mock_db = mock.Mock()
        mock_db.get_deployment.return_value = {}
        operations.update_operation('depid', 'wfid', test_kwarg='test')
        mock_getop.assert_called_once_with(mock.ANY, 'wfid')
        assert not mock_db.save_deployment.called

    @mock.patch.object(operations.LOG, 'warn')
    @mock.patch.object(operations, 'get_operation')
    @mock.patch('checkmate.operations.db.get_driver')
    def test_status_complete_nothing_to_do(self, mock_get_driver, mock_getop,
                                           mock_logger):
        mock_get_driver.return_value = mock_db = mock.Mock()
        mock_db.get_deployment.return_value = {}
        mock_getop.return_value = ('operation', -1, {'status': 'COMPLETE'})
        operations.update_operation('depid', 'wfid', test_kwarg='test')
        mock_logger.assert_called_once_with("Ignoring the update operation "
                                            "call as the operation is already "
                                            "COMPLETE")

    @mock.patch.object(operations, 'get_operation')
    @mock.patch('checkmate.operations.db.get_driver')
    def test_curr_operation_from_operation(self, mock_get_driver, mock_getop):
        mock_get_driver.return_value = mock_db = mock.Mock()
        mock_db.get_deployment.return_value = {}
        mock_getop.return_value = ('operation', -1, {'status': 'BUILD'})
        operations.update_operation('depid', 'wfid', test_kwarg='test')
        mock_db.save_deployment.assert_called_once_with(
            'depid', {'operation': {'test_kwarg': 'test'}}, partial=True)

    @mock.patch.object(operations, 'get_operation')
    @mock.patch('checkmate.operations.db.get_driver')
    def test_curr_operation_from_history(self, mock_get_driver, mock_getop):
        mock_get_driver.return_value = mock_db = mock.Mock()
        mock_db.get_deployment.return_value = {}
        mock_getop.return_value = (
            'operations-history', 0, {'status': 'BUILD'})
        operations.update_operation('depid', 'wfid', test_kwarg='test')
        mock_db.save_deployment.assert_called_once_with(
            'depid',
            {'operations-history': [{'test_kwarg': 'test'}]},
            partial=True
        )

    @mock.patch('checkmate.operations.db.get_driver')
    def test_update_operation(self, mock_get_driver):
        mock_db = mock.Mock()

        mock_db.get_deployment.return_value = {
            'id': '1234', 'operation': {'status': 'NEW'}
        }
        mock_db.save_deployment.return_value = None
        mock_get_driver.return_value = mock_db
        operations.update_operation('1234', '1234', status='NEW',
                                    driver=mock_db)
        mock_db.get_deployment.assert_called_with('1234', with_secrets=True)
        mock_db.save_deployment.assert_called_with(
            '1234',
            {'operation': {'status': 'NEW'}},
            partial=True
        )

    @mock.patch.object(operations, 'get_operation')
    @mock.patch('checkmate.operations.db.get_driver')
    def test_include_deployment_status(self, mock_get_driver, mock_getop):
        mock_get_driver.return_value = mock_db = mock.Mock()
        mock_db.get_deployment.return_value = {}
        mock_getop.return_value = ('operation', -1, {'status': 'BUILD'})
        operations.update_operation('depid', 'wfid',
                                    deployment_status='test_status',
                                    test_kwarg='test')
        mock_db.save_deployment.assert_called_once_with(
            'depid',
            {'operation': {'test_kwarg': 'test'}, 'status': 'test_status'},
            partial=True
        )

    @mock.patch.object(operations, 'get_operation')
    @mock.patch('checkmate.operations.db.get_driver')
    def test_op_status_matches_kwarg_status(self, mock_get_driver, mock_getop):
        mock_get_driver.return_value = mock_db = mock.Mock()
        mock_db.get_deployment.return_value = {}
        mock_getop.return_value = ('operation', -1, {'status': 'BUILD'})
        operations.update_operation('depid', 'wfid',
                                    status='BUILD')
        mock_db.save_deployment.assert_called_once_with(
            'depid', {'operation': {'status': 'BUILD'}}, partial=True)

    @mock.patch.object(operations, 'get_operation')
    @mock.patch('checkmate.operations.db.get_driver')
    def test_op_status_does_not_match_kwarg_status(self,
                                                   mock_get_driver,
                                                   mock_getop):
        mock_get_driver.return_value = mock_db = mock.Mock()
        mock_db.get_deployment.return_value = {}
        mock_getop.return_value = ('operation', -1, {'status': 'UP'})
        operations.update_operation('depid', 'wfid',
                                    status='BUILD')
        mock_db.save_deployment.assert_called_once_with(
            'depid',
            {'operation': {'status': 'BUILD'}, 'display-outputs': {}},
            partial=True
        )

    @mock.patch.object(operations, 'cmdep')
    @mock.patch.object(operations.LOG, 'warn')
    @mock.patch.object(operations, 'get_operation')
    @mock.patch('checkmate.operations.db.get_driver')
    def test_calculate_outputs_throws_key_error(self, mock_get_driver,
                                                mock_getop,
                                                mock_logger,
                                                mock_cmdep):
        mock_get_driver.return_value = mock_db = mock.Mock()
        mock_db.get_deployment.return_value = {}
        mock_dep = mock.Mock()
        mock_dep.calculate_outputs.side_effect = KeyError
        mock_cmdep.Deployment.return_value = mock_dep
        mock_getop.return_value = ('operation', -1, {'status': 'UP'})
        operations.update_operation('depid', 'wfid',
                                    status='BUILD')
        mock_db.save_deployment.assert_called_once_with(
            'depid',
            {'operation': {'status': 'BUILD'}},
            partial=True
        )
        mock_logger.assert_called_once_with(
            'Cannot update deployment outputs: %s', 'depid')


class TestOperationsCurrentWorkflowId(unittest.TestCase):
    def test_no_operation_in_deployment(self):
        self.assertEqual(None, operations.current_workflow_id({}))

    def test_no_workflow_id_no_dep_id(self):
        deployment = {'operation': {'blah': 'blah'}}
        self.assertEqual(None, operations.current_workflow_id(deployment))

    def test_no_workflow_id_defaults_to_dep_id(self):
        deployment = {'operation': {'blah': 'blah'}, 'id': 'depid'}
        self.assertEqual('depid', operations.current_workflow_id(deployment))

    def test_prefer_workflow_id_over_dep_id(self):
        deployment = {'operation': {'workflow-id': 'wfid'}, 'id': 'depid'}
        self.assertEqual('wfid', operations.current_workflow_id(deployment))


class TestOperationsGetOperation(unittest.TestCase):
    def test_get_operation_finds_nothing(self):
        with self.assertRaises(
                cmexc.CheckmateInvalidParameterError) as expected:
            operations.get_operation({'operation': {}}, 'wfid')
        self.assertEqual('Invalid workflow ID.', str(expected.exception))

    def test_wf_id_is_current_operation(self):
        result = operations.get_operation(
            {'operation': {'workflow-id': 'wfid'}}, 'wfid')
        self.assertEqual(('operation', -1, {'workflow-id': 'wfid'}), result)

    def test_wf_id_is_the_only_one_in_history(self):
        result = operations.get_operation(
            {'operations-history': [{'workflow-id': 'wfid'}]}, 'wfid')
        self.assertEqual(
            ('operations-history', 0, {'workflow-id': 'wfid'}), result)

    def test_wf_id_is_one_of_many_in_history(self):
        result = operations.get_operation(
            {'operations-history':
                [{'workflow-id': 'nothere'},
                 {'workflow-id': 'nope'},
                 {'workflow-id': 'wfid'},
                 {'workflow-id': 'nothisoneeither'}]},
            'wfid'
        )
        self.assertEqual(
            ('operations-history', 2, {'workflow-id': 'wfid'}), result)

    def test_wf_in_history_but_id_in_deployment(self):
        result = operations.get_operation(
            {'operations-history': [{'blah': 'blah'}], 'id': 'wfid'}, 'wfid')
        self.assertEqual(('operations-history', 0, {'blah': 'blah'}), result)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
