'''

Contains all Middleware used by the Checkmate Server

This needs to be changed so the middleware is loaded by configuration.

'''
import base64
import copy
import json
import logging
import os

# some distros install as PAM (Ubuntu, SuSE)
# https://bugs.launchpad.net/keystone/+bug/938801
try:
    import pam
except ImportError:
    import PAM  # pylint: disable=W0611,F0401,W0402
from urlparse import urlparse

from bottle import get, request, response, abort  # pylint: disable=E0611
from eventlet.green import httplib
import webob
import webob.dec
from webob.exc import HTTPNotFound, HTTPUnauthorized

from checkmate.common.caching import MemorizeMethod
from checkmate.db import any_tenant_id_problems
from checkmate.exceptions import CheckmateException
from checkmate.utils import to_json, to_yaml, import_class

LOG = logging.getLogger(__name__)


def generate_response(self, environ, start_response):
    '''A patch for webob.exc.WSGIHTTPException to handle YAML and JSON'''
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
    '''Strips /tenant_id/ from path and puts it in context

    This is needed by the authz middleware too
    '''
    def __init__(self, app, resources=None):
        '''
        :param resources: REST resources that are NOT tenants
        '''
        self.app = app
        self.resources = resources

    def __call__(self, environ, start_response):
        # Clear headers if supplied (anti-spoofing)
        self._remove_auth_headers(environ)

        if environ['PATH_INFO'] in [None, "", "/"]:
            pass  # Not a tenant call
        else:
            path_parts = environ['PATH_INFO'].split('/')
            tenant = path_parts[1]
            if self.resources and tenant in self.resources:
                pass  # Not a tenant call
            else:
                if len(tenant) > 32:
                    return HTTPUnauthorized("Invalid tenant")(environ,
                                                              start_response)
                errors = any_tenant_id_problems(tenant)
                if errors:
                    return HTTPNotFound(errors)(environ, start_response)
                context = request.context
                rewrite = "/%s" % '/'.join(path_parts[2:])
                LOG.debug("Rewrite for tenant %s from '%s' to '%s'", tenant,
                          environ['PATH_INFO'], rewrite)
                context.tenant = tenant
                environ['PATH_INFO'] = rewrite

        return self.app(environ, start_response)

    def _remove_auth_headers(self, env):
        '''Remove headers so a user can't fake authentication.

        :param env: wsgi request environment

        '''
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
        '''Remove http headers from environment.'''
        for k in keys:
            env_key = self._header_to_env_var(k)
            if env_key in env:
                LOG.debug('Removing header from request environment: %s',
                          env_key)
                del env[env_key]

    @staticmethod
    def _header_to_env_var(key):
        '''Convert header to wsgi env variable.

        :param key: http header name (ex. 'X-Auth-Token')
        :return wsgi env variable name (ex. 'HTTP_X_AUTH_TOKEN')

        '''
        return 'HTTP_%s' % key.replace('-', '_').upper()

    def _add_headers(self, env, headers):
        '''Add http headers to environment.'''
        for (key, value) in headers.iteritems():
            env_key = self._header_to_env_var(key)
            env[env_key] = value


class PAMAuthMiddleware(object):
    '''Authenticate basic auth calls to PAM and optionally mark user as admin

    - Authenticates any basic auth to PAM
        - 401 if fails
        - Mark authenticated as admin if all_admins is set
        - checks for domain if set. Ignores other domains otherwise
    - Adds basic auth header to any returning calls so client knows basic
      auth is supported
    '''
    def __init__(self, app, domain=None, all_admins=False):
        self.app = app
        self.domain = domain  # Which domain to authenticate in this instance
        self.all_admins = all_admins  # Does this authenticate admins?
        self.auth_header = 'Basic realm="Checkmate PAM Module"'

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
                    LOG.debug("PAM authenticated '%s' as admin", login)
                    context.domain = self.domain
                    context.username = username
                    context.authenticated = True
                    context.is_admin = self.all_admins

        return self.app(environ, start_response)

    def start_response_callback(self, start_response):
        '''Intercepts upstream start_response and adds our headers'''
        def callback(status, headers, exc_info=None):
            '''Intercepts upstream start_response and adds our headers'''
            # Add our headers to response
            headers.append(('WWW-Authenticate', self.auth_header))
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


TOKEN_CACHE_TIMEOUT = 600


class TokenAuthMiddleware(object):
    '''Authenticate any tokens provided.

    - Appends www-authenticate headers to returning calls
    - Authenticates all tokens passed in with X-Auth-Token
        - 401s if invalid
        - Marks authenticated if valid and populates user and catalog data
    '''
    def __init__(self, app, endpoint, anonymous_paths=None):
        self.app = app
        self.endpoint = endpoint
        self.anonymous_paths = anonymous_paths
        self.auth_header = 'Keystone uri="%s"' % endpoint['uri']
        if 'kwargs' in endpoint and 'realm' in endpoint['kwargs']:
            # Safer for many browsers if realm is first
            params = [
                ('realm', endpoint['kwargs']['realm'])
            ]
            params.extend([(k, v) for k, v in endpoint['kwargs'].items()
                           if k not in ['realm', 'protocol']])
            extras = ' '.join(['%s="%s"' % (k, v) for (k, v) in params])
            self.auth_header = str('Keystone uri="%s" %s' % (
                                   endpoint['uri'], extras))
        self.service_token = None
        self.service_username = None
        if 'kwargs' in endpoint:
            self.service_username = endpoint['kwargs'].get('username')
            self.service_password = endpoint['kwargs'].get('password')
        # FIXME: temporary logic. Make this get a new token when needed
        if self.service_username:
            try:
                result = self._auth_keystone(RequestContext(),
                                             username=self.service_username,
                                             password=self.service_password)
                self.service_token = result['access']['token']['id']
            except Exception:
                LOG.error("Unable to authenticate as a service. Endpoint '%s' "
                          "will be auth using client token",
                          endpoint.get('kwargs', {}).get('realm'))

    def __call__(self, environ, start_response):
        '''Authenticate calls with X-Auth-Token to the source auth service'''
        path_parts = environ['PATH_INFO'].split('/')
        root = path_parts[1] if len(path_parts) > 1 else None
        if self.anonymous_paths and root in self.anonymous_paths:
            # Allow anything marked as anonymous
            return self.app(environ, start_response)

        start_response = self.start_response_callback(start_response)

        if 'HTTP_X_AUTH_TOKEN' in environ:
            context = request.context
            token = environ['HTTP_X_AUTH_TOKEN']
            try:
                if self.service_token:
                    content = self._validate_keystone(token,
                                                      tenant_id=context.tenant)
                else:
                    content = self.auth_keystone(context.tenant,
                                                 self.endpoint['uri'],
                                                 self.auth_header,
                                                 token)
                environ['HTTP_X_AUTHORIZED'] = "Confirmed"
            except HTTPUnauthorized as exc:
                return exc(environ, start_response)
            context.auth_source = self.endpoint['uri']
            context.set_context(content)

        return self.app(environ, start_response)

    def _auth_keystone(self, context, token=None, username=None, apikey=None,
                       password=None):
        return self.auth_keystone(context.tenant,
                                  self.endpoint['uri'],
                                  self.auth_header,
                                  token=token,
                                  username=username,
                                  apikey=apikey,
                                  password=password)

    @MemorizeMethod(sensitive_kwargs=['token', 'apikey', 'password'],
                    timeout=600, cache_exceptions=True)
    def auth_keystone(self, tenant, auth_url, auth_header, token=None,
                      username=None, apikey=None, password=None):
        '''Authenticates to keystone'''
        url = urlparse(auth_url)
        if url.scheme == 'https':
            port = url.port or 443
            http = httplib.HTTPSConnection(url.hostname, port)
        else:
            port = url.port or 80
            http = httplib.HTTPConnection(url.hostname, port)

        if token:
            body = {"auth": {"token": {"id": token}}}
        elif password:
            body = {"auth": {"passwordCredentials": {
                    "username": username, 'password': password}}}
        elif apikey:
            body = {"auth": {"RAX-KSKEY:apiKeyCredentials": {
                    "username": username, 'apiKey': apikey}}}

        if tenant:
            auth = body['auth']
            auth['tenantId'] = tenant
            LOG.debug("Authenticating to tenant '%s'", tenant)
        headers = {
            'Content-type': 'application/json',
            'Accept': 'application/json',
        }
        try:
            LOG.debug('Authenticating to %s', auth_url)
            http.request('POST', url.path, body=json.dumps(body),
                         headers=headers)
            resp = http.getresponse()
            body = resp.read()
        except Exception as exc:
            LOG.error('HTTP connection exception: %s', exc)
            raise HTTPUnauthorized('Unable to communicate with %s' %
                                   auth_url)
        finally:
            http.close()

        if resp.status != 200:
            LOG.debug('Invalid token for tenant %s on %s: %s', tenant,
                      auth_url, resp.reason)
            raise HTTPUnauthorized("Token invalid or not valid for this "
                                   "tenant (%s)" % resp.reason,
                                   [('WWW-Authenticate', auth_header)])

        try:
            return json.loads(body)
        except ValueError:
            msg = 'Keystone did not return json-encoded body'
            LOG.debug(msg)
            raise HTTPUnauthorized(msg)

    @MemorizeMethod(sensitive_args=[0], timeout=600)
    def _validate_keystone(self, token, tenant_id=None):
        '''Validates a Keystone Auth Token using a service token'''
        url = urlparse(self.endpoint['uri'])
        if url.scheme == 'https':
            http_class = httplib.HTTPSConnection
            port = url.port or 443
        else:
            http_class = httplib.HTTPConnection
            port = url.port or 80
        host = url.hostname

        path = os.path.join(url.path, token)
        if tenant_id:
            path = "%s?belongsTo=%s" % (path, tenant_id)
            LOG.debug("Validating on tenant '%s'", tenant_id)
        headers = {
            'X-Auth-Token': self.service_token,
            'Accept': 'application/json',
        }
        LOG.debug('Validating token with %s', self.endpoint['uri'])
        http = http_class(host, port)
        try:
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

    def start_response_callback(self, start_response):
        '''Intercepts upstream start_response and adds our headers'''
        def callback(status, headers, exc_info=None):
            '''Intercepts upstream start_response and adds our headers'''
            # Add our headers to response
            header = ('WWW-Authenticate', self.auth_header)
            if header not in headers:
                headers.append(header)
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


class AuthorizationMiddleware(object):
    '''Checks that call is authenticated and authorized to access the resource
    requested.

    - Allows all calls to anonymous_paths
    - Allows all calls that have been validated
    - Denies all others (redirect to tenant URL if we have the tenant)
    Note: calls authenticated with PAM will not have an auth_token. They will
          not be able to access calls that need an auth token
    '''
    def __init__(self, app, anonymous_paths=None, admin_paths=None):
        self.app = app
        self.anonymous_paths = anonymous_paths
        self.admin_paths = admin_paths

    def __call__(self, environ, start_response):
        path_parts = environ['PATH_INFO'].split('/')
        root = path_parts[1] if len(path_parts) > 1 else None
        if self.anonymous_paths and root in self.anonymous_paths:
            # Allow anonymous calls
            return self.app(environ, start_response)

        context = request.context

        if context.is_admin is True:
            start_response = self.start_response_callback(start_response)
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

        LOG.debug('Auth-Z failed. Returning 401.')
        return HTTPUnauthorized()(environ, start_response)

    def start_response_callback(self, start_response):
        '''Intercepts upstream start_response and adds auth-z headers'''
        def callback(status, headers, exc_info=None):
            # Add our headers to response
            header = ('X-AuthZ-Admin', "True")
            if header not in headers:
                headers.append(header)
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


class StripPathMiddleware(object):
    '''Strips extra / at end of path'''
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['PATH_INFO'] = environ['PATH_INFO'].rstrip('/')
        return self.app(environ, start_response)


class ExtensionsMiddleware(object):
    '''Converts extensions to accept headers: yaml, json, html'''
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if environ['PATH_INFO'] in [None, "", "/"]:
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


class DebugMiddleware(object):
    '''Helper class for debugging a WSGI application.

    Can be inserted into any WSGI application chain to get information
    about the request and response.

    '''

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
        '''Iterator that prints the contents of a wrapper string.'''
        LOG.debug('%s %s %s', ('*' * 20), 'RESPONSE BODY', ('*' * 20))
        isimage = response.content_type.startswith("image")
        if (isimage):
            LOG.debug("(image)")
        for part in app_iter:
            if (not isimage):
                LOG.debug(part)
            yield part
        print


class ExceptionMiddleware(object):
    '''Formats errors correctly.'''

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
    '''
    Stores information about the security context under which the user
    accesses the system, as well as additional request information related to
    the current call, such as scope (which object, resource, etc).
    '''

    def __init__(self, auth_token=None, username=None, tenant=None,
                 is_admin=False, read_only=False, show_deleted=False,
                 authenticated=False, catalog=None, user_tenants=None,
                 roles=None, domain=None, auth_source=None, simulation=False,
                 base_url=None, region=None, **kwargs):
        self.authenticated = authenticated
        self.auth_source = auth_source
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
        self.simulation = simulation
        self.base_url = base_url
        self.region = region
        self.kwargs = kwargs  # store extra args and retrieve them when needed

    def get_queued_task_dict(self, **kwargs):
        '''Get a serializable dict of this context for use with remote, queued
        tasks.

        :param kwargs: any additional kwargs get added to the context

        Only certain fields are needed.
        Extra kwargs from __init__ are also provided.
        '''
        keyword_args = copy.copy(self.kwargs)
        if kwargs:
            keyword_args.update(self.__dict__)
        result = dict(**keyword_args)
        result.update(kwargs)
        return result

    def allowed_to_access_tenant(self, tenant_id=None):
        '''Checks if a tenant can be accessed by this current session.

        If no tenant is specified, the check will be done against the current
        context's tenant.'''
        return (tenant_id or self.tenant) in (self.user_tenants or [])

    def set_context(self, content):
        '''Updates context with current auth data'''
        catalog = self.get_service_catalog(content)
        self.catalog = catalog
        user_tenants = self.get_user_tenants(content)
        self.user_tenants = user_tenants
        self.auth_token = content['access']['token']['id']
        self.username = self.get_username(content)
        self.roles = self.get_roles(content)
        self.authenticated = True

    @staticmethod
    def get_service_catalog(content):
        '''Returns Service Catalog'''
        return content['access'].get('serviceCatalog')

    @staticmethod
    def get_user_tenants(content):
        '''Returns a list of tenants from token and catalog.'''

        user = content['access']['user']
        token = content['access']['token']

        def essex():
            '''Essex puts the tenant ID and name on the token.'''
            return token['tenant']['id']

        def pre_diablo():
            '''Pre-diablo, Keystone only provided tenantId.'''
            return token['tenantId']

        def default_tenant():
            '''Assume the user's default tenant.'''
            return user['tenantId']

        user_tenants = {}
        # Get tenants from token
        for method in [essex, pre_diablo, default_tenant]:
            try:
                user_tenants[method()] = None
            except KeyError:
                pass

        # Get tenants from service catalog
        catalog = RequestContext.get_service_catalog(content)
        if catalog:
            for service in catalog:
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    if 'tenantId' in endpoint:
                        user_tenants[endpoint['tenantId']] = None
        return user_tenants.keys()

    @staticmethod
    def get_username(content):
        '''Returns username'''
        # FIXME: when Global Auth implements name, remove the logic for 'id'
        user = content['access']['user']
        return user.get('name') or user.get('id')

    @staticmethod
    def get_roles(content):
        '''Returns roles for a given user'''
        user = content['access']['user']
        return [role['name'] for role in user.get('roles', [])]


class ContextMiddleware(object):
    '''Adds a request.context to the call which holds authn+z data'''
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        if 'CHECKMATE_OVERRIDE_URL' in os.environ:
            url = os.environ.get('CHECKMATE_OVERRIDE_URL')
        else:
            # PEP333: wsgi.url_scheme, HTTP_HOST, SERVER_NAME, and SERVER_PORT
            # can be used to reconstruct a request's complete URL
            url = environ['wsgi.url_scheme'] + '://'
            if environ.get('HTTP_HOST'):
                url += environ['HTTP_HOST']
            else:
                url += environ['SERVER_NAME']

                if environ['wsgi.url_scheme'] == 'https':
                    if environ['SERVER_PORT'] != '443':
                        url += ':' + environ['SERVER_PORT']
                else:
                    if environ['SERVER_PORT'] != '80':
                        url += ':' + environ['SERVER_PORT']

        # Use a default empty context
        request.context = RequestContext(base_url=url)
        LOG.debug("BASE URL IS %s", request.context.base_url)
        return self.app(environ, start_response)


class AuthTokenRouterMiddleware(object):
    '''

    Middleware that routes auth to multiple endpoints

    The list of available auth endpoints is always returned in the API HTTP
    response using standard HTTP WWW-Authorization headers. This is what
    clients are expected to use to determine how or where they want to
    authenticate.

    Example response:

        WWW-Authenticate: Keystone uri="https://keystone.us/v2.0/tokens"
        WWW-Authenticate: Keystone uri="https://keystone.uk/v2.0/tokens"
        WWW-Authenticate: MyProtocol uri="https://my.com/custom_auth"
        WWW-Authenticate: MyOther uri="https://my.uk/v2.0/another_auth"
        WWW-Authenticate: Basic uri="https://this.com/", realm="Checkmate"

    Once a client authenticates, they call back with their credentials and
    indicate the auth mechanism they used using an X-Auth-Source header which
    points to the URI they used.

    Note: this scheme requires that URI exists and is unique.

    All subsequent requests with an X-Auth-Source header get routed to that
    source for validation if it is in the list of valid endpoint URIs.
    If a default endpoint is selected, it receives all calls without an
    X-Auth-Source header.

    If no default is selected, calls are routed to each
    endpoint until a valid response is received.

    The middleware modules that will be instantiated will receive the endpoint
    and the anonymous_paths as kwargs. Expecting _nit__ to support:

            Class(endpoint, anonymous_path=None).

    '''
    def __init__(self, app, endpoints, anonymous_paths=None):
        '''
        :param endpoints: an array of auth endpoint dicts which is the list of
                endpoints to authenticate against.
                Each entry should have the following keys:

                middleware: the middleware class to load to parse this entry
                default: if this is the default endpoint to authenticate to
                uri: the uri used for the endpoints
                kwargs: the arguments to pass to the middleware

        :param anonymous_paths: paths to ignore and allow through.
        '''
        self.app = app

        # parse endpoints
        self.endpoints = []
        if endpoints:
            # Load (no duplicates) into self.endpoints maintaining order
            for endpoint in endpoints:
                if endpoint not in self.endpoints:
                    if 'middleware' not in endpoint:
                        raise CheckmateException("Required 'middleware' key "
                                                 "not specified in endpoint: "
                                                 "%s" % endpoint)
                    if 'uri' not in endpoint:
                        raise CheckmateException("Required 'uri' key "
                                                 "not specified in endpoint: "
                                                 "%s" % endpoint)
                    self.endpoints.append(endpoint)
                    if endpoint.get('default') is True:
                        self.default_endpoint = endpoint
            # Make sure a default exists (else use the first one)
            if not self.default_endpoint:
                self.default_endpoint = endpoints[0]

        self.middleware = {}
        self.default_middleware = None
        self.anonymous_paths = anonymous_paths

        self.last_status = None
        self.last_headers = None
        self.last_exc_info = None

        self.response_headers = []

        # For each endpoint, instantiate a middleware instance to process its
        # token auth calls. We'll route to it when appropriate
        for endpoint in self.endpoints:
            if 'middleware_instance' not in endpoint:
                middleware = import_class(endpoint['middleware'])
                instance = middleware(app, endpoint,
                                      anonymous_paths=self.anonymous_paths)
                endpoint['middleware'] = instance
                self.middleware[endpoint['uri']] = instance
                if endpoint is self.default_endpoint:
                    self.default_middleware = instance
                header = ('WWW-Authenticate', instance.auth_header)
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
                if source not in self.middleware:
                    LOG.info("Untrusted Auth Source supplied: %s", source)
                    return (HTTPUnauthorized("Untrusted Auth Source")
                            (environ, start_response))

                sources = {source: self.middleware[source]}
            else:
                sources = self.middleware

            sr_intercept = self.start_response_intercept(start_response)
            for source in sources.itervalues():
                result = source.__call__(environ, sr_intercept)
                if self.last_status:
                    if self.last_status.startswith('401 '):
                        # Unauthorized, let's try next route
                        continue
                    # We got an authorized response
                    if environ.get('HTTP_X_AUTHORIZED') == "Confirmed":
                        LOG.debug("Token Auth Router successfully authorized "
                                  "against %s", source.endpoint.get('uri'))
                    else:
                        LOG.debug("Token Auth Router authorized an "
                                  "unauthenticated call")
                    return result

            # Call default endpoint if not already called and if source was not
            # specified
            if 'HTTP_X_AUTH_SOURCE' not in environ and self.default_endpoint \
                    not in sources.values():
                result = self.default_middleware.__call__(environ,
                                                          sr_intercept)
                if not self.last_status.startswith('401 '):
                    # We got a good hit
                    LOG.debug("Token Auth Router got a successful response "
                              "against %s", self.default_endpoint)
                    return result

        return self.app(environ, start_response)

    def start_response_intercept(self, start_response):
        '''Intercepts upstream start_response and remembers status'''
        def callback(status, headers, exc_info=None):
            self.last_status = status
            self.last_headers = headers
            self.last_exc_info = exc_info
            if not self.last_status.startswith('401 '):
                start_response(status, headers, exc_info)
        return callback

    def start_response_callback(self, start_response):
        '''Intercepts upstream start_response and adds our headers'''
        def callback(status, headers, exc_info=None):
            # Add our headers to response
            for header in self.response_headers:
                if header not in headers:
                    headers.append(header)
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


class CatchAll404(object):
    '''Facilitates 404 responses for any path not defined elsewhere.  Kept in
       separate class to facilitate adding gui before this catchall definition
       is added.
    '''

    def __init__(self, app):
        self.app = app
        LOG.info("initializing CatchAll404")

        # Keep this at end so it picks up any remaining calls after all other
        # routes have been added (and some routes are added in the __main__
        # code)
        @get('<path:path>')
        def extensions(path):  # pylint: disable=W0612
            '''Catch-all unmatched paths (so we know we got the request, but
               didn't match it)'''
            abort(404, "Path '%s' not recognized" % path)

    def __call__(self, environ, start_response):
        return self.app(environ, start_response)
