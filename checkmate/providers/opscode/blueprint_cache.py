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

"""Blueprints cache."""

import errno
import hashlib
import logging
import os
import shutil
import sys

from simpl import git as simpl_git
from simpl import exceptions as simpl_exc

from checkmate.common import backports
from checkmate.common import config
from checkmate.contrib import urlparse
from checkmate import exceptions as cmexc
from checkmate import utils

CONFIG = config.current()
LOG = logging.getLogger(__name__)


class CommitableTemporaryDirectory(backports.TemporaryDirectory):

    """Create temp directory, persist it only if creation code succeeds.

    We use this context manager to avoid the race condition where a git repo is
    being cached by a number of processes or threads. Only the one that gets to
    write the directory name (using os.rename) gets to write to the directory.
    Others can only read and if they detect the race condition but find the
    directory already matches what they expect, then they pass quietly.
    Otherwise, they fail.
    Note that this returns the instance, not the path (in order to provide a
    commit() call.
    """

    def __enter__(self):
        """Context manager entrace."""
        return self

    def commit(self, path):
        """Commit temp dir to final destination."""
        try:
            os.rename(self.name, path)  # atomic by posix mandate
        except OSError as exc:
            if exc.errno == errno.ENOTEMPTY:
                # Assuming concurrency error, check for equality
                if utils.are_dir_trees_equal(self.name, path):
                    self._closed = True
                else:
                    raise

        self._closed = True


def hide_git_url_password(url):
    """Detect a password part of a URL and replaces it with *****.

    Also handles GitHub URL where username has OAuth token.
    """
    try:
        parsed = urlparse.urlsplit(url)
        if parsed.password:
            if parsed.password.lower() == 'x-auth-basic' and parsed.username:
                return url.replace('//%s:' % parsed.username, '//*****:')
            else:
                return url.replace(':%s@' % parsed.password, ':*****@')
    except StandardError:
        pass
    return url


def repo_cache_base():
    """Return the current config's base path to repo caches."""
    return os.path.join(CONFIG.cache_dir, "blueprint-repos")


def delete_cache(path):
    """Remove cache at 'path'.

    Raise CheckmateNothingToDo if the directory does not exist.
    """
    try:
        return shutil.rmtree(path)
    except OSError as err:
        if err.errno == errno.ENOENT:
            # No such file or directory
            raise (cmexc.CheckmateNothingToDo,
                   ("No existing repo cache to remove.",),
                   sys.exc_info()[2])
        else:
            raise


def delete_all_caches():
    """Delete *all* of the local repo caches."""
    return delete_cache(repo_cache_base())


def delete_repo_cache(source_repo, github_token=None):
    """Delete cache for the repo/token combo."""
    ident = get_ident_hash(source_repo, github_token=github_token)
    path = os.path.join(repo_cache_base(), ident)
    return delete_cache(path)


def get_ident_hash(source_repo, github_token=None):
    """Return an identifier for a repo/token combo."""
    if github_token:
        ident = "%s:%s" % (github_token, source_repo)
    else:
        ident = source_repo
    return hashlib.md5(ident).hexdigest()


def get_repo_cache_path(source_repo, github_token=None):
    """Return the calculated path to the cache for 'source_repo'."""
    suffix = get_ident_hash(source_repo, github_token=github_token)
    return os.path.join(repo_cache_base(), suffix)


def ensure_writable_cache_dir():
    """Check cache dir exists and is writeable. Create it if not."""
    base_dir = repo_cache_base()
    if not os.path.exists(base_dir):
        try:
            os.makedirs(base_dir, 0o770)
            LOG.info("Created cache directory '%s'", base_dir)
        except OSError as err:
            if err.errno != errno.EEXIST:
                raise
    if not os.access(base_dir, os.W_OK):
        raise OSError(errno.EACCES, "No access to write to cache directory.",
                      base_dir)


class BlueprintCache(object):

    """Blueprints cache."""

    def __init__(self, source_repo, github_token=None):
        """Initialize the blueprint repo cache with git location."""
        ensure_writable_cache_dir()
        self.source_repo = source_repo
        self.github_token = github_token

        # source_repo can be:
        #    github.com/user/repo#<commit_hash>
        #    github.com/user/repo#<short_commit_hash>
        #    github.com/user/repo#branch_name
        #    github.com/user/repo#tag_name

        if "#" in self.source_repo:
            self.source_url, self.source_ref = self.source_repo.split("#", 1)
        else:
            self.source_url = self.source_repo
            self.source_ref = "master"
        self._temp_branch = 'temp-%s-branch' % self.source_ref
        self.remote = self.source_url
        if self.github_token:
            self.remote = utils.set_url_creds(
                self.source_url, username=self.github_token,
                password='x-oauth-basic')

        self.cache_path = get_repo_cache_path(
            self.source_repo, github_token=self.github_token)
        self.repo = None

    def delete(self):
        """Delete this cache from disk."""
        return delete_cache(self.cache_path)

    def update(self):
        """Cache a blueprint repo or update an existing cache, if necessary."""
        try:
            self.repo = simpl_git.GitRepo(self.cache_path)
            return self._update_existing()
        except simpl_exc.SimplGitNotRepo:
            LOG.warning("Cached blueprint repo found at %s but it was "
                        "not a valid git repository. Re-creating.",
                        self.cache_path)
            # exists but is not a git repo. start from scratch
            delete_cache(self.cache_path)
            return self._create_new_cache()
        except OSError as err:
            if err.errno != errno.ENOENT:
                raise
            # does not exist at all
            LOG.debug("Blueprint repo %s does not exist yet. "
                      "Doing inital clone/create.",
                      self.cache_path)
            return self._create_new_cache()

    def _update_existing(self):
        """Fetch and checkout the correct revision."""
        if not self.repo:
            raise ValueError(
                "No existing self.repo (simpl GitRepo) "
                "attribute set on %s instance." % self)

        LOG.info("(cache) Updating repo: %s", self.repo)

        def checkout_ref(ref):
            self.repo.checkout(ref)
            if self.repo.current_branch == 'HEAD':
                # if we are in detached head state...
                self.repo.branch(self._temp_branch, checkout=True)

        try:
            # first see if we can checkout the ref/revision
            checkout_ref(self.source_ref)
        except simpl_exc.SimplGitCommandError as err:
            # nothing on-hand matches the ref. go fetch!
            LOG.info("Could not checkout ref '%s', will fetch objects from "
                     "%s and try again. Error output was: %s",
                     self.source_ref, self.source_url, err)
            self._fetch()
            # TODO(sam): How do we want to react if the following line fails??
            try:
                checkout_ref(self.source_ref)
            except simpl_exc.SimplGitCommandError as err:
                error = ("Invalid ref '%s' for repo. The ref must be "
                         "a tag, branch, or commit hash known to %s."
                         % (self.source_ref, self.source_url))
                LOG.error('%s | %r', error, err, exc_info=1)
                # NOTE: you could even get valid suggestions by calling
                #     self.repo.list_refs().keys()
                raise cmexc.CheckmateInvalidRepoUrl(
                    message=repr(err), friendly_message=error)
        else:
            # self.source_ref might be a commit hash !
            if self.repo.head.startswith(self.source_ref):
                LOG.info("Blueprint repo source ref '%s' is a commit hash.",
                         self.source_ref)
                return
            else:
                # verify that the correct revision is now checked out
                # querying the remote is a better alternative to
                # having a "TTL" on the blueprint repo

                # NOTE: If we are to have any "continue anyway" logic,
                # it will be right here. For example, a deployment is
                # created from a repo_url while it exists or is public,
                # then the owner deletes it from github or makes it private.
                # We still have a copy of the repo here, so should we use it?
                # In that circumstance, the following will throw an exception
                # because ls-remote will return
                # "Could not read from the remote repository"
                # TODO(sam): determine what, if any, fallback behavior we
                # want built in here**
                try:
                    revision = self.repo.remote_resolve_reference(
                        self.source_ref, remote=self.remote)
                except simpl_exc.SimplGitCommandError as err:
                    # TODO(sam): **Should we just continue w/ what we have?
                    #              (probably not)
                    error = ("Could not access a repo previously "
                             "cloned from %s"
                             % hide_git_url_password(self.remote))
                    LOG.error('%s | %r', error, err, exc_info=1)
                    raise cmexc.CheckmateInvalidRepoUrl(
                        message=repr(err), friendly_message=error)

                LOG.info("Found revision for ref '%s' --> %s",
                         self.source_ref, revision)
                if revision != self.repo.head:
                    LOG.info("The local revision for ref '%s' does not "
                             "match the remote revision for the same ref.",
                             self.source_ref)
                    self._fetch()
                    checkout_ref(revision)
                else:
                    LOG.info("Current revision for ref '%s' matches remote.",
                             self.source_ref)
        LOG.info("Successfully checked out ref '%s' for repo %s",
                 self.source_ref, self.repo)

    def _create_new_cache(self):
        """Create cache directory, init & clone the repository."""
        LOG.info("(cache) Cloning repo to %s", self.cache_path)

        with CommitableTemporaryDirectory(dir=repo_cache_base()) as tempdir:
            try:
                self.repo = simpl_git.GitRepo.clone(
                    self.remote, repo_dir=tempdir.name)
            except simpl_exc.SimplGitCommandError as err:
                error = ("Git repository could not be cloned from '%s'."
                         % hide_git_url_password(self.remote))
                LOG.error('%s | %r', error, err, exc_info=1)
                raise cmexc.CheckmateInvalidRepoUrl(
                    message=repr(err), friendly_message=error)
            # this will ensure the ref gets checked out
            self._update_existing()
            tempdir.commit(self.cache_path)
            # self.repo.repo_dir gets deleted by __exit__
            # so now we reset the self.repo attribute to point to the
            # correct directory
            self.repo.repo_dir = self.cache_path

        LOG.info("(cache) Repo %s cloned to cache.",
                 hide_git_url_password(self.remote))

    def _fetch(self):
        """Fetch updates from the remote into the cache."""
        if not self.repo:
            raise ValueError(
                "No existing self.repo (simpl GitRepo) "
                "attribute set on %s instance." % self)
        LOG.info("Fetching the latest revisions from remote at %s.",
                 self.source_url)
        # need to do both of these fetches on git < 1.9
        self.repo.fetch(remote=self.remote, tags=False)
        self.repo.fetch(remote=self.remote, tags=True)
