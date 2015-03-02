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

"""Keystone Auth Middleware used by the Checkmate Server."""

import logging
import re
import traceback

import webob
import webob.exc as webexc

from checkmate.common import caching
from checkmate.exceptions import BLUEPRINT_ERROR
from checkmate.exceptions import CheckmateException
from checkmate.middleware.os_auth import identity
from checkmate import utils

LOG = logging.getLogger(__name__)

TOKEN_CACHE_TIMEOUT = 600


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
        self.endpoint_uri = endpoint.get('uri')
        if anonymous_paths:
            self.anonymous_paths = [re.compile(p) for p in anonymous_paths]
        else:
            self.anonymous_paths = []
        self.auth_header = 'Keystone uri="%s"' % endpoint['uri']
        if 'kwargs' in endpoint and 'realm' in endpoint['kwargs']:
            # Safer for many browsers if realm is first
            params = [
                ('realm', endpoint['kwargs']['realm'])
            ]
            params.extend([(k, v) for k, v in endpoint['kwargs'].items()
                           if k not in ['realm', 'protocol']])
            extras = ' '.join(['%s="%s"' % (k, v) for (k, v) in params])
            self.auth_header = str('Keystone uri="%s" %s'
                                   % (endpoint['uri'], extras))
        self.service_token = None
        self.service_username = None
        if 'kwargs' in endpoint:
            self.service_username = endpoint['kwargs'].get('username')
            self.service_password = endpoint['kwargs'].get('password')
        # FIXME: temporary logic. Make this get a new token when needed
        if self.service_username:
            try:
                result = self.auth_keystone(tenant=None,
                                            auth_url=self.endpoint['uri'],
                                            username=self.service_username,
                                            password=self.service_password)
                self.service_token = result['access']['token']['id']
            except Exception as exc:
                LOG.error("Unable to authenticate as a service. Endpoint '%s' "
                          "will be auth using client token - ERROR %s",
                          endpoint.get('kwargs', {}).get('realm'), exc)
        LOG.info("Listening for Keystone auth for %s", self.endpoint['uri'])

    def __call__(self, environ, start_response):
        """Authenticate calls with X-Auth-Token to the source auth service."""
        request = webob.Request(environ)
        if any(path.match(request.path) for path in self.anonymous_paths):
            LOG.info("Allow anonymous path: %s", request.path)
            # Allow anything marked as anonymous
            return self.app(environ, start_response)

        start_response = self.start_response_callback(start_response)
        token = (request.headers.get('X-Auth-Token') or
                 request.cookies.get("auth_token"))
        if token:
            context = environ['context']
            if context.authenticated is True:
                # Auth has been handled by some other middleware
                pass
            else:
                try:
                    if self.service_token:
                        cnt = self._validate_keystone(token,
                                                      tenant_id=context.tenant)
                    else:
                        cnt = self.auth_keystone(tenant=context.tenant,
                                                 auth_url=self.endpoint['uri'],
                                                 token=token)
                    environ['HTTP_X_AUTHORIZED'] = "Confirmed"
                except webexc.HTTPUnauthorized as exc:
                    LOG.error('ERROR FAILURE IN AUTH: %s\n%s', exc,
                              traceback.format_exc())
                    return exc(environ, start_response)
                except Exception as exc:
                    LOG.error('NOTE - GENERAL ERROR: %s\n%s',
                              exc, traceback.format_exc())
                    return webexc.HTTPUnauthorized(
                        str(exc)
                    )(environ, start_response)
                else:
                    context.auth_source = self.endpoint['uri']
                    context.set_context(cnt)

        return self.app(environ, start_response)

    # Extranious Method required due to Decorator
    @caching.CacheMethod(sensitive_kwargs=['token', 'apikey', 'password'],
                         timeout=600,
                         cache_exceptions=True)
    def auth_keystone(self, tenant, auth_url, token=None, username=None,
                      apikey=None, password=None):
        """Authenticates to rax/openstack api.

        :param tenant:
        :param auth_url:
        :param auth_header:
        :param token:
        :param username:
        :param apikey:
        :param password:
        :return dict:
        """

        auth_base = {'auth_url': auth_url,
                     'username': username,
                     'tenant': tenant,
                     'apikey': apikey,
                     'password': password,
                     'token': token}

        LOG.debug('Authentication DATA dict == %s', auth_base)
        return identity.authenticate(auth_dict=auth_base)[3]

    # Extranious Method required due to Decorator
    @caching.CacheMethod(sensitive_args=[0], timeout=600)
    def _validate_keystone(self, token, tenant_id=None):
        """Validates a Keystone Auth Token using a service token.

        :param token:
        :param tenant_id:
        :return dict:
        """

        auth_base = {'auth_url': self.endpoint['uri'],
                     'token': token,
                     'tenant': tenant_id,
                     'service_token': self.service_token}
        LOG.debug('Token Validation DATA dict == %s', auth_base)
        return identity.auth_token_validate(auth_dict=auth_base)

    def start_response_callback(self, start_response):
        """Intercept upstream start_response and adds our headers."""
        def callback(status, headers, exc_info=None):
            """Intercept upstream start_response and adds our headers."""
            # Add our headers to response
            header = ('WWW-Authenticate', self.auth_header)
            if header not in headers:
                headers.append(header)
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


class AuthTokenRouterMiddleware(object):

    """Middleware that routes auth to multiple endpoints.

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
    """

    def __init__(self, app, endpoints, anonymous_paths=None):
        """Init for AuthTokenRouterMiddleware.

        :param endpoints: an array of auth endpoint dicts which is the list of
                endpoints to authenticate against.
                Each entry should have the following keys:

                middleware: the middleware class to load to parse this entry
                default: if this is the default endpoint to authenticate to
                uri: the uri used for the endpoints
                kwargs: the arguments to pass to the middleware

        :param anonymous_paths: paths to ignore and allow through.
        """
        self.app = app

        # parse endpoints
        self.endpoints = []
        if endpoints:
            # Load (no duplicates) into self.endpoints maintaining order
            for endpoint in endpoints:
                if endpoint not in self.endpoints:
                    if 'middleware' not in endpoint:
                        error_message = ("Required 'middleware' key "
                                         "not specified in endpoint: "
                                         "%s" % endpoint)
                        raise CheckmateException(error_message,
                                                 BLUEPRINT_ERROR)
                    if 'uri' not in endpoint:
                        error_message = ("Required 'uri' key not specified in"
                                         "endpoint: %s" % endpoint)
                        raise CheckmateException(error_message,
                                                 BLUEPRINT_ERROR)
                    self.endpoints.append(endpoint)
                    if endpoint.get('default') is True:
                        self.default_endpoint = endpoint
            # Make sure a default exists (else use the first one)
            if not self.default_endpoint:
                self.default_endpoint = endpoints[0]

        if anonymous_paths:
            self.anonymous_paths = [re.compile(p) for p in anonymous_paths]
        else:
            self.anonymous_paths = []

        self.middleware = {}
        self.default_middleware = None
        self.last_status = None
        self.last_headers = None
        self.last_exc_info = None
        self.response_headers = []
        self._router(app)

    def __call__(self, environ, start_response):
        start_response = self.start_response_callback(start_response)
        if 'HTTP_X_AUTH_TOKEN' in environ:
            if 'HTTP_X_AUTH_SOURCE' in environ:
                source = environ['HTTP_X_AUTH_SOURCE']
                if source not in self.middleware:
                    LOG.info("Untrusted Auth Source supplied: %s", source)
                    return (webexc.HTTPUnauthorized(
                        "Untrusted Auth Source"
                    )(environ, start_response))

                LOG.debug("Routing to provided source %s", source)
                sources = {source: self.middleware[source]}
            else:
                LOG.warning("No X-Auth-Source header provided. Routing to all "
                            "sources")
                sources = self.middleware

            sr_intercept = self.start_response_intercept(start_response)
            for source in sources.itervalues():
                LOG.debug("Authenticating against %s", source.endpoint_uri)
                result = source.__call__(environ, sr_intercept)
                if self.last_status:
                    LOG.debug("%s returned %s", source.endpoint_uri,
                              self.last_status)
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
            if ('HTTP_X_AUTH_SOURCE' not in environ
                    and self.default_endpoint not in sources.values()):
                result = self.default_middleware.__call__(environ,
                                                          sr_intercept)
                if not self.last_status.startswith('401 '):
                    # We got a good hit
                    LOG.debug("Token Auth Router got a successful response "
                              "against %s", self.default_endpoint)
                    return result

        return self.app(environ, start_response)

    def _router(self, app):
        """For each endpoint, instantiate a middleware instance.

        This is to process its token auth calls. We'll route to it when
        appropriate
        """
        for endpoint in self.endpoints:
            if 'middleware_instance' not in endpoint:
                middleware = utils.import_class(endpoint['middleware'])
                instance = middleware(app,
                                      endpoint,
                                      anonymous_paths=self.anonymous_paths)
                endpoint['middleware'] = instance
                self.middleware[endpoint['uri']] = instance
                if endpoint is self.default_endpoint:
                    self.default_middleware = instance
                header = ('WWW-Authenticate', instance.auth_header)
                if header not in self.response_headers:
                    self.response_headers.append(header)

        if self.default_endpoint and self.default_middleware is None:
            self.default_middleware = (
                TokenAuthMiddleware(app, endpoint=self.default_endpoint)
            )

    def start_response_intercept(self, start_response):
        """Intercept upstream start_response and remembers status."""
        def callback(status, headers, exc_info=None):
            """Call Back Method."""
            self.last_status = status
            self.last_headers = headers
            self.last_exc_info = exc_info
            if not self.last_status.startswith('401 '):
                start_response(status, headers, exc_info)
        return callback

    def start_response_callback(self, start_response):
        """Intercept upstream start_response and adds our headers."""
        def callback(status, headers, exc_info=None):
            """Call Back Method."""
            # Add our headers to response
            for header in self.response_headers:
                if header not in headers:
                    headers.append(header)
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback
