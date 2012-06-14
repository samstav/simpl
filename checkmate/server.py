#!/usr/bin/env python
""" REST API for CheckMate

*****************************************************
*          This is still a VERY MESSY WIP           *
*****************************************************


Implements these resources:
    /components:   juju charm-like definitions of services and components
    /environments: targets that can have resources deployed to them
    /blueprints:   *architect* definitions defining applications or solutions
    /deployments:  deployed resources (an instance of a blueprint deployed to
                   an environment)
    /workflows:    SpiffWorkflow workflows (persisted in database)

Special calls:
    POST /deployments/              This is where the meat of things gets done
                                    Triggers a celery task which can then be
                                    followed up on using deployments/:id/status
    GET  /deployments/:id/status    Check status of a deployment
    GET  /workflows/:id/status      Check status of a workflow
    GET  /workflows/:id/tasks/:id   Read a SpiffWorkflow Task
    POST /workflows/:id/tasks/:id   Partial update of a SpiffWorkflow Task
                                    Supports the following attributes: state,
                                    attributes, and internal_attributes
    GET  /workflows/:id/+execute    A browser-friendly way to run a workflow
    GET  /static/*                  Return files in /static folder
    PUT  /*/:id                     So you can edit/save objects without
                                    triggering actions (like a deployment).
                                    CAUTION: No locking or guarantees of
                                    atomicity across calls
Tools:
    GET  /test/dump      Dumps the database
    POST /test/parse     Parses the body (use to test your yaml or json)
    POST /test/hack      Testing random stuff....
    GET  /test/async     Returns a streamed response (3 x 1 second intervals)
    GET  /workflows/:id/tasks/:id/+reset   Reset a SpiffWorkflow Celery Task

Notes:
    .yaml/.json extensions override Accept headers (except in /static/)
    Trailing slashes are ignored (ex. /blueprints/ == /blueprints)
"""

import base64
import httplib
import os
import logging
# some distros install as PAM (Ubuntu, SuSE) https://bugs.launchpad.net/keystone/+bug/938801
try:
    import pam
except ImportError:
    import PAM
import sys
from time import sleep
from urlparse import urlparse
import uuid

# pylint: disable=E0611
from bottle import app, get, post, run, request, response, abort, static_file
import webob
import webob.dec
from webob.exc import HTTPNotFound, HTTPUnauthorized


# define a Handler which writes INFO messages or higher to the sys.stderr
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
# tell the handler to use this format
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger().addHandler(console)
logging.getLogger().setLevel(logging.DEBUG)
LOG = logging.getLogger(__name__)

from checkmate.db import get_driver, any_id_problems, any_tenant_id_problems

# Load routes
from checkmate import simulator
from checkmate import blueprints, components, deployments, environments, \
        workflows

from checkmate.utils import *

db = get_driver('checkmate.db.sql.Driver')


#
# Making life easy - calls that are handy but will not be in final API
#


@get('/test/dump')
def get_everything():
    return write_body(db.dump(), request, response)


@post('/test/parse')
def parse():
    """ For debugging only """
    return write_body(read_body(request), request, response)


@post('/test/hack')
def hack():
    """ Use it to test random stuff """
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    return write_body(entity, request, response)


@get('/test/async')
def async():
    """Test async responses"""
    response.set_header('content-type', "application/json")
    response.set_header('Location', "uri://something")

    def afunc():
        yield ('{"Note": "To watch this in real-time, run: curl '\
                'http://localhost:8080/test/async -N -v",')
        sleep(1)
        for i in range(3):
            yield '"%i": "Counting",' % i
            sleep(1)
        yield '"Done": 3}'
    return afunc()


#
# Status and Sytem Information
#
@get('/status/celery')
def get_celery_worker_status():
    """ Checking on celery """
    ERROR_KEY = "ERROR"
    try:
        from celery.task.control import inspect
        insp = inspect()
        d = insp.stats()
        if not d:
            d = {ERROR_KEY: 'No running Celery workers were found.'}
    except IOError as e:
        from errno import errorcode
        msg = "Error connecting to the backend: " + str(e)
        if len(e.args) > 0 and errorcode.get(e.args[0]) == 'ECONNREFUSED':
            msg += ' Check that the RabbitMQ server is running.'
        d = {ERROR_KEY: msg}
    except ImportError as e:
        d = {ERROR_KEY: str(e)}
    return write_body(d, request, response)


@get('/status/libraries')
def get_dependency_versions():
    """ Checking on dependencies """
    result = {}
    libraries = ['celery', 'kombu', 'SpiffWorkflow', 'stockton']
    for library in libraries:
        result[library] = {}
        if library in sys.modules:
            module = sys.modules[library]
            if hasattr(module, '__version__'):
                result[library]['version'] = module.__version__
            result[library]['path'] = module.__path__
            result[library]['status'] = 'loaded'
        else:
            result[library]['status'] = 'not loaded'

    return write_body(result, request, response)


#
# Static files & browser support
#
@get('/favicon.ico')
def favicon():
    """Without this, browsers keep getting a 404 and perceive slow response """
    return static_file('favicon.ico',
            root=os.path.join(os.path.dirname(__file__), 'static'))


@get('/static/<path:path>')
def wire(path):
    """Expose static files"""
    return static_file(path,
            root=os.path.join(os.path.dirname(__file__), 'static'))


@get('/')
def root():
    return write_body('Welcome to the CheckMate Administration Interface',
            request, response)


# Keep this at end
@get('<path:path>')
def extensions(path):
    """Catch-all unmatched paths (so we know we got teh request, but didn't
       match it)"""
    abort(404, "Path '%s' not recognized" % path)


class TenantMiddleware(object):
    """Strips /tenant_id/ from path and puts it in context

    This is needed by the authz middleware too"""
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        # Clear headers is supplied
        self._remove_auth_headers(e)

        if e['PATH_INFO'] in [None, "", "/"]:
            pass  # route with bottle. This call needs Admin rights.
        else:
            path_parts = e['PATH_INFO'].split('/')
            tenant = path_parts[1]
            if tenant in RESOURCES:
                pass  # route with bottle. This call needs Admin rights.
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
        LOG.debug('Removing headers from request environment: %s' %
                     ','.join(auth_headers))
        self._remove_headers(env, auth_headers)

    def _remove_headers(self, env, keys):
        """Remove http headers from environment."""
        for k in keys:
            env_key = self._header_to_env_var(k)
            try:
                del env[env_key]
            except KeyError:
                pass

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
    """Authenticate basic auth calls to PAM and mark success as admin

    - Authenticates any basic auth to PAM
        - 401 if fails
        - Mark authenticated as admin if true
    - Adds basic auth header to any returning calls so client knows basic
      auth is supported
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        # Authenticate basic auth calls to PAM
        #TODO: this header is not being returned in a 401
        response.add_header('WWW-Authenticate',
                            'Basic realm="CheckMate PAM Module"')

        if 'HTTP_AUTHORIZATION' in e:
            auth = e['HTTP_AUTHORIZATION'].split()
            if len(auth) == 2:
                if auth[0].lower() == "basic":
                    uname, passwd = base64.b64decode(auth[1]).split(':')
                    # TODO: maybe implement some caching?
                    if not pam.authenticate(uname, passwd, service='login'):
                        LOG.debug('PAM failing request because of bad creds')
                        return HTTPUnauthorized(None, [('WWW-Authenticate',
                                'Basic realm="CheckMate PAM Module"')])(e, h)
                    LOG.debug("PAM authenticated '%s' as admin" % uname)
                    context = request.context
                    context.user = uname
                    context.authenticated = True
                    context.is_admin = True

        return self.app(e, h)


class TokenAuthMiddleware(object):
    """Authenticate any tokens provided.

    ****************************************
    FIXME: THIS IS NOT PROVIDING SECURITY YET
    ****************************************

    - Appends www-authenticate headers to returning calls
    - Authenticates all tokens passed in with X-Auth-Token
        - 401s if invalid
        - Marks authenticated if valid and populates user and catalog data
    """
    def __init__(self, app, options={}):
        self.app = app
        self.options = options

    def __call__(self, e, h):
        # Authenticate calls with X-Auth-Token to the source auth service
        #TODO: this header is not being returned in a 401
        response.add_header('WWW-Authenticate',
                            'Keystone realm="CheckMate Token Auth Module"')

        if 'HTTP_X_AUTH_TOKEN' in e:
            context = request.context
            service = e.get('HTTP_X_AUTH_SOURCE',
                'https://identity.api.rackspacecloud.com/v2.0/tokens')

            url = urlparse(service)
            if url.scheme == 'https':
                http_class = httplib.HTTPSConnection
                port = url.port or 443
            else:
                http_class = httplib.HTTPConnection
                port = url.port or 80
            host = url.hostname

            http = http_class(host, port)
            body = {"auth": {"token": {"id": e['HTTP_X_AUTH_TOKEN']}}}
            if context.tenant:
                auth = body['auth']
                auth['tenantId'] = context.tenant
            headers = {
                    'Content-type': 'application/json',
                    'Accept': 'application/json',
                }
            # TODO: implement some caching to not overload auth
            try:
                http.request('POST', url.path, body=json.dumps(body),
                        headers=headers)
                resp = http.getresponse()
                if resp.status != 200:
                    LOG.debug('Invalid token for tenant: %s' % resp.reason)
                    return HTTPUnauthorized("Token invalid or not valid for "
                            "this tenant (%s)" % resp.reason)(e, h)

                body = resp.read()
            except Exception, e:
                LOG.error('HTTP connection exception: %s' % e)
                return HTTPUnauthorized('Unable to communicate with keystone')
            finally:
                http.close()

            try:
                content = json.loads(body)
            except ValueError:
                LOG.debug('Keystone did not return json-encoded body')
                content = {}
            catalog = self.get_catalog(content)
            context.catalog = catalog
            user_tenants = self.get_user_tenants(content)
            context.user_tenants = user_tenants
            context.auth_tok = e['HTTP_X_AUTH_TOKEN']
            context.user = self.get_user(content)
            context.roles = self.get_roles(content)

        return self.app(e, h)

    def get_catalog(self, content):
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

        # Get tenants from catalog
        catalog = self.get_catalog(content)
        for service in catalog:
            endpoints = service['endpoints']
            for endpoint in endpoints:
                if 'tenantId' in endpoint:
                    user_tenants[endpoint['tenantId']] = None
        return user_tenants.keys()

    def get_user(self, content):
        return content['access']['user']['name']

    def get_roles(self, content):
        user = content['access']['user']
        return [role['name'] for role in user.get('roles', [])]


class AuthorizationMiddleware(object):
    """Checks that call is authenticated and authorized to access the resource
    requested.

    ****************************************
    FIXME: THIS IS NOT PROVIDING SECURITY YET
    ****************************************

    - Allows all calls to /static/
    - Allows all calls that have been validated
    - Denies all others
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        path_parts = e['PATH_INFO'].split('/')
        root = path_parts[1]
        if root in ['static', 'test']:
            # Allow test and static calls
            return self.app(e, h)

        context = request.context

        if context.is_admin == True:
            # Allow all admin calls
            return self.app(e, h)
        elif context.tenant:
            # Authorize tenant calls
            if not context.allowed_to_access_tenant():
                return HTTPUnauthorized("Access to tenant not allowed")(e, h)
            return self.app(e, h)
        else:
            LOG.debug('Auth-Z failed. Returning 401')
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
        if e['PATH_INFO'].startswith('/static/'):
            pass  # staic files have fixed extensions
        elif e['PATH_INFO'].endswith('.json'):
            webob.Request(e).accept = 'application/json'
            e['PATH_INFO'] = e['PATH_INFO'][0:-5]
        elif e['PATH_INFO'].endswith('.yaml'):
            webob.Request(e).accept = 'application/x-yaml'
            e['PATH_INFO'] = e['PATH_INFO'][0:-5]
        elif e['PATH_INFO'].endswith('.html'):
            webob.Request(e).accept = 'text/html'
            e['PATH_INFO'] = e['PATH_INFO'][0:-5]
        return self.app(e, h)


#TODO: Get this from openstack common
class RequestContext(object):
    """
    Stores information about the security context under which the user
    accesses the system, as well as additional request information.
    """

    def __init__(self, auth_tok=None, user=None, tenant=None, is_admin=False,
                 read_only=False, show_deleted=False, authenticated=False,
                 catalog=None, user_tenants=None, roles=None):
        self.authenticated = authenticated
        self.auth_tok = auth_tok
        self.catalog = catalog
        self.user = user
        self.user_tenants = user_tenants
        self.tenant = tenant
        self.is_admin = is_admin
        self.roles = roles
        self.read_only = read_only
        self.show_deleted = show_deleted

    def allowed_to_access_tenant(self, tenant_id=None):
        return (tenant_id or self.tenant) in (self.user_tenants or [])


#TODO: Get this from openstack common
class ContextMiddleware(object):
    """Adds a request.context to the call which holds authn+z data"""
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        # Use a default empty context
        request.context = RequestContext()
        return self.app(e, h)


if __name__ == '__main__':
    LOG.setLevel(logging.DEBUG)
    # Build WSGI Chain:
    root_app = app()  # This is the main checkmate app
    no_path = StripPathMiddleware(root_app)
    no_ext = ExtensionsMiddleware(no_path)
    auth = AuthorizationMiddleware(no_ext)  # Make sure requests are allowed
    token = TokenAuthMiddleware(auth)  # Token Auth validator
    pam_auth = PAMAuthMiddleware(token)
    tenant = TenantMiddleware(pam_auth)
    context = ContextMiddleware(tenant)
    first = context
    run(app=first, host='127.0.0.1', port=8080, reloader=True,
            server='wsgiref')
