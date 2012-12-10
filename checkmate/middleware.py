import base64
import copy
import httplib
import json
import logging

# some distros install as PAM (Ubuntu, SuSE)
# https://bugs.launchpad.net/keystone/+bug/938801
try:
    import pam
except ImportError:
    import PAM
from urlparse import urlparse

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
from bottle import get, request, response, abort
from Crypto.Hash import MD5
import webob
import webob.dec
from webob.exc import HTTPNotFound, HTTPUnauthorized, HTTPFound

LOG = logging.getLogger(__name__)


from checkmate.db import any_tenant_id_problems
from checkmate.exceptions import CheckmateException
from checkmate.utils import RESOURCES, STATIC, to_json, to_yaml


def generate_response(self, environ, start_response):
    """A patch for webob.exc.WSGIHTTPException to handle YAML and JSON"""
    if self.content_length is not None:
        del self.content_length
    headerlist = list(self.headerlist)
    accept = environ.get('HTTP_ACCEPT', '')
    if accept and 'html' in accept or '*/*' in accept:
        content_type = 'text/html'
        body = self.html_body(environ)
    elif accept and 'yaml' in accept:
        content_type = 'application/x-yaml'
        data = dict(error=dict(explanation=self.__str__(), code=self.code,
                               description=self.title))
        body = to_yaml(data)
    elif accept and 'json' in accept:
        content_type = 'application/json'
        data = dict(error=dict(explanation=self.__str__(), code=self.code,
                               description=self.title))
        body = to_json(data)
    else:
        content_type = 'text/plain'
        body = self.plain_body(environ)
    extra_kw = {}
    if isinstance(body, unicode):
        extra_kw.update(charset='utf-8')
    resp = webob.Response(body, status=self.status,
                          headerlist=headerlist,
                          content_type=content_type,
                          **extra_kw)
    resp.content_type = content_type
    return resp(environ, start_response)

# Patch webob to support YAML and JSON
webob.exc.WSGIHTTPException.generate_response = generate_response


class TenantMiddleware(object):
    """Strips /tenant_id/ from path and puts it in context

    This is needed by the authz middleware too
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Clear headers if supplied (anti-spoofing)
        self._remove_auth_headers(environ)

        if environ['PATH_INFO'] in [None, "", "/"]:
            pass  # Not a tenant call
        else:
            path_parts = environ['PATH_INFO'].split('/')
            tenant = path_parts[1]
            if tenant in RESOURCES or tenant in STATIC:
                pass  # Not a tenant call
            else:
                errors = any_tenant_id_problems(tenant)
                if errors:
                    return HTTPNotFound(errors)(environ, start_response)
                context = request.context
                rewrite = "/%s" % '/'.join(path_parts[2:])
                LOG.debug("Rewrite for tenant %s from '%s' "
                          "to '%s'" % (tenant, environ['PATH_INFO'], rewrite))
                context.tenant = tenant
                environ['PATH_INFO'] = rewrite

        return self.app(environ, start_response)

    def _remove_auth_headers(self, env):
        """Remove headers so a user can't fake authentication.

        :param env: wsgi request environment

        """
        auth_headers = (
            'X-Identity-Status',
            'X-Tenant-Id',
            'X-Tenant-Name',
            'X-User-Id',
            'X-User-Name',
            'X-Roles',
            # Deprecated
            'X-User',
            'X-Tenant',
            'X-Role',
        )
        self._remove_headers(env, auth_headers)

    def _remove_headers(self, env, keys):
        """Remove http headers from environment."""
        for k in keys:
            env_key = self._header_to_env_var(k)
            if env_key in env:
                LOG.debug('Removing header from request environment: %s' %
                          env_key)
                del env[env_key]

    def _header_to_env_var(self, key):
        """Convert header to wsgi env variable.

        :param key: http header name (ex. 'X-Auth-Token')
        :return wsgi env variable name (ex. 'HTTP_X_AUTH_TOKEN')

        """
        return  'HTTP_%s' % key.replace('-', '_').upper()

    def _add_headers(self, env, headers):
        """Add http headers to environment."""
        for (key, value) in headers.iteritems():
            env_key = self._header_to_env_var(key)
            env[env_key] = value


class PAMAuthMiddleware(object):
    """Authenticate basic auth calls to PAM and optionally mark user as admin

    - Authenticates any basic auth to PAM
        - 401 if fails
        - Mark authenticated as admin if all_admins is set
        - checks for domain if set. Ignores other domains otherwise
    - Adds basic auth header to any returning calls so client knows basic
      auth is supported
    """
    def __init__(self, app, domain=None, all_admins=False):
        self.app = app
        self.domain = None  # Which domain to authenticate in this instance
        self.all_admins = all_admins  # Does this authenticate admins?

    def __call__(self, environ, start_response):
        # Authenticate basic auth calls to PAM
        #TODO: this header is not being returned in a 401
        start_response = self.start_response_callback(start_response)
        context = request.context

        if 'HTTP_AUTHORIZATION' in environ:
            if getattr(context, 'authenticated', False) is True:
                return self.app(environ, start_response)

            auth = environ['HTTP_AUTHORIZATION'].split()
            if len(auth) == 2:
                if auth[0].lower() == "basic":
                    login, passwd = base64.b64decode(auth[1]).split(':')
                    username = login
                    if self.domain:
                        if '\\' in login:
                            domain = login.split('\\')[0]
                            if domain != self.domain:
                                # Does not apply to this instance. Pass through
                                return self.app(environ, start_response)
                            username = login.split('\\')[len(domain) + 1:]
                    # TODO: maybe implement some caching?
                    if not pam.authenticate(login, passwd, service='login'):
                        LOG.debug('PAM failing request because of bad creds')
                        return (HTTPUnauthorized("Invalid credentials")
                                (environ, start_response))
                    LOG.debug("PAM authenticated '%s' as admin" % login)
                    context.domain = self.domain
                    context.username = username
                    context.authenticated = True
                    context.is_admin = self.all_admins

        return self.app(environ, start_response)

    def start_response_callback(self, start_response):
        """Intercepts upstream start_response and adds our headers"""
        def callback(status, headers, exc_info=None):
            """Intercepts upstream start_response and adds our headers"""
            # Add our headers to response
            headers.append(('WWW-Authenticate',
                           'Basic realm="Checkmate PAM Module"'))
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


class TokenAuthMiddleware(object):
    """Authenticate any tokens provided.

    - Appends www-authenticate headers to returning calls
    - Authenticates all tokens passed in with X-Auth-Token
        - 401s if invalid
        - Marks authenticated if valid and populates user and catalog data
    """
    def __init__(self, app, endpoint, anonymous_paths=None):
        self.app = app
        self.endpoint = endpoint
        self.anonymous_paths = anonymous_paths or []

    def __call__(self, environ, start_resposne):
        """Authenticate calls with X-Auth-Token to the source auth service"""
        path_parts = environ['PATH_INFO'].split('/')
        root = path_parts[1] if len(path_parts) > 1 else None
        if root in self.anonymous_paths:
            # Allow test and static calls
            return self.app(environ, start_response)

        start_response = self.start_response_callback(start_response)

        if 'HTTP_X_AUTH_TOKEN' in environ:
            context = request.context
            try:
                content = (self._auth_keystone(context,
                           token=environ['HTTP_X_AUTH_TOKEN']))
                environ['HTTP_X_AUTHORIZED'] = "Confirmed"
            except HTTPUnauthorized as exc:
                LOG.exception(exc)
                return exc(environ, start_response)
            context.set_context(content)

        return self.app(environ, start_response)

    def _auth_keystone(self, context, token=None, username=None, apikey=None,
                       password=None):
        """Authenticates to keystone"""
        url = urlparse(self.endpoint)
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

        if context.tenant:
            auth = body['auth']
            auth['tenantId'] = context.tenant
            LOG.debug("Authenticating to tenant '%s'" % context.tenant)
        headers = {
            'Content-type': 'application/json',
            'Accept': 'application/json',
        }
        # TODO: implement some caching to not overload auth
        try:
            LOG.debug('Authenticating to %s' % self.endpoint)
            http.request('POST', url.path, body=json.dumps(body),
                         headers=headers)
            resp = http.getresponse()
            body = resp.read()
        except Exception as exc:
            LOG.error('HTTP connection exception: %s' % exc)
            raise HTTPUnauthorized('Unable to communicate with keystone')
        finally:
            http.close()

        if resp.status != 200:
            LOG.debug('Invalid token for tenant: %s' % resp.reason)
            raise (HTTPUnauthorized("Token invalid or not valid for "
                   "this tenant (%s)" % resp.reason,
                   [('WWW-Authenticate', 'Keystone %s' % self.endpoint)]))

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
            header = ('WWW-Authenticate', 'Keystone uri="%s"' % self.endpoint)
            if header not in headers:
                headers.append(header)
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


class AuthorizationMiddleware(object):
    """Checks that call is authenticated and authorized to access the resource
    requested.

    - Allows all calls to anonymous_paths
    - Allows all calls that have been validated
    - Denies all others (redirect to tenant URL if we have the tenant)
    Note: calls authenticated with PAM will not have an auth_token. They will
          not be able to access calls that need an auth token
    """
    def __init__(self, app, anonymous_paths=None):
        self.app = app
        self.anonymous_paths = anonymous_paths

    def __call__(self, environ, start_response):
        path_parts = environ['PATH_INFO'].split('/')
        root = path_parts[1] if len(path_parts) > 1 else None
        if root in self.anonymous_paths:
            # Allow test and static calls
            return self.app(environ, start_response)

        context = request.context

        if context.is_admin is True:
            # Allow all admin calls
            return self.app(environ, start_response)
        elif context.tenant:
            # Authorize tenant calls
            if not context.authenticated:
                LOG.debug('Authentication required for this resource')
                return HTTPUnauthorized()(environ, start_response)
            if not context.allowed_to_access_tenant():
                LOG.debug('Access to tenant not allowed')
                return (HTTPUnauthorized("Access to tenant not allowed")
                        (environ, start_response))
            return self.app(environ, start_response)
        elif root in RESOURCES or root is None:
            # Failed attempt to access admin resource
            if context.user_tenants:
                for tenant in context.user_tenants:
                    if 'Mosso' not in tenant:
                        LOG.debug('Redirecting to tenant')
                        return (HTTPFound(location='/%s%s' % (tenant,
                                environ['PATH_INFO']))
                                (environ, start_response))

        LOG.debug('Auth-Z failed. Returning 401.')
        return HTTPUnauthorized()(environ, start_response)


class StripPathMiddleware(object):
    """Strips extra / at end of path"""
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['PATH_INFO'] = environ['PATH_INFO'].rstrip('/')
        return self.app(environ, start_response)


class ExtensionsMiddleware(object):
    """Converts extensions to accept headers: yaml, json, html"""
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if environ['PATH_INFO'] in [None, "", "/"]:
            return self.app(environ, start_response)
        else:
            path_parts = environ['PATH_INFO'].split('/')
            root = path_parts[1]
            if root in RESOURCES or root in STATIC:
                return self.app(environ, start_response)

        if environ['PATH_INFO'].endswith('.json'):
            webob.Request(environ).accept = 'application/json'
            environ['PATH_INFO'] = environ['PATH_INFO'][0:-5]
        elif environ['PATH_INFO'].endswith('.yaml'):
            webob.Request(environ).accept = 'application/x-yaml'
            environ['PATH_INFO'] = environ['PATH_INFO'][0:-5]
        elif environ['PATH_INFO'].endswith('.html'):
            webob.Request(environ).accept = 'text/html'
            environ['PATH_INFO'] = environ['PATH_INFO'][0:-5]
        return self.app(environ, start_response)


class DebugMiddleware():
    """Helper class for debugging a WSGI application.

    Can be inserted into any WSGI application chain to get information
    about the request and response.

    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        LOG.debug('%s %s %s', ('*' * 20), 'REQUEST ENVIRON', ('*' * 20))
        for key, value in environ.items():
            LOG.debug('%s = %s', key, value)
        LOG.debug('')
        LOG.debug('%s %s %s', ('*' * 20), 'REQUEST BODY', ('*' * 20))
        LOG.debug('')

        resp = self.print_generator(self.app(environ, start_response))

        LOG.debug('%s %s %s', ('*' * 20), 'RESPONSE HEADERS', ('*' * 20))
        for (key, value) in response.headers.iteritems():
            LOG.debug('%s = %s', key, value)
        LOG.debug('')

        return resp

    @staticmethod
    def print_generator(app_iter):
        """Iterator that prints the contents of a wrapper string."""
        LOG.debug('%s %s %s', ('*' * 20), 'RESPONSE BODY', ('*' * 20))
        isimage = response.content_type.startswith("image")
        if (isimage):
            LOG.debug("(image)")
        for part in app_iter:
            if (not isimage):
                LOG.debug(part)
            yield part
        print


class ExceptionMiddleware():
    """Formats errors correctly."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        try:
            return self.app(environ, start_response)
        except CheckmateException as exc:
            print "*** ERROR ***"
            LOG.exception(exc)
            resp = webob.Response()
            resp.status = "500 Server Error"
            resp.body = {'Error': exc.__str__()}
            return resp
        except AssertionError as exc:
            print "*** %s ***" % exc
            LOG.exception(exc)
            resp = webob.Response()
            resp.status = "406 Bad Request"
            resp.body = json.dumps({'Error': exc.__str__()})
            return resp
        except Exception as exc:
            print "*** %s ***" % exc
            LOG.exception(exc)
            raise exc


#
# Call Context (class and middleware)
#
#TODO: Get this from openstack common?
class RequestContext(object):
    """
    Stores information about the security context under which the user
    accesses the system, as well as additional request information related to
    the current call, such as scope (which object, resource, etc).
    """

    def __init__(self, auth_token=None, username=None, tenant=None,
                 is_admin=False, read_only=False, show_deleted=False,
                 authenticated=False, catalog=None, user_tenants=None,
                 roles=None, domain=None, **kwargs):
        self.authenticated = authenticated
        self.auth_token = auth_token
        self.catalog = catalog
        self.username = username
        self.user_tenants = user_tenants  # all allowed tenants
        self.tenant = tenant  # current tenant
        self.is_admin = is_admin
        self.roles = roles or []
        self.read_only = read_only
        self.show_deleted = show_deleted
        self.domain = domain  # which cloud?
        self.kwargs = kwargs  # store extra args and retrieve them when needed

    def get_queued_task_dict(self, **kwargs):
        """Get a serializable dict of this context for use with remote, queued
        tasks.

        :param kwargs: any additional kwargs get added to the context

        Only certain fields are needed.
        Extra kwargs from __init__ are also provided.
        """
        keyword_args = copy.copy(self.kwargs)
        if kwargs:
            keyword_args.update(kwargs)
        result = dict(**keyword_args)
        result.update(self.__dict__)
        return result

    def allowed_to_access_tenant(self, tenant_id=None):
        """Checks if a tenant can be accessed by this current session.

        If no tenant is specified, the check will be done against the current
        context's tenant."""
        return (tenant_id or self.tenant) in (self.user_tenants or [])

    def set_context(self, content):
        """Updates context with current auth data"""
        catalog = self.get_service_catalog(content)
        self.catalog = catalog
        user_tenants = self.get_user_tenants(content)
        self.user_tenants = user_tenants
        self.auth_token = content['access']['token']['id']
        self.username = self.get_username(content)
        self.roles = self.get_roles(content)
        self.authenticated = True

    def get_service_catalog(self, content):
        """Returns Service Catalog"""
        return content['access']['serviceCatalog']

    def get_user_tenants(self, content):
        """Returns a list of tenants from token and catalog."""

        user = content['access']['user']
        token = content['access']['token']

        def essex():
            """Essex puts the tenant ID and name on the token."""
            return token['tenant']['id']

        def pre_diablo():
            """Pre-diablo, Keystone only provided tenantId."""
            return token['tenantId']

        def default_tenant():
            """Assume the user's default tenant."""
            return user['tenantId']

        user_tenants = {}
        # Get tenants from token
        for method in [essex, pre_diablo, default_tenant]:
            try:
                user_tenants[method()] = None
            except KeyError:
                pass

        # Get tenants from service catalog
        catalog = self.get_service_catalog(content)
        for service in catalog:
            endpoints = service['endpoints']
            for endpoint in endpoints:
                if 'tenantId' in endpoint:
                    user_tenants[endpoint['tenantId']] = None
        return user_tenants.keys()

    def get_username(self, content):
        """Returns username"""
        return content['access']['user']['name']

    def get_roles(self, content):
        """Returns roles for a given user"""
        user = content['access']['user']
        return [role['name'] for role in user.get('roles', [])]


class ContextMiddleware(object):
    """Adds a request.context to the call which holds authn+z data"""
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Use a default empty context
        request.context = RequestContext()
        return self.app(environ, start_response)


class BasicAuthMultiCloudMiddleware(object):
    """Implements basic auth to multiple cloud endpoints

    - Authenticates any basic auth to PAM
        - 401 if fails
        - Mark authenticated as admin if true
    - Adds basic auth header to any returning calls so client knows basic
      auth is supported
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
        """"""
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


class AuthTokenRouterMiddleware():
    """Middleware that routes Keystone auth to multiple endpoints

    All tokens with an X-Auth-Source header get routed to that source if the
    source is in the list of allowed endpoints.
    If a default endpoint is selected, it receives all calls without an
    X-Auth-Source header. If no default is selected, calls are routed to each
    endpoint until a valid response is received
    """
    def __init__(self, app, endpoints, default=None, anonymous_paths=None):
        """
        :param domains: the hash of domains to authenticate against. Each key
                is a realm that points to a different cloud. The hash contains
                endpoint and protocol, which is one of:
                    keystone: using keystone protocol
        """
        self.app = app
        self.default_endpoint = default
        # Make endpoints unique and maintain order
        self.endpoints = []
        if endpoints:
            for endpoint in endpoints:
                if endpoint not in self.endpoints:
                    self.endpoints.append(endpoint)
        self.middleware = {}
        self.default_middleware = None
        self.anonymous_paths = anonymous_paths or []

        self.last_status = None
        self.last_headers = None
        self.last_exc_info = None

        self.response_headers = []

        # For each endpoint, instantiate a middleware instance to process its
        # token auth calls. We'll route to it when appropriate
        for endpoint in self.endpoints:
            if endpoint not in self.middleware:
                middleware = (TokenAuthMiddleware(app, endpoint=endpoint,
                              anonymous_paths=self.anonymous_paths))
                self.middleware[endpoint] = middleware
                if endpoint == self.default_endpoint:
                    self.default_middleware = middleware
                header = ('WWW-Authenticate', 'Keystone uri="%s"' % endpoint)
                if header not in self.response_headers:
                    self.response_headers.append(header)

        if self.default_endpoint and self.default_middleware is None:
            self.default_middleware = (TokenAuthMiddleware(app,
                                       endpoint=self.default_endpoint))

    def __call__(self, environ, start_response):
        start_response = self.start_response_callback(start_response)
        if 'HTTP_X_AUTH_TOKEN' in environ:
            if 'HTTP_X_AUTH_SOURCE' in environ:
                source = environ['HTTP_X_AUTH_SOURCE']
                if not (source in self.endpoints or
                        source == self.default_endpoint):
                    LOG.info("Untrusted Auth Source supplied: %s" % source)
                    return (HTTPUnauthorized("Untrusted Auth Source")
                            (environ, start_response))

                sources = [source]
            else:
                sources = self.endpoints

            sr = self.start_response_intercept(start_response)
            for source in sources:
                result = self.middleware[source].__call__(environ, sr)
                if self.last_status:
                    if self.last_status.startswith('401 '):
                        # Unauthorized, let's try next route
                        continue
                    # We got an authorized response
                    if environ.get('HTTP_X_AUTHORIZED') == "Confirmed":
                        LOG.debug("Token Auth Router successfully authorized "
                                  "against %s" % source)
                    else:
                        LOG.debug("Token Auth Router authorized an "
                                  "unauthenticated call")
                    return result

            # Call default endpoint if not already called and if source was not
            # specified
            if 'HTTP_X_AUTH_SOURCE' not in environ and self.default_endpoint \
                    not in sources:
                result = (self.middleware[self.default_endpoint].
                          __call__(environ, sr))
                if not self.last_status.startswith('401 '):
                    # We got a good hit
                    LOG.debug("Token Auth Router got a successful response "
                              "against %s" % self.default_endpoint)
                    return result

        return self.app(environ, start_response)

    def start_response_intercept(self, start_response):
        """Intercepts upstream start_response and remembers status"""
        def callback(status, headers, exc_info=None):
            self.last_status = status
            self.last_headers = headers
            self.last_exc_info = exc_info
            if not self.last_status.startswith('401 '):
                start_response(status, headers, exc_info)
        return callback

    def start_response_callback(self, start_response):
        """Intercepts upstream start_response and adds our headers"""
        def callback(status, headers, exc_info=None):
            # Add our headers to response
            for header in self.response_headers:
                if header not in headers:
                    headers.append(header)
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


class CatchAll404(object):
    """Facilitates 404 responses for any path not defined elsewhere.  Kept in
       separate class to facilitate adding gui before this catchall definition
       is added.
    """

    def __init__(self, app):
        self.app = app
        LOG.info("initializing CatchAll404")

        # Keep this at end so it picks up any remaining calls after all other
        # routes have been added (and some routes are added in the __main__
        # code)
        @get('<path:path>')
        def extensions(path):
            """Catch-all unmatched paths (so we know we got the request, but
               didn't match it)"""
            abort(404, "Path '%s' not recognized" % path)

    def __call__(self, e, h):
        return self.app(e, h)
