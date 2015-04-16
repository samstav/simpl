"""

Middleware that loads Rook routes and serves static files and necessary proxies
for auth and github (to avoid CORS limitations)

"""

import base64
import json
import logging
import os
import re
import time
from urlparse import urlparse

import bottle
import requests
from Crypto.Hash import MD5
from eventlet.green import httplib
from eventlet.green import socket
from eventlet.green import urllib
from eventlet.green import urllib2
import webob
from webob.exc import HTTPUnauthorized, HTTPNotFound

from checkmate.common import auth
from checkmate.common import config
from checkmate.middleware import keystone
from checkmate import utils
from checkmate.utils import (
    HANDLERS,
    write_body,
    read_body,
    support_only,
    get_time_string,
    import_class,
)
import rook


LOG = logging.getLogger(__name__)
CONFIG = config.current()
COOKIE_EXPIRES_FORMAT = "%a, %d-%b-%Y %T GMT"

__version_string__ = None

ROOK_STATIC = bottle.Bottle()
ROOK_API = bottle.Bottle()
GITHUB_TOKEN_EXPIRE_SECONDS = 60 * 60 * 24 * 365  # One year


def init_db():
    """Initialize the Feedback Database."""
    connection_string = os.environ.get('CHECKMATE_CONNECTION_STRING',
                                       'sqlite://')
    if connection_string.startswith('mongodb://'):
        driver_name = 'rook.db.feedback.MongoDriver'
    else:
        driver_name = 'rook.db.feedback.SqlDriver'
    driver = import_class(driver_name)
    return driver()

FEEDBACK_DB = init_db()

CATALOG_CACHE = {}  # mainly for iNova


class BrowserMiddleware(object):

    """Adds support for browser interaction and HTML content.

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

    supported = [
        'html',
        'gif',
        'ico',
        'jpeg',
        'jpg',
        'css',
        'js',
        'yml',
    ]

    def __init__(self, nextapp, config, proxy_endpoints=None,
                 with_simulator=False, with_admin=False):
        LOG.info("Loading Rook API")
        self.config = config
        self.nextapp = nextapp
        HANDLERS['application/vnd.github.v3.raw'] = write_raw
        self.proxy_endpoints = None
        if proxy_endpoints:
            self.proxy_endpoints = {
                endpoint['uri']: endpoint for endpoint in proxy_endpoints
            }
        self.with_simulator = with_simulator
        self.with_admin = with_admin

    def __call__(self, environ, handler):
        """Detect unauthenticated HTML calls and redirect them to root.

        This gets processed before the bottle routes
        """
        handler = self.start_response_callback(handler)
        try:
            token = environ.get('HTTP_X_AUTH_TOKEN')
            if token and token in CATALOG_CACHE:
                cached_response = CATALOG_CACHE[token]
                environ['context'].set_context(cached_response)
        except StandardError:
            pass
        try:
            ROOK_API.match(environ)
            environ['proxy_endpoints'] = self.proxy_endpoints
            return ROOK_API(environ, handler)
        except bottle.HTTPError:
            pass

        # .yaml, .json, and .xml not handled by rook
        #
        # Note: curl calls to .yaml resources will come with text/html or */*.
        # We need to pass those along
        path = environ['PATH_INFO']
        if path:
            extension = path.split('.')[-1]
            if (extension in ['yaml', 'json', 'wadl']):
                LOG.debug("Rook bypassing %s %s with extension %s",
                          environ['REQUEST_METHOD'], path, extension)
                return self.nextapp(environ, handler)

            if (extension in self.supported or
                    environ['PATH_INFO'].startswith('/static/')):
                LOG.debug("Rook handling %s %s with extension %s",
                          environ['REQUEST_METHOD'], path, extension)
                return ROOK_STATIC(environ, handler)

        accept = environ.get('HTTP_ACCEPT')
        if (accept and
                'application/json' not in accept and
                'application/x-yaml' not in accept):
            LOG.debug("Rook handling %s %s with accept header %s",
                      environ['REQUEST_METHOD'], path, accept)
            return ROOK_STATIC(environ, handler)

        return self.nextapp(environ, handler)

    def start_response_callback(self, start_response):
        """Intercepts upstream start_response and adds our headers."""
        def callback(status, headers, exc_info=None):
            """Add our headers to response"""
            if self.with_simulator:
                headers.append(("X-Simulator-Enabled", "True"))
            if self.config.github_api:
                headers.append(("X-Github-API", self.config.github_api))
            if self.config.github_client_id:
                headers.append(("X-Github-Client-ID",
                                self.config.github_client_id))
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


# Add static routes
@ROOK_STATIC.get('/marketing/<path:path>')
@support_only(['text/html', 'text/css', 'text/javascript'])
def marketing(path):
    """Returns files from the marketing path which have absolute links."""
    return bottle.static_file(path,
                              root=os.path.join(os.path.dirname(__file__),
                                                'static', 'marketing'))


@ROOK_STATIC.post('/autologin')
def autologin():
    """This handles automatic login from other systems."""
    fields = ['tenantId', 'token', 'username', 'api_key']
    for field in fields:
        value = bottle.request.forms.get(field) or ""
        bottle.response.add_header('Set-Cookie', '%s=%s' % (field, value))

    endpoint = bottle.request.forms.get('endpoint')
    endpoint = endpoint.replace('-internal', '')
    bottle.response.add_header('Set-Cookie', '%s=%s' % ('endpoint', endpoint))

    return bottle.static_file('index.html',
                              root=os.path.join(os.path.dirname(__file__),
                                                'static'))


@ROOK_STATIC.get('/')
@ROOK_STATIC.get('/<path:path>')
def static(path=None):
    """Expose UI."""
    root = os.path.join(os.path.dirname(__file__), 'static')
    # Ensure correct mimetype (bottle does not handle css)
    mimetype = 'auto'
    # bottle does not write this for css
    if path:
        if path.endswith('.css'):
            mimetype = 'text/css'
        elif path.endswith('.png'):
            mimetype = 'image/png'
        elif path.endswith('.gif'):
            mimetype = 'image/gif'
        elif path.endswith('.jpeg') or path.endswith('.jpeg'):
            mimetype = 'image/jpeg'
        elif path.endswith('.ico'):
            mimetype = 'image/x-icon'
        elif path.endswith('.yml'):
            mimetype = 'application/x-yaml'
    # Check if path exists and return it, otherwise serve index.html
    if path and os.path.exists(os.path.join(root, path)):
        return bottle.static_file(path, root=root, mimetype=mimetype)
    else:
        LOG.debug("Returning index.html because '%s' was not found", path)
        return bottle.static_file('/index.html', root=root, mimetype=mimetype)


#
# API calls (json)
#
@ROOK_API.get('/rookversion')
def get_rook_version():
    """Return api version information."""
    global __version_string__
    if not __version_string__:
        __version_string__ = rook.version()
    return write_body({"version": __version_string__},
                      bottle.request, bottle.response)


@ROOK_API.post('/accept-cookies')
@support_only(['application/json'])
def accept_cookies():
    """Accept client-side cookies from authenticated users on trusted systems.

    This call, used by a trusted system using `withCredentials` set to true,
    allows a trusted domain to set cookies on this server's domain.
    """
    if bottle.request.environ.get('CORS_TRUSTED_ORIGIN') is not True:
        return HTTPUnauthorized("Not a trusted CORS Origin")
    cookies = read_body(bottle.request)
    if cookies:
        one_day_away = time.gmtime(time.time() + (24 * 60 * 60))
        for key, params in cookies.items():
            params.setdefault('expires', one_day_away)
            params.setdefault('domain', bottle.request.urlparts.hostname)
            params.setdefault('path', '/')
            cookie_value = params.pop('value', None)
            if cookie_value is not None:
                for name, value in params.iteritems():
                    if isinstance(value, unicode):
                        params[name] = str(value)
                LOG.info("Cookie '%s' set from trusted CORS partner", key,
                         extra={'data': {key: params}})
                bottle.response.set_cookie(str(key), str(cookie_value),
                                           **params)

    bottle.response.set_header('Access-Control-Allow-Credentials', 'true')
    return bottle.response


@ROOK_API.post('/authproxy')
@ROOK_API.route('/authproxy/<path:path>', method=['POST', 'GET'])
@support_only(['application/json'])
def authproxy(path=None):
    """Proxy Auth Requests.

    The Ajax client cannot talk to auth because of CORS. This function
    allows it to authenticate through this server.
    """
    # Check for source
    source = bottle.request.get_header('X-Auth-Source')
    if not source:
        bottle.abort(401, "X-Auth-Source header not supplied. The header is "
                     "required and must point to a valid and permitted auth "
                     "endpoint.")

    url = urlparse(source)
    auth_root = url.scheme + "://" + url.hostname
    allowed_domain = False
    cache_catalog = False
    for uri, endpoint in bottle.request.environ['proxy_endpoints'].items():
        if uri.startswith(auth_root):
            allowed_domain = True
            cache_catalog = endpoint.get('kwargs', {}).get('cache_catalog')
            break

    if not allowed_domain:
        bottle.abort(401, "Auth endpoint not permitted: %s" % source)

    if bottle.request.body and getattr(bottle.request.body, 'len', -1) > 0:
        auth = read_body(bottle.request)
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
    http = http_class(host, port, timeout=10)

    headers = {}
    token = bottle.request.get_header('X-Auth-Token')
    if token:
        headers['X-Auth-Token'] = token
    headers['Content-Type'] = bottle.request.get_header('Content-Type',
                                                        'application/json')
    headers['Accept'] = bottle.request.get_header('Accept', 'application/json')

    # TODO: implement some caching to not overload auth
    LOG.debug('Proxy call to auth to %s', source)
    post_body = json.dumps(auth) if auth else None
    proxy_path = path or url.path
    if not proxy_path.startswith('/'):
        proxy_path = '/%s' % proxy_path
    try:
        http.request(bottle.request.method, proxy_path, body=post_body,
                     headers=headers)
        resp = http.getresponse()
        body = resp.read()
    except Exception as e:
        LOG.error('HTTP connection exception: %s', e)
        raise bottle.HTTPError(401, output='Unable to communicate with '
                               'keystone server')
    finally:
        http.close()

    if resp.status != 200:
        LOG.debug('Invalid authentication: %s', resp.reason)
        raise bottle.HTTPError(401, output=resp.reason)

    try:
        content = json.loads(body)
    except ValueError:
        msg = "Auth target did not return json-encoded body"
        LOG.debug(msg)
        raise bottle.HTTPError(401, output=msg)

    try:  # to detect if we just authenticated an admin
        for endpoint_url, endpoint in \
                bottle.request.environ['proxy_endpoints'].iteritems():
            if endpoint_url == source:
                role = endpoint.get('kwargs', {}).get('admin_role')
                if role:
                    if any(r for r in content['access']['user'].get('roles')
                           if r['name'] == role):
                        who = content['access']['user'].get('id', 'unknown')
                        LOG.debug("Admin authenticated: %s", who)
                        bottle.response.add_header('X-AuthZ-Admin', 'True')
    except StandardError as exc:
        LOG.debug("Ignored error checking roles: %s", exc)

    # Cache the catalog
    if cache_catalog and 'access' in content:
        try:
            CATALOG_CACHE[content['access']['token']['id']] = content
        except StandardError as exc:
            LOG.debug("Ignored error parsing response: %s", exc)

    return write_body(content, bottle.request, bottle.response)


@ROOK_API.get('/githubproxy/<path:path>')
@support_only(['application/json',
               'application/vnd.github.v3.raw'])
def githubproxy(path=None):
    """Proxy Github Requests.

    The Ajax client cannot talk to remote github servers because of
    CORS. This function proxies these calls through this server.

    The target server URL should be passed in through the
    X-Target-Url header.
    """
    source = bottle.request.get_header('X-Target-Url')
    if not source:
        bottle.abort(406, "X-Target-Url header not supplied. The header is "
                     "required and must point to a valid and permitted "
                     "git endpoint.")

    url = urlparse(source)
    if url.scheme == 'https':
        port = url.port or 443
    else:
        port = url.port or 80
    host = url.hostname

    query = urllib.urlencode(dict(bottle.request.query))
    query = '?%s' % query if query else ''

    auth = bottle.request.get_header('Authorization')
    if not auth:
        github_token = bottle.request.get_cookie('github_access_token')
        if github_token:
            auth = 'token %s' % github_token
    if not auth:
        # TODO (zns): we need to disable this at some point
        auth = 'token %s' % CONFIG.github_token
    headers = {
        'Accept': bottle.request.get_header('Accept', ['application/json']),
        'Authorization': auth,
        'Content-Type': bottle.request.get_header('Content-Type',
                                                  'application/json'),
    }
    body = None
    data = None
    try:
        request_url = (url.scheme + '://' + host + ':' + str(port) +
                       '/' + path + query)
        LOG.debug('Proxying github call to %s', request_url)
        req = urllib2.Request(request_url, data, headers)
        resp = urllib2.urlopen(req)
        status = resp.getcode()
        body = resp.read()
    except socket.gaierror as exc:
        LOG.error('HTTP connection exception: %s', exc)
        raise bottle.HTTPError(500, output="Unable to communicate with "
                               "github server: %s" % source)
    except urllib2.HTTPError as exc:
        LOG.error("HTTP connection exception of type '%s': %s",
                  exc.__class__.__name__, exc)
        raise bottle.HTTPError(exc.code, output="Unable to communicate with "
                               "github server")
    except Exception as exc:
        LOG.error("Caught exception of type '%s': %s",
                  exc.__class__.__name__, exc)
        raise bottle.HTTPError(401, output="Unable to communicate with "
                               "github server")

    if status != 200:
        LOG.debug('Invalid github call: %s\n\nBody: %s', resp.reason,
                  body)
        raise bottle.HTTPError(status, output=resp.reason)

    if 'application/json' in resp.info().getheader('Content-type'):
        try:
            content = json.loads(body)
        except ValueError:
            msg = 'Github did not return json-encoded body'
            LOG.debug(msg)
            raise bottle.HTTPError(status, output=msg)
    else:
        content = body

    return write_body(content, bottle.request, bottle.response)


@ROOK_API.get('/webhooks/github_auth')
@ROOK_API.get('/webhooks/github_auth/<path:re:.*>')
def github_callback(path=None):
    """Receive OAuth Callback from Github.

    This supports authenticating with Github.
    """
    path = path or ''
    session_code = bottle.request.query.get('code')
    body = {
        'client_id': CONFIG.github_client_id,
        'client_secret': CONFIG.github_client_secret,
        'code': session_code,
    }
    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
    }
    response = requests.post('https://github.com/login/oauth/access_token',
                             data=json.dumps(body), headers=headers)
    if response.ok:
        data = response.json()
        expires = time.time() + GITHUB_TOKEN_EXPIRE_SECONDS
        bottle.response.set_cookie('github_access_token', data['access_token'],
                                   expires=expires, path="/")
    bottle.redirect('/%s' % path)


@ROOK_API.route('/feedback', method=['POST', 'OPTIONS'])
@support_only(['application/json'])
def feedback():
    """Accepts feedback from UI."""
    if bottle.request.method == 'OPTIONS':
        origin = bottle.request.get_header('origin', 'http://noaccess')
        url = urlparse(origin)
        is_rax_pre_prod = 'chkmate.rackspace.net' in url.netloc
        is_rax_prod = (url.netloc == 'checkmate.rackspace.com')
        is_dev_box = (url.netloc == 'localhost:8080')
        if (is_rax_prod or is_rax_pre_prod or is_dev_box):
            bottle.response.add_header('Access-Control-Allow-Origin', origin)
            bottle.response.add_header('Access-Control-Allow-Methods',
                                       'POST, OPTIONS')
            bottle.response.add_header('Access-Control-Allow-Headers',
                                       'Origin, Accept, Content-Type, '
                                       'X-Requested-With, X-CSRF-Token, '
                                       'X-Auth-Source, X-Auth-Token')
        return write_body({}, bottle.request, bottle.response)
    user_feedback = read_body(bottle.request)
    if not user_feedback or 'feedback' not in user_feedback:
        bottle.abort(406, "Expecting a 'feedback' body in the request")
    token = bottle.request.get_header('X-Auth-Token')
    if token:
        user_feedback['feedback']['token'] = token
    user_feedback['feedback']['received'] = get_time_string()
    FEEDBACK_DB.save_feedback(user_feedback)
    return write_body(user_feedback, bottle.request, bottle.response)


# Wired to Checkmate!
@bottle.get('/admin/feedback')
@bottle.get('/admin/feedback.json')
@bottle.get('/admin/feedback/.json')
@support_only(['application/json'])
def get_admin():
    """Read feedback."""
    if bottle.request.path in ['/admin/feedback', '/admin/feedback/.json']:
        if bottle.request.environ['context'].is_admin is True:
            LOG.info("Administrator accessing feedback: %s",
                     bottle.request.environ['context'].username)
            results = FEEDBACK_DB.get_feedback()
            return write_body(results, bottle.request, bottle.response)
        else:
            bottle.abort(403, "Administrator privileges needed for this "
                         "operation")
    else:
        raise HTTPNotFound("File not found: %s" % bottle.request.path)


class RackspaceSSOAuthMiddleware(object):

    """Handle authentication for Rackers.

    Send X-Auth-token header or auth_token cookie to authenticate.
    Send X-Set-Auth-Cookie to return the token in the response as a cookie.
    Returns X-AuthZ-Admin if token belongs to an user in the admin role.
    Bypasses authentication if path matches one of regexes for anonymous_paths.
    """

    def __init__(self, app, endpoint, anonymous_paths=None, authenticator=None):
        """Require/check auth tokens to accompany requests."""
        # TODO(zns): port middleware interface to include authenticator & conf
        # BEGIN FAKE ARGUMENTS
        conf = CONFIG
        self.endpoint = endpoint
        endpoint_uri = endpoint['uri']
        kwargs = endpoint.get('kwargs') or {}
        conf['auth_endpoint'] = endpoint_uri
        conf['service_username'] = kwargs.get('username')
        conf['service_password'] = kwargs.get('password')
        conf['admin_role'] = kwargs.get('admin_role')
        authenticator = auth.SSOAuthenticator(conf)
        self.auth_header = authenticator.auth_header
        self.endpoint_uri = endpoint_uri
        if ('kwargs' in endpoint and 'realm' in endpoint['kwargs'] and
                'priority' in endpoint['kwargs']):
            self.auth_header = str('GlobalAuth uri="%s" realm="%s" '
                                   'priority="%s"' %
                                   (endpoint['uri'],
                                    endpoint['kwargs'].get('realm'),
                                    endpoint['kwargs'].get('priority')))
        elif 'kwargs' in endpoint and 'realm' in endpoint['kwargs']:
            self.auth_header = str('GlobalAuth uri="%s" realm="%s"' % (
                endpoint['uri'], endpoint['kwargs'].get('realm')))

        # END FAKE ARGUMENTS

        self.app = app
        self.authenticator = authenticator
        if anonymous_paths:
            self.anonymous_paths = [re.compile(p) for p in anonymous_paths]
        else:
            self.anonymous_paths = []
        LOG.info("Listening for SSO auth for %s", authenticator.endpoint_uri)

    def __call__(self, environ, start_response):
        """Authenticate calls with X-Auth-Token to the source auth service."""
        # Always add a WWW-Authenticate header
        extra_headers = [('WWW-Authenticate',
                          str(self.authenticator.auth_header))]
        start_response = self.start_response_callback(
            start_response, add_headers=extra_headers)

        # Skip authentication for anonymous paths
        request = webob.Request(environ)
        if any(path.match(request.path) for path in self.anonymous_paths):
            LOG.debug("Allow anonymous path: %s", request.path)
            return self.app(environ, start_response)

        # Fail authentication if we don't have a service_token
        if not self.authenticator.service_token:
            if not self.authenticator.service_username:
                exc = HTTPUnauthorized(
                    "Authentication misconfigured on server.")
                return exc(environ, start_response)
            self.authenticator._get_service_token()

        # Fail authentication if an auth token was not supplied
        token = (request.headers.get('X-Auth-Token') or
                 request.cookies.get("auth_token"))
        if not token:
            exc = HTTPUnauthorized("Token required for authentication.")
            return exc(environ, start_response)

        # Validate an auth token
        context = environ['context']
        try:
            content = self.authenticator.validate(token,
                                                  tenant=context.get('tenant'))
            # Let downstream WSGI apps know we authenticated
            environ['HTTP_X_AUTHORIZED'] = "Confirmed"
            # Return the token as a cookie if asked to do so
            if 'X-Set-Auth-Cookie' in request.headers:
                extra_headers.append(('Set-Cookie', 'auth_token=%s' % token))
            context['username'] = content['access']['user']['id']
            context['roles'] = content['access']['user'].get('roles')
            context['auth_token'] = token
            context['token_expiration'] = utils.parse_iso_time_string(
                content['access']['token']['expires'])
            # Let the client know the token belongs to an admin
            if (self.authenticator.admin_role and
                    any(r for r in context['roles']
                        if r['name'] == self.authenticator.admin_role)):
                environ['context']['is_admin'] = True
                LOG.debug("Admin authenticated: %s", context['username'])
                extra_headers.append(('X-AuthZ-Admin', 'True'))
            context.update_local_context()
            return self.app(environ, start_response)
        except HTTPUnauthorized as exc:
            return exc(environ, start_response)

    def start_response_callback(self, start_response, add_headers=None):
        """Intercept upstream start_response and adds headers."""
        def callback(status, headers, exc_info=None):
            """Intercept upstream start_response and adds headers."""
            # Add our header to response
            for header in add_headers:
                if header not in headers:
                    headers.append(header)
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


class BasicAuthMultiCloudMiddleware(object):
    """Implements basic auth to multiple cloud endpoints.

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
        """Initialize Multi-Cloud Router Middleware.

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
        for _, value in domains.iteritems():
            if value['protocol'] in ['keystone', 'keystone-rax']:
                value['middleware'] = (keystone.TokenAuthMiddleware(app,
                                       endpoint=value['endpoint']))

    def __call__(self, environ, start_response):
        """Authenticate basic auth calls to endpoints."""
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
                        LOG.debug('Detected domain authentication: %s', domain)
                        if domain in self.domains:
                            LOG.warning("Unrecognized domain: %s", domain)
                    else:
                        domain = 'default'
                    if domain in self.domains:
                        if self.domains[domain]['protocol'] == 'keystone':
                            context = environ['context']
                            try:
                                content = (self._auth_cloud_basic(context,
                                           uname, passwd,
                                           self.domains[domain]['middleware']))
                            except HTTPUnauthorized as exc:
                                return exc(environ, start_response)
                            context.set_context(content)
        return self.app(environ, start_response)

    def _auth_cloud_basic(self, context, uname, passwd, middleware):
        """Authenticates to Cloud."""
        cred_hash = MD5.new('%s%s%s' % (uname, passwd, middleware.endpoint)) \
            .hexdigest()
        if cred_hash in self.cache:
            content = self.cache[cred_hash]
            LOG.debug('Using cached catalog')
        else:
            try:
                LOG.debug('Authenticating to %s', middleware.endpoint)
                content = middleware._auth_keystone(context,
                                                    username=uname,
                                                    password=passwd)
                self.cache[cred_hash] = content
            except HTTPUnauthorized as exc:
                LOG.exception(exc)
                raise exc
        LOG.debug("Basic auth over Cloud authenticated '%s'", uname)
        return content

    def start_response_callback(self, start_response):
        """Intercepts upstream start_response and adds our headers."""
        def callback(status, headers, exc_info=None):
            """Intercepts upstream start_response and adds our headers."""
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
    """Write output in raw format."""
    bottle.response.set_header('Content-type', 'application/vnd.github.v3.raw')
    return data
