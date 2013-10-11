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
"""Chef Environment domain object."""
import json
import logging
import os
import shutil
import subprocess

from Crypto.PublicKey import RSA
from Crypto import Random
import errno

from checkmate.common import config
from checkmate import exceptions, utils
from checkmate.providers.opscode.solo.blueprint_cache import BlueprintCache
from checkmate.providers.opscode.solo.knife import Knife


CONFIG = config.current()
LOG = logging.getLogger(__name__)
PRIVATE_KEY_NAME = 'private.pem'
PUBLIC_KEY_NAME = 'checkmate.pub'


class ChefEnvironment(object):
    def __init__(self, env_name, root_path=None, kitchen_name="kitchen"):
        self.env_name = env_name
        self.root = root_path or CONFIG.deployments_path
        self._env_path = os.path.join(self.root, self.env_name)
        self._kitchen_path = os.path.join(self._env_path, kitchen_name)
        self._private_key_path = os.path.join(self._env_path,
                                              PRIVATE_KEY_NAME)
        self._public_key_path = os.path.join(self._env_path, PUBLIC_KEY_NAME)
        # if not os.path.exists(path):
        #     error_message = "Invalid path: %s" % path
        #     raise exceptions.CheckmateException(error_message)

    @property
    def kitchen_path(self):
        """Read only property for kitchen path"""
        return self._kitchen_path

    @property
    def path(self):
        """Read only property for kitchen path"""
        return self._env_path

    @property
    def private_key_path(self):
        return self._private_key_path

    @property
    def public_key_path(self):
        return self._public_key_path

    def create_env_dir(self):
        try:
            os.mkdir(self._env_path, 0o770)
            LOG.debug("Created environment directory: %s", self.env_name)
        except OSError as ose:
            if ose.errno == errno.EEXIST:
                LOG.warn("Environment directory %s already exists",
                         self._env_path, exc_info=True)
            else:
                msg = "Could not create environment %s" % self._env_path
                raise exceptions.CheckmateException(msg)

    def delete_cookbooks(self):
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
        """Remove the chef environment from the file system."""
        try:
            shutil.rmtree(self._env_path)
            LOG.debug("Removed environment directory: %s", self._env_path)
        except OSError as ose:
            if ose.errno == errno.ENOENT:
                LOG.warn("Environment directory %s does not exist",
                         self._env_path, exc_info=True)
            else:
                msg = ("Unable to delete environment %s. Reason '%s'. Error "
                       "Number %s" % (self._env_path, ose.strerror, ose.errno))
                raise exceptions.CheckmateException(msg, exceptions.CAN_RESUME)

    def create_environment_keys(self, private_key=None, public_key_ssh=None):
        """Put keys in an existing environment
        If none are provided, a new set of public/private keys are created
        """
        self._create_private_key(private_key)
        public_key_path, public_key_ssh = self._create_public_key(
            public_key_ssh)
        return dict(public_key_ssh=public_key_ssh,
                    public_key_path=public_key_path,
                    private_key_path=self._private_key_path)

    def create_kitchen(self, secret_key=None, source_repo=None):
        """Creates a new knife-solo kitchen in path

        Arguments:
        - `source_repo`: URL of the git-hosted blueprint
        - `secret_key`: PEM-formatted private key for data bag encryption
        """
        if not os.path.exists(self._kitchen_path):
            os.mkdir(self._kitchen_path, 0o770)
            LOG.debug("Created kitchen directory: %s", self._kitchen_path)
        else:
            LOG.debug("Kitchen directory exists: %s", self._kitchen_path)

        nodes_path = os.path.join(self._kitchen_path, 'nodes')
        if os.path.exists(nodes_path):
            if any((f.endswith('.json') for f in os.listdir(nodes_path))):
                msg = ("Kitchen already exists and seems to have nodes "
                       "defined in it: %s" % nodes_path)
                LOG.debug(msg)
                return {"kitchen": self._kitchen_path}

        # we don't pass the config file here because we're creating the
        # kitchen for the first time and knife will overwrite our config
        # file
        knife = Knife(self._kitchen_path)
        knife.init_solo()
        secret_key_path = knife.write_solo_config()

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
        if os.path.exists(secret_key_path):
            if secret_key:
                with file(secret_key_path, 'r') as secret_key_file_r:
                    data = secret_key_file_r.read(secret_key)
                if data != secret_key:
                    msg = ("Kitchen secrets key file '%s' already exists and "
                           "does not match the provided value" %
                           secret_key_path)
                    raise exceptions.CheckmateException(msg)
            LOG.debug("Stored secrets file exists: %s", secret_key_path)
        else:
            if not secret_key:
                # celery runs os.fork(). We need to reset the random number
                # generator before generating a key. See atfork.__doc__
                Random.atfork()
                key = RSA.generate(2048)
                secret_key = key.exportKey('PEM')
                LOG.debug("Generated secrets private key")
            with file(secret_key_path, 'w') as secret_key_file_w:
                secret_key_file_w.write(secret_key)
            LOG.debug("Stored secrets file: %s", secret_key_path)

        # Knife defaults to knife.rb, but knife-solo looks for solo.rb, so we
        # link both files so that knife and knife-solo commands will work
        # and anyone editing one will also change the other
        knife_file = os.path.join(self._kitchen_path, 'knife.rb')
        if os.path.exists(knife_file):
            LOG.debug("Knife.rb already exists: %s", knife_file)
        else:
            os.link(knife.solo_config_path, knife_file)
            LOG.debug("Linked knife.rb: %s", knife_file)

        # Copy blueprint files to kitchen
        if source_repo:
            cache = BlueprintCache(source_repo)
            cache.update()
            utils.copy_contents(cache.cache_path, self._kitchen_path,
                                with_overwrite=True, create_path=True)

        LOG.debug("Finished creating kitchen: %s", self._kitchen_path)
        return {"kitchen": self._kitchen_path}

    def _create_private_key(self, private_key):
        if os.path.exists(self._private_key_path):
            if private_key:
                with file(self._private_key_path, 'r') as pk_file:
                    data = pk_file.read()
                if data != private_key:
                    msg = ("A private key already exists in environment %s "
                           "and does not match the value provided" %
                           self._env_path)
                    raise exceptions.CheckmateException(msg)
        else:
            if private_key:
                with file(self._private_key_path, 'w') as pk_file:
                    pk_file.write(private_key)
                LOG.debug("Wrote environment private key: %s",
                          self._private_key_path)
            else:
                params = ['openssl', 'genrsa', '-out', self._private_key_path,
                          '2048']
                result = subprocess.check_output(params)
                LOG.debug(result)
                LOG.debug("Generated environment private key: %s",
                          self._private_key_path)

        # Secure private key
        os.chmod(self._private_key_path, 0o600)
        LOG.debug("Private cert permissions set: chmod 0600 %s",
                  self._private_key_path)
        return self._private_key_path

    def _create_public_key(self, public_key_ssh):
        if os.path.exists(self._public_key_path):
            LOG.debug("Public key exists. Retrieving it from %s",
                      self._public_key_path)
            with file(self._public_key_path, 'r') as public_key_file_r:
                public_key_ssh = public_key_file_r.read()
        else:
            if not public_key_ssh:
                params = ['ssh-keygen', '-y', '-f', self._private_key_path]
                public_key_ssh = subprocess.check_output(params)
                LOG.debug("Generated environment public key: %s",
                          self._public_key_path)
                # Write it to environment
            with file(self._public_key_path, 'w') as public_key_file_w:
                public_key_file_w.write(public_key_ssh)
            LOG.debug("Wrote environment public key: %s",
                      self._public_key_path)
        return self._public_key_path, public_key_ssh
