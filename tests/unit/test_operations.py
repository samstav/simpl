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
import mock
import unittest

#from SpiffWorkflow import specs
#from SpiffWorkflow import Workflow

from checkmate import operations


class TestOperations(unittest.TestCase):
    @mock.patch.object(operations, 'SIMULATOR_DB')
    @mock.patch.object(operations.utils, 'is_simulation', return_value=True)
    def test_get_db_driver_returns_simulation_driver(self, mock_is_sim, mock_db):
        result = operations._get_db_driver('simulation')
        mock_is_sim.assert_called_once_with('simulation')
        self.assertEqual(mock_db, result)

    @mock.patch.object(operations, 'DB')
    @mock.patch.object(operations.utils, 'is_simulation', return_value=False)
    def test_get_db_driver_returns_db_driver(self, mock_is_sim, mock_db):
        result = operations._get_db_driver('simulation')
        mock_is_sim.assert_called_once_with('simulation')
        self.assertEqual(mock_db, result)

    @mock.patch.object(operations.SpiffWorkflow, 'deserialize')
    @mock.patch.object(operations, 'add')
    @mock.patch.object(operations, '_get_db_driver')
    def test_operations_create(self, mock_get_db, mock_add, mock_deserialize):
        mock_get_db.return_value = mock_db = mock.Mock()

        operations._create('depid', 'wfid', 'test', '123456')

        mock_get_db.assert_called_once_with('depid')
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
    def test_add_operation_called_successfully(self, mock_init, mock_add):
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
        self.assertEqual(['new-op', 'old-op'], deployment['operations-history'])

    def test_no_operation_in_deployment(self):
        deployment = {}
        operations.add_operation(deployment, 'op_type')
        self.assertEqual(None, deployment.get('operations-history'))

    def test_passed_in_kwarg_added_to_operation(self):
        deployment = {}
        result = operations.add_operation(deployment, 'op_type', op_kwarg='op_stuff')
        self.assertEqual('op_stuff', result['op_kwarg'])

class TestOperationsUpdateOperation(unittest.TestCase):
    @mock.patch.object(operations, '_get_db_driver')
    def test_do_nothing_if_no_kwargs(self, mock_get_db):
        operations.update_operation('depid', 'wfid', driver='Mock')
        assert not mock_get_db.called

    @mock.patch.object(operations, '_get_db_driver')
    def test_db_driver_passed_in(self, mock_get_db):
        mock_db = mock.Mock()
        mock_db.get_deployment.return_value = {}
        operations.update_operation('depid', 'wfid', driver=mock_db,
                                    test_kwarg='test')
        assert not mock_get_db.called
        mock_db.get_deployment.assert_called_once_with('depid',
                                                       with_secrets=True)

    @mock.patch.object(operations, 'DB')
    def test_db_driver_not_passed_in(self, mock_db):
        operations.update_operation('depid', 'wfid', test_kwarg='test')
        mock_db.get_deployment.assert_called_once_with('depid',
                                                       with_secrets=True)

    @mock.patch.object(operations.LOG, 'warn')
    @mock.patch.object(operations, 'DB')
    def test_no_operation_found(self, mock_db, mock_log):
        mock_db.get_deployment.return_value = {}
        operations.update_operation('depid', 'wfid', test_kwarg='test')
        mock_log.assert_called_once_with(
            'Cannot find operation with workflow id %s in deployment %s',
            'wfid',
            'depid'
        )

    #@mock.patch.object(operations, 'DB')
    #def test_first_operation_value_is_a_list(self, mock_db):
    #    mock_db.get_deployment.return_value = {'operation': [[]]}
    #    operations.update_operation('depid', 'wfid', test_kwarg='test')


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
