import httplib
import json
import logging
import unittest

import mox

from checkmate.middleware import identity
from checkmate import test

LOG = logging.getLogger(__name__)


class FakeHttpResponse(object):
    """Setup a FAKE http response."""

    def __init__(self, status, reason, headers, body):
        """
        Accept user input and return a response for HTTP

        :param status:
        :param reason:
        :param headers:
        :param body:
        :return body:
        :return headers:
        """

        self.body = body
        self.status = status
        self.reason = reason
        self.headers = headers

    def read(self):
        """Return HTTP body."""

        return self.body

    def getheaders(self):
        """Return HTTP Headers."""

        return self.headers


class TestIdentity(test.ProviderTester):
    """Test Identity Provider."""

    def setUp(self):
        """Setup Unittest with Mox."""

        super(TestIdentity, self).setUp()
        self.mox = mox.Mox()
        self.mox.StubOutWithMock(httplib.HTTPConnection, 'connect')
        self.mox.StubOutWithMock(httplib.HTTPConnection, 'request')
        self.mox.StubOutWithMock(httplib.HTTPConnection, 'getresponse')
        self.mox.StubOutWithMock(httplib.HTTPConnection, 'close')
        self.inv_servicecat = json.dumps({
            "access": {
                "token": {
                    "expires": "2013-08-02T19:36:42Z",
                    "id": "12345678901234567890"
                }
            }
        })
        self.rax_servicecat = json.dumps({
            u"access": {
                u"token": {
                    u"RAX-AUTH:authenticatedBy": [u"APIKEY"],
                    u"expires": u"2013-08-01T20:35:04.450-05:00",
                    u"id": u"12345678901234567890",
                    u"tenant": {
                        u"id": u"123456",
                        u"name": u"123456"
                    }
                }
            }
        })
        self.pri_servicecat = json.dumps({
            u"access": {
                u"token": {
                    u"expires": u"2013-08-02T19:36:42Z",
                    u"id": u"12345678901234567890"
                },
                u"user": {
                    u"username": u"admin",
                    u"roles_links": [],
                    u"id": u"1234567890",
                    u"roles": [],
                    u"name": u"admin"
                }
            }
        })

    def tearDown(self):
        """Tear down Unittest with Mox."""

        super(TestIdentity, self).tearDown()
        self.mox.UnsetStubs()

    def test_parse_region_ord(self):
        """Test Region Test for Ord."""

        ctx = {'region': 'ord'}
        self.assertEqual(identity.parse_region(auth_dict=ctx),
                         ('identity.api.rackspacecloud.com', True))

    def test_parse_region_dfw(self):
        """Test Region Test for dfw."""

        ctx = {'region': 'dfw'}
        self.assertEqual(identity.parse_region(auth_dict=ctx),
                         ('identity.api.rackspacecloud.com', True))

    def test_parse_region_syd(self):
        """Test Region Test for syd."""

        ctx = {'region': 'syd'}
        self.assertEqual(identity.parse_region(auth_dict=ctx),
                         ('identity.api.rackspacecloud.com', True))

    def test_parse_region_lon(self):
        """Test Region Test for lon."""

        ctx = {'region': 'lon'}
        self.assertEqual(identity.parse_region(auth_dict=ctx),
                         ('lon.identity.api.rackspacecloud.com', True))

    def test_parse_region_pri(self):
        """Test Region Test for Openstack."""

        ctx = {'region': 'RegionOne',
               'auth_url': 'http://someauthurl.something'}
        self.assertEqual(identity.parse_region(auth_dict=ctx),
                         ('http://someauthurl.something', False))

    def test_parse_region_nourl(self):
        """Test Region Test for unknown Region without an auth URL."""

        ctx = {'region': 'RegionOne'}
        with self.assertRaises(AttributeError):
            identity.authenticate(auth_dict=ctx)

    def test_parse_region_no(self):
        """Test Region Test for No Region."""

        ctx = {'username': 'testuser',
               'apikey': 'testkey'}
        self.assertEqual(identity.parse_region(auth_dict=ctx),
                         ('identity.api.rackspacecloud.com', True))

    def test_authenticate_nokey(self):
        """Test Get Token for Without a Key/Password."""

        ctx = {'region': 'ord',
               'username': 'testuser'}
        with self.assertRaises(AttributeError):
            identity.authenticate(auth_dict=ctx)

    def test_authenticate_inv(self):
        """Test Get Token For Invalid Reply."""

        ctx = {'region': 'ord',
               'username': 'testuser',
               'apikey': 'testkey'}

        response = FakeHttpResponse(status=200,
                                    reason='OK',
                                    headers=[('Foo', 'Bar')],
                                    body=self.inv_servicecat)
        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(mox.IgnoreArg(),
                                       mox.IgnoreArg(),
                                       mox.IgnoreArg(),
                                       mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(response)
        httplib.HTTPConnection.close()

        self.mox.ReplayAll()
        with self.assertRaises(identity.NoTenantIdFound):
            identity.authenticate(auth_dict=ctx)

    def test_authenticate_rax(self):
        """Test Get Token For RAX."""

        ctx = {'region': 'ord',
               'username': 'testuser',
               'apikey': 'testkey'}

        response = FakeHttpResponse(status=200,
                                    reason='OK',
                                    headers=[('Foo', 'Bar')],
                                    body=self.rax_servicecat)
        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(mox.IgnoreArg(),
                                       mox.IgnoreArg(),
                                       mox.IgnoreArg(),
                                       mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(response)
        httplib.HTTPConnection.close()

        self.mox.ReplayAll()
        self.assertEqual(identity.authenticate(auth_dict=ctx),
                         (u'12345678901234567890',
                          u'123456',
                          u'testuser',
                          json.loads(self.rax_servicecat)))

    def test_authenticate_pri(self):
        """Test Get Token For Openstack."""

        ctx = {'auth_url': 'http://someauthurl.something',
               'username': 'testuser',
               'password': 'testkey'}

        response = FakeHttpResponse(status=200,
                                    reason='OK',
                                    headers=[('Foo', 'Bar')],
                                    body=self.pri_servicecat)
        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(mox.IgnoreArg(),
                                       mox.IgnoreArg(),
                                       mox.IgnoreArg(),
                                       mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(response)
        httplib.HTTPConnection.close()
        self.mox.ReplayAll()
        self.assertEqual(identity.authenticate(auth_dict=ctx),
                         (u'12345678901234567890',
                          u'admin',
                          u'testuser',
                          json.loads(self.pri_servicecat)))

    def test_get_token(self):
        """Test Get Token Return on field 0."""

        ctx = {'region': 'testregion',
               'username': 'testuser',
               'password': 'testkey'}
        self.mox.StubOutWithMock(identity, 'get_token')
        identity.get_token(context=ctx).AndReturn('token')

        self.mox.ReplayAll()
        self.assertEqual(identity.get_token(context=ctx), 'token')


if __name__ == '__main__':
    # Run tests. Handle our parameters separately
    import sys

    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
