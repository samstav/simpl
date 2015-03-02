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

"""Tenant Middleware used by the Checkmate Server."""

import logging

import webob.exc as webexc

from checkmate.db import any_tenant_id_problems

LOG = logging.getLogger(__name__)


class TenantMiddleware(object):

    """Strips /tenant_id/ from path and puts it in context

    This is needed by the authz middleware too
    """

    def __init__(self, app, resources=None):
        """Init for TenantMiddleware.

        :param resources: REST resources that are NOT tenants
        """
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
                    return webexc.HTTPUnauthorized(
                        "Invalid tenant"
                    )(environ, start_response)
                errors = any_tenant_id_problems(tenant)
                if errors:
                    return webexc.HTTPNotFound(errors)(environ, start_response)
                context = environ['context']
                rewrite = "/%s" % '/'.join(path_parts[2:])
                LOG.debug("Rewrite for tenant %s from '%s' to '%s'", tenant,
                          environ['PATH_INFO'], rewrite)
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
                LOG.debug('Removing header from request environment: %s',
                          env_key)
                del env[env_key]

    @staticmethod
    def _header_to_env_var(key):
        """Convert header to wsgi env variable.

        :param key: http header name (ex. 'X-Auth-Token')
        :return wsgi env variable name (ex. 'HTTP_X_AUTH_TOKEN')

        """
        return 'HTTP_%s' % key.replace('-', '_').upper()

    def _add_headers(self, env, headers):
        """Add http headers to environment."""
        for (key, value) in headers.iteritems():
            env_key = self._header_to_env_var(key)
            env[env_key] = value
