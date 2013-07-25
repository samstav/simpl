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
import json
import os
import unittest

import bottle
import mock
import mox
from mox import IgnoreArg
from webtest import TestApp

os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'
from checkmate import deployments, test, utils


class TestAPICalls(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.app = TestApp(self.filters)

        self.manager = self.mox.CreateMockAnything()
        self.router = deployments.Router(self.root_app, self.manager)

    def tearDown(self):
        self.mox.UnsetStubs()

    def _assert_good_count(self, ret, expected_count):
        self.assertIsNotNone(ret, "No count returned")
        self.assertIn("count", ret, "Return does not contain count")
        self.assertEqual(expected_count, ret.get("count", -1),
                         "Wrong count returned")

    def test_created_by_assigned(self):
        req = self.mox.CreateMockAnything()
        req.context = self.mox.CreateMockAnything()
        req.context.username = 'john'
        req.headers = {}
        self.mox.StubOutWithMock(utils, 'read_body')
        utils.read_body(req).AndReturn({})
        self.mox.ReplayAll()
        result = deployments.router._content_to_deployment(request=req,
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
        self.assertDictEqual(result, expected)

    def test_created_not_overwritten(self):
        req = self.mox.CreateMockAnything()
        req.context = self.mox.CreateMockAnything()
        req.context.username = 'john'
        req.headers = {}
        self.mox.StubOutWithMock(utils, 'read_body')
        utils.read_body(req).AndReturn({'created-by': 'tom'})
        self.mox.ReplayAll()
        result = deployments.router._content_to_deployment(request=req,
                                                           deployment_id="1",
                                                           tenant_id="A")
        self.mox.VerifyAll()
        self.assertEqual(result['created-by'], 'tom')

    def test_get_count(self):
        self.manager.count(tenant_id="123").AndReturn(3)
        self.mox.ReplayAll()
        res = self.app.get('/123/deployments/count')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 3)

    def test_post_asynchronous(self):
        """ Test that POST /deployments?asynchronous=1 returns a 202 """
        deployment = {
            'id': '1234',
            'tenantId': 'T1000',
            'environment': {},
            'blueprint': {
                'name': 'Test',
                'services': {}
            }
        }
        self.manager.save_deployment(IgnoreArg(), api_id='1234',
                                     tenant_id="T1000").AndReturn(None)
        self.mox.StubOutWithMock(deployments.router, "tasks")
        tasks = deployments.router.tasks
        tasks.process_post_deployment = self.mox.CreateMockAnything()
        tasks.process_post_deployment.delay(IgnoreArg(),
                                            IgnoreArg()).AndReturn(None)

        self.mox.ReplayAll()
        res = self.app.post('/T1000/deployments?asynchronous=1',
                            json.dumps(deployment),
                            content_type='application/json')
        self.assertEqual(res.status, '202 Accepted')
        self.assertEqual(res.content_type, 'application/json')

    def test_post_synchronous(self):
        """ Test that POST /deployments returns a 202 """
        deployment = {
            'id': '1234',
            'tenantId': 'T1000',
            'environment': {},
            'blueprint': {
                'name': 'Test',
                'services': {}
            }
        }
        self.manager.select_driver('1234').AndReturn(self.manager)
        self.manager.save_deployment(deployment, IgnoreArg(),
                                     tenant_id="T1000").AndReturn(None)
        self.mox.StubOutWithMock(deployments.router, "tasks")
        tasks = deployments.router.tasks
        tasks.process_post_deployment(IgnoreArg(), IgnoreArg(),
                                      driver=IgnoreArg()).AndReturn(None)

        self.mox.ReplayAll()
        res = self.app.post('/T1000/deployments',
                            json.dumps(deployment),
                            content_type='application/json')
        self.assertEqual(res.status, '202 Accepted')
        self.assertEqual(res.content_type, 'application/json')

    def test_get_deployment_secrets_ok(self):
        deployment = {
            'id': '1234',
            'tenantId': 'T1000',
        }
        self.manager.get_deployment('1234', tenant_id="T1000")\
            .AndReturn(deployment)

        context = self.mox.CreateMockAnything()
        context.is_admin = True
        self.mox.StubOutWithMock(bottle.request, "context")
        bottle.request.context = context
        data = {'foo': 1}
        self.manager.get_deployment_secrets('1234', tenant_id="T1000")\
            .AndReturn(data)
        self.mox.StubOutWithMock(deployments.router.utils, "write_body")
        utils.write_body(data, bottle.request, bottle.response).AndReturn(42)

        self.mox.ReplayAll()
        result = self.router.get_deployment_secrets('1234', tenant_id="T1000")
        self.assertEqual(42, result)

    def test_get_deployment_secrets_not_admin(self):
        deployment = {
            'id': '1234',
            'tenantId': 'T1000',
        }
        self.manager.get_deployment('1234', tenant_id="T1000")\
            .AndReturn(deployment)

        context = self.mox.CreateMockAnything()
        context.is_admin = False
        self.mox.StubOutWithMock(bottle.request, "context")
        bottle.request.context = context
        data = {'foo': 1}
        self.manager.get_deployment_secrets('1234', tenant_id="T1000")\
            .AndReturn(data)
        self.mox.StubOutWithMock(deployments.router.utils, "write_body")
        utils.write_body(data, bottle.request, bottle.response).AndReturn(42)

        self.mox.ReplayAll()
        with self.assertRaises(bottle.HTTPError):
            self.router.get_deployment_secrets('1234', tenant_id="T1000")


class TestGetDeployments(unittest.TestCase):

    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.app = TestApp(self.filters)

        self.manager = mock.Mock()
        self.router = deployments.Router(self.root_app, self.manager)
        results = {'_links': {}, 'results': {}, 'collection-count': 0}
        self.manager.get_deployments.return_value = results

    def test_pass_empty_query(self):
        self.router.get_deployments()
        self.manager.get_deployments.assert_called_with(
            status=mock.ANY,
            tenant_id=mock.ANY,
            with_deleted=mock.ANY,
            limit=mock.ANY,
            offset=mock.ANY,
            query={}
        )

    def test_query_only_allowed_params(self):
        query_params = {
            'name': ['fake name'],
            'blueprint.name': ['fake blue'],
            'search': ['fake search'],
            'param_not_whitelisted': ['evil param'],
        }
        with mock.patch.dict(bottle.request.query.dict, query_params):
            self.router.get_deployments()
            self.manager.get_deployments.assert_called_with(
                tenant_id=mock.ANY,
                offset=mock.ANY,
                limit=mock.ANY,
                with_deleted=mock.ANY,
                status=mock.ANY,
                query={
                    'name': 'fake name',
                    'blueprint.name': 'fake blue',
                    'search': 'fake search',
                }
            )


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
