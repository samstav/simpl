# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232,E1101,E1103
'''
Test Tenant Manager
'''
import unittest

import mox

from checkmate import admin


class TenantTagsTests(unittest.TestCase):
    '''Test tenant manager'''

    def setUp(self):
        unittest.TestCase.setUp(self)
        self.mox = mox.Mox()
        self.db = self.mox.CreateMockAnything()
        self.controller = admin.TenantManager({'default': self.db})

    def tearDown(self):
        self.mox.VerifyAll()
        self.mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_add_tags(self):
        self.db.add_tenant_tags('1234', 'foo', 'bar', 'baz')
        self.mox.ReplayAll()
        self.controller.add_tenant_tags('1234', ['foo', 'bar', 'baz'])

    def test_add_notags(self):
        self.db.add_tenant_tags('1234')
        self.mox.ReplayAll()
        self.controller.add_tenant_tags('1234', [])

    def test_get_tenant(self):
        self.db.get_tenant('1234').AndReturn({'id': '1234'})
        self.mox.ReplayAll()
        tenant = self.controller.get_tenant('1234')
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
        self.db.list_tenants([]).AndReturn(resp)
        self.mox.ReplayAll()
        tenants = self.controller.list_tenants([])
        self.assertIsNotNone(tenants)
        self.assertDictEqual(resp, tenants)

    def test_put_tenant(self):
        tenant = {
            "id": '1234',
            "tags": [
                'foo',
                'bar',
                'racker'
            ]
        }
        self.db.save_tenant(tenant).AndReturn(tenant)
        self.mox.ReplayAll()
        self.controller.save_tenant('1234', tenant)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
