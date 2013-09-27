# pylint: disable=C0103,R0904,W0201

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

"""Tests for Deployments Manager."""
import copy
import json
import mock
import os
import unittest

from checkmate import deployment as cmdep
from checkmate import deployments
from checkmate import workflow_spec
from checkmate.workflows import tasks as workflow_tasks


class TestManager(unittest.TestCase):

    def setUp(self):
        self.driver = mock.Mock()
        get_driver_patcher = mock.patch.object(deployments.manager.db,
                                               'get_driver')
        mock_get_driver = get_driver_patcher.start()
        mock_get_driver.return_value = self.driver
        self.addCleanup(get_driver_patcher.stop)

        self.controller = deployments.Manager()
        unittest.TestCase.setUp(self)

    def tearDown(self):
        unittest.TestCase.tearDown(self)

    @mock.patch('checkmate.operations.add')
    @mock.patch('checkmate.workflow.create_workflow')
    @mock.patch(
        'checkmate.workflow_spec.WorkflowSpec.create_resource_offline_spec')
    @mock.patch('checkmate.db.get_driver')
    def test_deploy_take_resource_offline(self, mock_driver, mock_spec,
                                          mock_workflow, mock_add_operation):
        deployment = {'id': "DEP_ID"}
        context = mock.Mock()
        driver = mock_driver.return_value
        spec = mock_spec.return_value
        workflow = mock_workflow.return_value
        operation = mock_add_operation.return_value
        self.controller.save_deployment = mock.Mock()
        actual = self.controller.deploy_take_resource_offline(deployment,
                                                              "res_id",
                                                              context,
                                                              "tenant_id")
        self.assertEqual(operation, actual)
        mock_spec.assert_called_once_with(deployment, "res_id", context)
        mock_workflow.assert_called_once_with(spec, deployment, context,
                                              driver=driver,
                                              wf_type="TAKE OFFLINE")
        mock_add_operation.assert_called_once_with(deployment, workflow,
                                                   "TAKE OFFLINE",
                                                   "tenant_id")

    @mock.patch('checkmate.operations.add')
    @mock.patch('checkmate.workflow.create_workflow')
    @mock.patch(
        'checkmate.workflow_spec.WorkflowSpec.create_resource_online_spec')
    @mock.patch('checkmate.db.get_driver')
    def test_deploy_get_resource_online(self, mock_driver, mock_spec,
                                        mock_workflow, mock_add_operation):
        deployment = {'id': "DEP_ID"}
        context = mock.Mock()
        driver = mock_driver.return_value
        spec = mock_spec.return_value
        workflow = mock_workflow.return_value
        operation = mock_add_operation.return_value
        self.controller.save_deployment = mock.Mock()
        actual = self.controller.deploy_get_resource_online(deployment,
                                                            "res_id",
                                                            context,
                                                            "tenant_id")
        self.assertEqual(operation, actual)
        mock_spec.assert_called_once_with(deployment, "res_id", context)
        mock_workflow.assert_called_once_with(spec, deployment, context,
                                              driver=driver,
                                              wf_type="GET ONLINE")
        mock_add_operation.assert_called_once_with(deployment, workflow,
                                                   "GET ONLINE",
                                                   "tenant_id")

    @mock.patch('checkmate.workflow.create_workflow')
    @mock.patch('checkmate.operations.add')
    @mock.patch.object(workflow_spec.WorkflowSpec, 'create_delete_node_spec')
    def test_delete_nodes(self, mock_create_delete, mock_add, mock_create_wf):
        resources = {
            '0': {},
            '1': {},
            '2': {},
            '3': {},
        }
        deployment = cmdep.Deployment({'id': 'DEP_ID'})
        mock_get_resources = mock.Mock(return_value=resources)
        deployment.get_resources_for_service = mock_get_resources
        mock_context = mock.Mock()
        mock_spec = mock.Mock()
        mock_wf = mock.Mock()
        mock_create_delete.return_value = mock_spec

        mock_create_wf.return_value = mock_wf
        self.controller.delete_nodes(deployment, mock_context, 'web', 2,
                                     ['1', '2'], "T_ID")
        mock_create_wf.assert_called_with(
            mock_spec,
            deployment,
            mock_context,
            driver=self.driver,
            wf_type="SCALE DOWN"
        )
        mock_add.assert_called_with(deployment, mock_wf,
                                    'SCALE DOWN', 'T_ID')

    @mock.patch('checkmate.workflow.create_workflow')
    @mock.patch('checkmate.operations.add')
    @mock.patch.object(workflow_spec.WorkflowSpec,
                       'create_workflow_spec_deploy')
    def test_deploy_add_nodes(self,
                              mock_create_wf_s_d,
                              mock_add,
                              mock_create_wf):
        deployment = {"id": "DEP_ID"}
        mock_context = mock.Mock()
        mock_spec = mock.Mock()
        mock_wf = mock.Mock()
        mock_create_wf_s_d.return_value = mock_spec

        mock_create_wf.return_value = mock_wf
        self.controller.deploy_add_nodes(deployment, mock_context, "T_ID")
        mock_create_wf_s_d.assert_called_with(deployment, mock_context)
        mock_create_wf.assert_called_with(
            mock_spec,
            deployment,
            mock_context,
            driver=self.driver,
            wf_type="SCALE UP"
        )
        mock_add.assert_called_with(deployment, mock_wf,
                                    'SCALE UP', 'T_ID')

    def test_reset_failed_resources(self):
        deployment_id = 1234
        deployment = {
            "id": deployment_id,
            "tenantId": 1000,
            "resources": {
                "0": {
                    "index": "0",
                    "status": "ERROR",
                    "instance": {
                        "id": "instance_id",
                    },
                    "relations": {
                        "host": {
                            "name": "something",
                        },
                    }
                },
            }
        }
        expected_deployment = copy.deepcopy(deployment)
        expected_deployment.pop("resources")
        expected_deployment.update({"resources": {
            "0": {
                "status": "PLANNED",
                "instance": None,
                "relations": {
                    "host": {
                        "name": "something",
                    },
                },
            },
            "1": {
                "index": "1",
                "status": "ERROR",
                "instance": {
                    "id": "instance_id",
                }
            }
        }})

        self.driver.get_deployment.return_value = deployment
        self.driver.save_deployment(deployment_id, expected_deployment, None,
                                    tenant_id=1000, partial=True)
        self.controller.reset_failed_resource(deployment_id, "0")
        self.driver.get_deployment.assert_called_with(deployment_id,
                                                      with_secrets=False)

    def test_reset_failed_resources_without_instance_key(self):
        deployment_id = 1234
        deployment = {
            "id": deployment_id,
            "tenantId": 1000,
            "resources": {
                "0": {
                    "status": "ERROR",
                },
            }
        }
        self.driver.get_deployment.return_value = deployment
        self.controller.reset_failed_resource(deployment_id, "0")
        self.driver.get_deployment.assert_called_with(deployment_id,
                                                      with_secrets=False)

    def test_reset_failed_resources_without_instance_id_key(self):
        deployment_id = 1234
        deployment = {
            "id": deployment_id,
            "tenantId": 1000,
            "resources": {
                "0": {
                    "status": "ERROR",
                    "instance": {
                    },
                },
            }
        }
        self.driver.get_deployment.return_value = deployment
        self.controller.reset_failed_resource(deployment_id, "0")
        self.driver.get_deployment.assert_called_with(deployment_id,
                                                      with_secrets=False)

    def test_reset_failed_resources_without_error_status(self):
        deployment_id = 1234
        deployment = {
            "id": deployment_id,
            "tenantId": 1000,
            "resources": {
                "0": {
                    "status": "PLANNED",
                    "instance": {
                        "id": "instance_id",
                    },
                },
            }
        }
        self.driver.get_deployment.return_value = deployment
        self.controller.reset_failed_resource(deployment_id, "0")
        self.driver.get_deployment.assert_called_with(deployment_id,
                                                      with_secrets=False)

    @mock.patch.object(workflow_tasks.cycle_workflow, 'apply_async')
    @mock.patch.object(deployments.Manager, 'get_deployment')
    def test_execute(self, mock_get_dep, mock_apply_async):
        api_id = "DEP_ID"
        mock_context = mock.Mock()
        mock_context.get_queued_task_dict.return_value = "context"
        deployment = {"id": "DEP_ID"}
        mock_get_dep.return_value = deployment
        mock_apply_async.return_value = "result"

        result = self.controller.execute(api_id, mock_context)
        self.assertEqual(result, "result")
        mock_apply_async.assert_called_with(args=["DEP_ID", "context"])

    @mock.patch.object(workflow_tasks.cycle_workflow, 'apply_async')
    @mock.patch.object(deployments.Manager, 'get_deployment')
    def test_execute_with_timeout(self, mock_get_dep, mock_apply_async):
        """Check that timeout is used."""
        api_id = "DEP_ID"
        mock_context = mock.Mock()
        mock_context.get_queued_task_dict.return_value = "context"
        deployment = {"id": "DEP_ID"}
        mock_get_dep.return_value = deployment
        mock_apply_async.return_value = "result"

        result = self.controller.execute(api_id, mock_context, timeout=2400)
        self.assertEqual(result, "result")
        mock_apply_async.assert_called_with(
            args=["DEP_ID", "context"],
            time_limit=2400,  # supplied timeout
            max_retries=480   # double estimate from default delay
        )

    @mock.patch.object(workflow_tasks.cycle_workflow, 'apply_async')
    @mock.patch.object(deployments.Manager, 'get_deployment')
    def test_execute_min_timeout(self, mock_get_dep, mock_apply_async):
        """Check that timeout does not reduce task settings."""
        api_id = "DEP_ID"
        mock_context = mock.Mock()
        mock_context.get_queued_task_dict.return_value = "context"
        deployment = {"id": "DEP_ID"}
        mock_get_dep.return_value = deployment
        mock_apply_async.return_value = "result"

        result = self.controller.execute(api_id, mock_context, timeout=10)
        self.assertEqual(result, "result")
        mock_apply_async.assert_called_with(
            args=["DEP_ID", "context"],
            time_limit=600,   # minimum is 10 minutes
            max_retries=120   # double estimate default from delay
        )

    @mock.patch.object(workflow_tasks.cycle_workflow, 'apply_async')
    @mock.patch.object(deployments.Manager, 'get_deployment')
    def test_execute_max_timeout(self, mock_get_dep, mock_apply_async):
        """Check that timeout does not go over maximum (one hour)."""
        api_id = "DEP_ID"
        mock_context = mock.Mock()
        mock_context.get_queued_task_dict.return_value = "context"
        deployment = {"id": "DEP_ID"}
        mock_get_dep.return_value = deployment
        mock_apply_async.return_value = "result"

        result = self.controller.execute(api_id, mock_context, timeout=3600)
        self.assertEqual(result, "result")
        mock_apply_async.assert_called_with(
            args=["DEP_ID", "context"],
            time_limit=3600,  # remains at default
            max_retries=720   # double estimate default from delay
        )


class TestCount(unittest.TestCase):
    def setUp(self):
        self._deployments = json.load(open(os.path.join(
            os.path.dirname(__file__), '../data', 'deployments.json')))
        self.driver = mock.Mock()

        get_driver_patcher = mock.patch.object(deployments.manager.db,
                                               'get_driver')
        mock_get_driver = get_driver_patcher.start()
        mock_get_driver.return_value = self.driver
        self.addCleanup(get_driver_patcher.stop)

        self.controller = deployments.Manager()
        unittest.TestCase.setUp(self)

    def tearDown(self):
        unittest.TestCase.tearDown(self)

    def test_get_count_all(self):
        self.driver.get_deployments = mock.Mock(
            return_value=self._deployments)
        self.assertEqual(self.controller.count(), 4)
        self.driver.get_deployments.assert_called_with(tenant_id=None,
                                                       with_count=True,
                                                       status=None,
                                                       query=None)

    def test_get_count_tenant(self):
        # remove the deployments that dont belong to our tenant
        deps = self._deployments.copy()
        deps['results'].pop("3fgh")
        deps['results'].pop("4ijk")
        deps['collection-count'] = 2
        self.driver.get_deployments = mock.Mock(return_value=deps)
        self.assertEqual(self.controller.count(tenant_id="12345"), 2)
        self.driver.get_deployments.assert_called_with(tenant_id="12345",
                                                       with_count=True,
                                                       status=None,
                                                       query=None)

    def test_get_count_blueprint(self):
        self.driver.get_deployments = mock.Mock(
            return_value=self._deployments)
        result = self.controller.count(blueprint_id="blp-123-aabc-efg")
        self.assertEqual(result, 2)
        self.driver.get_deployments.assert_called_with(tenant_id=None,
                                                       with_count=True,
                                                       status=None,
                                                       query=None)

    def test_get_count_blueprint_and_tenant(self):
        deps = self._deployments.copy()
        deps['results'].pop("2def")
        deps['results'].pop("3fgh")
        deps['results'].pop("4ijk")
        deps['collection-count'] = 1

        self.driver.get_deployments = mock.Mock(return_value=deps)
        result = self.controller.count(blueprint_id="blp-123-aabc-efg",
                                       tenant_id="12345")
        self.assertEquals(result, 1)
        self.driver.get_deployments.assert_called_with(tenant_id="12345",
                                                       with_count=True,
                                                       status=None,
                                                       query=None)

    def test_send_query_to_driver(self):
        # set up
        results = {'_links': {}, 'results': {}, 'collection-count': 0}
        self.driver.get_deployments.return_value = results

        self.controller.count(query='fake query')
        self.driver.get_deployments.assert_called_with(
            tenant_id=mock.ANY,
            with_count=mock.ANY,
            status=mock.ANY,
            query='fake query',
        )


class TestSecrets(unittest.TestCase):

    def setUp(self):
        self.manager = mock.Mock()
        data = {
            'id': '1',
            'tenantId': 'T1000',
            'created-by': 'john',
            'blueprint': {
                'display-outputs': {
                    "New Password": {
                        'is-secret': True,
                        'source': 'options://password',
                    },
                    "Server Count": {
                        'source': 'options://servers',
                    },
                },
            },
            'display-outputs': {
                'Locked Password': {
                    'is-secret': True,
                    'value': 'SHH!!',
                    'status': 'LOCKED',
                },
                'Future Password': {
                    'is-secret': True,
                    'status': 'GENERATING',
                },
                'Public Key': {
                    'value': 'Anyone can see this'
                }
            },
            'inputs': {
                'password': "Keep Private",
                'servers': 10,
            }
        }
        deployment = cmdep.Deployment(data)
        deployment['display-outputs'].update(deployment.calculate_outputs())
        self.deployment = deployment
        self.driver = mock.Mock()

        get_driver_patcher = mock.patch.object(deployments.manager.db,
                                               'get_driver')
        mock_get_driver = get_driver_patcher.start()
        mock_get_driver.return_value = self.driver
        self.addCleanup(get_driver_patcher.stop)

        self.manager = deployments.Manager()

    def test_get_deployment_hides_secrets(self):
        """Check that GET deployment responds without secrets."""
        self.driver.get_deployment = mock.Mock(return_value=self.deployment)
        dep = self.manager.get_deployment('1', tenant_id="T1000",
                                          with_secrets=False)

        self.assertEqual(dep['id'], '1')
        self.assertIn('display-outputs', dep)
        outputs = dep['display-outputs']
        self.assertNotIn('value', outputs['Locked Password'])
        self.assertNotIn('value', outputs['New Password'])
        self.assertIn('value', outputs['Public Key'])
        self.driver.get_deployment.assert_called_with('1', with_secrets=False)

    def test_locked_secrets_not_returned(self):
        """Check that locked secrets are not returned."""
        self.driver.get_deployment = mock.Mock(return_value=self.deployment)

        dep = self.manager.get_deployment_secrets('1', tenant_id="T1000")

        secrets = dep['secrets']
        self.assertIn('Locked Password', secrets)
        locked_pass = secrets['Locked Password']
        self.assertNotIn('value', locked_pass)
        self.assertEqual('LOCKED', locked_pass['status'])
        self.driver.get_deployment.assert_called_with('1', with_secrets=True)

    def test_status_generating_trumps_available(self):
        self.driver.get_deployment = mock.Mock(return_value=self.deployment)
        dep = self.manager.get_deployment('1', tenant_id="T1000",
                                          with_secrets=False)

        self.assertEqual(dep['id'], '1')
        self.assertIn('secrets', dep)
        self.assertEquals(dep['secrets'], 'GENERATING')
        self.driver.get_deployment.assert_called_with('1', with_secrets=False)

    def test_get_secrets_works_when_blank(self):
        """Check that GET deployment secrets wotks if there are no secrets."""
        del self.deployment['display-outputs']
        self.driver.get_deployment = mock.Mock(return_value=self.deployment)

        dep = self.manager.get_deployment('1', tenant_id="T1000",
                                          with_secrets=False)

        self.assertEqual(dep['id'], '1')

        self.assertIn('secrets', dep)
        self.assertEquals(dep['secrets'], 'NO SECRETS')
        self.driver.get_deployment.assert_called_with('1', with_secrets=False)

    def test_status_available_trumps_locked(self):
        """New secrets should be flagged as available."""
        del self.deployment['display-outputs']['Future Password']
        self.driver.get_deployment = mock.Mock(return_value=self.deployment)
        dep = self.manager.get_deployment('1', tenant_id="T1000",
                                          with_secrets=False)

        self.assertEqual(dep['id'], '1')
        self.assertIn('secrets', dep)
        self.assertEquals(dep['secrets'], 'AVAILABLE')
        self.driver.get_deployment.assert_called_with('1', with_secrets=False)

    def test_get_deployments_strips_secrets(self):
        self.driver.get_deployments = mock.Mock(return_value={
            'results': {'1': self.deployment}
        })
        results = self.manager.get_deployments(tenant_id="T1000")

        out = results['results']['1']
        self.assertIs(out, self.deployment)
        outputs = out['display-outputs']
        self.assertNotIn('value', outputs['Locked Password'])
        self.assertNotIn('value', outputs['New Password'])
        self.driver.get_deployments.assert_called_with(tenant_id="T1000",
                                                       offset=None,
                                                       limit=None,
                                                       with_deleted=False,
                                                       status=None,
                                                       query=None)


class TestDeploymentManager(unittest.TestCase):

    def setUp(self):
        results = {'_links': {}, 'results': {}, 'collection-count': 0}
        self.driver = mock.Mock()
        get_driver_patcher = mock.patch.object(deployments.manager.db,
                                               'get_driver')
        mock_get_driver = get_driver_patcher.start()
        mock_get_driver.return_value = self.driver
        self.addCleanup(get_driver_patcher.stop)

        self.driver.get_deployments.return_value = results
        self.manager = deployments.Manager()


class TestGetDeployments(TestDeploymentManager):

    def test_send_query_to_driver(self):
        self.manager.get_deployments(query='fake query')
        self.driver.get_deployments.assert_called_with(
            tenant_id=mock.ANY,
            offset=mock.ANY,
            limit=mock.ANY,
            with_deleted=mock.ANY,
            status=mock.ANY,
            query='fake query',
        )


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
