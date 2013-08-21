# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
import json
import logging
import unittest

import bottle
import mock
from webtest import TestApp

from checkmate import test
from checkmate import admin

LOG = logging.getLogger(__name__)


class TestAdminDeploymentCounts(unittest.TestCase):
    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = TestApp(self.filters)

        self.manager = mock.Mock()
        self.tenant_manager = mock.Mock()
        self.router = admin.Router(self.root_app, self.manager,
                                   self.tenant_manager)

        unittest.TestCase.setUp(self)

    def tearDown(self):
        unittest.TestCase.tearDown(self)

    def test_get_count_all(self):
        self.manager.count.return_value = 3
        res = self.app.get('/admin/deployments/count')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 3)
        self.manager.count.assert_called_once_with(tenant_id=None,
                                                   status=None,
                                                   query=mock.ANY)

    def test_get_count_tenant(self):
        self.manager.count.return_value = 2
        res = self.app.get('/admin/deployments/count?tenant_id=12345')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 2)
        self.manager.count.assert_called_once_with(tenant_id='12345',
                                                   status=None,
                                                   query=mock.ANY)

    def test_get_count_by_blueprint(self):
        self.manager.count.return_value = 4
        res = self.app.get('/admin/deployments/count/blp-123-aa')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 4)
        self.manager.count.assert_called_once_with(tenant_id=None,
                                                   blueprint_id='blp-123-aa')

    def test_get_count_deployment_and_tenant(self):
        self.manager.count.return_value = 5
        res = self.app.get('/admin/deployments/count/blp-123-aa?tenant_id=456')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 5)
        self.manager.count.assert_called_once_with(tenant_id='456',
                                                   blueprint_id='blp-123-aa')

    def _assert_good_count(self, ret, expected_count):
        self.assertIsNotNone(ret, "No count returned")
        self.assertIn("count", ret, "Return does not contain count")
        self.assertEqual(expected_count, ret.get("count", -1),
                         "Wrong count returned")


class TestAdminTenants(unittest.TestCase):
    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = TestApp(self.filters)

        self.manager = mock.Mock()
        self.tenant_manager = mock.Mock()
        self.router = admin.Router(self.root_app, self.manager,
                                   self.tenant_manager)

        unittest.TestCase.setUp(self)

    def tearDown(self):
        unittest.TestCase.tearDown(self)

    def test_get_tenant(self):
        self.tenant_manager.get_tenant.return_value = {'id': '456'}
        res = self.app.get('/admin/tenants/456')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(json.loads(res.body), {'id': '456'})
        self.tenant_manager.get_tenant.assert_called_once_with('456')

    def test_get_tenants(self):
        tenants = {'123': {'id': '123'}, '456': {'id': '456'}}
        self.tenant_manager.list_tenants.return_value = tenants
        res = self.app.get('/admin/tenants')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(json.loads(res.body), tenants)

    def test_put_tenant(self):
        res = self.app.put('/admin/tenants/456', json.dumps({'id': '456'}),
                           content_type='application/json')
        self.assertEqual(res.status, '201 Created')
        self.tenant_manager.save_tenant.assert_called_once_with('456',
                                                                {'id': '456'})

    def test_put_tenant_tags(self):
        res = self.app.post('/admin/tenants/456', json.dumps({'tags': ['A']}),
                            content_type='application/json')
        self.assertEqual(res.status, '204 No Content')
        self.tenant_manager.add_tenant_tags.assert_called_once_with('456', 'A')


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
