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

"""Tests for Tenant Tags."""
import unittest

import mock

from checkmate import admin


class TenantTagsTests(unittest.TestCase):
    """Test tenant manager"""

    def setUp(self):
        unittest.TestCase.setUp(self)
        self.mock_db = mock.Mock()
        self.controller = admin.TenantManager({'default': self.mock_db})

    def tearDown(self):
        unittest.TestCase.tearDown(self)

    def test_add_tags(self):
        self.mock_db.add_tenant_tags('1234', 'foo', 'bar', 'baz')
        self.controller.add_tenant_tags('1234', 'foo', 'bar', 'baz')

    def test_add_notags(self):
        self.mock_db.add_tenant_tags('1234')
        self.controller.add_tenant_tags('1234')

    def test_get_tenant(self):
        self.mock_db.get_tenant.return_value = {'id': '1234'}
        tenant = self.controller.get_tenant('1234')
        self.mock_db.get_tenant.assert_called_once_with('1234')
        self.assertIsNotNone(tenant)
        self.assertEqual('1234', tenant.get('id'))

    def test_get_tenants(self):
        resp = {
            "1234": {
                "tenant_id": '1234',
                "tags": [
                    'foo',
                    'bar',
                    'racker'
                ]
            },
            "5678": {
                "tenant_id": '5678',
                "tags": [
                    'racker'
                ]
            },
            "9012": {
                "tenant_id": '9012',
            }
        }
        self.mock_db.list_tenants.return_value = resp
        tenants = self.controller.list_tenants([])
        self.assertIsNotNone(tenants)
        self.assertDictEqual(resp, tenants)
        self.mock_db.list_tenants.assert_called_once_with([])

    def test_put_tenant(self):
        tenant = {
            "id": '1234',
            "tags": [
                'foo',
                'bar',
                'racker'
            ]
        }
        self.mock_db.save_tenant(tenant).AndReturn(tenant)
        self.controller.save_tenant('1234', tenant)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
