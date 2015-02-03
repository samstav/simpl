# pylint: disable=R0912,R0913,R0914,R0915,W0613

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

import hashlib
import logging
import os
import shutil
import subprocess
import time

from checkmate import exceptions
from checkmate import utils

from checkmate.common import config

CONFIG = config.current()
LOG = logging.getLogger(__name__)


def repo_cache_base():
    """Return the current config's base path to repo caches."""
    return os.path.join(CONFIG.deployments_path, "cache", "blueprints")


def delete_cache(path):
    """Remove cache at 'path'.

    Raise CheckmateNothingToDo if the directory does not exist.
    """
    try:
        return shutil.rmtree(path)
    except OSError as err:
        if err.errno == 2:
            # nothing to delete
            raise exceptions.CheckmateNothingToDo(
                "No existing repo cache to remove.")
        else:
            raise


def delete_all_caches():
    """Are you sure?"""
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


class BlueprintCache(object):

    """Blueprints cache."""

    def __init__(self, source_repo, github_token=None):
        suffix = get_ident_hash(source_repo, github_token=github_token)
        self.source_repo = source_repo
        self.github_token = github_token
        self._cache_path = os.path.join(repo_cache_base(), suffix)

    @property
    def cache_path(self):
        """Cache path for blueprint."""
        return self._cache_path

    def delete(self):
        """Delete this cache from disk."""
        return delete_cache(self._cache_path)

    def _create_new_cache(self, url, branch, token_remote=None):
        """Create cache directory and clone repository."""
        LOG.debug("(cache) Cloning repo to %s", self.cache_path)
        dirsmade = None
        try:
            os.makedirs(self.cache_path)
            dirsmade = self.cache_path
        except OSError:
            # makedirs() will not overwrite: cache_path exists
            # previous clone likely failed
            pass
        try:
            if token_remote:
                utils.git_init(self.cache_path)
                utils.git_pull(self.cache_path, branch,
                               remote=token_remote)
            else:
                utils.git_clone(self.cache_path, url, branch=branch)
        except subprocess.CalledProcessError as exc:
            if dirsmade:
                # only remove if this same fn call was the creator
                os.rmdir(dirsmade)
            error_message = ("Git repository could not be cloned from "
                             "'%s'. The error returned was '%s'"
                             % (url, exc))
            raise exceptions.CheckmateException(error_message)
        try:
            tags = utils.git_tags(self.cache_path)
            if branch in tags:
                utils.git_checkout(self.cache_path, branch)
            else:
                LOG.warning("No such branch %s for git repository "
                            "%s located at %s. Using 'master'",
                            branch, url, self.cache_path)
        except subprocess.CalledProcessError as exc:
            if dirsmade:
                os.rmdir(dirsmade)
            error_message = ("Failed to checkout branch %s for git "
                             "repository %s located at %s."
                             % (branch, url, self.cache_path))
            raise exceptions.CheckmateException(error_message)

    def update(self):
        """Cache a blueprint repo or update an existing cache, if necessary."""
        cache_expire_time = os.environ.get("CHECKMATE_BLUEPRINT_CACHE_EXPIRE")
        if cache_expire_time is None:
            cache_expire_time = 3600
            LOG.info("(cache) CHECKMATE_BLUEPRINT_CACHE_EXPIRE variable not "
                     "set. Defaulting to %s", cache_expire_time)
        cache_expire_time = int(cache_expire_time)
        if "#" in self.source_repo:
            url, branch = self.source_repo.split("#", 1)
        else:
            url = self.source_repo
            branch = "master"
        token_remote = None
        if self.github_token:
            token_remote = utils.set_url_creds(url, username=self.github_token,
                                               password='x-oauth-basic')

        if (os.path.exists(self.cache_path)
                and os.path.exists(os.path.join(self.cache_path, '.git'))):
            # The mtime of .git/FETCH_HEAD changes upon every "git
            # fetch".  FETCH_HEAD is only created after the first
            # fetch, so use HEAD if it's not there
            if os.path.isfile(os.path.join(self.cache_path, ".git",
                                           "FETCH_HEAD")):
                head_file = os.path.join(self.cache_path, ".git", "FETCH_HEAD")

            elif os.path.isfile(os.path.join(self.cache_path, ".git", "HEAD")):
                head_file = os.path.join(self.cache_path, ".git", "HEAD")
            else:
                return self._create_new_cache(
                    url, branch, token_remote=token_remote)
            last_update = time.time() - os.path.getmtime(head_file)
            LOG.debug("(cache) cache_expire_time: %s", cache_expire_time)
            LOG.debug("(cache) last_update: %s", last_update)

            if last_update > cache_expire_time:  # Cache miss
                LOG.debug("(cache) Updating repo: %s", self.cache_path)
                tags = utils.git_tags(self.cache_path)
                if branch in tags:
                    tag = branch
                    refspec = "refs/tags/" + tag + ":refs/tags/" + tag
                    try:
                        if token_remote:
                            utils.git_fetch(self.cache_path, refspec,
                                            remote=token_remote)
                        else:
                            utils.git_fetch(self.cache_path, refspec)
                        utils.git_checkout(self.cache_path, tag)
                    except subprocess.CalledProcessError:
                        LOG.info("Unable to update git tags from the git "
                                 "repository at %s.  Using the cached "
                                 "repository", url)
                else:
                    try:
                        if token_remote:
                            utils.git_pull(self.cache_path, branch,
                                           remote=token_remote)
                        else:
                            utils.git_pull(self.cache_path, branch)
                    except subprocess.CalledProcessError:
                        LOG.info("Unable to pull from git repository at %s.  "
                                 "Using the cached repository", url)
            else:  # Cache hit
                LOG.debug("(cache) Using cached repo: %s", self.cache_path)
        else:  # Cache does not exist
            return self._create_new_cache(
                url, branch, token_remote=token_remote)
