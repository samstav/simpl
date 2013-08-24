# pylint: disable=R0904

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

"""Tests for Admin Tenants and Admin Tenants Deployment Counts."""
import json
import logging
import unittest

import bottle
import mox
import webtest

from checkmate import admin
from checkmate import test

LOG = logging.getLogger(__name__)


class TestAdminDeploymentCounts(unittest.TestCase):
    def setUp(self):
        self._mox = mox.Mox()

        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = webtest.TestApp(self.filters)

        self.manager = self._mox.CreateMockAnything()
        self.tenant_manager = self._mox.CreateMockAnything()
        self.router = admin.Router(self.root_app, self.manager,
                                   self.tenant_manager)

        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_get_count_all(self):
        self.manager.count(tenant_id=None, status=None,
                           query=mox.IgnoreArg())\
            .AndReturn(3)
        self._mox.ReplayAll()
        res = self.app.get('/admin/deployments/count')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 3)

    def test_get_count_tenant(self):
        self.manager.count(tenant_id="12345", status=None,
                           query=mox.IgnoreArg())\
            .AndReturn(2)
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

    def test_get_count_dep_and_tenant(self):
        self.manager.count(tenant_id="456", blueprint_id="blp-123-aa")\
            .AndReturn(5)
        self._mox.ReplayAll()
        res = self.app.get('/admin/deployments/count/blp-123-aa?tenant_id=456')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 5)

    def _assert_good_count(self, ret, expected_count):
        """Helper method for asserting count value."""
        self.assertIsNotNone(ret, "No count returned")
        self.assertIn("count", ret, "Return does not contain count")
        self.assertEqual(expected_count, ret.get("count", -1),
                         "Wrong count returned")


class TestAdminTenants(unittest.TestCase):
    def setUp(self):
        self._mox = mox.Mox()

        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = webtest.TestApp(self.filters)

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
    import sys

    test.run_with_params(sys.argv[:])
