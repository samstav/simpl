# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import os
import unittest

from mock import patch

from checkmate.git import manager
from checkmate.git import middleware
from checkmate import wsgi_git_http_backend


class TestGitMiddleware_set_git_environ(unittest.TestCase):

    #@unittest.skip("Temp skip")
    def test_set_git_environ_no_env(self):
        environE = {}
        environ = middleware._set_git_environ(environE)
        testEnviron = {
            'GIT_PROJECT_ROOT': os.environ.get(
            "CHECKMATE_CHEF_LOCAL_PATH",
            "/var/local/checkmate/deployments"
            ) + "/",
            'PATH_INFO': '/.',
            'GIT_HTTP_EXPORT_ALL': '1'
        }
        self.assertEqual(testEnviron, environ)

    #@unittest.skip("Temp skip")
    def test_set_git_environ_extra_env(self):
        environE = {'foo': 'bar'}
        environ = middleware._set_git_environ(environE)
        testEnviron = {
            'GIT_PROJECT_ROOT': os.environ.get(
            "CHECKMATE_CHEF_LOCAL_PATH",
            "/var/local/checkmate/deployments"
            ) + "/",
            'PATH_INFO': '/.',
            'GIT_HTTP_EXPORT_ALL': '1'
        }
        self.assertEqual(testEnviron, environ)

    def test_set_git_environ_path_valid_dep_url(self):
        environE = {
            'PATH_INFO':
            '/547249/deployments/b3fe346f543a4a95b4712969c420dde6.git'
        }
        dep_path = os.environ.get(
            "CHECKMATE_CHEF_LOCAL_PATH",
            "/var/local/checkmate/deployments"
        )
        environ = middleware._set_git_environ(environE)
        self.assertEqual(
            dep_path + '/b3fe346f543a4a95b4712969c420dde6',
            environ['GIT_PROJECT_ROOT']
        )
        self.assertEqual('/.git', environ['PATH_INFO'])


class TestGitMiddleware_git_route_callback(unittest.TestCase):

    @patch.object(middleware, 'Response')
    @patch.object(os.path, 'isdir')
    @patch.object(middleware, '_set_git_environ')
    @patch.object(middleware, 'request')
    @patch.object(manager, 'init_deployment_repo')
    @patch.object(wsgi_git_http_backend, 'wsgi_to_git_http_backend')
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
        middleware._git_route_callback()
        assert mock_wsgi.called


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
