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

import unittest

from checkmate import exceptions as cmexc
from checkmate.providers.opscode import blueprint_cache as bpc_mod


class TestBlueprintCache(unittest.TestCase):

    """Patches the repo cache into a temporary directory."""

    repo_cache_base = os.path.join(
        tempfile.gettempdir(), 'checkmate-test-blueprint-cache')

    @classmethod
    def setUpClass(cls):
        cls.patch_repo_cache_base()

    @classmethod
    def tearDownClass(cls):
        try:
            shutil.rmtree(cls.repo_cache_base)
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise

    @classmethod
    def patch_repo_cache_base(self):
        # patch repo_cache_base to avoid
        # OSError: [Errno 13] Permission denied: '/var/local'
        bpc_mod.repo_cache_base = lambda: self.repo_cache_base


class TestUpdateBPC(TestBlueprintCache):

    def setUp(self):
        super(TestUpdateBPC, self).setUp()
        self.source_repo = "https://foo.com/checkmate/wordpress.git"
        self.cache = bpc_mod.BlueprintCache(self.source_repo)

    def test_cache_creation_succeeds(self):
        temp_base_dir = tempfile.gettempdir()
        target_dir_name = next(tempfile._get_candidate_names())
        target_dir_path = os.path.join(temp_base_dir, target_dir_name)
        with bpc_mod.CommitableTemporaryDirectory(dir=temp_base_dir) as tdc:
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
        with bpc_mod.CommitableTemporaryDirectory(dir=temp_base_dir) as tdc:
            with open(os.path.join(tdc.name, 'foo.txt'), 'w') as handle:
                handle.write("Hi!")
            with bpc_mod.CommitableTemporaryDirectory(
                    dir=temp_base_dir) as tdc2:
                with open(os.path.join(tdc2.name, 'foo.txt'), 'w') as handle2:
                    handle2.write("Not Hi!!!!")
                tdc2.commit(target_dir_path)
            with self.assertRaises(OSError):
                tdc.commit(target_dir_path)

    def test_cache_concurrent_succeeds(self):
        temp_base_dir = tempfile.gettempdir()
        target_dir_name = next(tempfile._get_candidate_names())
        target_dir_path = os.path.join(temp_base_dir, target_dir_name)
        with bpc_mod.CommitableTemporaryDirectory(dir=temp_base_dir) as tdc:
            with open(os.path.join(tdc.name, 'foo.txt'), 'w') as handle:
                handle.write("Hi!")
            with bpc_mod.CommitableTemporaryDirectory(
                    dir=temp_base_dir) as tdc2:
                with open(os.path.join(tdc2.name, 'foo.txt'), 'w') as handle2:
                    handle2.write("Hi!")
                tdc2.commit(target_dir_path)
            tdc.commit(target_dir_path)  # Should not fail


if __name__ == '__main__':
    import sys
    from checkmate import test as cmtest
    cmtest.run_with_params(sys.argv[:])
