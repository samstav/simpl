# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232,E1101,E1103
import json
import logging
import unittest

import bottle
import mox
from webtest import TestApp

from checkmate import test
from checkmate import admin

LOG = logging.getLogger(__name__)


class TestAdminDeploymentCounts(unittest.TestCase):
    ''''Tests getting deployment numbers.'''

    def setUp(self):
        self._mox = mox.Mox()

        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = TestApp(self.filters)

        self.manager = self._mox.CreateMockAnything()
        self.tenant_manager = self._mox.CreateMockAnything()
        self.router = admin.Router(self.root_app, self.manager,
                                   self.tenant_manager)

        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_get_count_all(self):
        self.manager.count(tenant_id=None, status=None, query={}).AndReturn(3)
        self._mox.ReplayAll()
        res = self.app.get('/admin/deployments/count')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 3)

    def test_get_count_tenant(self):
        self.manager.count(tenant_id="12345", status=None, query={}).AndReturn(2)
        self._mox.ReplayAll()
        res = self.app.get('/admin/deployments/count?tenant_id=12345')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 2)

    def test_get_count_by_blueprint(self):
        self.manager.count(tenant_id=None, blueprint_id="blp-123-aa")\
            .AndReturn(4)
        self._mox.ReplayAll()
        res = self.app.get('/admin/deployments/count/blp-123-aa')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 4)

    def test_get_count_deployment_and_tenant(self):
        self.manager.count(tenant_id="456", blueprint_id="blp-123-aa")\
            .AndReturn(5)
        self._mox.ReplayAll()
        res = self.app.get('/admin/deployments/count/blp-123-aa?tenant_id=456')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 5)

    def _assert_good_count(self, ret, expected_count):
        self.assertIsNotNone(ret, "No count returned")
        self.assertIn("count", ret, "Return does not contain count")
        self.assertEqual(expected_count, ret.get("count", -1),
                         "Wrong count returned")


class TestAdminTenants(unittest.TestCase):
    ''''Tests tenant calls.'''

    def setUp(self):
        self._mox = mox.Mox()

        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = TestApp(self.filters)

        self.manager = self._mox.CreateMockAnything()
        self.tenant_manager = self._mox.CreateMockAnything()
        self.router = admin.Router(self.root_app, self.manager,
                                   self.tenant_manager)

        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_get_tenant(self):
        self.tenant_manager.get_tenant("456").AndReturn({'id': '456'})
        self._mox.ReplayAll()
        res = self.app.get('/admin/tenants/456')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(json.loads(res.body), {'id': '456'})

    def test_get_tenants(self):
        tenants = {'123': {'id': '123'}, '456': {'id': '456'}}
        self.tenant_manager.list_tenants().AndReturn(tenants)
        self._mox.ReplayAll()
        res = self.app.get('/admin/tenants')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(json.loads(res.body), tenants)

    def test_put_tenant(self):
        self.tenant_manager.save_tenant("456", {'id': '456'}).AndReturn(None)
        self._mox.ReplayAll()
        res = self.app.put('/admin/tenants/456', json.dumps({'id': '456'}),
                           content_type='application/json')
        self.assertEqual(res.status, '201 Created')

    def test_put_tenant_tags(self):
        self.tenant_manager.add_tenant_tags("456", 'A').AndReturn(None)
        self._mox.ReplayAll()
        res = self.app.post('/admin/tenants/456', json.dumps({'tags': ['A']}),
                            content_type='application/json')
        self.assertEqual(res.status, '204 No Content')


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
