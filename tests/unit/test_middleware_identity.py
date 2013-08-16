# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
# Not sure why but "No value passed for parameter 'self'" throughout test
# pylint: disable=E1120
import httplib
import json
import logging
import unittest

import mox

from checkmate.middleware.os_auth import auth_utils
from checkmate.middleware.os_auth import exceptions
from checkmate.middleware.os_auth import identity


LOG = logging.getLogger(__name__)


class FakeHttpResponse(object):
    """Setup a FAKE http response."""

    def __init__(self, status, reason, headers, body):
        """Accept user input and return a response for HTTP

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


class TestIdentity(unittest.TestCase):
    """Test Identity Provider."""

    def setUp(self):
        """Setup Unittest with Mox."""

        super(TestIdentity, self).setUp()
        self.mox = mox.Mox()
        self.mox.StubOutWithMock(httplib.HTTPConnection, 'connect')
        self.mox.StubOutWithMock(httplib.HTTPConnection, 'request')
        self.mox.StubOutWithMock(httplib.HTTPConnection, 'getresponse')
        self.mox.StubOutWithMock(httplib.HTTPConnection, 'close')

        # All Service Catalogs
        self.nouser_servicecat = json.dumps({
            u"access": {
                u"token": {
                    u"expires": u"2013-08-02T19:36:42Z",
                    u"id": u"12345678901234567890"
                }
            }
        })
        self.inv_servicecat = json.dumps({
            u"access": {
                u"token": {
                    u"expires": u"2013-08-02T19:36:42Z",
                    u"id": u"12345678901234567890"
                },
                u"user": {
                    u"RAX-AUTH:defaultRegion": u"SOMEREGION",
                    u"id": u"123456",
                    u"name": u"testuser"
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
                },
                u"user": {
                    u"RAX-AUTH:defaultRegion": u"SOMEREGION",
                    u"id": u"123456",
                    u"name": u"testuser"
                }
            }
        })
        self.unscoped_response = json.dumps({
            u"access": {
                u"token": {
                    u"expires": u"2013-08-02T19:36:42Z",
                    u"id": u"12345678901234567890",
                },
                u"user": {
                    u"username": u"testuser",
                    u"roles_links": [],
                    u"id": u"1234567890",
                    u"roles": [],
                    u"name": u"testuser"
                }
            }
        })
        self.scoped_response = json.dumps({
            u"access": {
                u"token": {
                    u"expires": u"2013-08-02T19:36:42Z",
                    u"id": u"12345678901234567890",
                    u"tenant": {
                        u"description": u"Test Tenant",
                        u"enabled": True,
                        u"id": u"3b2602019a73496485dd87d11e720e39",
                        u"name": u"T1000"
                    },
                },
                u"user": {
                    u"username": u"testuser",
                    u"roles_links": [],
                    u"id": u"1234567890",
                    u"roles": [],
                    u"name": u"testuser"
                }
            }
        })

    def tearDown(self):
        """Tear down Unittest with Mox."""

        super(TestIdentity, self).tearDown()
        self.mox.UnsetStubs()

    def test_is_https_true_rax(self):
        """If URL is https or HTTP."""

        url = 'https://identity.api.rackspacecloud.com'
        rax = True
        self.assertEqual(auth_utils.is_https(url=url, rax=rax), True)

    def test_is_https_false_rax(self):
        """If URL is https or HTTP."""

        url = 'http://identity.api.rackspacecloud.com'
        rax = True
        self.assertEqual(auth_utils.is_https(url=url, rax=rax), True)

    def test_is_https_true_pri(self):
        """If URL is https or HTTP."""

        url = 'https://something.else'
        rax = False
        self.assertEqual(auth_utils.is_https(url=url, rax=rax), True)

    def test_is_https_false_pri(self):
        """If URL is https or HTTP."""

        url = 'http://something.else'
        rax = False
        self.assertEqual(auth_utils.is_https(url=url, rax=rax), False)

    def test_parse_url_https(self):
        """If URL is https or HTTP."""

        url = 'https://identity.api.rackspacecloud.com'
        self.assertEqual(auth_utils.parse_url(url=url),
                         'identity.api.rackspacecloud.com')

    def test_parse_url_http(self):
        """If URL is https or HTTP."""

        url = 'http://identity.api.rackspacecloud.com'
        self.assertEqual(auth_utils.parse_url(url=url),
                         'identity.api.rackspacecloud.com')

    def test_parse_auth_response_negative(self):
        """Parse Auth Response and return Token, TenantID and Username."""

        parsed_response = json.loads(self.nouser_servicecat)
        with self.assertRaises(exceptions.NoTenantIdFound):
            auth_utils.parse_auth_response(parsed_response)

    def test_parse_auth_response_unscoped(self):
        """Parse Auth Response and return Token, TenantID and Username."""

        parsed_response = json.loads(self.unscoped_response)
        self.assertEqual(auth_utils.parse_auth_response(parsed_response),
                         ('12345678901234567890', None, 'testuser'))

    def test_parse_auth_response_scoped(self):
        """Parse Auth Response and return Token, TenantID and Username."""

        parsed_response = json.loads(self.scoped_response)
        self.assertEqual(auth_utils.parse_auth_response(parsed_response),
                         ('12345678901234567890', 'T1000', 'testuser'))

    def test_parse_auth_response_rax(self):
        """Parse Auth Response and return Token, TenantID and Username."""

        parsed_response = json.loads(self.rax_servicecat)
        self.assertEqual(auth_utils.parse_auth_response(parsed_response),
                         ('12345678901234567890', '123456', 'testuser'))

    def test_parse_reqtype_inv(self):
        auth_dict = {'auth_url': 'identity.api.rackspacecloud.com',
                     'username': 'TestUser',
                     'tenant': '123456',
                     'apikey': None,
                     'password': None,
                     'token': None}
        with self.assertRaises(AttributeError):
            auth_utils.parse_reqtype(auth_body=auth_dict)

    def test_parse_reqtype_token(self):
        auth_dict = {'auth_url': 'identity.api.rackspacecloud.com',
                     'username': 'TestUser',
                     'tenant': '123456',
                     'apikey': None,
                     'password': None,
                     'token': '12345678901234567890'}
        auth_body = {'auth': {
            'tenantName': '123456',
            'token': {
                'id': '12345678901234567890'},
        }}
        self.assertEqual(auth_utils.parse_reqtype(auth_body=auth_dict),
                         auth_body)

    def test_parse_reqtype_password(self):
        auth_dict = {'auth_url': 'identity.api.rackspacecloud.com',
                     'username': 'TestUser',
                     'tenant': '123456',
                     'apikey': None,
                     'password': 'password1234',
                     'token': None}
        auth_body = {'auth': {
            'passwordCredentials': {
                'username': 'TestUser',
                'password': 'password1234'
            }
        }}

        self.assertEqual(auth_utils.parse_reqtype(auth_body=auth_dict),
                         auth_body)

    def test_parse_reqtype_apikey(self):
        auth_dict = {'auth_url': 'identity.api.rackspacecloud.com',
                     'username': 'TestUser',
                     'tenant': '123456',
                     'apikey': 'ThisIsAnApiKey1234567890',
                     'password': None,
                     'token': None}
        auth_body = {'auth': {
            'RAX-KSKEY:apiKeyCredentials': {
                'username': 'TestUser',
                'apiKey': 'ThisIsAnApiKey1234567890'}
        }}

        self.assertEqual(auth_utils.parse_reqtype(auth_body=auth_dict),
                         auth_body)

    def test_parse_region_ord(self):
        """Test Region Test for Ord."""

        ctx = {'region': 'ord'}
        self.assertEqual(auth_utils.parse_region(auth_dict=ctx),
                         ('identity.api.rackspacecloud.com', True))

    def test_parse_region_dfw(self):
        """Test Region Test for dfw."""

        ctx = {'region': 'dfw'}
        self.assertEqual(auth_utils.parse_region(auth_dict=ctx),
                         ('identity.api.rackspacecloud.com', True))

    def test_parse_region_syd(self):
        """Test Region Test for syd."""

        ctx = {'region': 'syd'}
        self.assertEqual(auth_utils.parse_region(auth_dict=ctx),
                         ('identity.api.rackspacecloud.com', True))

    def test_parse_region_lon(self):
        """Test Region Test for lon."""

        ctx = {'region': 'lon'}
        self.assertEqual(auth_utils.parse_region(auth_dict=ctx),
                         ('lon.identity.api.rackspacecloud.com', True))

    def test_parse_region_pri(self):
        """Test Region Test for Openstack."""

        ctx = {'region': 'RegionOne',
               'auth_url': 'http://someauthurl.something'}
        self.assertEqual(auth_utils.parse_region(auth_dict=ctx),
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
        self.assertEqual(auth_utils.parse_region(auth_dict=ctx),
                         ('identity.api.rackspacecloud.com', True))

    def test_request_invalid_url(self):
        """Test Get Token For Invalid Reply."""

        self.mox.ReplayAll()
        with self.assertRaises(identity.HTTPUnauthorized):
            auth_utils.request_process(aurl='http://thisisnotaurl.things',
                                       req=(None, None, None, None))

    def test_request_invalid_reponse(self):
        """Test Get Token For Invalid Reply."""

        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(method=mox.IgnoreArg(),
                                       url=mox.IgnoreArg(),
                                       body=mox.IgnoreArg(),
                                       headers=mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(None)
        httplib.HTTPConnection.close()

        self.mox.ReplayAll()
        with self.assertRaises(AttributeError):
            auth_utils.request_process(aurl='identity.api.rackspacecloud.com',
                                       req=(None, None, None, None))

    def test_request_bad_status_code(self):
        """Test Get Token For RAX."""

        message = json.dumps({'message': 'Go Away bad person'})
        response = FakeHttpResponse(status=401,
                                    reason='NotAuthorized',
                                    headers=[('Foo', 'Bar')],
                                    body=message)

        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(method=mox.IgnoreArg(),
                                       url=mox.IgnoreArg(),
                                       body=mox.IgnoreArg(),
                                       headers=mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(response)
        httplib.HTTPConnection.close()

        self.mox.ReplayAll()
        with self.assertRaises(auth_utils.HTTPUnauthorized):
            auth_utils.request_process(aurl='identity.api.rackspacecloud.com',
                                       req=(None, None, None, None))

    def test_request_pri(self):
        """Test Get Token For RAX."""

        response = FakeHttpResponse(status=200,
                                    reason='OK',
                                    headers=[('Foo', 'Bar')],
                                    body=self.unscoped_response)

        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(method=mox.IgnoreArg(),
                                       url=mox.IgnoreArg(),
                                       body=mox.IgnoreArg(),
                                       headers=mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(response)
        httplib.HTTPConnection.close()

        self.mox.ReplayAll()
        self.assertEqual(
            auth_utils.request_process(aurl='someauthurl.something',
                                       req=(None, None, None, None),
                                       https=False),
            self.unscoped_response
        )

    def test_request_rax(self):
        """Test Get Token For RAX."""

        response = FakeHttpResponse(status=200,
                                    reason='OK',
                                    headers=[('Foo', 'Bar')],
                                    body=self.rax_servicecat)

        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(method=mox.IgnoreArg(),
                                       url=mox.IgnoreArg(),
                                       body=mox.IgnoreArg(),
                                       headers=mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(response)
        httplib.HTTPConnection.close()

        self.mox.ReplayAll()
        self.assertEqual(
            auth_utils.request_process(aurl='identity.api.rackspacecloud.com',
                                       req=(None, None, None, None)),
            self.rax_servicecat
        )

    def test_authenticate_nokey(self):
        """Test Get Token for Without a Key/Password."""

        ctx = {'region': 'ord',
               'username': 'testuser'}
        with self.assertRaises(AttributeError):
            identity.authenticate(auth_dict=ctx)

    def test_authenticate_rax(self):
        """Test Authenticate for Rackspace."""

        ctx = {'auth_url': 'identity.api.rackspacecloud.com',
               'username': 'testuser',
               'password': 'testkey'}

        response = FakeHttpResponse(status=200,
                                    reason='OK',
                                    headers=[('Foo', 'Bar')],
                                    body=self.rax_servicecat)

        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(method=mox.IgnoreArg(),
                                       url=mox.IgnoreArg(),
                                       body=mox.IgnoreArg(),
                                       headers=mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(response)
        httplib.HTTPConnection.close()

        self.mox.ReplayAll()
        self.assertEqual(identity.authenticate(auth_dict=ctx),
                         (u'12345678901234567890',
                          u'123456',
                          u'testuser',
                          json.loads(self.rax_servicecat)))

    def test_authenticate_unscoped(self):
        """Test Authenticate For Openstack."""

        ctx = {'auth_url': 'http://someauthurl.something',
               'username': 'testuser',
               'password': 'testkey'}

        response = FakeHttpResponse(status=200,
                                    reason='OK',
                                    headers=[('Foo', 'Bar')],
                                    body=self.unscoped_response)
        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(method=mox.IgnoreArg(),
                                       url=mox.IgnoreArg(),
                                       body=mox.IgnoreArg(),
                                       headers=mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(response)
        httplib.HTTPConnection.close()
        self.mox.ReplayAll()
        self.assertEqual(identity.authenticate(auth_dict=ctx),
                         (u'12345678901234567890',
                          None,
                          u'testuser',
                          json.loads(self.unscoped_response)))

    def test_authenticate_scoped(self):
        """Test Authenticate For Openstack."""

        ctx = {'auth_url': 'http://someauthurl.something',
               'username': 'testuser',
               'password': 'testkey',
               'tenant': 'T1000'}

        response = FakeHttpResponse(status=200,
                                    reason='OK',
                                    headers=[('Foo', 'Bar')],
                                    body=self.scoped_response)
        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(method=mox.IgnoreArg(),
                                       url=mox.IgnoreArg(),
                                       body=mox.IgnoreArg(),
                                       headers=mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(response)
        httplib.HTTPConnection.close()
        self.mox.ReplayAll()
        self.assertEqual(identity.authenticate(auth_dict=ctx),
                         (u'12345678901234567890',
                          u'T1000',
                          u'testuser',
                          json.loads(self.scoped_response)))

    def test_get_token(self):
        """Test Get Token Return on field 0."""

        ctx = {'region': 'testregion',
               'username': 'testuser',
               'password': 'testkey'}

        self.mox.StubOutWithMock(identity, 'get_token')
        identity.get_token(context=ctx).AndReturn('token')

        self.mox.ReplayAll()
        self.assertEqual(identity.get_token(context=ctx), 'token')

    def test_auth_token_validate_valid(self):
        """Test Token Validation Openstack."""

        ctx = {'auth_url': 'the.auth.url.something',
               'token': '12345678901234567890',
               'tenant': '123456',
               'service_token': '09876543210987654321'}

        response = FakeHttpResponse(status=200,
                                    reason='OK',
                                    headers=[('Foo', 'Bar')],
                                    body=self.unscoped_response)

        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(method=mox.IgnoreArg(),
                                       url=mox.IgnoreArg(),
                                       body=mox.IgnoreArg(),
                                       headers=mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(response)
        httplib.HTTPConnection.close()

        self.mox.ReplayAll()
        self.assertEqual(identity.auth_token_validate(auth_dict=ctx),
                         json.loads(self.unscoped_response))

    def test_auth_token_validate_inv(self):
        """Test Token Validation Openstack."""

        ctx = {'auth_url': 'the.auth.url.something',
               'token': '12345678901234567890',
               'tenant': '123456',
               'service_token': '09876543210987654321'}

        response = FakeHttpResponse(status=200,
                                    reason='OK',
                                    headers=[('Foo', 'Bar')],
                                    body='NOTJSON')

        httplib.HTTPConnection.connect()
        httplib.HTTPConnection.request(method=mox.IgnoreArg(),
                                       url=mox.IgnoreArg(),
                                       body=mox.IgnoreArg(),
                                       headers=mox.IgnoreArg())
        httplib.HTTPConnection.getresponse().AndReturn(response)
        httplib.HTTPConnection.close()

        self.mox.ReplayAll()
        with self.assertRaises(identity.HTTPUnauthorized):
            identity.auth_token_validate(auth_dict=ctx)


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
