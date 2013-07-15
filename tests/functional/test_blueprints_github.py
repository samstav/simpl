# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import base64
import os
import unittest

import github as gh
import mox

from checkmate.blueprints import github
from checkmate.common.config import Config


class TestGitHubManager(unittest.TestCase):
    '''Tests GitHubManager.'''

    def setUp(self):
        self.mox = mox.Mox()
        self.config = Config({
            'github_api': 'http://localhost',
            'organization': 'Blueprints',
            'ref': 'master',
            'cache_dir': '/tmp',
        })
        self.manager = github.GitHubManager({}, self.config)

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_get_blueprint_bad_yaml(self):
        '''Test _get_blueprint handles invalid YAML and returns None.'''
        yaml = '@'
        tag = self.config.ref
        repo = self.mox.CreateMock(gh.Repository.Repository)
        repo.clone_url = "https://clone"

        self.mox.StubOutWithMock(self.manager, '_repo_contains_ref')
        self.manager._repo_contains_ref(repo, tag).AndReturn(True)

        dep_file = self.mox.CreateMockAnything()
        dep_file.content = base64.b64encode(yaml)
        repo.get_file_contents("checkmate.yaml", ref=tag).AndReturn(dep_file)

        self.mox.ReplayAll()
        result = self.manager._get_blueprint(repo, tag)
        self.mox.VerifyAll()
        self.assertIsNone(result)

    def test_get_blueprint_yaml_sans_blueprint(self):
        '''Test _get_blueprint handles file with no blueprint.'''
        yaml = 'inputs: {}'
        tag = self.config.ref
        repo = self.mox.CreateMock(gh.Repository.Repository)
        repo.clone_url = "https://clone"

        self.mox.StubOutWithMock(self.manager, '_repo_contains_ref')
        self.manager._repo_contains_ref(repo, tag).AndReturn(True)

        dep_file = self.mox.CreateMockAnything()
        dep_file.content = base64.b64encode(yaml)
        repo.get_file_contents("checkmate.yaml", ref=tag).AndReturn(dep_file)

        self.mox.ReplayAll()
        result = self.manager._get_blueprint(repo, tag)
        self.mox.VerifyAll()
        self.assertIsNone(result)

    def test_get_blueprint_bad_escape(self):
        '''Test _get_blueprint handles invalid YAML escapes.'''
        yaml = ('- regex: "[A-Za-z0-9!#$%&''*+/=?^_`{|}~-]+ Za-z0-9!#$%&''*+/='
                '?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&''*+/=?^_`{|}~-]+')
        tag = self.config.ref
        repo = self.mox.CreateMock(gh.Repository.Repository)
        repo.clone_url = "https://clone"

        self.mox.StubOutWithMock(self.manager, '_repo_contains_ref')
        self.manager._repo_contains_ref(repo, tag).AndReturn(True)

        dep_file = self.mox.CreateMockAnything()
        dep_file.content = base64.b64encode(yaml)
        repo.get_file_contents("checkmate.yaml", ref=tag).AndReturn(dep_file)

        self.mox.ReplayAll()
        result = self.manager._get_blueprint(repo, tag)
        self.mox.VerifyAll()
        self.assertIsNone(result)

    def test_write_cache_no_dir_access(self):
        '''Test cannot write to cache file.'''
        self.mox.StubOutWithMock(github, 'REDIS')
        github.REDIS = None

        self.mox.StubOutWithMock(os.path, 'exists')
        os.path.exists(self.config.cache_dir).AndReturn(False)

        error = OSError("[Errno 13] Permission denied: '%s'" %
                        self.config.cache_dir)
        self.mox.StubOutWithMock(os, 'makedirs')
        os.makedirs(self.config.cache_dir, 502).AndRaise(error)

        self.mox.ReplayAll()
        self.manager._update_cache()
        self.mox.VerifyAll()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
