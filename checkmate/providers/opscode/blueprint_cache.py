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
import tempfile
import time
import urlparse

from checkmate.common import config
from checkmate.common import git as common_git
from checkmate import exceptions as cmexc
from checkmate import utils

CONFIG = config.current()
LOG = logging.getLogger(__name__)


class TransactionalDirCreation(object):  # pylint: disable=R0903

    """Create directory if all post-creation jobs succeed."""

    def __init__(self, path):
        self.path = path
        self.working_dir = None

    def __enter__(self):
        if os.path.exists(self.path):
            raise OSError(errno.EEXIST, os.strerror(errno.EEXIST), self.path)
        self.working_dir = tempfile.mkdtemp()
        return self.working_dir

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if not exc_type:
                # Move temp dir to final location
                try:
                    shutil.move(self.working_dir, self.path)
                except OSError as exc:
                    if exc_type.errno != errno.EEXIST:
                        raise
                    # Otherwise exist is fine! We should be OK
        finally:
            try:
                shutil.rmtree(self.working_dir)
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    LOG.error("Unable to clean up '%s'", self.working_dir,
                              exc_info=exc)


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


def good_cache_exists(cache_path):
    """Determine if a good cache exists.

    If a good cache exists, return the path to its HEAD or FETCH_HEAD.
    """
    if not os.path.exists(cache_path):
        return False
    dotgit = os.path.join(cache_path, '.git')
    if not os.path.exists(dotgit):
        return False
    # The mtime of .git/FETCH_HEAD changes upon every "git
    # fetch".  FETCH_HEAD is only created after the first
    # fetch, so use HEAD if it's not there
    fetch_head = os.path.join(dotgit, 'FETCH_HEAD')
    if os.path.isfile(fetch_head):
        return fetch_head
    head = os.path.join(dotgit, 'HEAD')
    if os.path.isfile(head):
        return head


class BlueprintCache(object):

    """Blueprints cache."""

    def __init__(self, source_repo, github_token=None):
        """Initialize the blueprint repo cache with git location."""
        self.source_repo = source_repo
        self.github_token = github_token
        self.cache_path = get_repo_cache_path(
            source_repo, github_token=github_token)
        self._repo = None

    @property
    def repo(self):
        """Pointer to this cache's GitRepo instance."""
        if not self._repo:
            self._repo = common_git.GitRepo(self.cache_path)
        return self._repo

    def delete(self):
        """Delete this cache from disk."""
        return delete_cache(self.cache_path)

    def update(self):
        """Cache a blueprint repo or update an existing cache, if necessary."""
        if "#" in self.source_repo:
            url, ref = self.source_repo.split("#", 1)
        else:
            url = self.source_repo
            ref = "master"
        remote = url
        if self.github_token:
            remote = utils.set_url_creds(url, username=self.github_token,
                                         password='x-oauth-basic')
        head_file = good_cache_exists(self.cache_path)
        if head_file:
            return self._update_existing(
                head_file, url, ref)
        else:
            # if a good cache does not exist, blow away the broken cache
            try:
                shutil.rmtree(self.cache_path)
            except OSError as err:
                if err.errno != errno.ENOENT:
                    raise
            return self._create_new_cache(remote, ref)

    def _update_existing(self, head_file, remote, ref):
        """Cache exists, fetch latest (if stale) and perform checkout."""
        last_update = time.time() - os.path.getmtime(head_file)
        cache_expire_time = CONFIG.blueprint_cache_expiration
        LOG.debug("(cache) cache_expire_time: %s", cache_expire_time)
        LOG.debug("(cache) last_update: %s", last_update)

        if last_update > cache_expire_time:  # Cache miss
            LOG.info("(cache) Updating repo: %s", self.cache_path)
            tags = self.repo.list_tags()
            if ref in tags:
                refspec = "refs/tags/" + ref + ":refs/tags/" + ref
                try:
                    self.repo.fetch(remote=remote, refspec=refspec)
                    self.repo.checkout('FETCH_HEAD')
                except cmexc.CheckmateCalledProcessError as exc:
                    LOG.error("Unable to fetch tag '%s' from the git "
                              "repository at %s. Using the cached repo."
                              "The output during error was '%s'",
                              ref, hide_git_url_password(remote), exc.output)
            else:
                try:
                    self.repo.fetch(remote=remote, refspec=ref)
                    self.repo.checkout('FETCH_HEAD')
                except cmexc.CheckmateCalledProcessError as exc:
                    LOG.error("Unable to fetch ref '%s' from the git "
                              "repository at %s. Using the cached "
                              "repository. The output during error was %s",
                              ref, hide_git_url_password(remote), exc.output)
        else:  # Cache hit
            LOG.info("(cache) Using cached repo: %s", self.cache_path)

    def _create_new_cache(self, remote, ref):
        """Create cache directory, init & clone the repository."""
        LOG.info("(cache) Cloning repo to %s", self.cache_path)

        # Make sure base exists
        base_dir = repo_cache_base()
        if not os.path.exists(base_dir):
            try:
                os.makedirs(base_dir, 0o770)
            except OSError as err:
                if err.errno != errno.EEXIST:
                    raise

        # Make sure path is clear for creation
        if os.path.exists(self.cache_path):
            LOG.warning("Cache directory already exists: %s", self.cache_path)
            if os.listdir(self.cache_path):
                raise cmexc.CheckmateException(
                    "Target dir %s for clone is non-empty" % self.cache_path,
                    options=cmexc.CAN_RETRY)

        with TransactionalDirCreation(self.cache_path) as temp_path:
            repo = common_git.GitRepo(temp_path)
            try:
                repo.clone(remote, branch_or_tag=ref)
            except cmexc.CheckmateCalledProcessError as exc:
                LOG.error("Git repository could not be cloned from '%s'. The "
                          "output during error was '%s'",
                          hide_git_url_password(remote), exc.output,
                          exc_info=exc)
                raise

            try:
                tags = repo.list_tags()
                if ref in tags:
                    repo.checkout(ref)
                # the ref *should* already be checked out
            except cmexc.CheckmateCalledProcessError as exc:
                LOG.error("Failed to checkout '%s' for git repository %s "
                          "located at %s. The output during error was '%s'.",
                          ref, hide_git_url_password(remote),
                          temp_path, exc.output)
                raise
        LOG.info("(cache) Repo %s cloned to cache.",
                 hide_git_url_password(remote))
