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
"""Rackspace solo provider manager."""
import logging
import os
import shutil

from checkmate import exceptions, utils
from checkmate.common import config
from checkmate.providers.opscode.solo.chef_environment import ChefEnvironment

CONFIG = config.current()
LOG = logging.getLogger(__name__)


class Manager(object):
    """Contains loadbalancer provider model and logic for interaction."""

    @staticmethod
    def delete_cookbooks(name, service_name, path=None):
        """Remove cookbooks directory and contents from the file system."""
        environment = ChefEnvironment(name, root_path=path,
                                      kitchen_name=service_name)
        environment.delete_cookbooks()

    @staticmethod
    def delete_environment(name, path=None):
        """Remove the chef environment from the file system."""
        environment = ChefEnvironment(name, root_path=path)
        environment.delete()

    @staticmethod
    def create_environment(name, service_name, path=None, private_key=None,
                           public_key_ssh=None, secret_key=None,
                           source_repo=None, simulation=False):
        """Create a knife-solo environment

        The environment is a directory structure that is self-contained and
        separate from other environments. It is used by this provider to run
        knife solo commands.

        :param name: the name of the environment. This will be the directory
         name.
        :param path: an override to the root path where to create this
        environment
        :param private_key: PEM-formatted private key
        :param public_key_ssh: SSH-formatted public key
        :param secret_key: used for data bag encryption
        :param source_repo: provides cookbook repository in valid git syntax
        """
        if simulation:
            return {
                'environment': '/var/tmp/%s/' % name,
                'kitchen': '/var/tmp/%s/kitchen' % name,
                'private_key_path': '/var/tmp/%s/private.pem' % name,
                'public_key_path': '/var/tmp/%s/checkmate.pub' % name,
            }

        environment = ChefEnvironment(name, root_path=path,
                                      kitchen_name=service_name)
        # Create environment
        environment.create_env_dir()
        results = {"environment": environment.path}

        key_data = environment.create_environment_keys(
            private_key=private_key, public_key_ssh=public_key_ssh)

        # Kitchen is created in a /kitchen subfolder since it gets completely
        # rsynced to hosts. We don't want the whole environment rsynced
        kitchen_data = environment.create_kitchen(secret_key=secret_key,
                                                  source_repo=source_repo)
        # Copy environment public key to kitchen certs folder
        kitchen_key_path = os.path.join(environment.kitchen_path,
                                        'certificates',
                                        'checkmate-environment.pub')
        shutil.copy(environment.public_key_path, kitchen_key_path)
        LOG.debug("Wrote environment public key to kitchen: %s",
                  kitchen_key_path)

        if source_repo:
            # if Berksfile exists, run berks to pull in cookbooks
            if os.path.exists(os.path.join(environment.kitchen_path,
                                           'Berksfile')):
                _ensure_berkshelf_environment()
                utils.run_ruby_command(name, environment.kitchen_path,
                                       'berks',
                                       ['install', '--path', os.path.join(
                                           environment.kitchen_path,
                                           'cookbooks')], lock=True)
                LOG.debug("Ran 'berks install' in: %s",
                          environment.kitchen_path)
            # If Cheffile exists, run librarian-chef to pull in cookbooks
            elif os.path.exists(os.path.join(environment.kitchen_path,
                                             'Cheffile')):
                utils.run_ruby_command(name, environment.kitchen_path,
                                       'librarian-chef', ['install'],
                                       lock=True)
                LOG.debug("Ran 'librarian-chef install' in: %s",
                          environment.kitchen_path)
        else:
            error_message = "Source repo not supplied and is required"
            raise exceptions.CheckmateException(
                error_message, friendly_message=exceptions.BLUEPRINT_ERROR)

        results.update(kitchen_data)
        results.update(key_data)
        LOG.debug("create_environment returning: %s", results)
        return results


def _ensure_berkshelf_environment():
    """Checks the Berkshelf environment and sets it up if necessary."""
    berkshelf_path = CONFIG.berkshelf_path
    if not berkshelf_path:
        local_path = CONFIG.deployments_path
        if not local_path:
            local_path = "/var/local/checkmate/deployments"
            LOG.warning("CHECKMATE_CHEF_LOCAL_PATH not defined. Using "
                        "%s", local_path)
        berkshelf_path = os.path.join(os.path.dirname(local_path), "cache")
        LOG.warning("BERKSHELF_PATH variable not set. Defaulting "
                    "to %s", berkshelf_path)
    if 'BERKSHELF_PATH' not in os.environ:
        # Berkshelf relies on this being set as an environent variable
        os.environ["BERKSHELF_PATH"] = berkshelf_path
    if not os.path.exists(berkshelf_path):
        os.makedirs(berkshelf_path)
        LOG.info("Created berkshelf_path: %s", berkshelf_path)
