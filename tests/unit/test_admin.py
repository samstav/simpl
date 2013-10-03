# pylint: disable=R0904

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

"""Tests for Admin endpoints."""
import json
import logging
import unittest

import bottle
import mock
import webtest

from checkmate import admin
from checkmate import test

LOG = logging.getLogger(__name__)


class TestAdminDeploymentCounts(unittest.TestCase):
    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = webtest.TestApp(self.filters)

        self.manager = mock.Mock()
        self.tenant_manager = mock.Mock()
        self.router = admin.Router(self.root_app, self.manager,
                                   self.tenant_manager)

        unittest.TestCase.setUp(self)

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

    def test_count_deploy_with_tenant(self):
        self.manager.count.return_value = 5
        res = self.app.get('/admin/deployments/count/blp-123-aa?tenant_id=456')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 5)
        self.manager.count.assert_called_once_with(tenant_id='456',
                                                   blueprint_id='blp-123-aa')

    def _assert_good_count(self, ret, expected_count):
        """Helper method to assert count matches expected count."""
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
        self.app = webtest.TestApp(self.filters)

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
    test.run_with_params()
