import unittest
from mock import patch, Mock, mock_open
import os
import git
from checkmate import git_middleware
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


class TestGitMiddleware_init_deployment(unittest.TestCase):

    @patch.object(git.Repo, 'init')
    @patch.object(git_middleware, '_is_git_repo')
    def test_git_repo(self, mock_is_git_repo, mock_init):
        # mocks
        mock_is_git_repo.return_value = True
        # kick off
        git_middleware._git_init_deployment('/dep/path')
        assert not mock_init.called

    @patch.object(os, 'chmod')
    @patch.object(os, 'listdir')
    @patch.object(os, 'path')
    @patch.object(git.Repo, 'init')
    @patch.object(git_middleware, '_is_git_repo')
    #@unittest.skip("Temp skip")
    def test_no_git_repo_no_content(
        self, mock_is_git_repo,
        mock_init, mock_listdir, mock_path, mock_chmod
    ):
        with patch.object(
            git_middleware,
            'open',
            mock_open(read_data='foobar'),
            create=True
        ) as m:
            # mocks
            mock_repo = Mock()
            mock_cw = Mock()
            mock_repo.config_writer = mock_cw
            mock_is_git_repo.return_value = False
            mock_init.return_value = mock_repo
            mock_listdir.return_value = []
            mock_chmod.return_value = True
            mock_path.isfile.return_value = False
            # kick off
            git_middleware._git_init_deployment('/dep/path')
            #mock_repo.git.commit.assert_called_with(m='init deployment: path')
            assert mock_repo.git.submodule.called
            assert mock_repo.git.commit.called
            #mock_repo.git.submodule.assert_called_with(
            #   'update', '--init', '--recursive'
            #)
            mock_repo.git.add.assert_called_with('*')
            #mock_repo.git.commit.assert_called_with(m='add subfolders: path')
            mock_cw.set_value.asset_called_with(
                'receive',
                'denyCurrentBranch',
                'ignore')
            mock_cw.set_value.asset_called_with('http', 'receivepack', 'true')

    @patch.object(os, 'chmod')
    @patch.object(os, 'listdir')
    @patch.object(os, 'path')
    @patch.object(git.Repo, 'init')
    @patch.object(git_middleware, '_is_git_repo')
    #@unittest.skip("Temp skip")
    def test_no_git_repo_with_file(
            self, mock_is_git_repo,
            mock_init, mock_path, mock_listdir, mock_chmod
    ):
        with patch.object(
            git_middleware,
            'open',
            mock_open(read_data='foobar'),
            create=True
        ) as m:
            # mocks
            mock_repo = Mock()
            mock_cw = Mock()
            mock_repo.config_writer = mock_cw
            mock_is_git_repo.return_value = False
            mock_init.return_value = mock_repo
            mock_listdir.return_value = ['file']
            mock_chmod.return_value = True
            mock_path.isfile.return_value = True
            # kick off
            git_middleware._git_init_deployment('/dep/path')
            mock_repo.git.add.asset_called_with('/dep/path/file')
            #mock_repo.git.commit.assert_called_with(m='init deployment: path')
            assert mock_repo.git.commit.called
            mock_cw.set_value.asset_called_with(
                'receive',
                'denyCurrentBranch',
                'ignore')
            mock_cw.set_value.asset_called_with('http', 'receivepack', 'true')

    @patch.object(os, 'chmod')
    @patch.object(os, 'listdir')
    @patch.object(os, 'path')
    @patch.object(git.Repo, 'init')
    @patch.object(git_middleware, '_is_git_repo')
    #@unittest.skip("Temp skip")
    def test_no_git_repo_with_folder(
            self, mock_is_git_repo,
            mock_init, mock_path, mock_listdir, mock_chmod
    ):
        with patch.object(
            git_middleware,
            'open',
            mock_open(read_data='foobar'),
            create=True
        ) as m:
            # mocks
            mock_repo = Mock()
            mock_cw = Mock()
            mock_repo.config_writer = mock_cw
            mock_is_git_repo.return_value = False
            mock_init.return_value = mock_repo
            mock_listdir.return_value = ['folder']
            mock_chmod.return_value = True
            mock_path.isfile.return_value = False
            # kick off
            git_middleware._git_init_deployment('/dep/path')
            mock_repo.git.add.asset_called_with('/dep/path/folder')
            #mock_repo.git.commit.assert_called_with(m='init deployment: path')
            assert mock_repo.git.commit.called
            mock_cw.set_value.asset_called_with(
                'receive',
                'denyCurrentBranch',
                'ignore')
            mock_cw.set_value.asset_called_with('http', 'receivepack', 'true')

    @patch.object(os, 'chmod')
    @patch.object(os, 'listdir')
    @patch.object(os, 'path')
    @patch.object(git.Repo, 'init')
    @patch.object(git_middleware, '_is_git_repo')
    #@unittest.skip("Temp skip")
    def test_no_git_repo_with_submodule(
            self, mock_is_git_repo,
            mock_init, mock_path, mock_listdir, mock_chmod
    ):
        with patch.object(
            git_middleware,
            'open',
            mock_open(read_data='foobar'),
            create=True
        ) as m:
            # mocks
            mock_repo = Mock()
            mock_cw = Mock()
            mock_repo.config_writer = mock_cw
            mock_is_git_repo.return_value = False
            mock_init.return_value = mock_repo
            mock_listdir.return_value = ['submod']
            mock_chmod.return_value = True
            mock_path.isfile.return_value = False
            # kick off
            git_middleware._git_init_deployment('/dep/path')
            #mock_repo.git.submodule.asset_called_with(
            #    'add', '--path=submodule', '--ignore=dirty')
            #mock_repo.git.commit.assert_called_with(m='init deployment: path')
            assert mock_repo.git.commit.called
            mock_cw.set_value.asset_called_with(
                'receive',
                'denyCurrentBranch',
                'ignore')
            mock_cw.set_value.asset_called_with('http', 'receivepack', 'true')
