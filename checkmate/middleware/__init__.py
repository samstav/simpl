# pylint: disable=R0903
# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Middleware used by the Checkmate Server.

This needs to be changed so the middleware is loaded by configuration.
"""

from __future__ import print_function

import copy
import json
import logging
import os
import re
import uuid

import bottle
import webob
import webob.dec
import webob.exc as webexc

from checkmate.common import threadlocal
from checkmate.exceptions import CheckmateException
# Temporarily import this to not break existing deployments
from checkmate.middleware.keystone import TokenAuthMiddleware  # noqa
from checkmate import utils

LOG = logging.getLogger(__name__)


def generate_response(self, environ, start_response):
    """A patch for webob.exc.WSGIHTTPException to handle YAML and JSON."""
    if self.content_length is not None:
        del self.content_length
    headerlist = list(self.headerlist)
    accept = environ.get('HTTP_ACCEPT', '')
    if accept and 'html' in accept or '*/*' in accept:
        content_type = 'text/html'
        body = self.html_body(environ)
    elif accept and 'yaml' in accept:
        content_type = 'application/x-yaml'
        data = dict(error=dict(explanation=self.__str__(),
                               code=self.code,
                               description=self.title))
        body = utils.to_yaml(data)
    elif accept and 'json' in accept:
        content_type = 'application/json'
        data = dict(error=dict(explanation=self.__str__(),
                               code=self.code,
                               description=self.title))
        body = utils.to_json(data)
    else:
        content_type = 'text/plain'
        body = self.plain_body(environ)
    extra_kw = {}
    if isinstance(body, unicode):
        extra_kw.update(charset='utf-8')
    resp = webob.Response(body,
                          status=self.status,
                          headerlist=headerlist,
                          content_type=content_type,
                          **extra_kw)
    resp.content_type = content_type
    return resp(environ, start_response)

# Patch webob to support YAML and JSON
webob.exc.WSGIHTTPException.generate_response = generate_response


class AuthorizationMiddleware(object):

    """Checks that call is authenticated and authorized to access.

    - Allows all calls to anonymous_paths
    - Allows all calls that have been validated
    - Denies all others (redirect to tenant URL if we have the tenant)
    Note: calls authenticated with PAM will not have an auth_token. They will
          not be able to access calls that need an auth token
    """

    def __init__(self, app, anonymous_paths=None, admin_paths=None):
        self.app = app
        if anonymous_paths:
            self.anonymous_paths = [re.compile(p) for p in anonymous_paths]
        else:
            self.anonymous_paths = []
        self.admin_paths = admin_paths

    def __call__(self, environ, start_response):
        request = webob.Request(environ)
        if any(path.match(request.path) for path in self.anonymous_paths):
            # Allow anonymous calls
            LOG.info("Allow anonymous path: %s", request.path)
            return self.app(environ, start_response)

        context = environ['context']

        if context.is_admin is True:
            start_response = self.start_response_callback(start_response)
            # Allow all admin calls
            return self.app(environ, start_response)
        elif context.tenant:
            # Authorize tenant calls
            if not context.authenticated:
                LOG.debug('Authentication required for this resource')
                return webexc.HTTPUnauthorized()(environ, start_response)
            if not context.allowed_to_access_tenant():
                LOG.debug('Access to tenant not allowed')
                return (webexc.HTTPUnauthorized(
                    "Access to tenant not allowed"
                )(environ, start_response))
            return self.app(environ, start_response)

        LOG.debug('Auth-Z failed. Returning 401.')
        return webexc.HTTPUnauthorized()(environ, start_response)

    def start_response_callback(self, start_response):
        """Intercept upstream start_response and add auth-z headers."""
        def callback(status, headers, exc_info=None):
            """Call Back with headers."""
            # Add our headers to response
            header = ('X-AuthZ-Admin', "True")
            if header not in headers:
                headers.append(header)
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


class StripPathMiddleware(object):

    """Strips extra / at end of path."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['PATH_INFO'] = environ['PATH_INFO'].rstrip('/')
        return self.app(environ, start_response)


class ExtensionsMiddleware(object):

    """Converts extensions to accept headers: yaml, json, wadl."""

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
        elif environ['PATH_INFO'].endswith('.wadl'):
            webob.Request(environ).accept = 'application/vnd.sun.wadl+xml'
            environ['PATH_INFO'] = environ['PATH_INFO'][0:-5]
        return self.app(environ, start_response)


class DebugMiddleware(object):

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
        req = webob.Request(environ)
        LOG.debug(req.body)
        LOG.debug('')

        resp = self.print_generator(self.app(environ, start_response))

        LOG.debug('%s %s %s', ('*' * 20), 'RESPONSE HEADERS', ('*' * 20))
        for (key, value) in bottle.response.headers.iteritems():
            LOG.debug('%s = %s', key, value)
        LOG.debug('')

        return resp

    @staticmethod
    def print_generator(app_iter):
        """Iterator that prints the contents of a wrapper string."""
        LOG.debug('%s %s %s', ('*' * 20), 'RESPONSE BODY', ('*' * 20))
        isimage = bottle.response.content_type.startswith("image")
        if isimage:
            LOG.debug("(image)")
        for part in app_iter:
            if not isimage:
                LOG.debug(part)
            yield part
        print()


class ExceptionMiddleware(object):

    """Formats errors correctly."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        try:
            return self.app(environ, start_response)
        except CheckmateException as exc:
            print("*** ERROR ***")
            LOG.exception(exc)
            resp = webob.Response()
            resp.status = "500 Server Error"
            resp.body = {'Error': exc.__str__()}
            return resp
        except AssertionError as exc:
            print("*** %s ***" % exc)
            LOG.exception(exc)
            resp = webob.Response()
            resp.status = "406 Bad Request"
            resp.body = json.dumps({'Error': exc.__str__()})
            return resp
        except Exception as exc:
            print("*** %s ***" % exc)
            LOG.exception(exc)
            raise


#
# Call Context (class and middleware)
#
# TODO(any): Get this from openstack common?
class RequestContext(object):

    """Stores information about the security context.

    The user accesses the system under this security context.
    Also sets additional request information related to
    the current call, such as scope (which object, resource, etc).
    """

    def __init__(self, auth_token=None, username=None, tenant=None,
                 is_admin=False, read_only=False, show_deleted=False,
                 authenticated=False, catalog=None, user_tenants=None,
                 roles=None, domain=None, auth_source=None, simulation=False,
                 base_url=None, region=None, resource=None, user_id=None,
                 **kwargs):
        """Initialize context.

        :param user_id: for use by clients that need the user id
        """
        self.authenticated = authenticated
        self.auth_source = auth_source
        self.auth_token = auth_token
        self.catalog = catalog
        self.username = username
        self.user_id = user_id
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
        self.resource = resource
        self.kwargs = kwargs  # store extra args and retrieve them when needed
        self.update_local_context()

    def update_local_context(self):
        """Replicate data to threadlocal context.

        This method is here temporarily until we get rid of RequestContext.
        """
        new_context = threadlocal.get_context()
        new_context.update(self.get_queued_task_dict())

    def get_queued_task_dict(self, **kwargs):
        """Get a serializable dict of this context.

        For use with remote, queued tasks.

        :param kwargs: any additional kwargs get added to the context

        Only certain fields are needed.
        Extra kwargs from __init__ are also provided.
        """
        keyword_args = copy.copy(self.kwargs)
        if self.__dict__:
            keyword_args.update(self.__dict__)
        result = dict(**keyword_args)
        result.update(kwargs)
        return result

    def allowed_to_access_tenant(self, tenant_id=None):
        """Check if a tenant can be accessed by this current session.

        If no tenant is specified, the check will be done against the current
        context's tenant.
        """
        return tenant_id or self.tenant in self.user_tenants or []

    def set_context(self, content):
        """Updates context with current auth data."""
        catalog = self.get_service_catalog(content)
        self.catalog = catalog
        user_tenants = self.get_user_tenants(content)
        self.user_tenants = user_tenants
        self.auth_token = content['access']['token']['id']
        self.username = self.get_username(content)
        self.roles = self.get_roles(content)
        self.authenticated = True
        try:
            self.user_id = content['access']['user'].get('id')
        except KeyError:
            pass
        self.update_local_context()

    @staticmethod
    def get_service_catalog(content):
        """Return Service Catalog."""
        return content['access'].get('serviceCatalog')

    @staticmethod
    def get_user_tenants(content):
        """Return a list of tenants from token and catalog."""

        user = content['access']['user']
        token = content['access']['token']

        def essex():
            """Essex puts the tenant ID and name on the token."""
            return token['tenant']['name']

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
        """Return username."""
        # FIXME: when Global Auth implements name, remove the logic for 'id'
        user = content['access']['user']
        return user.get('name') or user.get('id')

    @staticmethod
    def get_roles(content):
        """Return roles for a given user."""
        user = content['access']['user']
        return [role['name'] for role in user.get('roles', [])]

    def __getitem__(self, key):
        try:
            return self.kwargs[key]
        except KeyError:
            if hasattr(self, key):
                return getattr(self, key)

    def __setitem__(self, key, value):
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            self.kwargs[key] = value

    def __contains__(self, key):
        return hasattr(self, key) or key in self.kwargs

    def get(self, key, default=None):
        """Implement get to act like a dictionary."""
        try:
            return self[key]
        except KeyError:
            return default


class ContextMiddleware(object):

    """Adds a call context to the call environ which holds authn+z data."""

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
        transaction_id = uuid.uuid4().hex
        # TODO(zns): remove duplicate context logic
        new_context = threadlocal.get_context()
        new_context['base_url'] = url
        new_context['transaction_id'] = transaction_id
        old_context = RequestContext(base_url=url)
        environ['context'] = old_context
        LOG.debug("BASE URL IS %s", old_context.base_url)
        return self.app(environ, start_response)


class GitHubTokenMiddleware(object):

    """Takes github credentials and adds them to context."""

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        request = webob.Request(environ)
        token = (request.cookies.get("github_access_token") or
                 request.headers.get("X-Github-Access-Token"))
        if token:
            environ['context']['github_token'] = token
            # TODO(zns): remove duplicate context logic
            new_context = threadlocal.get_context()
            new_context['github_token'] = token
        return self.app(environ, start_response)


class CatchAll404(object):

    """Facilitate 404 responses for any path not defined elsewhere.

    Kept in separate class to facilitate adding gui before this catchall
    definition is added.
    """

    def __init__(self, app):
        """From app catch everything that we can.

        :param app:
        """
        self.app = app
        LOG.info("initializing CatchAll404")

        # Keep this at end so it picks up any remaining calls after all other
        # routes have been added (and some routes are added in the __main__
        # code)
        @bottle.get('<path:path>')
        def extensions(path):  # pylint: disable=W0612
            """Catch-all unmatched paths.

            We know we got the request, but didn't match it.
            """
            bottle.abort(404, "Path '%s' not recognized" % path)

    def __call__(self, environ, start_response):
        return self.app(environ, start_response)
