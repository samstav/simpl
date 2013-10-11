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
import os
import subprocess
import time

import mock
import unittest

from checkmate.providers.opscode.solo.blueprint_cache import BlueprintCache
from checkmate import utils, exceptions


class TestUpdate(unittest.TestCase):
    def setUp(self):
        self.source_repo = "https://foo.com/checkmate/wordpress.git"
        self.cache = BlueprintCache(self.source_repo)

    def test_non_existing_cache(self):
        os.path.exists = mock.Mock(return_value=False)
        os.makedirs = mock.Mock()
        utils.git_clone = mock.Mock()
        utils.git_tags = mock.Mock(return_value=['master', 'working'])
        utils.git_checkout = mock.Mock()

        self.cache.update()

        os.path.exists.assert_called_once_with(self.cache.cache_path)
        os.makedirs.assert_called_once_with(self.cache.cache_path)
        utils.git_clone.assert_called_once_with(self.cache.cache_path,
                                                self.source_repo,
                                                branch='master')
        utils.git_tags.assert_called_once_with(self.cache.cache_path)
        utils.git_checkout.assert_called_once_with(self.cache.cache_path,
                                                   'master')

    def test_non_existing_cache_exc_handling(self):
        os.path.exists = mock.Mock(return_value=False)
        os.makedirs = mock.Mock()
        utils.git_clone = mock.Mock(
            side_effect=subprocess.CalledProcessError(1, "cmd"))

        self.assertRaises(exceptions.CheckmateException, self.cache.update)

        os.path.exists.assert_called_once_with(self.cache.cache_path)
        os.makedirs.assert_called_once_with(self.cache.cache_path)
        utils.git_clone.assert_called_once_with(self.cache.cache_path,
                                                self.source_repo,
                                                branch='master')

    def test_cache_hit(self):
        head_file_path = "%s/.git/FETCH_HEAD" % self.cache.cache_path
        os.path.exists = mock.Mock(return_value=True)
        os.path.isfile = mock.Mock(return_value=True)
        time.time = mock.Mock(return_value=100)
        os.path.getmtime = mock.Mock(return_value=50)

        self.cache.update()

        os.path.exists.assert_called_once_with(self.cache.cache_path)
        os.path.isfile.assert_called_once_with(head_file_path)
        self.assertTrue(time.time.called)
        os.path.getmtime.assert_called_once_with(head_file_path)

    def test_cache_miss_for_default_branch(self):
        head_file_path = "%s/.git/FETCH_HEAD" % self.cache.cache_path
        os.path.exists = mock.Mock(return_value=True)
        os.path.isfile = mock.Mock(return_value=True)
        time.time = mock.Mock(return_value=4000)
        os.path.getmtime = mock.Mock(return_value=50)
        utils.git_tags = mock.Mock(return_value=['master'])
        utils.git_fetch = mock.Mock()
        utils.git_checkout = mock.Mock()

        self.cache.update()

        os.path.exists.assert_called_once_with(self.cache.cache_path)
        os.path.isfile.assert_called_once_with(head_file_path)
        self.assertTrue(time.time.called)
        os.path.getmtime.assert_called_once_with(head_file_path)
        utils.git_tags.assert_called_once_with(self.cache.cache_path)
        utils.git_fetch.assert_called_once_with(
            self.cache.cache_path, "refs/tags/master:refs/tags/master")
        utils.git_checkout.assert_called_once_with(self.cache.cache_path,
                                                   'master')

    def test_cache_miss_for_missing_tag(self):
        head_file_path = "%s/.git/FETCH_HEAD" % self.cache.cache_path
        os.path.exists = mock.Mock(return_value=True)
        os.path.isfile = mock.Mock(return_value=True)
        time.time = mock.Mock(return_value=4000)
        os.path.getmtime = mock.Mock(return_value=50)
        utils.git_tags = mock.Mock(return_value=[])
        utils.git_pull = mock.Mock()

        self.cache.update()

        os.path.exists.assert_called_once_with(self.cache.cache_path)
        os.path.isfile.assert_called_once_with(head_file_path)
        self.assertTrue(time.time.called)
        os.path.getmtime.assert_called_once_with(head_file_path)
        utils.git_tags.assert_called_once_with(self.cache.cache_path)
        utils.git_pull.assert_called_once_with(self.cache.cache_path,
                                               'master')
