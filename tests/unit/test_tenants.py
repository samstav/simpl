import unittest2 as unittest
from checkmate.tenants import add_tenant_tags, get_tenant, get_tenants,\
    put_tenant
import mox
import bottle
from checkmate import tenants
from mox import IgnoreArg
from bottle import HTTPError
import json


class TenantTagsTests(unittest.TestCase):
    """ Test tenant tagging endpoints """

    def __init__(self, methodName='runTest'):
        unittest.TestCase.__init__(self, methodName=methodName)
        self.mox = mox.Mox()

    def setUp(self):
        unittest.TestCase.setUp(self)
        bottle.request.bind({})

    def tearDown(self):
        unittest.TestCase.tearDown(self)
        self.mox.UnsetStubs()

    def test_add_tags(self):
        tags = {'tags': ['foo', 'bar', 'baz']}
        self.mox.StubOutWithMock(tenants, 'request')
        self.mox.StubOutWithMock(tenants, 'response')
        self.mox.StubOutWithMock(tenants, "read_body")
        tenants.read_body(IgnoreArg()).AndReturn(tags)
        self.mox.ReplayAll()
        add_tenant_tags('1234')
        self.assertEqual(204, tenants.response.status)

    def test_add_notags(self):
        tags = {'tags': []}
        self.mox.StubOutWithMock(tenants, 'request')
        self.mox.StubOutWithMock(tenants, 'response')
        self.mox.StubOutWithMock(tenants, "read_body")
        tenants.read_body(IgnoreArg()).AndReturn(tags)
        self.mox.ReplayAll()
        self.assertRaises(HTTPError, add_tenant_tags, '1234')

    def test_get_tenant(self):
        self.mox.StubOutWithMock(tenants, 'request')
        self.mox.StubOutWithMock(tenants, 'response')
        self.mox.StubOutWithMock(tenants, "DB")
        tenants.DB.get_tenant('1234').AndReturn({'tenant_id': '1234'})
        tenants.response.set_header(IgnoreArg(), IgnoreArg())
        (tenants.request.get_header('Accept', ['application/json'])
         .AndReturn('application/json'))
        tenants.response.set_header('content-type', 'application/json')
        self.mox.ReplayAll()
        tenant = json.loads(get_tenant('1234'))
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
        self.mox.StubOutWithMock(tenants, 'request')
        mockParams = self.mox.CreateMockAnything()
        tenants.request.query = mockParams
        mockParams.getall('tag').AndReturn([])
        self.mox.StubOutWithMock(tenants, 'response')
        self.mox.StubOutWithMock(tenants, "DB")
        tenants.DB.list_tenants().AndReturn(resp)
        tenants.response.set_header(IgnoreArg(), IgnoreArg())
        (tenants.request.get_header('Accept', ['application/json'])
         .AndReturn('application/json'))
        tenants.response.set_header('content-type', 'application/json')
        self.mox.ReplayAll()
        tens = json.loads(get_tenants())
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
        self.mox.StubOutWithMock(tenants, 'request')
        tenants.request.content_length = 10
        self.mox.StubOutWithMock(tenants, "read_body")
        tenants.read_body(IgnoreArg()).AndReturn(tenant)
        self.mox.StubOutWithMock(tenants, 'response')
        self.mox.StubOutWithMock(tenants, "DB")
        tenants.DB.save_tenant(tenant)
        self.mox.ReplayAll()
        put_tenant(tenant.get('tenant_id'))
        self.mox.VerifyAll()
