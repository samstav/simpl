# Copyright (c) 2011-2013 Rackspace Hosting
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
"""
Middleware to detect and handle git SmartHTTP traffic



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
from __future__ import absolute_import

import os
import re

import bottle

from checkmate.common import caching
from checkmate.common import config
from checkmate.contrib import wsgi_git_http_backend
from checkmate.git import manager

CONFIG = config.current()
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


class GitMiddleware():

    """Adds support for git http-backend interaction."""

    def __init__(self, app, root_path):
        self.app = app
        self.root = root_path

    def __call__(self, e, h):
        if e.get('CONTENT_TYPE') in [
            'application/x-git-upload-pack-request',
            'application/x-git-receive-pack-request'
        ]:
            pass
        elif e['QUERY_STRING'] in [
            'service=git-upload-pack',
            'service=git-receive-pack'
        ]:
            pass
        else:
            return self.app(e, h)
        try:
            GIT_SERVER_APP.match(e)
            e['GIT_PROJECT_BASE'] = self.root
            return GIT_SERVER_APP(e, h)
        except bottle.HTTPError:
            pass
        return self.app(e, h)


#
# Route utility routines
#
@caching.Cache(sensitive_args=[1], timeout=600, cache_exceptions=True)
def _check_git_auth(user, passwd):
    """Basic Auth for git back-end (smart HTTP).

    :returns: true/false - true means authenticated successfully
    """
    endpoints = os.environ.get('CHECKMATE_AUTH_ENDPOINTS')
    auth_endpoint = None
    if endpoints:
        endpoints = json.loads(endpoints)
        for endpoint in endpoints:
            if (endpoint.get('middleware') != 
                    'checkmate.middleware.TokenAuthMiddleware'):
                middleware = utils.import_class(endpoint['middleware'])
                instance = middleware(None,
                                      endpoint)
                auth_endpoint = instance
                break

    if not auth_endpoint:
        return False

    try:
        access = auth_endpoint._auth_keystone(self, bottle.request.context,
                                              username=user, password=passwd)

    except StandardError:
        return False



def _set_git_environ(environ, repo, path):
    """Bottle environment tweaking for git kitchen routes.

    :param environ: CGI environment (converted from WSGI)
    :param repo: the git repo to base calls off off (a single path part that
        gets added to GIT_PROJECT_BASE)
    :param path: the path into the repo that is being requested
    """
    cgi_env = dict()
    for env_var in EXPECTED_ENVIRONMENT_LIST:
        if env_var in environ:
            cgi_env[env_var] = environ[env_var]
    if 'PATH_INFO' not in cgi_env:
        cgi_env['PATH_INFO'] = ''
    cgi_env['GIT_HTTP_EXPORT_ALL'] = '1'
    cgi_env['GIT_PROJECT_ROOT'] = os.path.join(environ['GIT_PROJECT_BASE'],
                                               repo)
    cgi_env['PATH_INFO'] = '/%s' % path
    if (
        re.search('/info/refs', cgi_env['PATH_INFO']) and
        cgi_env['REQUEST_METHOD'] == 'GET'
    ):
        cgi_env['CONTENT_TYPE'] = ''
    # TODO: (REMOTE_USER) where some authorization could go
    return cgi_env


def _git_route_callback(dep_id, path):
    """Check deployment and verify it is valid before git backend call."""
    environ = _set_git_environ(dict(bottle.request.environ), dep_id, path)
    if not os.path.isdir(environ['GIT_PROJECT_ROOT']):
        # TODO: not sure what to do about this
        raise bottle.HTTPError(code=404, output="%s not found" %
                               environ['PATH_INFO'])
    manager.init_deployment_repo(environ['GIT_PROJECT_ROOT'])
    (status_line, headers, response_body_generator
     ) = wsgi_git_http_backend.wsgi_to_git_http_backend(environ)
    for header, value in headers:
        bottle.response.set_header(header, value)
    bottle.response.status = status_line
    return response_body_generator


#
# Bottle routes
#
@GIT_SERVER_APP.get("/<tenant_id>/deployments/<dep_id>.git/<path:re:.+>")
@bottle.auth_basic(_check_git_auth) #basic auth
def git_route_get(tenant_id, dep_id, path):
    return _git_route_callback(dep_id, path)


@GIT_SERVER_APP.post("/<tenant_id>/deployments/<dep_id>.git/<path:re:.+>")
@bottle.auth_basic(_check_git_auth) #basic auth
def git_route_post(tenant_id, dep_id, path):
    return _git_route_callback(dep_id, path)
