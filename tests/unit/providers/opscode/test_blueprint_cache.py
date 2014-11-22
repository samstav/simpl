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

"""Test Blueprints cache."""

import subprocess
import time

import mock
import unittest

from checkmate import exceptions
from checkmate.providers.opscode.blueprint_cache import BlueprintCache


class TestUpdate(unittest.TestCase):
    def setUp(self):
        self.source_repo = "https://foo.com/checkmate/wordpress.git"
        self.cache = BlueprintCache(self.source_repo)

    @mock.patch('checkmate.utils.git_checkout')
    @mock.patch('checkmate.utils.git_tags')
    @mock.patch('checkmate.utils.git_clone')
    @mock.patch('os.makedirs')
    @mock.patch('os.path.exists')
    def test_non_existing_cache(self, mock_path_exists, mock_make_dirs,
                                mock_clone, mock_tags, mock_checkout):
        mock_path_exists.return_value = False
        mock_tags.return_value = ['master', 'working']

        self.cache.update()

        mock_path_exists.assert_called_once_with(self.cache.cache_path)
        mock_make_dirs.assert_called_once_with(self.cache.cache_path)
        mock_clone.assert_called_once_with(self.cache.cache_path,
                                           self.source_repo, branch='master')
        mock_tags.assert_called_once_with(self.cache.cache_path)
        mock_checkout.assert_called_once_with(self.cache.cache_path, 'master')

    @mock.patch('checkmate.utils.git_clone')
    @mock.patch('os.makedirs')
    @mock.patch('os.path.exists')
    def test_non_existing_cache_exc_handling(self, mock_path_exists,
                                             mock_make_dirs, mock_clone):
        mock_path_exists.return_value = False
        mock_clone.side_effect = subprocess.CalledProcessError(1, "cmd")

        self.assertRaises(exceptions.CheckmateException, self.cache.update)

        mock_path_exists.assert_called_once_with(self.cache.cache_path)
        mock_make_dirs.assert_called_once_with(self.cache.cache_path)
        mock_clone.assert_called_once_with(self.cache.cache_path,
                                           self.source_repo, branch='master')

    @mock.patch('os.environ.get')
    @mock.patch('os.path.getmtime')
    @mock.patch('time.time')
    @mock.patch('os.path.isfile')
    @mock.patch('os.path.exists')
    def test_cache_hit(self, mock_path_exists, mock_is_file, mock_time,
                       mock_mtime, mock_environ_get):
        head_file_path = "%s/.git/FETCH_HEAD" % self.cache.cache_path
        mock_path_exists.return_value = True
        mock_is_file.return_value = True
        mock_time.return_value = 100
        mock_mtime.return_value = 50
        mock_environ_get.return_value = None

        self.cache.update()

        mock_path_exists.assert_called_once_with(self.cache.cache_path)
        mock_is_file.assert_called_once_with(head_file_path)
        self.assertTrue(time.time.called)
        mock_mtime.assert_called_once_with(head_file_path)
        mock_environ_get.assert_called_once_with(
            "CHECKMATE_BLUEPRINT_CACHE_EXPIRE")

    @mock.patch('checkmate.utils.git_checkout')
    @mock.patch('checkmate.utils.git_tags')
    @mock.patch('checkmate.utils.git_fetch')
    @mock.patch('os.path.getmtime')
    @mock.patch('time.time')
    @mock.patch('os.path.isfile')
    @mock.patch('os.path.exists')
    def test_cache_miss_for_default_branch(self, mock_path_exists,
                                           mock_is_file, mock_time,
                                           mock_mtime, mock_fetch, mock_tags,
                                           mock_checkout):
        head_file_path = "%s/.git/FETCH_HEAD" % self.cache.cache_path
        mock_path_exists.return_value = True
        mock_is_file.return_value = True
        mock_time.return_value = 4000
        mock_mtime.return_value = 50
        mock_tags.return_value = ['master']

        self.cache.update()

        mock_path_exists.assert_called_once_with(self.cache.cache_path)
        mock_is_file.assert_called_once_with(head_file_path)
        self.assertTrue(time.time.called)
        mock_mtime.assert_called_once_with(head_file_path)
        mock_tags.assert_called_once_with(self.cache.cache_path)
        mock_fetch.assert_called_once_with(
            self.cache.cache_path, "refs/tags/master:refs/tags/master")
        mock_checkout.assert_called_once_with(self.cache.cache_path, 'master')

    @mock.patch('checkmate.utils.git_tags')
    @mock.patch('checkmate.utils.git_pull')
    @mock.patch('os.path.getmtime')
    @mock.patch('time.time')
    @mock.patch('os.path.isfile')
    @mock.patch('os.path.exists')
    def test_cache_miss_for_missing_tag(self, mock_path_exists,
                                        mock_is_file, mock_time, mock_mtime,
                                        mock_pull, mock_tags):
        head_file_path = "%s/.git/FETCH_HEAD" % self.cache.cache_path
        mock_path_exists.return_value = True
        mock_is_file.return_value = True
        mock_time.return_value = 4000
        mock_mtime.return_value = 50
        mock_tags.return_value = []

        self.cache.update()

        mock_path_exists.assert_called_once_with(self.cache.cache_path)
        mock_is_file.assert_called_once_with(head_file_path)
        self.assertTrue(time.time.called)
        mock_mtime.assert_called_once_with(head_file_path)
        mock_tags.assert_called_once_with(self.cache.cache_path)
        mock_pull.assert_called_once_with(self.cache.cache_path, 'master')

if __name__ == '__main__':
    import sys
    from checkmate import test as cmtest
    cmtest.run_with_params(sys.argv[:])
