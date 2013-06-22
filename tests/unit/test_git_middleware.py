import unittest
from mock import patch, Mock, mock_open
import os
import git
from checkmate.git import middleware
from checkmate import wsgi_git_http_backend


class TestGitMiddleware_set_git_environ(unittest.TestCase):

    #@unittest.skip("Temp skip")
    def test_set_git_environ_no_env(self):
        environE = {}
        environ = git_middleware._set_git_environ(environE)
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
        environ = git_middleware._set_git_environ(environE)
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
        environ = git_middleware._set_git_environ(environE)
        self.assertEqual(
            dep_path+'/b3fe346f543a4a95b4712969c420dde6',
            environ['GIT_PROJECT_ROOT']
        )
        self.assertEqual('/.git', environ['PATH_INFO'])


class TestGitMiddleware_git_route_callback(unittest.TestCase):

    @patch.object(git_middleware, 'Response')
    @patch.object(os.path, 'isdir')
    @patch.object(git_middleware, '_set_git_environ')
    @patch.object(git_middleware, 'request')
    @patch.object(git_middleware, '_git_init_deployment')
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
        git_middleware._git_route_callback()
        assert mock_wsgi.called


