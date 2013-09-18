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

from checkmate.contrib import wsgi_git_http_backend
from checkmate.common.git import manager
from checkmate.common.git import middleware



class TestGitMiddlewareSetGitEnviron(unittest.TestCase):

    def test_set_git_environ_no_env(self):
        environ_dict = {}
        environ = middleware._set_git_environ(environ_dict, None, None)
        expected_env = {
            'PATH_INFO': '/',
            'GIT_HTTP_EXPORT_ALL': '1'
        }
        self.assertEqual(expected_env, environ)

    def test_set_git_environ_extra_env(self):
        environ_dict = {'foo': 'bar'}
        environ = middleware._set_git_environ(environ_dict, None, None)
        expected_env = {
            'PATH_INFO': '/',
            'GIT_HTTP_EXPORT_ALL': '1'
        }
        self.assertEqual(expected_env, environ)

    def test_set_env_path_valid_url(self):
        environ_dict = {
            'PATH_INFO':
            '/547249/deployments/b3fe346f543a4a95b4712969c420dde6.git',
            'GIT_PROJECT_BASE': '/blah',
        }
        environ = middleware._set_git_environ(environ_dict, "repo", ".git")
        self.assertEqual( '/blah/repo', environ['GIT_PROJECT_ROOT'])
        self.assertEqual('/.git', environ['PATH_INFO'])


class TestGitMiddlewareGitRouteCallback(unittest.TestCase):

    @mock.patch.object(os.path, 'isdir')
    @mock.patch.object(middleware, '_set_git_environ')
    @mock.patch.object(middleware.bottle, 'request')
    @mock.patch.object(manager, 'init_deployment_repo')
    @mock.patch.object(wsgi_git_http_backend, 'wsgi_to_git_http_backend')
    def test_route_cb(self, mock_wsgi, mock_init, mock_req, mock_env,
                      mock_isdir):
        # mocks
        mock_isdir.return_value = True
        mock_env.return_value = {'GIT_PROJECT_ROOT': '/git/project/root'}
        mock_init.return_value = True
        mock_wsgi.return_value = ("200 OK", {}, "fxn")
        # kick off
        middleware._git_route_callback(None, None)
        self.assertTrue(mock_wsgi.called)


if __name__ == '__main__':
    import sys
    from checkmate import test
    test.run_with_params(sys.argv[:])
