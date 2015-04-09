# pylint: disable=R0913
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

"""Chef Kitchen domain object."""

import errno
import json
import logging
import os
import shutil
import subprocess

from Crypto.PublicKey import RSA
from Crypto import Random

from checkmate.common import config
from checkmate import exceptions
from checkmate.providers.opscode import base
from checkmate.providers.opscode.blueprint_cache import BlueprintCache
from checkmate.providers.opscode.knife import Knife
from checkmate import utils

CONFIG = config.current()
LOG = logging.getLogger(__name__)
PRIVATE_KEY_NAME = 'private.pem'
PUBLIC_KEY_NAME = 'checkmate.pub'


class ChefKitchen(object):

    """Domain object for chef kitchen.

    TODO(zns): still combines workspace directory and chef kitchen logic. Those
    should be decoupled.
    """

    def __init__(self, env_name, root_path=None, kitchen_name="kitchen",
                 github_token=None):
        self.env_name = env_name
        self.root = root_path or CONFIG.deployments_path
        self.kitchen_name = kitchen_name
        self._env_path = os.path.join(self.root, self.env_name)
        if not os.path.exists(self.root):
            raise exceptions.CheckmateException("Invalid path: %s" % self.root)
        self._kitchen_path = os.path.join(self._env_path, kitchen_name)
        self._private_key_path = os.path.join(self._env_path,
                                              PRIVATE_KEY_NAME)
        self._public_key_path = os.path.join(self._env_path, PUBLIC_KEY_NAME)
        self.github_token = github_token
        self._knife = Knife(self._kitchen_path)
        self.secret_key_path = None

    @property
    def kitchen_path(self):
        """Read only property for kitchen path."""
        return self._kitchen_path

    @property
    def path(self):
        """Read only property for kitchen path."""
        return self._env_path

    @property
    def private_key_path(self):
        """Read only property for private key path."""
        return self._private_key_path

    @property
    def public_key_path(self):
        """Read only property for public key path."""
        return self._public_key_path

    def create_env_dir(self):
        """Creates the kitchen directory."""
        try:
            os.mkdir(self._env_path, 0o770)
            LOG.debug("Created kitchen directory: %s", self.env_name)
        except OSError as ose:
            if ose.errno == errno.EEXIST:
                LOG.warn("Kitchen directory %s already exists", self._env_path)
            else:
                msg = "Could not create kitchen %s" % self._env_path
                exception = exceptions.CheckmateException(
                    str(ose), friendly_message=msg,
                    options=exceptions.CAN_RESUME)
                raise exception

    def fetch_cookbooks(self):
        """Fetches cookbooks."""
        if os.path.exists(os.path.join(self._kitchen_path, 'Berksfile')):
            env = os.environ.copy()
            env['BERKSHELF_CHEF_CONFIG'] = os.path.join(self.kitchen_path,
                                                        '.chef', 'knife.rb')
            self._ensure_berkshelf_kitchen()
            utils.run_ruby_command(self._kitchen_path, 'berks',
                                   ['install'], env=env, lock=True)
            LOG.debug("Ran 'berks install' in: %s", self._kitchen_path)
        elif os.path.exists(os.path.join(self._kitchen_path, 'Cheffile')):
            utils.run_ruby_command(self._kitchen_path,
                                   'librarian-chef', ['install'],
                                   lock=True)
            LOG.debug("Ran 'librarian-chef install' in: %s",
                      self._kitchen_path)

    def cook(self, host, username='root', password=None, identity_file=None,
             port=22, run_list=None, attributes=None):
        """Calls cooks for a host."""
        self._knife.cook(host, username=username, password=password,
                         identity_file=identity_file, port=port,
                         run_list=run_list, attributes=attributes)

    def delete_cookbooks(self):
        """Deletes cookbooks."""
        cookbook_config_exists = (
            os.path.exists(os.path.join(self._kitchen_path, 'Berksfile'))
            or
            os.path.exists(os.path.join(self.kitchen_path, 'Cheffile'))
        )

        if cookbook_config_exists:
            cookbooks_path = os.path.join(self.kitchen_path, 'cookbooks')
            try:
                shutil.rmtree(cookbooks_path)
                LOG.debug("Removed cookbooks directory: %s", cookbooks_path)
            except OSError as ose:
                if ose.errno == errno.ENOENT:
                    LOG.warn("Cookbooks directory %s does not exist",
                             cookbooks_path, exc_info=True)
                else:
                    msg = ("Could not delete cookbooks directory %s. Reason "
                           "'%s'. Error Number %s" % (cookbooks_path,
                                                      ose.strerror,
                                                      ose.errno))
                    raise exceptions.CheckmateException(msg)
        else:
            LOG.warn("Berksfile or Cheffile not found. Cookbooks were not "
                     "deleted")

    def delete(self):
        """Remove the chef kitchen from the file system."""
        try:
            shutil.rmtree(self._env_path)
            LOG.debug("Removed kitchen directory: %s", self._env_path)
        except OSError as ose:
            if ose.errno == errno.ENOENT:
                LOG.warn("Kitchen directory %s does not exist",
                         self._env_path, exc_info=True)
            else:
                msg = ("Unable to delete kitchen %s. Reason '%s'. Error "
                       "Number %s" % (self._env_path, ose.strerror, ose.errno))
                raise exceptions.CheckmateException(
                    msg, options=exceptions.CAN_RESUME)

    def write_file(self, relative_path, content):
        """Write file to workspace."""
        full_path = os.path.join(self._env_path, relative_path)
        dir_path, file_name = os.path.split(full_path)
        try:
            os.makedirs(dir_path)
            LOG.info("Created directory for %s", full_path)
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise
        with open(full_path, 'w') as handle:
            LOG.info("Writing to %s", full_path)
            handle.write(content)

    def write_kitchen_file(self, relative_path, content):
        """Write file to kitchen."""
        kitchen_path = os.path.join(self.kitchen_name, relative_path)
        return self.write_file(kitchen_path, content)

    def create_kitchen_keys(self, private_key=None, public_key_ssh=None):
        """Put keys in an existing kitchen.

        If none are provided, a new set of public/private keys are created
        """
        self._create_private_key(private_key)
        public_key_path, public_key_ssh = self._create_public_key(
            public_key_ssh)
        return dict(public_key_ssh=public_key_ssh,
                    public_key_path=public_key_path,
                    private_key_path=self._private_key_path)

    def ensure_kitchen_path_exists(self):
        """Check for or Create a new knife kitchen path."""
        if not os.path.exists(self._kitchen_path):
            os.mkdir(self._kitchen_path, 0o770)
            LOG.debug("Created kitchen directory: %s", self._kitchen_path)
        else:
            LOG.debug("Kitchen directory exists: %s", self._kitchen_path)

    def ensure_path_exists(self, relative_path):
        """Check for or Create a new path."""
        path = os.path.join(self._env_path, relative_path)
        if not os.path.exists(path):
            os.makedirs(path, 0o770)
            LOG.debug("Created directory: %s", path)
        else:
            LOG.debug("Directory exists: %s", path)

    def create_kitchen(self, secret_key=None, source_repo=None,
                       berksfile=None):
        """Create a new knife kitchen in path.

        Arguments:
        - `source_repo`: URL of the git-hosted blueprint
        - `secret_key`: PEM-formatted private key for data bag encryption
        - `berksfile`: berksfile content to add/merge to existing repo if
            supplied.
        """
        self.ensure_kitchen_path_exists()
        self.secret_key_path = self._knife.write_config()

        # Create bootstrap.json in the kitchen
        bootstrap_path = os.path.join(self._kitchen_path, 'bootstrap.json')
        if not os.path.exists(bootstrap_path):
            with file(bootstrap_path, 'w') as the_file:
                json.dump({"run_list": ["recipe[build-essential]"]}, the_file)

        # Create certificates folder
        certs_path = os.path.join(self._kitchen_path, 'certificates')
        if os.path.exists(certs_path):
            LOG.debug("Certs directory exists: %s", certs_path)
        else:
            os.mkdir(certs_path, 0o770)
            LOG.debug("Created certs directory: %s", certs_path)

        # Store (generate if necessary) the secrets file
        if os.path.exists(self.secret_key_path):
            if secret_key:
                with file(self.secret_key_path, 'r') as secret_key_file_r:
                    data = secret_key_file_r.read(secret_key)
                if data != secret_key:
                    msg = ("Kitchen secrets key file '%s' already exists and "
                           "does not match the provided value" %
                           self.secret_key_path)
                    raise exceptions.CheckmateException(msg)
            LOG.debug("Stored secrets file exists: %s", self.secret_key_path)
        else:
            if not secret_key:
                # celery runs os.fork(). We need to reset the random number
                # generator before generating a key. See atfork.__doc__
                Random.atfork()
                key = RSA.generate(2048)
                secret_key = key.exportKey('PEM')
                LOG.debug("Generated secrets private key")
            with file(self.secret_key_path, 'w') as secret_key_file_w:
                secret_key_file_w.write(secret_key)
            LOG.debug("Stored secrets file: %s", self.secret_key_path)

        # Copy blueprint files to kitchen
        if source_repo:
            cache = BlueprintCache(source_repo, github_token=self.github_token)
            cache.update()
            utils.copy_contents(cache.cache_path, self._kitchen_path,
                                with_overwrite=True, create_path=True)
        berks_file = os.path.join(self._kitchen_path, 'Berksfile')
        if berksfile:
            if os.path.exists(berks_file):
                # Merge content if existing
                with open(berks_file, 'r') as read_handle:
                    existing = read_handle.read()
                berksfile = base.merge_berks_entries([berksfile, existing])
            with open(berks_file, 'w') as write_handle:
                write_handle.write(berksfile)
        if CONFIG.git_use_https:
            if os.path.exists(berks_file):
                self._ensure_berks_https(berks_file)
        LOG.debug("Finished creating kitchen: %s", self._kitchen_path)
        return {"kitchen": self._kitchen_path}

    def _create_private_key(self, private_key):
        """Creates the private key for an kitchen."""
        if os.path.exists(self._private_key_path):
            if private_key:
                with file(self._private_key_path, 'r') as pk_file:
                    data = pk_file.read()
                if data != private_key:
                    msg = ("A private key already exists in kitchen %s "
                           "and does not match the value provided" %
                           self._env_path)
                    raise exceptions.CheckmateException(msg)
        else:
            if private_key:
                with file(self._private_key_path, 'w') as pk_file:
                    pk_file.write(private_key)
                LOG.debug("Wrote kitchen private key: %s",
                          self._private_key_path)
            else:
                params = ['openssl', 'genrsa', '-out', self._private_key_path,
                          '2048']
                result = subprocess.check_output(params)
                LOG.debug(result)
                LOG.debug("Generated kitchen private key: %s",
                          self._private_key_path)

        # Secure private key
        os.chmod(self._private_key_path, 0o600)
        LOG.debug("Private cert permissions set: chmod 0600 %s",
                  self._private_key_path)
        return self._private_key_path

    def _create_public_key(self, public_key_ssh):
        """Creates the public key for an kitchen."""
        if os.path.exists(self._public_key_path):
            LOG.debug("Public key exists. Retrieving it from %s",
                      self._public_key_path)
            with file(self._public_key_path, 'r') as public_key_file_r:
                public_key_ssh = public_key_file_r.read()
        else:
            if not public_key_ssh:
                params = ['ssh-keygen', '-y', '-f', self._private_key_path]
                public_key_ssh = subprocess.check_output(params)
                LOG.debug("Generated kitchen public key: %s",
                          self._public_key_path)
                # Write it to kitchen
            with file(self._public_key_path, 'w') as public_key_file_w:
                public_key_file_w.write(public_key_ssh)
            LOG.debug("Wrote kitchen public key: %s",
                      self._public_key_path)
        return self._public_key_path, public_key_ssh

    @staticmethod
    def _ensure_berkshelf_kitchen():
        """Checks the Berkshelf kitchen and sets it up if necessary."""
        berkshelf_path = CONFIG.berkshelf_path
        if not berkshelf_path:
            local_path = CONFIG.cache_path
            berkshelf_path = os.path.join(os.path.dirname(local_path),
                                          "berkshelf")
            LOG.warning("BERKSHELF_PATH variable not set. Defaulting "
                        "to %s", berkshelf_path)
        if 'BERKSHELF_PATH' not in os.environ:
            # Berkshelf relies on this being set as an environent variable
            os.environ["BERKSHELF_PATH"] = berkshelf_path
        if not os.path.exists(berkshelf_path):
            os.makedirs(berkshelf_path)
            LOG.info("Created berkshelf_path: %s", berkshelf_path)

    @staticmethod
    def _ensure_berks_https(berks_file_path):
        """Updates the Berkshelf file to use https and not git: protocol.

        TODO (zns): make this handle other github domains
        """
        with open(berks_file_path, 'r') as read_handle:
            contents = read_handle.read()
        if 'git@' in contents:
            updated = contents.replace('git@github.com:',
                                       'https://github.com/')
            with open(berks_file_path, 'w') as write_handle:
                write_handle.write(updated)
            LOG.info("Rewrote Berksfile to use https instead of ssh")
