# pylint: disable=R0904,W0212

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

"""Tests for git middleware."""
import mock
import os
import unittest

from checkmate.git import manager
from checkmate.git import middleware
from checkmate import wsgi_git_http_backend


@unittest.skip("Not yet ported to latest refactor")
class TestGitMiddlewareSetGitEnviron(unittest.TestCase):

    #@unittest.skip("Temp skip")
    def test_set_git_environ_no_env(self):
        environ_dict = {}
        environ = middleware._set_git_environ(environ_dict, None, None)
        expected_env = {
            'GIT_PROJECT_ROOT': os.environ.get(
            "CHECKMATE_CHEF_LOCAL_PATH",
            "/var/local/checkmate/deployments"
            ) + "/",
            'PATH_INFO': '/.',
            'GIT_HTTP_EXPORT_ALL': '1'
        }
        self.assertEqual(expected_env, environ)

    #@unittest.skip("Temp skip")
    def test_set_git_environ_extra_env(self):
        environ_dict = {'foo': 'bar'}
        environ = middleware._set_git_environ(environ_dict, None, None)
        expected_env = {
            'GIT_PROJECT_ROOT': os.environ.get(
            "CHECKMATE_CHEF_LOCAL_PATH",
            "/var/local/checkmate/deployments"
            ) + "/",
            'PATH_INFO': '/.',
            'GIT_HTTP_EXPORT_ALL': '1'
        }
        self.assertEqual(expected_env, environ)

    def test_set_env_path_valid_url(self):
        environ_dict = {
            'PATH_INFO':
            '/547249/deployments/b3fe346f543a4a95b4712969c420dde6.git'
        }
        dep_path = os.environ.get(
            "CHECKMATE_CHEF_LOCAL_PATH",
            "/var/local/checkmate/deployments"
        )
        environ = middleware._set_git_environ(environ_dict, None, None)
        self.assertEqual(
            dep_path + '/b3fe346f543a4a95b4712969c420dde6',
            environ['GIT_PROJECT_ROOT']
        )
        self.assertEqual('/.git', environ['PATH_INFO'])


@unittest.skip("Not yet ported to latest refactor")
class TestGitMiddlewareGitRouteCallback(unittest.TestCase):

    @mock.patch.object(middleware, 'Response')
    @mock.patch.object(os.path, 'isdir')
    @mock.patch.object(middleware, '_set_git_environ')
    @mock.patch.object(middleware, 'request')
    @mock.patch.object(manager, 'init_deployment_repo')
    @mock.patch.object(wsgi_git_http_backend, 'wsgi_to_git_http_backend')
    #@unittest.skip("Temp skip")
    def test_route_cb(
        self, mock_wsgi,
        mock_init, mock_req, mock_env, mock_isdir, mock_response
    ):
        # mocks
        mock_isdir.return_value = True
        mock_env.return_value = {'GIT_PROJECT_ROOT': '/git/project/root'}
        mock_init.return_value = True
        mock_wsgi.return_value = (1, 2, 3)
        mock_response.return_value = True
        # kick off
        middleware._git_route_callback(None, None)
        assert mock_wsgi.called


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
