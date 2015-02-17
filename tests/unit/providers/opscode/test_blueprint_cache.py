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

"""Test Blueprints cache."""

import errno
import os
import tempfile
import time

import mock
import unittest

from checkmate import exceptions as cmexc
from checkmate.common import git as common_git
from checkmate.providers.opscode.blueprint_cache import BlueprintCache
from checkmate.providers.opscode.blueprint_cache import \
    CommitableTemporaryDirectory


class TestUpdate(unittest.TestCase):
    def setUp(self):
        self.source_repo = "https://foo.com/checkmate/wordpress.git"
        self.cache = BlueprintCache(self.source_repo)

    @unittest.skip("TODO(zns): I doubt this test's usefulness")
    @mock.patch('checkmate.common.git.git_checkout')
    @mock.patch('checkmate.common.git.git_list_tags')
    @mock.patch('checkmate.common.git.git_clone')
    @mock.patch('os.makedirs')
    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    def test_non_existing_cache(self, mock_listdir, mock_path_exists,
                                mock_make_dirs, mock_clone, mock_tags,
                                mock_checkout):
        mock_listdir.return_value = []
        mock_path_exists.return_value = False
        mock_tags.return_value = ['master', 'working']

        self.cache.update()

        mock_path_exists.assert_called_with(self.cache.cache_path)
        mock_make_dirs.assert_called_with(
            os.path.dirname(self.cache.cache_path), 0o770)
        mock_clone.assert_called_with(
            self.cache.cache_path, self.source_repo,
            branch_or_tag='master', verbose=False)
        mock_tags.assert_called_once_with(self.cache.cache_path,
                                          with_messages=False)
        mock_checkout.assert_called_with(self.cache.cache_path, 'master')

    @unittest.skip("TODO(zns): I doubt this test's usefulness")
    @mock.patch.object(common_git.GitRepo, '__init__')
    @mock.patch('checkmate.common.git.git_clone')
    @mock.patch('os.makedirs')
    @mock.patch('os.rmdir')
    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    def test_non_existing_cache_exc_handling(self, mock_listdir,
                                             mock_path_exists, mock_rm,
                                             mock_make_dirs, mock_clone,
                                             mock_repo_init):
        mock_listdir.return_value = []
        mock_repo_init.return_value = None
        self.cache.repo.repo_dir = self.cache.cache_path
        mock_path_exists.return_value = False
        mock_clone.side_effect = cmexc.CheckmateCalledProcessError(1, "cmd")

        self.assertRaises(cmexc.CheckmateCalledProcessError, self.cache.update)

        mock_path_exists.assert_called()
        mock_make_dirs.assert_called_once()
        mock_clone.assert_called_once_with(mock.ANY,
                                           self.source_repo,
                                           branch_or_tag='master',
                                           verbose=False)

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

        mock_path_exists.assert_any_call(self.cache.cache_path)
        mock_is_file.assert_called_once_with(head_file_path)
        self.assertTrue(time.time.called)
        mock_mtime.assert_called_once_with(head_file_path)

    @unittest.skip("TODO(zns): works in python, fails in nose")
    @mock.patch('checkmate.common.git.git_checkout')
    @mock.patch('checkmate.common.git.git_list_tags')
    @mock.patch('checkmate.common.git.git_fetch')
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

        mock_path_exists.assert_any_call(self.cache.cache_path)
        mock_is_file.assert_called_once_with(head_file_path)
        self.assertTrue(time.time.called)
        mock_mtime.assert_called_once_with(head_file_path)
        mock_tags.assert_called_once_with(
            os.path.normpath(self.cache.cache_path), with_messages=False)
        mock_fetch.assert_called_once_with(
            self.cache.cache_path, remote=self.source_repo,
            refspec="refs/tags/master:refs/tags/master",
            verbose=False)
        mock_checkout.assert_called_once_with(self.cache.cache_path,
                                              'FETCH_HEAD')

    @unittest.skip("TODO(zns): works in python, fails in nose")
    @mock.patch('checkmate.common.git.git_list_tags')
    @mock.patch('checkmate.common.git.git_fetch')
    @mock.patch('checkmate.common.git.git_checkout')
    @mock.patch('os.path.getmtime')
    @mock.patch('time.time')
    @mock.patch('os.path.isfile')
    @mock.patch('os.path.exists')
    def test_cache_miss_for_missing_tag(self, mock_path_exists,
                                        mock_is_file, mock_time, mock_mtime,
                                        mock_checkout, mock_fetch, mock_tags):
        head_file_path = "%s/.git/FETCH_HEAD" % self.cache.cache_path
        mock_path_exists.return_value = True
        mock_is_file.return_value = True
        mock_time.return_value = 4000
        mock_mtime.return_value = 50
        mock_tags.return_value = []

        self.cache.update()

        mock_path_exists.assert_any_call(self.cache.cache_path)
        mock_is_file.assert_called_once_with(head_file_path)
        self.assertTrue(time.time.called)
        mock_mtime.assert_called_once_with(head_file_path)
        mock_tags.assert_called_once_with(
            os.path.normpath(self.cache.cache_path), with_messages=False)
        mock_fetch.assert_called_once_with(
            self.cache.cache_path, remote=self.source_repo,
            verbose=False, refspec="master")
        mock_checkout.assert_called_once_with(self.cache.cache_path,
                                              'FETCH_HEAD')

    def test_cache_creation_succeeds(self):
        temp_base_dir = tempfile.gettempdir()
        target_dir_name = next(tempfile._get_candidate_names())
        target_dir_path = os.path.join(temp_base_dir, target_dir_name)
        with CommitableTemporaryDirectory(dir=temp_base_dir) as tdc:
            with open(os.path.join(tdc.name, 'foo.txt'), 'w') as handle:
                handle.write("Hi!")
            tdc.commit(target_dir_path)

        assert not os.path.exists(tdc.name)
        assert os.path.exists(target_dir_path)
        assert os.path.exists(os.path.join(target_dir_path, 'foo.txt'))
        return temp_base_dir, target_dir_path

    def test_cache_concurrent_content_failure(self):
        """Check that concurrent write with differences fails."""
        temp_base_dir = tempfile.gettempdir()
        target_dir_name = next(tempfile._get_candidate_names())
        target_dir_path = os.path.join(temp_base_dir, target_dir_name)
        with CommitableTemporaryDirectory(dir=temp_base_dir) as tdc:
            with open(os.path.join(tdc.name, 'foo.txt'), 'w') as handle:
                handle.write("Hi!")
            with CommitableTemporaryDirectory(dir=temp_base_dir) as tdc2:
                with open(os.path.join(tdc2.name, 'foo.txt'), 'w') as handle2:
                    handle2.write("Not Hi!!!!")
                tdc2.commit(target_dir_path)
            with self.assertRaises(OSError):
                tdc.commit(target_dir_path)

    def test_cache_concurrent_succeeds(self):
        temp_base_dir = tempfile.gettempdir()
        target_dir_name = next(tempfile._get_candidate_names())
        target_dir_path = os.path.join(temp_base_dir, target_dir_name)
        with CommitableTemporaryDirectory(dir=temp_base_dir) as tdc:
            with open(os.path.join(tdc.name, 'foo.txt'), 'w') as handle:
                handle.write("Hi!")
            with CommitableTemporaryDirectory(dir=temp_base_dir) as tdc2:
                with open(os.path.join(tdc2.name, 'foo.txt'), 'w') as handle2:
                    handle2.write("Hi!")
                tdc2.commit(target_dir_path)
            tdc.commit(target_dir_path)  # Should not fail


if __name__ == '__main__':
    import sys
    from checkmate import test as cmtest
    cmtest.run_with_params(sys.argv[:])
