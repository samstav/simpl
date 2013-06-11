# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''
import json
import os
import unittest2 as unittest
import uuid
from copy import deepcopy

import mox

from checkmate.deployment import Deployment
from checkmate import deployments


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

    def test_create_failed_resources_with_existing_errored_resource(self):
        deployment_id = 1234
        deployment = {
            "id": deployment_id,
            "tenantId": 1000,
            "resources": {
                "0": {
                    "status": "ERROR",
                    "relations": {
                        "host": {
                            "name": "something",
                        },
                    }
                },
            }
        }
        expected_deployment = deepcopy(deployment)
        expected_deployment.pop("resources")
        expected_deployment.update({"resources": {
            "1": {
                "index": "1",
                "status": "ERROR"
            }
        }})

        self.db.get_deployment(deployment_id, with_secrets=False).AndReturn(
            deployment)
        self.db.save_deployment(deployment_id, expected_deployment, None,
                                tenant_id=1000, partial=True)
        self._mox.ReplayAll()
        self.controller.create_failed_resource(deployment_id, "0")

    def test_create_failed_resources_without_any_errored_resource(self):
        deployment_id = 1234
        deployment = {
            "id": deployment_id,
            "tenantId": 1000,
            "resources": {
                "0": {
                    "status": "PLANNED",
                },
            }
        }
        self.db.get_deployment(deployment_id, with_secrets=False).AndReturn(
            deployment)
        self._mox.ReplayAll()
        self.controller.create_failed_resource(deployment_id, "0")
        self._mox.VerifyAll()


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
        self.db.get_deployments(tenant_id=None).AndReturn(self._deployments)
        self._mox.ReplayAll()
        self.assertEqual(self.controller.count(), 3)

    def test_get_count_tenant(self):
        # remove the extra deployment
        self._deployments.pop("3fgh")
        self.db.get_deployments(tenant_id="12345").AndReturn(
            self._deployments)
        self._mox.ReplayAll()
        self.assertEqual(self.controller.count(tenant_id="12345"), 2)

    def test_get_count_deployment(self):
        self.db.get_deployments(tenant_id=None).AndReturn(
            self._deployments)
        self._mox.ReplayAll()
        result = self.controller.count(blueprint_id="blp-123-aabc-efg")
        self.assertEqual(result, 2)

    def test_get_count_deployment_and_tenant(self):
        raw_deployments = self._deployments.copy()
        raw_deployments.pop("3fgh")
        self._deployments.pop("2def")
        self._deployments.pop("1abc")
        self.db.get_deployments(tenant_id="854673")\
            .AndReturn(self._deployments)
        self.db.get_deployments(tenant_id="12345").AndReturn(raw_deployments)
        self._mox.ReplayAll()
        result = self.controller.count(blueprint_id="blp-123-aabc-efg",
                                       tenant_id="854673")
        self.assertEquals(result, 1)
        result = self.controller.count(blueprint_id="blp123avc",
                                       tenant_id="12345")
        self.assertEquals(result, 1)


class TestSecrets(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()
        self.manager = self.mox.CreateMockAnything()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_get_deployment_secrets_hidden(self):
        '''Check that GET deployment responds without secrets'''
        id1 = uuid.uuid4().hex[0:7]
        data = {
            'id': id1,
            'tenantId': 'T1000',
            'created-by': 'john',
            'blueprint': {
                'display-outputs': {
                    "Password": {
                        'is-secret': True,
                        'source': 'options://password',
                    },
                    "Server Count": {
                        'source': 'options://servers',
                    },
                },
            },
            'inputs': {
                'password': "Keep Private",
                'servers': 10,
            }
        }
        deployment = Deployment(data)
        deployment['display-outputs'] = deployment.calculate_outputs()
        driver = self.mox.CreateMockAnything()
        driver.get_deployment(id1, with_secrets=False).AndReturn(deployment)

        manager = deployments.Manager({'default': driver})

        self.mox.ReplayAll()
        dep = manager.get_a_deployment(id1, tenant_id="T1000",
                                       with_secrets=False)
        self.mox.VerifyAll()

        self.assertEqual(dep['id'], id1)
        self.assertIn('display-outputs', dep)
        self.assertNotIn('value', dep['display-outputs']['Password'])
        self.assertIn('value', dep['display-outputs']['Server Count'])

        self.assertIn('secrets', dep)
        self.assertEquals(dep['secrets'], 'AVAILABLE')

    def test_get_deployment_secrets_blank(self):
        '''Check that GET deployment responds without secrets'''
        id1 = uuid.uuid4().hex[0:7]
        data = {
            'id': id1,
            'tenantId': 'T1000',
            'created-by': 'john',
            'blueprint': {},
            'inputs': {
                'password': "Keep Private",
                'servers': 10,
            }
        }
        deployment = Deployment(data)
        driver = self.mox.CreateMockAnything()
        driver.get_deployment(id1, with_secrets=False).AndReturn(deployment)

        manager = deployments.Manager({'default': driver})

        self.mox.ReplayAll()
        dep = manager.get_a_deployment(id1, tenant_id="T1000",
                                       with_secrets=False)
        self.mox.VerifyAll()

        self.assertEqual(dep['id'], id1)

        self.assertIn('secrets', dep)
        self.assertEquals(dep['secrets'], 'NO SECRETS')


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
