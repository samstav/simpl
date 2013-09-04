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

from checkmate import deployment as cmdep
from checkmate import exceptions as cmexc
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

    @mock.patch.object(operations, 'get_operation', side_effect=cmexc.CheckmateInvalidParameterError)
    @mock.patch.object(operations, 'DB')
    def test_no_operation_found(self, mock_db, mock_getop):
        mock_db.get_deployment.return_value = {}
        operations.update_operation('depid', 'wfid', test_kwarg='test')
        mock_getop.assert_called_once_with(mock.ANY, 'wfid')

    def test_status_complete_nothing_to_do(self):
        pass

class TestOperationsCurrentWorkflowIdAndGetOperation(unittest.TestCase):
    def setUp(self):
        deployment_dict = {
            'id': 'test',
            'name': 'test',
            'resources': {
                '0': {'provider': 'test'},
                '1': {'status': 'DELETED'},
                '2': {'status': 'ACTIVE'}
            },
            'status': 'NEW',
            'operation': {
                'status': 'NEW',
            },
            'plan': {
                'services': {
                    'web': {
                        'component': {
                            'instances': ["1", "2"]
                        }
                    }
                }
            }
        }
        self.deployment = cmdep.Deployment(deployment_dict)
        self.deployment.environment = mock.Mock()
        self.context = mock.MagicMock()
        environment = mock.Mock()
        self.provider = mock.Mock()
        self.deployment.environment.return_value = environment
        environment.get_provider.return_value = self.provider

    def test_get_workflow_id_when_w_id_not_in_operation(self):
        workflow_id = operations.current_workflow_id(self.deployment)
        self.assertEqual(workflow_id, self.deployment['id'])

    def test_get_workflow_id_when_w_id_in_operation(self):
        self.deployment['operation']['workflow-id'] = 'w_id'
        workflow_id = operations.current_workflow_id(self.deployment)
        self.assertEqual(workflow_id, 'w_id')

    def test_get_operation_invalid_id_and_no_history(self):
        with self.assertRaises(
                cmexc.CheckmateInvalidParameterError) as expected:
            operations.get_operation(self.deployment, 'bad-id')
        self.assertEqual('Invalid workflow ID.', str(expected.exception))

    def test_get_operation_invalid_id_with_history(self):
        self.deployment['operations-history'] = [{'status': 'PAUSED',
                                                 'workflow-id': 'w_id'}]
        with self.assertRaises(
                cmexc.CheckmateInvalidParameterError) as expected:
            operations.get_operation(self.deployment, 'foobar_w_id')

        self.assertEqual('Invalid workflow ID.', str(expected.exception))

    def test_get_operation_from_current_operation(self):
        self.assertEqual(('operation', -1, {'status': 'NEW'}),
                         operations.get_operation(self.deployment, "test"))

    def test_get_operation_from_history(self):
        self.deployment['operations-history'] = [{'status': 'PAUSED',
                                                  'workflow-id': 'w_id'}]
        expected = ('operations-history', 0,
                    {'status': 'PAUSED', 'workflow-id': 'w_id'})
        self.assertEqual(expected, operations.get_operation(self.deployment, 'w_id'))

    def test_get_operation_from_history_with_multiples(self):
        self.deployment['operations-history'] = [{'status': 'PAUSED',
                                                  'workflow-id': 'w_id'},
                                                 {'status': 'NEW',
                                                  'workflow-id': 'w_id2'}]
        expected = ('operations-history', 1,
                    {'status': 'NEW', 'workflow-id': 'w_id2'})
        self.assertEqual(expected, operations.get_operation(self.deployment, 'w_id2'))

    def test_get_operation_old_deployment_with_no_id_in_history(self):
        self.deployment['operation'] = {}
        self.deployment['operations-history'] = [{'status': 'PAUSED'}]
        self.assertEqual(('operations-history', 0, {'status': 'PAUSED'}),
                         operations.get_operation(self.deployment, 'test'))


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
