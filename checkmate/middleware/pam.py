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

"""PAM Auth Middleware used by the Checkmate Server."""

import base64
import logging

# some distros install as PAM (Ubuntu, SuSE)
try:
    import pam
except ImportError:
    import PAM as pam

import webob.exc as webexc

LOG = logging.getLogger(__name__)


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
        self.domain = domain  # Which domain to authenticate in this instance
        self.all_admins = all_admins  # Does this authenticate admins?
        self.auth_header = 'Basic realm="Checkmate PAM Module"'

    def __call__(self, environ, start_response):
        # Authenticate basic auth calls to PAM
        # TODO(any): this header is not being returned in a 401
        start_response = self.start_response_callback(start_response)
        context = environ['context']

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
                    # TODO(any): maybe implement some caching?
                    if not pam.authenticate(login, passwd, service='login'):
                        LOG.debug('PAM failing request because of bad creds')
                        return (webexc.HTTPUnauthorized(
                            "Invalid credentials"
                        )(environ, start_response))
                    LOG.debug("PAM authenticated '%s' as admin", login)
                    context.domain = self.domain
                    context.username = username
                    context.authenticated = True
                    context.is_admin = self.all_admins

        return self.app(environ, start_response)

    def start_response_callback(self, start_response):
        """Intercept upstream start_response and adds our headers."""
        def callback(status, headers, exc_info=None):
            """Intercept upstream start_response and adds our headers."""
            # Add our headers to response
            headers.append(('WWW-Authenticate', self.auth_header))
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback
