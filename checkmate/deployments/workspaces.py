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

"""Workspace.

A directory where file operations can be performed for a deployment.

Handles:
- directory creation
- TODO: workspace cleanup
- TODO: archiving, zipping, and transporting a deployment workspace
- retrieving contents from blueprint repository
- caching repositories (GitHub decoupling)


Examples:
- chef: kitchen for knife solo
- script: repo to rsync up to hosts
"""

import errno
import hashlib
import logging
import os
import subprocess
import time

from celery.task import task

from checkmate.common import config
from checkmate.common import statsd
from checkmate import exceptions
from checkmate.providers.opscode import blueprint_cache
from checkmate import utils

CONFIG = config.current()
LOG = logging.getLogger(__name__)


def workspace_root_path():
    """Get the root path for all workspaces.

    Ensure it exists.
    :returns: string path
    """
    root = CONFIG.deployments_path
    if not os.path.exists(root):
        msg = "Invalid workspace root path: %s" % root
        raise exceptions.CheckmateException(msg)
    return root


def get_workspace(deployment_id):
    """Create/return deployment workspace.

    :param deployment_id: the ID of the deployment the workspace is for
    """
    root = workspace_root_path()
    fullpath = os.path.join(root, deployment_id)

    if os.path.exists(fullpath):
        return fullpath

    if not os.path.exists(root):
        raise exceptions.CheckmateException("Root workspace directory does "
                                            "not exist: %s", root)
    try:
        os.mkdir(fullpath, 0o770)
        LOG.info("Created workspace: %s", fullpath)
    except OSError as ose:
        if ose.errno == errno.EEXIST:
            LOG.warn("Workspace exists but os.path.exists returned False: "
                     "%s", fullpath, exc_info=True)
        else:
            msg = "Could not create workspace %s" % fullpath
            raise exceptions.CheckmateException(msg)
    return fullpath


def get_blueprints_cache_path(source_repo):
    """Return the path of the blueprint cache directory."""
    utils.match_celery_logging(LOG)
    LOG.debug("source_repo: %s", source_repo)
    return blueprint_cache.get_repo_cache_path(source_repo)


def cache_blueprint(source_repo):
    """Cache a blueprint repo or update an existing cache, if necessary."""
    LOG.debug("(cache) Running %s.cache_blueprint()...", __name__)
    blueprint_repo_cache = blueprint_cache.BlueprintCache(source_repo)
    blueprint_repo_cache.update()


def blueprint_exists(source, dest):
    """Check that all files in the source blueprint exist in the destination.

    """
    for source_file in os.listdir(source):
        dest_file = os.path.join(dest, source_file)
        if not os.path.exists(dest_file):
            return False
    return True


def download_blueprint(destination, source_repo):
    """Update the blueprint cache and copy the blueprint to the destination.

    :param destination: Path to the destination
    :param source_repo: URL of the git-hosted blueprint
    """
    utils.match_celery_logging(LOG)
    cache_blueprint(source_repo)
    repo_cache = get_blueprints_cache_path(source_repo)
    if not os.path.exists(repo_cache):
        message = "No blueprint repository found in %s" % repo_cache
        raise exceptions.CheckmateException(message)
    LOG.debug("repo_cache: %s", repo_cache)
    LOG.debug("destination: %s", destination)
    if not blueprint_exists(repo_cache, destination):
        utils.copy_contents(repo_cache,
                            destination,
                            create_path=True,
                            with_overwrite=True)


@task
@statsd.collect
def create_workspace(context, name, source_repo=None):
    """Create a filesystem workspace.

    The workspace is a directory structure that is self-contained and
    seperate from other workspaces. It is used by providers to perform
    operations that need a file system.

    :param name: the name of the workspace. This will be the directory name.
    :param source_repo: provides a git repository to clone into the workspace
    """
    utils.match_celery_logging(LOG)

    # TODO(zns): add context
    if context['simulation'] is True:
        return {
            'workspace': '/var/tmp/%s/' % name
        }

    path = get_workspace(name)
    results = {'workspace': path}

    if source_repo:
        download_blueprint(path, source_repo)
    LOG.debug("create_workspace returning: %s", results)
    return results
