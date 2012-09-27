import copy
import httplib
import json
import os
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
# pylint: disable=E0611
from bottle import get, post, request, response, abort, \
        static_file, HTTPError, route
from Crypto.Hash import MD5
from jinja2 import BaseLoader, Environment as jinjaEnvironment, \
        TemplateNotFound
import webob
import webob.dec
from webob.exc import HTTPNotFound, HTTPUnauthorized, HTTPFound

LOG = logging.getLogger(__name__)


from checkmate.db import any_tenant_id_problems
from checkmate.exceptions import CheckmateException
from checkmate.utils import HANDLERS, RESOURCES, STATIC, write_body, \
        read_body, support_only, with_tenant


class TenantMiddleware(object):
    """Strips /tenant_id/ from path and puts it in context

    This is needed by the authz middleware too
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        # Clear headers if supplied (anti-spoofing)
        self._remove_auth_headers(e)

        if e['PATH_INFO'] in [None, "", "/"]:
            pass  # Not a tenant call
        else:
            path_parts = e['PATH_INFO'].split('/')
            tenant = path_parts[1]
            if tenant in RESOURCES or tenant in STATIC:
                pass  # Not a tenant call
            else:
                errors = any_tenant_id_problems(tenant)
                if errors:
                    return HTTPNotFound(errors)(e, h)
                context = request.context
                rewrite = "/%s" % '/'.join(path_parts[2:])
                LOG.debug("Rewrite for tenant %s from '%s' "
                        "to '%s'" % (tenant, e['PATH_INFO'], rewrite))
                context.tenant = tenant
                e['PATH_INFO'] = rewrite

        return self.app(e, h)

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
        for (k, v) in headers.iteritems():
            env_key = self._header_to_env_var(k)
            env[env_key] = v


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

    def __call__(self, e, h):
        # Authenticate basic auth calls to PAM
        #TODO: this header is not being returned in a 401
        h = self.start_response_callback(h)
        context = request.context

        if 'HTTP_AUTHORIZATION' in e:
            if getattr(context, 'authenticated', False) is True:
                return self.app(e, h)

            auth = e['HTTP_AUTHORIZATION'].split()
            if len(auth) == 2:
                if auth[0].lower() == "basic":
                    login, passwd = base64.b64decode(auth[1]).split(':')
                    username = login
                    if self.domain:
                        if '\\' in login:
                            domain = login.split('\\')[0]
                            if domain != self.domain:
                                # Does not apply to this instance. Pass through
                                return self.app(e, h)
                            username = login.split('\\')[len(domain) + 1:]
                    # TODO: maybe implement some caching?
                    if not pam.authenticate(login, passwd, service='login'):
                        LOG.debug('PAM failing request because of bad creds')
                        return HTTPUnauthorized("Invalid credentials")(e, h)
                    LOG.debug("PAM authenticated '%s' as admin" % login)
                    context.domain = self.domain
                    context.username = username
                    context.authenticated = True
                    context.is_admin = self.all_admins

        return self.app(e, h)

    def start_response_callback(self, start_response):
        """Intercepts upstream start_response and adds our headers"""
        def callback(status, headers, exc_info=None):
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
    def __init__(self, app, endpoint):
        self.app = app
        self.endpoint = endpoint

    def __call__(self, e, h):
        # Authenticate calls with X-Auth-Token to the source auth service
        h = self.start_response_callback(h)

        if 'HTTP_X_AUTH_TOKEN' in e:
            context = request.context
            try:
                content = self._auth_keystone(context,
                        token=e['HTTP_X_AUTH_TOKEN'])
            except HTTPUnauthorized as exc:
                LOG.exception(exc)
                return exc(e, h)
            context.set_context(content)

        return self.app(e, h)

    def _auth_keystone(self, context, token=None, username=None,
                apikey=None, password=None):
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
        except Exception, e:
            LOG.error('HTTP connection exception: %s' % e)
            raise HTTPUnauthorized('Unable to communicate with keystone')
        finally:
            http.close()

        if resp.status != 200:
            LOG.debug('Invalid token for tenant: %s' % resp.reason)
            raise HTTPUnauthorized("Token invalid or not valid for "
                    "this tenant (%s)" % resp.reason)

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
            # Add our headers to response
            headers.append(('WWW-Authenticate',
                            'Keystone uri="%s"' % self.endpoint))
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

    def __call__(self, e, h):
        path_parts = e['PATH_INFO'].split('/')
        root = path_parts[1] if len(path_parts) > 1 else None
        if root in self.anonymous_paths:
            # Allow test and static calls
            return self.app(e, h)

        context = request.context

        if context.is_admin is True:
            # Allow all admin calls
            return self.app(e, h)
        elif context.tenant:
            # Authorize tenant calls
            if not context.authenticated:
                LOG.debug('Authentication required for this resource')
                return HTTPUnauthorized()(e, h)
            if not context.allowed_to_access_tenant():
                LOG.debug('Access to tenant not allowed')
                return HTTPUnauthorized("Access to tenant not allowed")(e, h)
            return self.app(e, h)
        elif root in RESOURCES or root is None:
            # Failed attempt to access admin resource
            if context.user_tenants:
                for tenant in context.user_tenants:
                    if 'Mosso' not in tenant:
                        LOG.debug('Redirecting to tenant')
                        return HTTPFound(location='/%s%s' % (tenant,
                                e['PATH_INFO']))(e, h)

        LOG.debug('Auth-Z failed. Returning 401.')
        return HTTPUnauthorized()(e, h)


class StripPathMiddleware(object):
    """Strips extra / at end of path"""
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        e['PATH_INFO'] = e['PATH_INFO'].rstrip('/')
        return self.app(e, h)


class ExtensionsMiddleware(object):
    """Converts extensions to accept headers: yaml, json, html"""
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        if e['PATH_INFO'] in [None, "", "/"]:
            return self.app(e, h)
        else:
            path_parts = e['PATH_INFO'].split('/')
            root = path_parts[1]
            if root in RESOURCES or root in STATIC:
                return self.app(e, h)

        if e['PATH_INFO'].endswith('.json'):
            webob.Request(e).accept = 'application/json'
            e['PATH_INFO'] = e['PATH_INFO'][0:-5]
        elif e['PATH_INFO'].endswith('.yaml'):
            webob.Request(e).accept = 'application/x-yaml'
            e['PATH_INFO'] = e['PATH_INFO'][0:-5]
        elif e['PATH_INFO'].endswith('.html'):
            webob.Request(e).accept = 'text/html'
            e['PATH_INFO'] = e['PATH_INFO'][0:-5]
        return self.app(e, h)


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

    def __init__(self, app, proxy_endpoints=None, with_simulator=False):
        self.app = app
        HANDLERS['text/html'] = BrowserMiddleware.write_html
        STATIC.extend(['static', 'favicon.ico', 'apple-touch-icon.png',
                'authproxy', 'marketing', 'admin', '', 'images', 'ui', None])
        self.proxy_endpoints = proxy_endpoints
        self.with_simulator = with_simulator
        from checkmate.environments import Environment  # Loads db abd routes

        # Add static routes
        @get('/favicon.ico')
        def favicon():
            """Without this, browsers keep getting a 404 and users perceive
            slow response """
            return static_file('favicon.ico',
                    root=os.path.join(os.path.dirname(__file__), 'static'))

        @get('/apple-touch-icon.png')
        def apple_touch():
            """For iOS devices"""
            return static_file('apple-touch-icon.png',
                    root=os.path.join(os.path.dirname(__file__), 'static'))

        @get('/')
        @get('/ui/<path:path>')
        #TODO: remove application/json and fix angular to call partials with
        #  text/html
        @support_only(['text/html', 'text/css', 'text/javascript',
                       'application/json'])  # Angular calls template in json
        def ui(path=None):
            """Expose new javascript UI"""
            root = os.path.join(os.path.dirname(__file__), 'static', 'ui')
            if path and path.startswith('/js/'):
                root = os.path.join(os.path.dirname(__file__), 'static', 'ui',
                                    'js')
            if not path or not os.path.exists(os.path.join(root, path)):
                return static_file("index.html", root=root)
            if path.endswith('.css'):
                return static_file(path, root=root, mimetype='text/css')
            elif path.endswith('.html'):
                if 'partials' in path.split('/'):
                    return static_file(path, root=root)
                else:
                    return static_file("index.html", root=root)
            return static_file(path, root=root)

        @get('/static/<path:path>')
        #TODO: remove application/json and fix angular to call partials with
        #  text/html
        @support_only(['text/html', 'text/css', 'text/javascript', 'image/*',
                       'application/json'])  # Angular calls template in json
        def static(path):
            """Expose static files (images, css, javascript, etc...)"""
            root = os.path.join(os.path.dirname(__file__), 'static')
            # Ensure correct mimetype
            mimetype = 'auto'
            if path.endswith('.css'):  # bottle does not write this for css
                mimetype = 'text/css'
            httpResponse=static_file(path, root=root, mimetype=mimetype)
            if self.with_simulator and path.endswith('deployment-new.html') and isinstance(httpResponse.output, file):
                httpResponse.output = httpResponse.output.read().replace("<!-- SIMULATE BUTTON PLACEHOLDER - do not cheange this comment, used for substitution!! -->",
                                          '<button ng-click="simulate()" class="btn" ng-disabled="!auth.loggedIn">Simulate It</button>')
            return httpResponse

        @get('/images/<path:path>')  # for RackspaceCalculator
        def images(path):
            """Expose image files"""
            root = os.path.join(os.path.dirname(__file__), 'static',
                    'RackspaceCalculator', 'images')
            return static_file(path, root=root)

        @get('/admin')
        def admin():
            return write_body(None, request, response)

        @get('/marketing/<path:path>')
        @support_only(['text/html', 'text/css', 'text/javascript'])
        def home(path):
            return static_file(path,
                    root=os.path.join(os.path.dirname(__file__), 'static',
                        'marketing'))

        @post('/authproxy')
        @support_only(['application/json', 'application/x-yaml'])
        def authproxy():
            """Proxy Auth Requests

            The Ajax client cannot talk to auth because of CORS. This function
            allows it to authenticate through this server.
            """
            auth = read_body(request)
            if not auth:
                abort(406, "Expecting a body in the request")
            source = request.get_header('X-Auth-Source')
            if not source:
                abort(401, "X-Auth-Source header not supplied. The header is "
                        "required and must point to a valid and permitted "
                        "auth endpoint.")
            if source not in self.proxy_endpoints:
                abort(401, "Auth endpoint not permitted: %s" % source)

            url = urlparse(source)
            if url.scheme == 'https':
                http_class = httplib.HTTPSConnection
                port = url.port or 443
            else:
                http_class = httplib.HTTPConnection
                port = url.port or 80
            host = url.hostname

            http = http_class(host, port)
            headers = {
                'Content-type': 'application/json',
                'Accept': 'application/json',
                }
            # TODO: implement some caching to not overload auth
            try:
                LOG.debug('Proxy authenticating to %s' % source)
                http.request('POST', url.path, body=json.dumps(auth),
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
                msg = 'Keystone did not return json-encoded body'
                LOG.debug(msg)
                raise HTTPError(401, output=msg)

            return write_body(content, request, response)

        @route('/providers/<provider_id>/proxy/<path:path>')
        @with_tenant
        def provider_proxy(provider_id, tenant_id=None, path=None):
            vendor = None
            if "." in provider_id:
                vendor = provider_id.split(".")[0]
                provider_id = provider_id.split(".")[1]
            environment = Environment(dict(providers={provider_id:
                    dict(vendor=vendor)}))
            try:
                provider = environment.get_provider(provider_id)
            except KeyError:
                abort(404, "Invalid provider: %s" % provider_id)
            results = provider.proxy(path, request, tenant_id=tenant_id)

            return write_body(results, request, response)

    def __call__(self, e, h):
        """Detect unauthenticated calls and redirect them to root.
        This gets processed before the bottle routes"""
        if 'text/html' in webob.Request(e).accept or \
                e['PATH_INFO'].endswith('.html'):  # Angular requests json
            if e['PATH_INFO'] not in [None, "", "/", "/authproxy"]:
                path_parts = e['PATH_INFO'].split('/')
                if path_parts[1] in STATIC:
                    # Not a tenant call. Bypass auth and return static content
                    LOG.debug("Browser middleware stripping creds")
                    if 'HTTP_X_AUTH_TOKEN' in e:
                        del e['HTTP_X_AUTH_TOKEN']
                    if 'HTTP_X_AUTH_SOURCE' in e:
                        del e['HTTP_X_AUTH_SOURCE']
                elif path_parts[1] in RESOURCES:
                    # If not ajax call, entered in browser address bar
                    # then return client app
                    context = request.context
                    if (not context.authenticated) and \
                            e.get('HTTP_X_REQUESTED_WITH') != 'XMLHttpRequest':
                        e['PATH_INFO'] = "/"  # return client app
        return self.app(e, h)

    @staticmethod
    def get_template_name_from_path(path):
        """ Returns template name from request path"""
        name = 'default'
        if path:
            if path[0] == '/':
                # normalize to always not include first path
                parts = path[1:].split('/')
            else:
                parts = path.split('/')
            if len(parts) > 0 and parts[0] not in RESOURCES and \
                    parts[0] not in STATIC:
                # Assume it is a tenant (and remove it from our evaluation)
                parts = parts[1:]

            # IDs are 2nd or 4th: /[type]/[id]/[type2|action]/[id2]/action
            if len(parts) == 1:
                # Resource
                name = "%s" % parts[0]
            elif len(parts) == 2:
                # Single resource
                name = "%s" % parts[0][0:-1]  # strip s
            elif len(parts) == 3:
                if parts[2].startswith('+'):
                    # Action
                    name = "%s.%s" % (parts[0][0:-1], parts[2][1:])
                elif parts[2] in ['tasks']:
                    # Subresource
                    name = "%s.%s" % (parts[0][0:-1], parts[2])
                else:
                    # 'status' and the like
                    name = "%s.%s" % (parts[0][0:-1], parts[2])
            elif len(parts) > 3:
                if parts[2] in ['tasks']:
                    # Subresource
                    name = "%s.%s" % (parts[0][0:-1], parts[2][0:-1])
                else:
                    # 'status' and the like
                    name = "%s.%s" % (parts[0][0:-1], parts[2])
        LOG.debug("Template for '%s' returned as '%s'" % (path, name))
        return name

    @staticmethod
    def write_html(data, request, response):
        """Write output in html"""
        response.add_header('content-type', 'text/html')

        name = BrowserMiddleware.get_template_name_from_path(request.path)

        class MyLoader(BaseLoader):
            def __init__(self, path):
                self.path = path

            def get_source(self, environment, template):
                path = os.path.join(self.path, template)
                if not os.path.exists(path):
                    raise TemplateNotFound(template)
                mtime = os.path.getmtime(path)
                with file(path) as f:
                    source = f.read().decode('utf-8')
                return source, path, lambda: mtime == os.path.getmtime(path)
        env = jinjaEnvironment(loader=MyLoader(os.path.join(os.path.dirname(
            __file__), 'static')))

        def do_prepend(value, param='/'):
            """
            Prepend a string if the passed in string exists.

            Example:
            The template '{{ root|prepend('/')}}/path';
            Called with root undefined renders:
                /path
            Called with root defined as 'root' renders:
                /root/path
            """
            if value:
                return '%s%s' % (param, value)
            else:
                return ''
        env.filters['prepend'] = do_prepend
        env.json = json
        context = request.context
        tenant_id = context.tenant
        try:
            template = env.get_template("%s.template" % name)
            return template.render(data=data, source=json.dumps(data,
                    indent=2), tenant_id=tenant_id, context=context)
        except StandardError as exc:
            print exc
            try:
                template = env.get_template("default.template")
                return template.render(data=data, source=json.dumps(data,
                        indent=2), tenant_id=tenant_id, context=context)
            except StandardError as exc2:
                LOG.exception(exc2)
                pass  # fall back to JSON


class DebugMiddleware():
    """Helper class for debugging a WSGI application.

    Can be inserted into any WSGI application chain to get information
    about the request and response.

    """

    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        LOG.debug('%s %s %s', ('*' * 20), 'REQUEST ENVIRON', ('*' * 20))
        for key, value in e.items():
            LOG.debug('%s = %s', key, value)
        LOG.debug('')
        LOG.debug('%s %s %s', ('*' * 20), 'REQUEST BODY', ('*' * 20))
        LOG.debug('')

        resp = self.print_generator(self.app(e, h))

        LOG.debug('%s %s %s', ('*' * 20), 'RESPONSE HEADERS', ('*' * 20))
        for (key, value) in response.headers.iteritems():
            LOG.debug('%s = %s', key, value)
        LOG.debug('')

        return resp

    @staticmethod
    def print_generator(app_iter):
        """Iterator that prints the contents of a wrapper string."""
        LOG.debug('%s %s %s', ('*' * 20), 'RESPONSE BODY', ('*' * 20))
        for part in app_iter:
            #sys.stdout.write(part)
            LOG.debug(part)
            #sys.stdout.flush()
            yield part
        print


class ExceptionMiddleware():
    """Formats errors correctly."""

    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        try:
            return self.app(e, h)
        except CheckmateException as exc:
            print "*** ERROR ***"
            resp = webob.Response()
            resp.status = "500 Server Error"
            resp.body = {'Error': exc.__str__()}
            return resp
        except Exception as exc:
            print "*** %s ***" % exc
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
        self.roles = roles
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
        result = dict(
                username=self.username,
                auth_token=self.auth_token,
                catalog=self.catalog,
                **keyword_args
            )
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
        return content['access']['user']['name']

    def get_roles(self, content):
        user = content['access']['user']
        return [role['name'] for role in user.get('roles', [])]


class ContextMiddleware(object):
    """Adds a request.context to the call which holds authn+z data"""
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        # Use a default empty context
        request.context = RequestContext()
        return self.app(e, h)


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
                value['middleware'] = TokenAuthMiddleware(app,
                        endpoint=value['endpoint'])

    def __call__(self, e, h):
        # Authenticate basic auth calls to endpoints
        h = self.start_response_callback(h)

        if 'HTTP_AUTHORIZATION' in e:
            auth = e['HTTP_AUTHORIZATION'].split()
            if len(auth) == 2:
                if auth[0].lower() == "basic":
                    creds = base64.b64decode(auth[1]).split(':')
                    if len(creds) != 2:
                        return HTTPUnauthorized('Invalid credentials')(e, h)
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
                                content = self._auth_cloud_basic(context,
                                        uname, passwd,
                                        self.domains[domain]['middleware'])
                            except HTTPUnauthorized as exc:
                                return exc(e, h)
                            context.set_context(content)
        return self.app(e, h)

    def _auth_cloud_basic(self, context, uname, passwd, middleware):
        cred_hash = MD5.new('%s%s%s' % (uname, passwd, middleware.endpoint))\
                .hexdigest()
        if cred_hash in self.cache:
            content = self.cache[cred_hash]
            LOG.debug('Using cached catalog')
        else:
            try:
                LOG.debug('Authenticating to %s' % middleware.endpoint)
                content = middleware._auth_keystone(context,
                        username=uname, password=passwd)
                self.cache[cred_hash] = content
            except HTTPUnauthorized as exc:
                LOG.exception(exc)
                raise exc
        LOG.debug("Basic auth over Cloud authenticated '%s'" % uname)
        return content

    def start_response_callback(self, start_response):
        """Intercepts upstream start_response and adds our headers"""
        def callback(status, headers, exc_info=None):
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
    def __init__(self, app, endpoints, default=None):
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

        self.last_status = None
        self.last_headers = None
        self.last_exc_info = None

        # For each endpoint, instantiate a middleware instance to process its
        # token auth calls. We'll route to it when appropriate
        for endpoint in self.endpoints:
            if endpoint not in self.middleware:
                middleware = TokenAuthMiddleware(app, endpoint=endpoint)
                self.middleware[endpoint] = middleware
                if endpoint == self.default_endpoint:
                    self.default_middleware = middleware

        if self.default_endpoint and self.default_middleware is None:
            self.default_middleware = TokenAuthMiddleware(app,
                    endpoint=self.default_endpoint)

    def __call__(self, e, h):
        if 'HTTP_X_AUTH_TOKEN' in e:
            if 'HTTP_X_AUTH_SOURCE' in e:
                source = e['HTTP_X_AUTH_SOURCE']
                if not (source in self.endpoints or
                        source == self.default_endpoint):
                    LOG.info("Untrusted Auth Source supplied: %s" % source)
                    return HTTPUnauthorized("Untrusted Auth Source")(e, h)

                sources = [source]
            else:
                sources = self.endpoints

            sr = self.start_response_intercept(h)
            for source in sources:
                result = self.middleware[source].__call__(e, sr)
                if self.last_status:
                    if self.last_status.startswith('401 '):
                        # Unauthorized, let's try next route
                        continue
                    # We got an authorized response
                    LOG.debug("Token Auth Router successfully authorized "
                            "against %s" % source)
                    h(self.last_status, self.last_headers,
                        exc_info=self.last_exc_info)
                    return result

            # Call default endpoint if not already called and if source was not
            # specified
            if 'HTTP_X_AUTH_SOURCE' not in e and self.default_endpoint not in\
                    sources:
                result = self.middleware[self.default_endpoint].__call__(e, sr)
                if not self.last_status.startswith('401 '):
                    # We got a good hit
                    LOG.debug("Token Auth Router got a successful response "
                            "against %s" % self.default_endpoint)
                    h(self.last_status, self.last_headers,
                        exc_info=self.last_exc_info)
                    return result

        return self.app(e, h)

    def start_response_intercept(self, start_response):
        """Intercepts upstream start_response and remembers status"""
        def callback(status, headers, exc_info=None):
            self.last_status = status
            self.last_headers = headers
            self.last_exc_info = exc_info
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