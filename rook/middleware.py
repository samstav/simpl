'''

Middleware that loads Rook routes and serves static files and necessary proxies
for auth and github (to avoid CORS limitations)

'''

import base64
import httplib
import json
import logging
import os
from socket import gaierror
import urllib2
from urlparse import urlparse

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
from checkmate.middleware import TokenAuthMiddleware, RequestContext
init_console_logging()
# pylint: disable=E0611
from bottle import (
    abort,
    Bottle,
    HTTPError,
    request,
    response,
    static_file,
)
from Crypto.Hash import MD5
import webob
import webob.dec
from webob.exc import HTTPUnauthorized, HTTPNotFound

import rook

LOG = logging.getLogger(__name__)

from checkmate.utils import (
    HANDLERS,
    write_body,
    read_body,
    support_only,
    get_time_string,
    import_class,
)

__version_string__ = None

ROOK_STATIC = Bottle()
ROOK_API = Bottle()


def init_db():
    '''Initialize the Feedback Database'''
    connection_string = os.environ.get('CHECKMATE_CONNECTION_STRING',
                                       'sqlite://')
    if connection_string.startswith('mongodb://'):
        driver_name = 'rook.db.feedback.MongoDriver'
    else:
        driver_name = 'rook.db.feedback.SqlDriver'
    driver = import_class(driver_name)
    return driver()

FEEDBACK_DB = init_db()


class BrowserMiddleware(object):
    """Adds support for browser interaction and HTML content

    Adds these paths:
        /favicon.ico - returns Checkmate icon
        /authproxy for Ajax clients to authenticate (to address CORS)
        /static to serve static files
        /images to serve static files for add-ons like RackspaceCalculator

    Handles text/html requests as follows:
        - authenticated: render using bottle routes and text/html HANDLER
        - unauthenticated to anonymous route: use normal bottle route
        - unauthenticated to resource route: render root UI so client can auth
    """

    def __init__(self, nextapp, proxy_endpoints=None,
                 with_simulator=False, with_admin=False):
        self.nextapp = nextapp
        HANDLERS['application/vnd.github.v3.raw'] = write_raw
        self.proxy_endpoints = None
        if proxy_endpoints:
            self.proxy_endpoints = [environ['uri'] for environ in
                                    proxy_endpoints]
        self.with_simulator = with_simulator
        self.with_admin = with_admin

    def __call__(self, environ, handler):
        """

        Detect unauthenticated HTML calls and redirect them to root.

        This gets processed before the bottle routes

        """
        handler = self.start_response_callback(handler)
        try:
            ROOK_API.match(environ)
            request.proxy_endpoints = self.proxy_endpoints
            return ROOK_API(environ, handler)
        except HTTPError:
            pass

        if 'text/html' in webob.Request(environ).accept:
            return ROOK_STATIC(environ, handler)
        elif environ['PATH_INFO'].endswith('.html'):  # Angular requests json
            return ROOK_STATIC(environ, handler)

        return self.nextapp(environ, handler)

    def start_response_callback(self, start_response):
        """Intercepts upstream start_response and adds our headers"""
        def callback(status, headers, exc_info=None):
            # Add our headers to response
            if self.with_simulator:
                headers.append(("X-Simulator-Enabled", "True"))
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


# Add static routes
@ROOK_STATIC.get('/favicon.ico')
def favicon():
    """Without this, browsers keep getting a 404 and users perceive
    slow response """
    return static_file('favicon.ico',
                       root=os.path.join(os.path.dirname(__file__),
                       'static'))


@ROOK_STATIC.get('/apple-touch-icon.png')
def apple_touch():
    """For iOS devices"""
    return static_file('apple-touch-icon.png',
                       root=os.path.join(os.path.dirname(__file__),
                       'static'))


@ROOK_STATIC.get('/images/<path:path>')  # for RackspaceCalculator
def images(path):
    """Expose image files"""
    root = os.path.join(os.path.dirname(__file__), 'static',
                        'RackspaceCalculator', 'images')
    return static_file(path, root=root)


@ROOK_STATIC.get('/marketing/<path:path>')
@support_only(['text/html', 'text/css', 'text/javascript'])
def marketing(path):
    '''Returns files from the marketing path which have absolute links'''
    return static_file(path,
                       root=os.path.join(os.path.dirname(__file__),
                                         'static', 'marketing'))


@ROOK_STATIC.post('/autologin')
def autologin():
    """This handles automatic login from other systems"""
    fields = ['tenantId', 'token', 'endpoint']
    for field in fields:
        value = request.forms.get(field) or ""
        response.add_header('Set-Cookie', '%s=%s' % (field, value))

    return static_file('index.html',
                       root=os.path.join(os.path.dirname(__file__),
                       'static'))


@ROOK_STATIC.get('/')
@ROOK_STATIC.get('/<path:path>')
#TODO: remove application/json and fix angular to call partials with
#  text/html
@support_only(['text/html', 'text/css', 'text/javascript', 'image/*',
               'application/json'])  # Angular calls template in json
def static(path=None):
    """Expose UI"""
    root = os.path.join(os.path.dirname(__file__), 'static')
    # Ensure correct mimetype (bottle does not handle css)
    mimetype = 'auto'
    # bottle does not write this for css
    if path and path.endswith('.css'):
        mimetype = 'text/css'
    # Check if path exists and return it, otherwise serve index.html
    if path and os.path.exists(os.path.join(root, path)):
        return static_file(path, root=root, mimetype=mimetype)
    else:
        return static_file('/index.html', root=root, mimetype=mimetype)


#
# API calls (json)
#
@ROOK_API.get('/rookversion')
def get_rook_version():
    """ Return api version information """
    global __version_string__
    if not __version_string__:
        __version_string__ = rook.version()
    return write_body({"version": __version_string__},
                      request, response)


@ROOK_API.post('/authproxy')
@ROOK_API.route('/authproxy/<path:path>', method=['POST', 'GET'])
@support_only(['application/json'])
def authproxy(path=None):
    """Proxy Auth Requests

    The Ajax client cannot talk to auth because of CORS. This function
    allows it to authenticate through this server.

    """
    # Check for source
    source = request.get_header('X-Auth-Source')
    if not source:
        abort(401, "X-Auth-Source header not supplied. The header is "
              "required and must point to a valid and permitted auth "
              "endpoint.")

    url = urlparse(source)
    domain = url.scheme + "://" + url.hostname
    allowed_domain = False
    for endpoint in request.proxy_endpoints:
        if endpoint.startswith(domain):
            allowed_domain = True

    if not allowed_domain:
        abort(401, "Auth endpoint not permitted: %s" % source)

    if request.body and getattr(request.body, 'len', -1) > 0:
        auth = read_body(request)
    else:
        auth = None

    # Prepare proxy call
    if url.scheme == 'https':
        http_class = httplib.HTTPSConnection
        port = url.port or 443
    else:
        http_class = httplib.HTTPConnection
        port = url.port or 80
    host = url.hostname
    http = http_class(host, port)

    headers = {}
    token = request.get_header('X-Auth-Token')
    if token:
        headers['X-Auth-Token'] = token
    headers['Content-type'] = 'application/json'
    headers['Accept'] = 'application/json'

    # TODO: implement some caching to not overload auth
    LOG.debug('Proxy call to auth to %s' % source)
    post_body = json.dumps(auth) if auth else None
    proxy_path = path or url.path
    if not proxy_path.startswith('/'):
        proxy_path = '/%s' % proxy_path
    try:
        http.request(request.method, proxy_path, body=post_body,
                     headers=headers)
        resp = http.getresponse()
        body = resp.read()
    except Exception, e:
        LOG.error('HTTP connection exception: %s' % e)
        raise HTTPError(401, output='Unable to communicate with '
                        'keystone server')
    finally:
        http.close()

    if resp.status != 200:
        LOG.debug('Invalid authentication: %s' % resp.reason)
        raise HTTPError(401, output=resp.reason)

    try:
        content = json.loads(body)
    except ValueError:
        msg = "Auth target did not return json-encoded body"
        LOG.debug(msg)
        raise HTTPError(401, output=msg)

    try:  # to detect if we just authenticated an admin
        for endpoint in request.proxy_endpoints:
            if endpoint['uri'] == source:
                role = endpoint.get('kwargs', {}).get('admin_role')
                if role:
                    roles = content['access']['user'].get('roles')
                    if {"name": role} in roles:
                        response.add_header('X-AuthZ-Admin', 'True')
    except StandardError:
        pass

    return write_body(content, request, response)


@ROOK_API.get('/githubproxy/<path:path>')
@support_only(['application/json',
               'application/vnd.github.v3.raw'])
def githubproxy(path=None):
    """Proxy Github Requests

    The Ajax client cannot talk to remote github servers because of
    CORS. This function proxies these calls through this server.

    The target server URL should be passed in through the
    X-Target-Url header.
    """
    source = request.get_header('X-Target-Url')
    if not source:
        abort(406, "X-Target-Url header not supplied. The header is "
              "required and must point to a valid and permitted "
              "git endpoint.")

    url = urlparse(source)
    if url.scheme == 'https':
        port = url.port or 443
    else:
        port = url.port or 80
    host = url.hostname

    headers = {
        'Accept': request.get_header('Accept', ['application/json']),
    }
    body = None
    data = None
    try:
        request_url = (url.scheme + '://' + host + ':' + str(port) +
                       '/' + path)
        LOG.debug('Proxying github call to %s' % request_url)
        req = urllib2.Request(request_url, data, headers)
        resp = urllib2.urlopen(req)
        status = resp.getcode()
        body = resp.read()
    except gaierror as exc:
        LOG.error('HTTP connection exception: %s', exc)
        raise HTTPError(500, output="Unable to communicate with "
                        "github server: %s" % source)
    except urllib2.HTTPError as exc:
        LOG.error("HTTP connection exception of type '%s': %s",
                  exc.__class__.__name__, exc)
        raise HTTPError(exc.code, output="Unable to communicate with "
                        "github server")
    except Exception as exc:
        LOG.error("Caught exception of type '%s': %s",
                  exc.__class__.__name__, exc)
        raise HTTPError(401, output="Unable to communicate with "
                        "github server")

    if status != 200:
        LOG.debug('Invalid github call: %s\n\nBody: %s', resp.reason,
                  body)
        raise HTTPError(status, output=resp.reason)

    if 'application/json' in resp.info().getheader('Content-type'):
        try:
            content = json.loads(body)
        except ValueError:
            msg = 'Github did not return json-encoded body'
            LOG.debug(msg)
            raise HTTPError(status, output=msg)
    else:
        content = body

    return write_body(content, request, response)


@ROOK_API.route('/feedback', method=['POST', 'OPTIONS'])
@support_only(['application/json'])
def feedback():
    """Accepts feedback from UI"""
    if request.method == 'OPTIONS':
        origin = request.get_header('origin', 'http://noaccess')
        url = urlparse(origin)
        is_rax_pre_prod = 'chkmate.rackspace.net' in url.netloc
        is_rax_prod = (url.netloc == 'checkmate.rackspace.com')
        is_dev_box = (url.netloc == 'localhost:8080')
        if (is_rax_prod or is_rax_pre_prod or is_dev_box):
            response.add_header('Access-Control-Allow-Origin', origin)
            response.add_header('Access-Control-Allow-Methods',
                                'POST, OPTIONS')
            response.add_header('Access-Control-Allow-Headers',
                                'Origin, Accept, Content-Type, '
                                'X-Requested-With, X-CSRF-Token, '
                                'X-Auth-Source, X-Auth-Token')
        return write_body({}, request, response)
    user_feedback = read_body(request)
    if not user_feedback or 'feedback' not in user_feedback:
        abort(406, "Expecting a 'feedback' body in the request")
    token = request.get_header('X-Auth-Token')
    if token:
        user_feedback['feedback']['token'] = token
    user_feedback['feedback']['received'] = get_time_string()
    FEEDBACK_DB.save_feedback(user_feedback)
    return write_body(user_feedback, request, response)


@ROOK_API.get('/admin/feedback')
@ROOK_API.get('/admin/feedback.json')
@ROOK_API.get('/admin/feedback/.json')
@support_only(['text/html', 'application/json'])
def get_admin():
    """Read feedback"""
    if request.path in ['/admin/feedback/', '/admin/feedback/.json']:
        if 'text/html' in request.get_header('Accept', ['text/html']):
            return static(path=None)
        else:
            if request.context.is_admin is True:
                LOG.info("Administrator accessing feedback: %s",
                         request.context.username)
                results = FEEDBACK_DB.get_feedback()
                return write_body(results, request, response)
            else:
                abort(403, "Administrator privileges needed for this "
                      "operation")
    else:
        raise HTTPNotFound("File not found: %s" % request.path)


class RackspaceSSOAuthMiddleware(object):
    def __init__(self, app, endpoint, anonymous_paths=None):
        self.app = app
        self.endpoint = endpoint
        self.anonymous_paths = anonymous_paths or []
        self.auth_header = 'GlobalAuth uri="%s"' % endpoint['uri']
        if 'kwargs' in endpoint and 'realm' in endpoint['kwargs'] and 'priority' in endpoint['kwargs']:
            self.auth_header = str('GlobalAuth uri="%s" realm="%s" priority="%s"' % (
                                   endpoint['uri'],
                                   endpoint['kwargs'].get('realm'),
                                   endpoint['kwargs'].get('priority')))
        elif 'kwargs' in endpoint and 'realm' in endpoint['kwargs']:
            self.auth_header = str('GlobalAuth uri="%s" realm="%s"' % (
                                   endpoint['uri'],
                                   endpoint['kwargs'].get('realm')))
        self.service_token = None
        self.service_username = endpoint['kwargs'].get('username')
        self.service_password = endpoint['kwargs'].get('password')
        if 'kwargs' in endpoint:
            self.admin_role = {"name": endpoint['kwargs'].get('admin_role')}
        else:
            self.admin_role = None

        # FIXME: temoporary logic. Make this get a new toiken when needed
        try:
            result = self._auth_keystone(RequestContext(),
                                         username=self.service_username,
                                         password=self.service_password)
            self.service_token = result['access']['token']['id']
        except Exception:
            LOG.error("Unable to authenticate to Global Auth. Endpoint '%s' "
                      "will be disabled", endpoint.get('kwargs', {}).
                      get('realm'))

    def __call__(self, environ, start_response):
        """Authenticate calls with X-Auth-Token to the source auth service"""
        path_parts = environ['PATH_INFO'].split('/')
        root = path_parts[1] if len(path_parts) > 1 else None
        if root in self.anonymous_paths:
            # Allow anything marked as anonymous
            return self.app(environ, start_response)

        start_response = self.start_response_callback(start_response)

        if 'HTTP_X_AUTH_TOKEN' in environ and self.service_token:
            context = request.context
            try:
                content = (self._validate_keystone(context,
                           token=environ['HTTP_X_AUTH_TOKEN']))
                environ['HTTP_X_AUTHORIZED'] = "Confirmed"
                if self.admin_role in content['access']['user']['roles']:
                    request.context.is_admin = True
            except HTTPUnauthorized as exc:
                LOG.exception(exc)
                return exc(environ, start_response)
            context.set_context(content)

        return self.app(environ, start_response)

    def _validate_keystone(self, context, token=None, username=None,
                           apikey=None, password=None):
        """Validates a Keystone Auth Token"""
        url = urlparse(self.endpoint['uri'])
        if url.scheme == 'https':
            http_class = httplib.HTTPSConnection
            port = url.port or 443
        else:
            http_class = httplib.HTTPConnection
            port = url.port or 80
        host = url.hostname

        http = http_class(host, port)

        path = os.path.join(url.path, token)
        if context.tenant:
            path = "%s?belongsTo=%s" % (path, context.tenant)
            LOG.debug("Validating on tenant '%s'", context.tenant)
        headers = {
            'X-Auth-Token': self.service_token,
            'Accept': 'application/json',
        }
        # TODO: implement some caching to not overload auth
        try:
            LOG.debug('Validating token with %s' % self.endpoint['uri'])
            http.request('GET', path, headers=headers)
            resp = http.getresponse()
            body = resp.read()
        except StandardError as exc:
            LOG.error('HTTP connection exception: %s', exc)
            raise HTTPUnauthorized('Unable to communicate with %s' %
                                   self.endpoint['uri'])
        finally:
            http.close()

        if resp.status != 200:
            LOG.debug('Invalid token for tenant: %s', resp.reason)
            raise HTTPUnauthorized("Token invalid or not valid for this "
                                   "tenant (%s)" % resp.reason,
                                   [('WWW-Authenticate', self.auth_header)])

        try:
            content = json.loads(body)
        except ValueError:
            msg = 'Keystone did not return json-encoded body'
            LOG.debug(msg)
            raise HTTPUnauthorized(msg)
        return content

    def _auth_keystone(self, context, token=None, username=None, apikey=None,
                       password=None):
        """Authenticates to keystone"""
        url = urlparse(self.endpoint['uri'])
        if url.scheme == 'https':
            http_class = httplib.HTTPSConnection
            port = url.port or 443
        else:
            http_class = httplib.HTTPConnection
            port = url.port or 80
        host = url.hostname

        http = http_class(host, port)
        if token:
            body = {"auth": {"token": {"id": token}}}
        elif password:
            body = {"auth": {"passwordCredentials": {
                    "username": username, 'password': password}}}
        elif apikey:
            body = {"auth": {"RAX-KSKEY:apiKeyCredentials": {
                    "username": username, 'apiKey': apikey}}}
        else:
            raise HTTPUnauthorized('No credentials supplied or detected')

        if context.tenant:
            auth = body['auth']
            auth['tenantId'] = context.tenant
            LOG.debug("Authenticating to tenant '%s'", context.tenant)
        headers = {
            'Content-type': 'application/json',
            'Accept': 'application/json',
        }
        # TODO: implement some caching to not overload auth
        try:
            LOG.debug('Authenticating to %s', self.endpoint['uri'])
            http.request('POST', url.path, body=json.dumps(body),
                         headers=headers)
            resp = http.getresponse()
            body = resp.read()
        except Exception as exc:
            LOG.error('HTTP connection exception: %s', exc)
            raise HTTPUnauthorized('Unable to communicate with %s' %
                                   self.endpoint['uri'])
        finally:
            http.close()

        if resp.status != 200:
            LOG.debug('Invalid token for tenant: %s', resp.reason)
            raise HTTPUnauthorized("Token invalid or not valid for this "
                                   "tenant (%s)" % resp.reason,
                                   [('WWW-Authenticate', self.auth_header)])

        try:
            content = json.loads(body)
        except ValueError:
            msg = 'Keystone did not return json-encoded body'
            LOG.debug(msg)
            raise HTTPUnauthorized(msg)
        return content

    def start_response_callback(self, start_response):
        """Intercepts upstream start_response and adds our headers"""
        def callback(status, headers, exc_info=None):
            """Intercepts upstream start_response and adds our headers"""
            # Add our headers to response
            header = ('WWW-Authenticate', self.auth_header)
            if header not in headers:
                headers.append(header)
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


class RackspaceImpersonationAuthMiddleware(TokenAuthMiddleware):
    def __init__(self, app, endpoint, anonymous_paths=None):
        self.app = app
        self.endpoint = endpoint
        self.anonymous_paths = anonymous_paths or []
        self.auth_header = 'GlobalAuthImpersonation uri="%s"' % endpoint['uri']
        if 'kwargs' in endpoint and 'realm' in endpoint['kwargs']:
            self.auth_header = str('GlobalAuthImpersonation uri="%s" '
                                   'realm="%s"' % (
                                   endpoint['uri'],
                                   endpoint['kwargs']['realm']))


class BasicAuthMultiCloudMiddleware(object):
    """Implements basic auth to multiple cloud endpoints

    - Authenticates any basic auth to PAM
        - 401 if fails
        - Mark authenticated as admin if true
    - Adds basic auth header to any returning calls so client knows basic
      auth is supported

    Usage:
        domains = {
                'UK': {
                        'protocol': 'keystone',
                        'endpoint':
                                'https://lon.identity.api.rackspacecloud.com/'
                                'v2.0/tokens',
                    },
                'US': {
                        'protocol': 'keystone',
                        'endpoint': 'https://identity.api.rackspacecloud.com/'
                        'v2.0/tokens',
                    },
            }
        next = middleware.BasicAuthMultiCloudMiddleware(next, domains=domains)

    """
    def __init__(self, app, domains=None):
        """
        :param domains: the hash of domains to authenticate against. Each key
                is a realm that points to a different cloud. The hash contains
                endpoint and protocol, which is one of:
                    keystone: using keystone protocol
        """
        self.domains = domains
        self.app = app
        self.cache = {}
        # For each endpoint, instantiate a middleware instance to process its
        # token auth calls. We'll route to it when appropriate
        for key, value in domains.iteritems():
            if value['protocol'] in ['keystone', 'keystone-rax']:
                value['middleware'] = (TokenAuthMiddleware(app,
                                       endpoint=value['endpoint']))

    def __call__(self, environ, start_response):
        # Authenticate basic auth calls to endpoints
        start_response = self.start_response_callback(start_response)

        if 'HTTP_AUTHORIZATION' in environ:
            auth = environ['HTTP_AUTHORIZATION'].split()
            if len(auth) == 2:
                if auth[0].lower() == "basic":
                    creds = base64.b64decode(auth[1]).split(':')
                    if len(creds) != 2:
                        return (HTTPUnauthorized('Invalid credentials')
                                (environ, start_response))
                    uname, passwd = creds
                    if '\\' in uname:
                        domain, uname = uname.split('\\')
                        LOG.debug('Detected domain authentication: %s' %
                                  domain)
                        if domain in self.domains:
                            LOG.warning("Unrecognized domain: %s" % domain)
                    else:
                        domain = 'default'
                    if domain in self.domains:
                        if self.domains[domain]['protocol'] == 'keystone':
                            context = request.context
                            try:
                                content = (self._auth_cloud_basic(context,
                                           uname, passwd,
                                           self.domains[domain]['middleware']))
                            except HTTPUnauthorized as exc:
                                return exc(environ, start_response)
                            context.set_context(content)
        return self.app(environ, start_response)

    def _auth_cloud_basic(self, context, uname, passwd, middleware):
        """Authenticates to Cloud"""
        cred_hash = MD5.new('%s%s%s' % (uname, passwd, middleware.endpoint)) \
            .hexdigest()
        if cred_hash in self.cache:
            content = self.cache[cred_hash]
            LOG.debug('Using cached catalog')
        else:
            try:
                LOG.debug('Authenticating to %s' % middleware.endpoint)
                content = (middleware._auth_keystone(context,
                           username=uname, password=passwd))
                self.cache[cred_hash] = content
            except HTTPUnauthorized as exc:
                LOG.exception(exc)
                raise exc
        LOG.debug("Basic auth over Cloud authenticated '%s'" % uname)
        return content

    def start_response_callback(self, start_response):
        """Intercepts upstream start_response and adds our headers"""
        def callback(status, headers, exc_info=None):
            """Intercepts upstream start_response and adds our headers"""
            # Add our headers to response
            if self.domains:
                for key, value in self.domains.iteritems():
                    if value['protocol'] in ['keystone', 'keystone-rax']:
                        headers.extend([
                            ('WWW-Authenticate', 'Basic realm="%s"' % key),
                            ('WWW-Authenticate', 'Keystone uri="%s"' %
                             value['endpoint']),
                        ])
                    elif value['protocol'] == 'PAM':
                        headers.append(('WWW-Authenticate', 'Basic'))
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


def write_raw(data, request, response):
    """Write output in raw format"""
    response.set_header('content-type', 'application/vnd.github.v3.raw')
    return data
