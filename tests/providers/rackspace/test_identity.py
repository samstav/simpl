import logging
import unittest
import httplib
import json
import mox

from checkmate.providers.rackspace import identity

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
            "access": {
                "token": {
                    "RAX-AUTH:authenticatedBy": ["APIKEY"],
                    "expires": "2013-08-01T20:35:04.450-05:00",
                    "id": "12345678901234567890",
                    "tenant": {
                        "id": "123456",
                        "name": "123456"
                    }
                }
            }
        })
        self.pri_servicecat = json.dumps({
            "access": {
                "token": {
                    "expires": "2013-08-02T19:36:42Z",
                    "id": "12345678901234567890"
                },
                "user": {
                    "username": "admin",
                    "roles_links": [],
                    "id": "1234567890",
                    "roles": [],
                    "name": "admin"
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
        self.assertEqual(identity.parse_region(context=ctx),
                         ('identity.api.rackspacecloud.com', True))

    def test_parse_region_dfw(self):
        """Test Region Test for dfw."""

        ctx = {'region': 'dfw'}
        self.assertEqual(identity.parse_region(context=ctx),
                         ('identity.api.rackspacecloud.com', True))

    def test_parse_region_syd(self):
        """Test Region Test for syd."""

        ctx = {'region': 'syd'}
        self.assertEqual(identity.parse_region(context=ctx),
                         ('identity.api.rackspacecloud.com', True))

    def test_parse_region_lon(self):
        """Test Region Test for lon."""

        ctx = {'region': 'lon'}
        self.assertEqual(identity.parse_region(context=ctx),
                         ('lon.identity.api.rackspacecloud.com', True))

    def test_parse_region_pri(self):
        """Test Region Test for Openstack."""

        ctx = {'region': 'RegionOne',
               'auth_url': 'http://someauthurl.something'}
        self.assertEqual(identity.parse_region(context=ctx),
                         ('http://someauthurl.something', False))

    def test_parse_region_nourl(self):
        """Test Region Test for unknown Region without an auth URL."""

        ctx = {'region': 'RegionOne'}
        with self.assertRaises(AttributeError):
            identity.parse_region(context=ctx)

    def test_parse_region_no(self):
        """Test Region Test for No Region."""

        with self.assertRaises(AttributeError):
            identity.parse_region(context=None)

    def test_get_token_nokey(self):
        """Test Get Token for Without a Key/Password."""

        ctx = {'region': 'ord',
               'username': 'testuser'}
        with self.assertRaises(AttributeError):
            identity.get_token(context=ctx)

    def test_get_token_inv(self):
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
        with self.assertRaises(identity.NoTenatIdFound):
            identity.get_token(context=ctx)

    def test_get_token_rax(self):
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
        self.assertEqual(identity.get_token(context=ctx),
                         '12345678901234567890')

    def test_get_token_pri(self):
        """Test Get Token For Openstack."""

        ctx = {'region': 'ord',
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
        self.assertEqual(identity.get_token(context=ctx),
                         '12345678901234567890')


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