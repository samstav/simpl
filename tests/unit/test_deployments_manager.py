# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''
import copy
import json
import os
import unittest

import mock
import mox

from checkmate import deployments
from checkmate import operations
from checkmate import workflow
from checkmate.deployment import Deployment


class TestManager(unittest.TestCase):

    def setUp(self):
        self._mox = mox.Mox()
        self.db = self._mox.CreateMockAnything()
        self.controller = deployments.Manager({'default': self.db})
        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.VerifyAll()
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    # def test_add_node(self):
    #     deployment = {}
    #     mockContext = self._mox.CreateMockAnything()
    #     self._mox.StubOutClassWithMocks(deployments, "Planner")
    #     mock_planner = deployments.Planner(deployment)
    #     mock_planner.plan_additional_nodes(mockContext, "service_name", 3)
    #     self._mox.ReplayAll()
    #     self.controller.add_nodes(deployment, mockContext, 'service_name', 3)
    #     self._mox.VerifyAll()

    def test_deploy_add_nodes(self):
        deployment = {}
        mock_context = self._mox.CreateMockAnything()
        mock_spec = self._mox.CreateMockAnything()
        mock_wf = self._mox.CreateMockAnything()
        self._mox.StubOutWithMock(workflow, "create_workflow_spec_deploy")
        workflow.create_workflow_spec_deploy(deployment, mock_context)\
            .AndReturn(mock_spec)
        self._mox.StubOutWithMock(workflow, "create_workflow")
        workflow.create_workflow(
            mock_spec, deployment, mock_context, driver=self.controller.driver
        ).AndReturn(mock_wf)
        self._mox.StubOutWithMock(operations, "add")
        operations.add(deployment, mock_wf, "SCALE UP", "T_ID")
        self._mox.ReplayAll()
        self.controller.deploy_add_nodes(deployment, mock_context, "T_ID")

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

        self.db.get_deployment(deployment_id, with_secrets=False).AndReturn(
            deployment)
        self.db.save_deployment(deployment_id, expected_deployment, None,
                                tenant_id=1000, partial=True)
        self._mox.ReplayAll()
        self.controller.reset_failed_resource(deployment_id, "0")

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
        self.db.get_deployment(deployment_id, with_secrets=False).AndReturn(
            deployment)
        self._mox.ReplayAll()
        self.controller.reset_failed_resource(deployment_id, "0")

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
        self.db.get_deployment(deployment_id, with_secrets=False).AndReturn(
            deployment)
        self._mox.ReplayAll()
        self.controller.reset_failed_resource(deployment_id, "0")

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
        self.db.get_deployment(deployment_id, with_secrets=False).AndReturn(
            deployment)
        self._mox.ReplayAll()
        self.controller.reset_failed_resource(deployment_id, "0")


class TestCount(unittest.TestCase):
    """ Tests getting deployment counts """

    def setUp(self):
        self._mox = mox.Mox()
        self._deployments = json.load(open(os.path.join(
            os.path.dirname(__file__), '../data', 'deployments.json')))
        self.db = self._mox.CreateMockAnything()
        self.controller = deployments.Manager({'default': self.db})
        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_get_count_all(self):
        self.db.get_deployments(tenant_id=None, with_count=True,
                                status=None).AndReturn(self._deployments)
        self._mox.ReplayAll()
        self.assertEqual(self.controller.count(), 4)

    def test_get_count_tenant(self):
        # remove the deployments that dont belong to our tenant
        deps = self._deployments.copy()
        deps['results'].pop("3fgh")
        deps['results'].pop("4ijk")
        deps['collection-count'] = 2
        self.db.get_deployments(tenant_id="12345", with_count=True,
                                status=None).AndReturn(deps)
        self._mox.ReplayAll()
        self.assertEqual(self.controller.count(tenant_id="12345"), 2)

    def test_get_count_blueprint(self):
        self.db.get_deployments(status=None, tenant_id=None, with_count=True)\
            .AndReturn(self._deployments)
        self._mox.ReplayAll()
        result = self.controller.count(blueprint_id="blp-123-aabc-efg")
        self.assertEqual(result, 2)

    def test_get_count_blueprint_and_tenant(self):
        deps = self._deployments.copy()
        deps['results'].pop("2def")
        deps['results'].pop("3fgh")
        deps['results'].pop("4ijk")
        deps['collection-count'] = 1

        self.db.get_deployments(tenant_id="12345", with_count=True,
                                status=None).AndReturn(deps)
        self._mox.ReplayAll()
        result = self.controller.count(blueprint_id="blp-123-aabc-efg",
                                       tenant_id="12345")
        self.assertEquals(result, 1)


class TestSecrets(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()
        self.manager = self.mox.CreateMockAnything()
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
        self.driver = self.mox.CreateMockAnything()
        self.manager = deployments.Manager({'default': self.driver})

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_get_deployment_hides_secrets(self):
        '''Check that GET deployment responds without secrets.'''
        self.driver.get_deployment('1', with_secrets=False)\
            .AndReturn(self.deployment)
        self.mox.ReplayAll()
        dep = self.manager.get_deployment('1', tenant_id="T1000",
                                          with_secrets=False)
        self.mox.VerifyAll()

        self.assertEqual(dep['id'], '1')
        self.assertIn('display-outputs', dep)
        outputs = dep['display-outputs']
        self.assertNotIn('value', outputs['Locked Password'])
        self.assertNotIn('value', outputs['New Password'])
        self.assertIn('value', outputs['Public Key'])

    def test_locked_secrets_not_returned(self):
        '''Check that locked secrets are not returned'''
        self.driver.get_deployment('1', with_secrets=True)\
            .AndReturn(self.deployment)

        self.mox.ReplayAll()
        dep = self.manager.get_deployment_secrets('1', tenant_id="T1000")
        self.mox.VerifyAll()

        secrets = dep['secrets']
        self.assertIn('Locked Password', secrets)
        locked_pass = secrets['Locked Password']
        self.assertNotIn('value', locked_pass)
        self.assertEqual('LOCKED', locked_pass['status'])

    def test_status_generating_trumps_available(self):
        self.driver.get_deployment('1', with_secrets=False)\
            .AndReturn(self.deployment)
        self.mox.ReplayAll()
        dep = self.manager.get_deployment('1', tenant_id="T1000",
                                          with_secrets=False)
        self.mox.VerifyAll()

        self.assertEqual(dep['id'], '1')
        self.assertIn('secrets', dep)
        self.assertEquals(dep['secrets'], 'GENERATING')

    def test_get_secrets_works_when_blank(self):
        '''Check that GET deployment secrets wotks if there are no secrets.'''
        del self.deployment['display-outputs']
        self.driver.get_deployment('1', with_secrets=False)\
            .AndReturn(self.deployment)

        self.mox.ReplayAll()
        dep = self.manager.get_deployment('1', tenant_id="T1000",
                                          with_secrets=False)
        self.mox.VerifyAll()

        self.assertEqual(dep['id'], '1')

        self.assertIn('secrets', dep)
        self.assertEquals(dep['secrets'], 'NO SECRETS')

    def test_status_available_trumps_locked(self):
        '''New secrets should be flagged as available.'''
        del self.deployment['display-outputs']['Future Password']
        self.driver.get_deployment('1', with_secrets=False)\
            .AndReturn(self.deployment)
        self.mox.ReplayAll()
        dep = self.manager.get_deployment('1', tenant_id="T1000",
                                          with_secrets=False)
        self.mox.VerifyAll()

        self.assertEqual(dep['id'], '1')
        self.assertIn('secrets', dep)
        self.assertEquals(dep['secrets'], 'AVAILABLE')

    def test_get_deployments_strips_secrets(self):
        self.driver.get_deployments(tenant_id="T1000", offset=None, limit=None,
                                    with_deleted=False, status=None, query=None)\
            .AndReturn({'results': {'1': self.deployment}})
        self.mox.ReplayAll()
        results = self.manager.get_deployments(tenant_id="T1000")
        self.mox.VerifyAll()

        out = results['results']['1']
        self.assertIs(out, self.deployment)
        outputs = out['display-outputs']
        self.assertNotIn('value', outputs['Locked Password'])
        self.assertNotIn('value', outputs['New Password'])


class TestGetDeployments(unittest.TestCase):

    def setUp(self):
        results = {'_links': {}, 'results': {}, 'collection-count': 0}
        self.driver = mock.Mock()
        self.driver.get_deployments.return_value = results
        self.manager = deployments.Manager({'default': self.driver})

    def test_send_empty_query_to_driver(self):
        self.manager.get_deployments(query={})
        self.driver.get_deployments.assert_called_with(
            tenant_id=mock.ANY,
            offset=mock.ANY,
            limit=mock.ANY,
            with_deleted=mock.ANY,
            status=mock.ANY,
            query={}
        )

    def test_send_query_to_driver(self):
        self.manager.get_deployments(query={'name': 'fake name'})
        self.driver.get_deployments.assert_called_with(
            tenant_id=mock.ANY,
            offset=mock.ANY,
            limit=mock.ANY,
            with_deleted=mock.ANY,
            status=mock.ANY,
            query={'name': 'fake name'}
        )


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
