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

"""Middleware to detect and handle git SmartHTTP traffic.


-----------------------------------------------------------------------
Git http-backend Bottle Routes
-----------------------------------------------------------------------

Tested bottle routes:

    (1) git clone http://localhost:8080/deployments/{key}.git
    (2) git push (with local .git/config set from the clone)
    (3) git pull (with local .git/config set from the clone)

Currently, all git http-backend routes initiate with this request type:


    NEEDED BY HTTP-PBACKEND:
        GET /{tenant_id}/deployments/{key}.git/info/refs HTTP/1.1

        PATH_INFO: /deployments/{key}.git/info/refs
        REQUEST_METHOD: GET
        QUERY_STRING: service=git-upload-pack
        GIT_HTTP_EXPORT_ALL: 1

    NEEDED BY OTHER FOLKS (middleware, etc):
        CONTENT_TYPE: text/plain
        wsgi.version: (1,0)
        wsgi.run_once: False
        wsgi.input: <eventlet.wsgi.Input object>
        wsgi.errors: <open file '<stderr>', mode 'w'>
        wsgi.multiprocess: False, 'wsgi.input': <eventlet.wsgi.Input object>
        wsgi.multithread: True

Currently, all successful git http-backend routes end with this response:

    HTTP/1.1 200 OK
    Content-Type: application/x-git-upload-pack-advertisement
    Pragma: no-cache
    Cache-Control: no-cache, max-age=0, must-revalidate
    Expires: Fri, 01 Jan 1980 00:00:00 GMT

    Note: reponse body data is in binary form.

Git clone request perform a 2nd chained request type:

    POST /{tenant_id}/deployments/{key}.git/git-upload-pack HTTP/1.1

    PATH_INFO: /deployments/{key}.git/git-upload-pack
    REQUEST_METHOD: POST
    CONTENT_TYPE: application/x-git-upload-pack-request
    CONTENT_LENGTH: 174
    GIT_HTTP_EXPORT_ALL: 1
    wsgi.version: (1,0)
    wsgi.run_once: False
    wsgi.input: <eventlet.wsgi.Input object>
    wsgi.errors: <open file '<stderr>', mode 'w'>
    wsgi.multiprocess: False
    wsgi.multithread: True

Git push request perform a 2nd chained request type:

    GET /{tenant_id}/deployments/{key}.git/HEAD HTTP/1.1

    PATH_INFO: '/ba3ce9f785f8438c9c8bd6a7cf1a7569.git/HEAD'
    REQUEST_METHOD': GET
    CONTENT_TYPE: text/plain
    GIT_HTTP_EXPORT_ALL: 1
    wsgi.version: (1,0)
    wsgi.run_once: False
    wsgi.input: <eventlet.wsgi.Input object>
    wsgi.errors: <open file '<stderr>', mode 'w'>
    wsgi.multiprocess: False
    wsgi.multithread: True

No other request or reponse environ/header settings are given
to/by gitHttpBackend.

    ie, not observed:

      # X-Auth-Token: 0d6f2078-55f9-4a7c-97c5-7acb57b1c663
      # Host: checkmate.rackspace.com
      # Content-Type: application/json

    Note-1: Tokens aren't observsed currently. We may want to add
    this ability however.
    Note-2: Mixed case 'Content-Type' isn't used. Upper case
    'CONTENT_TYPE' is.
    Note-3: Bottle sends alot of environ settings. Some are
    causing conflicts with gitHttpBackend. Attempts have been made
    to filter out only the absolutely necessary ones.
    This is why 'Host', etc. aren't seen.

-----------------------------------------------------------------------
"""

import json
import logging
import os
import re

import bottle
from eventlet.green import httplib

from checkmate.common import caching
from checkmate.common.git import manager
from checkmate.contrib import urlparse
from checkmate.contrib import wsgi_git_http_backend

GIT_SERVER_APP = bottle.Bottle()
EXPECTED_ENVIRONMENT_LIST = [
    'wsgi.errors',
    'wsgi.input',
    'wsgi.multiprocess',
    'wsgi.multithread',
    'wsgi.run_once',
    'wsgi.url.scheme',
    'wsgi.version',
    'CONTENT_LENGTH',
    'CONTENT_TYPE',
    'PATH_INFO',
    'QUERY_STRING',
    'REQUEST_METHOD'
]
LOG = logging.getLogger(__name__)


class GitMiddleware(object):

    """Add support for git http-backend interaction."""

    def __init__(self, app, root_path):
        self.app = app
        self.root = root_path

    def __call__(self, env, handler):
        if env.get('CONTENT_TYPE') in [
                'application/x-git-upload-pack-request',
                'application/x-git-receive-pack-request'
        ]:
            pass
        elif env.get('QUERY_STRING') in [
                'service=git-upload-pack',
                'service=git-receive-pack'
        ]:
            pass
        else:
            return self.app(env, handler)
        try:
            GIT_SERVER_APP.match(env)
            env['GIT_PROJECT_BASE'] = self.root
            return GIT_SERVER_APP(env, handler)
        except bottle.HTTPError:
            pass
        return self.app(env, handler)


#
# Route utility routines
#
@caching.Cache(sensitive_args=[1], timeout=600, cache_exceptions=True)
def _check_git_auth(user, password):
    """Basic Auth for git back-end (smart HTTP).

    :returns: true/false - true means authenticated successfully
    """
    LOG.debug("Authenticating %s for git access", user)
    endpoint_uri = None
    try:
        endpoints = os.environ.get('CHECKMATE_AUTH_ENDPOINTS')
        if endpoints:
            endpoints = json.loads(endpoints)
            for endpoint in endpoints:
                if 'identity-internal' in endpoint['uri']:
                    endpoint_uri = endpoint['uri']
                    break
    except StandardError as exc:
        LOG.info("Error authenticating %s: %s", user, exc)
        return False

    if not endpoint_uri:
        LOG.info("No auth endpoint to authenticate %s", user)
        return False

    try:
        access = _auth_racker(endpoint_uri, user, password)
        if 'access' in access:
            return True
    except StandardError as exc:
        LOG.warning("Rejecting authenticatation for %s: %s", user, exc)
    return False


def _auth_racker(endpoint_uri, username, password):
    """Authenticate to Global Auth."""
    if not username:
        LOG.info("Username not supplied")
        return None
    url = urlparse.urlparse(endpoint_uri)
    use_https = url.scheme == 'https'
    if use_https:
        port = url.port or 443
    else:
        port = url.port or 80
    if use_https:
        http_class = httplib.HTTPSConnection  # pylint: disable=E1101
    else:
        http_class = httplib.HTTPConnection  # pylint: disable=E1101
    http = http_class(url.hostname, port, timeout=10)
    body = {
        "auth": {
            "RAX-AUTH:domain": {
                "name": "Rackspace"
            },
            "passwordCredentials": {
                "username": username,
                "password": password,
            }
        }
    }

    headers = {
        'Content-type': 'application/json',
        'Accept': 'application/json',
    }
    try:
        LOG.debug('Authenticating to %s', endpoint_uri)
        http.request('POST', url.path, body=json.dumps(body),
                     headers=headers)
        resp = http.getresponse()
        body = resp.read()
    except Exception as exc:
        LOG.error('HTTP connection exception: %s', exc)
        return None
    finally:
        http.close()

    if resp.status != 200:
        LOG.debug('Authentication failed: %s', resp.reason)
        return None

    try:
        content = json.loads(body)
    except ValueError:
        msg = 'Keystone did not return json-encoded body'
        LOG.debug(msg)
        return None
    return content


def _set_git_environ(environ, repo, path):
    """Bottle environment tweaking for git kitchen routes.

    :param environ: CGI environment (converted from WSGI)
    :param repo: the git repo to base calls off off (a single path part that
        gets added to GIT_PROJECT_BASE)
    :param path: the path into the repo that is being requested
    """
    cgi_env = {}
    for env_var in EXPECTED_ENVIRONMENT_LIST:
        if env_var in environ:
            cgi_env[env_var] = environ[env_var]
    if 'PATH_INFO' not in cgi_env:
        cgi_env['PATH_INFO'] = ''
    cgi_env['GIT_HTTP_EXPORT_ALL'] = '1'
    if 'GIT_PROJECT_BASE' in environ:
        cgi_env['GIT_PROJECT_ROOT'] = os.path.join(environ['GIT_PROJECT_BASE'],
                                                   repo)
    cgi_env['PATH_INFO'] = '/%s' % (path or '')
    if (re.search('/info/refs', cgi_env['PATH_INFO']) and
            cgi_env['REQUEST_METHOD'] == 'GET'):
        cgi_env['CONTENT_TYPE'] = ''
    return cgi_env


def _git_route_callback(dep_id, path):
    """Check deployment and verify it is valid before git backend call."""
    environ = _set_git_environ(dict(bottle.request.environ), dep_id, path)
    if not os.path.isdir(environ['GIT_PROJECT_ROOT']):
        raise bottle.HTTPError(status=404, output="%s not found" %
                               environ['PATH_INFO'])
    manager.init_deployment_repo(environ.get('GIT_PROJECT_ROOT'))
    status_line, headers, response_body_generator = (
        wsgi_git_http_backend.wsgi_to_git_http_backend(environ))
    for header, value in headers:
        bottle.response.set_header(header, value)
    bottle.response.status = status_line
    return response_body_generator


#
# Bottle routes
#
# pylint: disable=W0613
@GIT_SERVER_APP.get("/<tenant_id>/deployments/<dep_id>.git/<path:re:.+>")
@bottle.auth_basic(_check_git_auth)
def git_route_get(tenant_id, dep_id, path):
    """Call git-http-server callback for GET."""
    return _git_route_callback(dep_id, path)


@GIT_SERVER_APP.post("/<tenant_id>/deployments/<dep_id>.git/<path:re:.+>")
@bottle.auth_basic(_check_git_auth)
def git_route_post(tenant_id, dep_id, path):
    """Call git-http-server callback for POST."""
    return _git_route_callback(dep_id, path)
