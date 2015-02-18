"""Authentication and token validation for Rackers and Service Accounts."""

import json
import logging
import os
import urlparse

import eventlet
from eventlet.green import httplib
from webob.exc import HTTPUnauthorized

from checkmate.contrib import caching

MODULE_CACHE = {}
LOG = logging.getLogger(__name__)


class SSOAuthenticator(object):

    """Handle authentication for Rackers."""

    def __init__(self, conf):
        # Parse endpiont URL
        assert conf.get('auth_endpoint'), "Auth Endpoint is not set"
        self.endpoint_uri = conf['auth_endpoint']
        url = urlparse.urlparse(self.endpoint_uri)
        self.use_https = url.scheme == 'https'
        self.host = url.hostname
        self.base_path = url.path
        if self.use_https:
            self.port = url.port or 443
        else:
            self.port = url.port or 80

        self.auth_header = 'GlobalAuth uri="%s"' % self.endpoint_uri
        self.service_token = None
        self.service_username = conf.get('service_username')
        self.service_password = conf.get('service_password')
        self.admin_role = conf.get('admin_role')

        if self.service_username:
            eventlet.spawn_n(self._get_service_token)

        self.enable_caching(conf.get('cache_connection_string'))

    def enable_caching(self, cache_connection_string=None):
        """Cache _validate_token.

        We use a caching decorator specific to this instance so multiple
        instances of this class don't share a cache.
        """
        if cache_connection_string:
            cache = caching.get_shared_cache_backend(cache_connection_string)
            decorator = caching.Cache(
                sensitive_args=[0],  # encrypt token
                timeout=600,
                backing_store_key="validate",
                backing_store=cache)
        else:
            decorator = caching.Cache(
                sensitive_args=[0],  # encrypt token
                timeout=600)
        self.validate = decorator(self.validate)

    def _get_service_token(self):
        """Retrieve service token from auth to use for validation."""
        LOG.info("Obtaining new service token from %s", self.endpoint_uri)
        try:
            result = self.authenticate({},
                                       username=self.service_username,
                                       password=self.service_password)
            self.service_token = result['access']['token']['id']
            LOG.info("Service token obtained. %s enabled", self.endpoint_uri)
        except Exception as exc:
            self.service_token = None
            LOG.debug("Error obtaining service token: %s", exc)
            LOG.error("Unable to authenticate to Global Auth. Endpoint "
                      "'%s' will be disabled", self.endpoint_uri)

    def validate(self, token, tenant=None):
        """Validate a Keystone Auth Token."""
        if self.use_https:
            http_class = httplib.HTTPSConnection
        else:
            http_class = httplib.HTTPConnection
        http = http_class(self.host, self.port, timeout=10)
        path = os.path.join(self.base_path, token)
        if tenant:
            path = "%s?belongsTo=%s" % (path, tenant)
            LOG.debug("Validating token for tenant '%s'", tenant)
        if self.service_username and self.service_token is None:
            self._get_service_token()
        headers = {
            'Accept': 'application/json',
        }
        if self.service_token:
            headers['X-Auth-Token'] = self.service_token
        try:
            LOG.debug('Validating token with %s', self.endpoint_uri)
            http.request('GET', path, headers=headers)
            resp = http.getresponse()
            body = resp.read()
        except Exception as exc:
            LOG.error('Error validating token: %s', exc)
            raise HTTPUnauthorized('Unable to communicate with %s' %
                                   self.endpoint_uri)
        finally:
            http.close()

        if resp.status == 200:
            LOG.debug('Token validated against %s', self.endpoint_uri)
            try:
                content = json.loads(body)
                return content
            except ValueError:
                msg = 'Keystone did not return json-encoded body'
                LOG.debug(msg)
                raise HTTPUnauthorized(msg)
        elif resp.status == 404:
            LOG.debug('Invalid token: %s', resp.reason)
            raise HTTPUnauthorized("Token invalid or not valid for this "
                                   "tenant (%s)" % resp.reason,
                                   [('WWW-Authenticate', self.auth_header)])
        elif resp.status == 401:
            LOG.info('Service token expired')
            self._get_service_token()
            if self.service_token:
                return self.validate(token, tenant=tenant)
        LOG.debug("Unexpected response validating token: %s", resp.reason)
        raise HTTPUnauthorized(resp.reason)

    def authenticate(self, context, token=None, username=None, apikey=None,
                     password=None, rsa_key=None, domain=None):
        """Authenticate to Keystone v2.0 API."""
        if self.use_https:
            http_class = httplib.HTTPSConnection
        else:
            http_class = httplib.HTTPConnection
        http = http_class(self.host, self.port, timeout=10)
        if token:
            body = {"auth": {"token": {"id": token}}}
        elif password:
            body = {"auth": {"passwordCredentials": {
                    "username": username, 'password': password}}}
        elif apikey:
            body = {"auth": {"RAX-KSKEY:apiKeyCredentials": {
                    "username": username, 'apiKey': apikey}}}
        elif rsa_key:
            body = {"auth": {"RAX-AUTH:rsaCredentials": {
                    "username": username, 'tokenKey': rsa_key}}}
        else:
            raise HTTPUnauthorized('No credentials supplied or detected')

        tenant = context.get('tenant')
        if tenant:
            auth = body['auth']
            auth['tenantId'] = tenant
            LOG.debug("Authenticating to tenant '%s'", tenant)
        if domain:
            body['auth']['RAX-AUTH:domain'] = {'name': domain}
        headers = {
            'Content-type': 'application/json',
            'Accept': 'application/json',
        }
        # TODO(zns): implement some caching to not overload auth
        try:
            LOG.debug('Authenticating to %s', self.endpoint_uri)
            http.request('POST', self.base_path, body=json.dumps(body),
                         headers=headers)
            resp = http.getresponse()
            body = resp.read()
        except Exception as exc:
            LOG.error('HTTP connection exception: %s', exc)
            raise HTTPUnauthorized('Unable to communicate with %s' %
                                   self.endpoint_uri)
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


def get_service_token_args(conf):
    """Use checkmate config to call get_service_token."""
    return conf.service_username, conf.service_password, conf.auth_endpoint


@caching.Cache(store=MODULE_CACHE, sensitive_args=[0, 1],
               cache_exceptions=False)
def get_service_token(service_username, service_password, endpoint):
    """Fetch auth token from keystone endpoint."""
    if not service_username or not service_password:
        raise ValueError("Must provide valid values for both "
                         "'username' and 'password'.")
    endpoint = endpoint.strip().strip('/')
    if not endpoint.endswith('/tokens'):
        if not endpoint.endswith('/v2.0'):
            endpoint = "%s%s" % (endpoint, '/v2.0')
        endpoint = "%s%s" % (endpoint, '/tokens')
    servargs = {
        'service_username': service_username,
        'service_password': service_password,
        'auth_endpoint': endpoint,
    }

    authenticator = SSOAuthenticator(servargs)
    authenticator._get_service_token()
    return authenticator.service_token
