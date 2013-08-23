# pylint: disable=C0103,R0904,W0201
"""Tests for Deployments Manager."""
import copy
import json
import os
import unittest

import mock

from checkmate import deployments
from checkmate import workflows
from checkmate.deployment import Deployment


class TestManager(unittest.TestCase):

    def setUp(self):
        self.mock_db = mock.Mock()
        self.controller = deployments.Manager({'default': self.mock_db})
        unittest.TestCase.setUp(self)

    def tearDown(self):
        unittest.TestCase.tearDown(self)

    @mock.patch('checkmate.workflow.create_workflow')
    @mock.patch('checkmate.operations.add')
    @mock.patch.object(workflows.WorkflowSpec, 'create_delete_node_spec')
    def test_delete_nodes(self, mock_create_delete, mock_add, mock_create_wf):
        resources = {
            '0': {},
            '1': {},
            '2': {},
            '3': {},
        }
        deployment = Deployment({'id': 'DEP_ID'})
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
            driver=self.controller.driver
        )
        mock_add.assert_called_with(deployment, mock_wf,
                                    'SCALE DOWN', 'T_ID')

    @mock.patch('checkmate.workflow.create_workflow')
    @mock.patch('checkmate.operations.add')
    @mock.patch.object(workflows.WorkflowSpec, 'create_workflow_spec_deploy')
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
            driver=self.controller.driver
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

        self.mock_db.get_deployment.return_value = deployment
        self.mock_db.save_deployment(deployment_id, expected_deployment, None,
                                     tenant_id=1000, partial=True)
        self.controller.reset_failed_resource(deployment_id, "0")
        self.mock_db.get_deployment.assert_called_with(deployment_id,
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
        self.mock_db.get_deployment.return_value = deployment
        self.controller.reset_failed_resource(deployment_id, "0")
        self.mock_db.get_deployment.assert_called_with(deployment_id,
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
        self.mock_db.get_deployment.return_value = deployment
        self.controller.reset_failed_resource(deployment_id, "0")
        self.mock_db.get_deployment.assert_called_with(deployment_id,
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
        self.mock_db.get_deployment.return_value = deployment
        self.controller.reset_failed_resource(deployment_id, "0")
        self.mock_db.get_deployment.assert_called_with(deployment_id,
                                                       with_secrets=False)


class TestCount(unittest.TestCase):
    """ Tests getting deployment counts """

    def setUp(self):
        self._deployments = json.load(open(os.path.join(
            os.path.dirname(__file__), '../data', 'deployments.json')))
        self.mock_db = mock.Mock()
        self.controller = deployments.Manager({'default': self.mock_db})
        unittest.TestCase.setUp(self)

    def tearDown(self):
        unittest.TestCase.tearDown(self)

    def test_get_count_all(self):
        self.mock_db.get_deployments = mock.Mock(return_value=self._deployments)
        self.assertEqual(self.controller.count(), 4)
        self.mock_db.get_deployments.assert_called_with(tenant_id=None,
                                                        with_count=True,
                                                   status=None, query=None)

    def test_get_count_tenant(self):
        # remove the deployments that dont belong to our tenant
        deps = self._deployments.copy()
        deps['results'].pop("3fgh")
        deps['results'].pop("4ijk")
        deps['collection-count'] = 2
        self.mock_db.get_deployments = mock.Mock(return_value=deps)
        self.assertEqual(self.controller.count(tenant_id="12345"), 2)
        self.mock_db.get_deployments.assert_called_with(tenant_id="12345",
                                                        with_count=True,
                                                   status=None,
                                                   query=None)

    def test_get_count_blueprint(self):
        self.mock_db.get_deployments = mock.Mock(return_value=self._deployments)
        result = self.controller.count(blueprint_id="blp-123-aabc-efg")
        self.assertEqual(result, 2)
        self.mock_db.get_deployments.assert_called_with(tenant_id=None,
                                                        with_count=True,
                                                   status=None,
                                                   query=None)

    def test_get_count_blueprint_and_tenant(self):
        deps = self._deployments.copy()
        deps['results'].pop("2def")
        deps['results'].pop("3fgh")
        deps['results'].pop("4ijk")
        deps['collection-count'] = 1

        self.mock_db.get_deployments = mock.Mock(return_value=deps)
        result = self.controller.count(blueprint_id="blp-123-aabc-efg",
                                       tenant_id="12345")
        self.assertEquals(result, 1)
        self.mock_db.get_deployments.assert_called_with(tenant_id="12345",
                                                        with_count=True,
                                                   status=None,
                                                   query=None)

    def test_send_query_to_driver(self):
        # set up
        results = {'_links': {}, 'results': {}, 'collection-count': 0}
        self.driver = mock.Mock()
        self.driver.get_deployments.return_value = results
        self.manager = deployments.Manager({'default': self.driver})

        self.manager.count(query='fake query')
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
        deployment = Deployment(data)
        deployment['display-outputs'].update(deployment.calculate_outputs())
        self.deployment = deployment
        self.driver = mock.Mock()
        self.manager = deployments.Manager({'default': self.driver})

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
        """Check that locked secrets are not returned"""
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
        self.driver.get_deployments.return_value = results
        self.manager = deployments.Manager({'default': self.driver})


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
