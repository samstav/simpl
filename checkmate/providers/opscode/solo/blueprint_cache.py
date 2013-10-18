# pylint: disable=R0912,R0913,R0914,R0915,W0613

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
"""Blueprints cache."""
import hashlib
import logging
import os
import subprocess
import time

from checkmate import exceptions
from checkmate import utils

from checkmate.common import config

CONFIG = config.current()
LOG = logging.getLogger(__name__)


class BlueprintCache(object):
    """Blueprints cache."""
    def __init__(self, source_repo):
        prefix = CONFIG.deployments_path
        suffix = hashlib.md5(source_repo).hexdigest()
        self.source_repo = source_repo
        self._cache_path = os.path.join(prefix, "cache", "blueprints", suffix)

    @property
    def cache_path(self):
        """Cache path for blueprint."""
        return self._cache_path

    def update(self):
        """Cache a blueprint repo or update an existing cache, if necessary."""
        cache_expire_time = os.environ.get("CHECKMATE_BLUEPRINT_CACHE_EXPIRE")
        if not cache_expire_time:
            cache_expire_time = 3600
            LOG.info("(cache) CHECKMATE_BLUEPRINT_CACHE_EXPIRE variable not "
                     "set. Defaulting to %s", cache_expire_time)
        cache_expire_time = int(cache_expire_time)
        if "#" in self.source_repo:
            url, branch = self.source_repo.split("#")
        else:
            url = self.source_repo
            branch = "master"
        if os.path.exists(self.cache_path):  # Cache exists
            # The mtime of .git/FETCH_HEAD changes upon every "git
            # fetch".  FETCH_HEAD is only created after the first
            # fetch, so use HEAD if it's not there
            if os.path.isfile(os.path.join(self.cache_path, ".git",
                                           "FETCH_HEAD")):
                head_file = os.path.join(self.cache_path, ".git", "FETCH_HEAD")
            else:
                head_file = os.path.join(self.cache_path, ".git", "HEAD")
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
                        utils.git_fetch(self.cache_path, refspec)
                        utils.git_checkout(self.cache_path, tag)
                    except subprocess.CalledProcessError:
                        LOG.info("Unable to update git tags from the git "
                                 "repository at %s.  Using the cached "
                                 "repository", url)
                else:
                    try:
                        utils.git_pull(self.cache_path, branch)
                    except subprocess.CalledProcessError:
                        LOG.info("Unable to pull from git repository at %s.  "
                                 "Using the cached repository", url)
            else:  # Cache hit
                LOG.debug("(cache) Using cached repo: %s", self.cache_path)
        else:  # Cache does not exist
            LOG.debug("(cache) Cloning repo to %s", self.cache_path)
            os.makedirs(self.cache_path)
            try:
                utils.git_clone(self.cache_path, url, branch=branch)
            except subprocess.CalledProcessError as exc:
                error_message = ("Git repository could not be cloned from "
                                 "'%s'. The error returned was '%s'" % (url,
                                                                        exc))
                raise exceptions.CheckmateException(error_message)
            tags = utils.git_tags(self.cache_path)
            if branch in tags:
                utils.git_checkout(self.cache_path, branch)
