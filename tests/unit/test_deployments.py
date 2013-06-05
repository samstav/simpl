# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method
'''
import os
import unittest2 as unittest
import uuid

import bottle
import mox
from webtest import TestApp

os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'
from checkmate import deployments, test, utils
from checkmate.deployment import Deployment


class TestAPICalls(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = TestApp(self.filters)

        self.manager = self.mox.CreateMockAnything()
        self.router = deployments.DeploymentsRouter(self.root_app,
                                                    self.manager)

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_created_by_assigned(self):
        req = self.mox.CreateMockAnything()
        req.context = self.mox.CreateMockAnything()
        req.context.username = 'john'
        self.mox.StubOutWithMock(utils, 'read_body')
        utils.read_body(req).AndReturn({})
        self.mox.ReplayAll()
        result = deployments.router._content_to_deployment(req,
                                                           deployment_id="1",
                                                           tenant_id="A")
        self.mox.VerifyAll()
        self.assertIn('created', result)
        expected = {
            'status': 'NEW',
            'tenantId': 'A',
            'created-by': 'john',
            'id': '1',
            'created': result['created'],
        }
        self.assertDictEqual(result._data, expected)

    def test_created_not_overwritten(self):
        req = self.mox.CreateMockAnything()
        req.context = self.mox.CreateMockAnything()
        req.context.username = 'john'
        self.mox.StubOutWithMock(utils, 'read_body')
        utils.read_body(req).AndReturn({'created-by': 'tom'})
        self.mox.ReplayAll()
        result = deployments.router._content_to_deployment(req,
                                                           deployment_id="1",
                                                           tenant_id="A")
        self.mox.VerifyAll()
        self.assertEqual(result['created-by'], 'tom')

    def test_get_deployment_secrets(self):
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


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
