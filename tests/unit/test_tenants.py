'''
Test Admin Calls
'''
import json
import sys
import unittest2 as unittest

import bottle
from bottle import HTTPError
import mox
from mox import IgnoreArg

from checkmate.admin import tenants
from checkmate.admin import router
from checkmate.admin import Router
from checkmate.admin import TenantManager

from checkmate import utils


class TenantTagsTests(unittest.TestCase):
    """ Test tenant tagging endpoints """

    def setUp(self):
        self.mox = mox.Mox()
        unittest.TestCase.setUp(self)
        bottle.request.bind({})

    def tearDown(self):
        unittest.TestCase.tearDown(self)
        self.mox.UnsetStubs()

    def test_add_tags(self):
        tags = {'tags': ['foo', 'bar', 'baz']}
        self.mox.StubOutWithMock(router, 'request')
        self.mox.StubOutWithMock(router, 'response')
        self.mox.StubOutWithMock(utils, "read_body")
        utils.read_body(IgnoreArg()).AndReturn(tags)
        self.mox.ReplayAll()
        Router.add_tenant_tags('1234')
        self.assertEqual(204, router.response.status)

    def test_add_notags(self):
        tags = {'tags': []}
        self.mox.StubOutWithMock(router, 'request')
        self.mox.StubOutWithMock(router, 'response')
        self.mox.StubOutWithMock(utils, "read_body")
        utils.read_body(IgnoreArg()).AndReturn(tags)
        self.mox.ReplayAll()
        self.assertRaises(HTTPError, Router.add_tenant_tags, '1234')

    def test_get_tenant(self):
        self.mox.StubOutWithMock(router, 'request')
        self.mox.StubOutWithMock(router, 'response')
        TenantManager.driver.Router.get_tenant('1234').AndReturn({'tenant_id':
                                                            '1234'})
        router.response.set_header(IgnoreArg(), IgnoreArg())
        (router.request.get_header('Accept', ['application/json'])
         .AndReturn('application/json'))
        router.response.set_header('content-type', 'application/json')
        self.mox.ReplayAll()
        tenant = json.loads(Router.get_tenant('1234'))
        self.assertIsNotNone(tenant)
        self.assertEqual('1234', tenant.get('tenant_id'))

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
        self.mox.StubOutWithMock(router, 'request')
        mockParams = self.mox.CreateMockAnything()
        router.request.query = mockParams
        mockParams.getall('tag').AndReturn([])
        self.mox.StubOutWithMock(router, 'response')
        self.mox.StubOutWithMock(router, "DB")
        TenantManager.driver.list_tenants().AndReturn(resp)
        router.response.set_header(IgnoreArg(), IgnoreArg())
        (router.request.get_header('Accept', ['application/json'])
         .AndReturn('application/json'))
        router.response.set_header('content-type', 'application/json')
        self.mox.ReplayAll()
        tens = json.loads(Router.get_tenants())
        self.assertIsNotNone(tens)
        self.assertDictEqual(resp, tens)

    def test_put_tenants(self):
        tenant = {
            "tenant_id": '1234',
            "tags": [
                'foo',
                'bar',
                'racker'
            ]
        }
        self.mox.StubOutWithMock(router, 'request')
        router.request.content_length = 10
        self.mox.StubOutWithMock(utils, "read_body")
        utils.read_body(IgnoreArg()).AndReturn(tenant)
        self.mox.StubOutWithMock(router, 'response')
        TenantManager.driver.save_tenant(tenant)
        self.mox.ReplayAll()
        Router.put_tenant(tenant.get('tenant_id'))
        self.mox.VerifyAll()


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
