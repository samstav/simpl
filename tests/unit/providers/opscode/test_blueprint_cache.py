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
import shutil
import tempfile

import mock
import simpl
import unittest

from checkmate import exceptions as cmexc
from checkmate.providers.opscode import blueprint_cache as bpc_mod


class TestBlueprintCache(unittest.TestCase):

    """Patches the repo cache into a temporary directory."""

    repo_cache_base = os.path.join(
        tempfile.gettempdir(), 'checkmate-test-blueprint-cache')

    def setUp(self):
        self.repo_cache_base_patcher = mock.patch.object(
            bpc_mod, 'repo_cache_base')
        repo_cache_base_mock = self.repo_cache_base_patcher.start()
        repo_cache_base_mock.return_value = self.repo_cache_base

    def tearDown(self):
        self.repo_cache_base_patcher.stop()
        try:
            shutil.rmtree(self.repo_cache_base)
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise


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


TEST_GIT_USERNAME = 'checkmate_blueprint_cache_test_user'


def _configure_test_user(gitrepo):

    email = '%s@%s.test' % (TEST_GIT_USERNAME, TEST_GIT_USERNAME)
    gitrepo.run_command('git config --local user.name %s' % TEST_GIT_USERNAME)
    gitrepo.run_command('git config --local user.email %s' % email)


class TestBPCRefs(TestBlueprintCache):

    def setUp(self):
        super(TestBPCRefs, self).setUp()
        self.remote = simpl.git.GitRepo.init(temp=True)
        _configure_test_user(self.remote)
        self.remote.commit(message='Initial commit')
        self.initial_revision = self.remote.head

    def test_defaults_to_master_ref(self):
        source_repo = self.remote.repo_dir
        bpc = bpc_mod.BlueprintCache(source_repo)
        self.assertTrue(bpc.source_ref == 'master')

    def test_ref_can_be_tag(self):
        self.remote.commit(message='tag this commit')
        tag = 'whatatag'
        tagged_revision = self.remote.head
        self.remote.tag(tag)
        self.remote.run_command(
            ['git', 'reset', '--hard', self.initial_revision])
        source_repo = '%s#%s' % (self.remote.repo_dir, tag)
        bpc = bpc_mod.BlueprintCache(source_repo)
        bpc.update()
        # this assertion is to prove we aren't "just getting lucky"
        self.assertNotEqual(bpc.repo.head, self.remote.head)
        self.assertEqual(bpc.repo.head, tagged_revision)

    def test_ref_can_be_branch(self):
        self.remote.commit(message='branch from this commit')
        branch = 'whatabranch'
        branched_revision = self.remote.head
        self.remote.branch(branch)
        self.remote.run_command(
            ['git', 'reset', '--hard', self.initial_revision])
        source_repo = '%s#%s' % (self.remote.repo_dir, branch)
        bpc = bpc_mod.BlueprintCache(source_repo)
        bpc.update()
        # this assertion is to prove we aren't "just getting lucky"
        self.assertNotEqual(bpc.repo.head, self.remote.head)
        self.assertEqual(bpc.repo.head, branched_revision)

    def test_ref_can_be_commit_hash(self):
        self.remote.commit(message='reference this commit')
        committed_revision = self.remote.head
        self.remote.run_command(
            ['git', 'reset', '--hard', self.initial_revision])
        source_repo = '%s#%s' % (self.remote.repo_dir, committed_revision)
        bpc = bpc_mod.BlueprintCache(source_repo)
        bpc.update()
        # this assertion is to prove we aren't "just getting lucky"
        self.assertNotEqual(bpc.repo.head, self.remote.head)
        self.assertEqual(bpc.repo.head, committed_revision)

    def test_ref_can_be_short_commit_hash(self):
        self.remote.commit(message='reference this commit')
        short_committed_revision = self.remote.head[:8]
        self.remote.run_command(
            ['git', 'reset', '--hard', self.initial_revision])
        source_repo = '%s#%s' % (
            self.remote.repo_dir, short_committed_revision)
        bpc = bpc_mod.BlueprintCache(source_repo)
        bpc.update()
        # this assertion is to prove we aren't "just getting lucky"
        self.assertNotEqual(bpc.repo.head, self.remote.head)
        self.assertTrue(bpc.repo.head.startswith(short_committed_revision))

    def test_tag_ref_gets_updated_on_remote(self):
        tag = 'whatatag'
        self.remote.tag(tag)
        source_repo = '%s#%s' % (self.remote.repo_dir, tag)
        bpc = bpc_mod.BlueprintCache(source_repo)
        bpc.update()
        self.remote.commit(message='re-tag this commit')
        desired_revision = self.remote.head
        self.remote.tag(tag)
        # assert that we *need* to update
        self.assertNotEqual(bpc.repo.head, desired_revision)
        bpc.update()
        # assert that calling update() fixed our clone
        self.assertEqual(bpc.repo.head, desired_revision)

    def test_branch_ref_gets_updated_on_remote(self):
        branch = 'whatabranch'
        self.remote.branch(branch)
        source_repo = '%s#%s' % (self.remote.repo_dir, branch)
        bpc = bpc_mod.BlueprintCache(source_repo)
        bpc.update()
        self.remote.commit(message='re-branch this commit')
        desired_revision = self.remote.head
        # this will overwrite the 'whatabranch' branch
        self.remote.branch(branch)
        # assert that we *need* to update
        self.assertNotEqual(bpc.repo.head, desired_revision)
        bpc.update()
        # assert that calling update() fixed our clone
        self.assertEqual(bpc.repo.head, desired_revision)

    def test_bad_person_uses_same_name_gets_tag(self):
        """Prefer tags to branches."""
        tag_and_branch = 'spam'
        self.remote.commit(message='tag me')
        self.remote.tag(tag_and_branch)
        tagged_revision = self.remote.head
        self.remote.commit(message='branch me')
        self.remote.branch(tag_and_branch)
        source_repo = '%s#%s' % (self.remote.repo_dir, tag_and_branch)
        bpc = bpc_mod.BlueprintCache(source_repo)
        bpc.update()
        self.assertEqual(bpc.repo.head, tagged_revision)

    def test_no_such_ref(self):
        self.remote.tag('realness')
        source_repo = '%s#%s' % (self.remote.repo_dir, 'wat')
        bpc = bpc_mod.BlueprintCache(source_repo)
        with self.assertRaises(cmexc.CheckmateInvalidRepoUrl) as cntxt:
            bpc.update()
        friendly = ("Invalid ref 'wat' for repo. The ref must be a tag, "
                    "branch, or commit hash known to %s."
                    % self.remote.repo_dir)
        self.assertEqual(friendly, cntxt.exception.friendly_message)

    def test_no_such_repo(self):
        source_repo = '%s' % 'i/dont/exist'
        bpc = bpc_mod.BlueprintCache(source_repo)
        with self.assertRaises(cmexc.CheckmateInvalidRepoUrl) as cntxt:
            bpc.update()
        friendly = "Git repository could not be cloned from 'i/dont/exist'."
        self.assertEqual(friendly, cntxt.exception.friendly_message)

    def test_has_been_deleted_or_made_private_since_clone(self):
        source_repo = self.remote.repo_dir
        bpc = bpc_mod.BlueprintCache(source_repo)
        bpc.update()
        # this should be equivalent to a repo going private
        shutil.rmtree(self.remote.repo_dir)
        with self.assertRaises(cmexc.CheckmateInvalidRepoUrl) as cntxt:
            bpc.update()
        friendly = ('Could not access a repo previously cloned from %s'
                    % self.remote.repo_dir)
        self.assertEqual(friendly, cntxt.exception.friendly_message)


if __name__ == '__main__':

    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
