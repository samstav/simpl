# pylint: disable=E1103,W0212

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

"""Tests for Blueprints' GithubManager class."""
import base64
import os
import unittest

import github as gh
import mox

from checkmate.blueprints import github
from checkmate.common import config as cmconf


class TestGitHubManager(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()
        self.config = cmconf.Config({
            'github_api': 'http://localhost',
            'organization': 'Blueprints',
            'ref': 'master',
            'cache_dir': '/tmp',
        })
        self.manager = github.GitHubManager(self.config)

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_get_blueprint_bad_yaml(self):
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
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
