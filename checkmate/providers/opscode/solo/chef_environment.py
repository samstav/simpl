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
import errno
import json
import logging
import os
import shutil
import subprocess

from Crypto.PublicKey import RSA
from Crypto import Random
from eventlet.green import threading

from checkmate.common import config
from checkmate import exceptions, utils
from checkmate.providers.opscode.solo.blueprint_cache import BlueprintCache
from checkmate.providers.opscode.solo.knife_solo import KnifeSolo


CONFIG = config.current()
LOG = logging.getLogger(__name__)
PRIVATE_KEY_NAME = 'private.pem'
PUBLIC_KEY_NAME = 'checkmate.pub'


class ChefEnvironment(object):
    """Domain object for chef environment."""
    def __init__(self, env_name, root_path=None, kitchen_name="kitchen"):
        self.env_name = env_name
        self.root = root_path or CONFIG.deployments_path
        self._env_path = os.path.join(self.root, self.env_name)
        if not os.path.exists(self.root):
            raise exceptions.CheckmateException("Invalid path: %s" % self.root)
        self._kitchen_path = os.path.join(self._env_path, kitchen_name)
        self._private_key_path = os.path.join(self._env_path,
                                              PRIVATE_KEY_NAME)
        self._public_key_path = os.path.join(self._env_path, PUBLIC_KEY_NAME)
        self._knife = KnifeSolo(self._kitchen_path)

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
        """Creates the environment directory."""
        try:
            os.mkdir(self._env_path, 0o770)
            LOG.debug("Created environment directory: %s", self.env_name)
        except OSError as ose:
            if ose.errno == errno.EEXIST:
                LOG.warn("Environment directory %s already exists",
                         self._env_path, exc_info=True)
            else:
                msg = "Could not create environment %s" % self._env_path
                exception = exceptions.CheckmateException(
                    str(ose), friendly_message=msg,
                    options=exceptions.CAN_RESUME)
                raise exception

    def register_node(self, host, password=None, omnibus_version=None,
                      identity_file=None):
        """Registers a node in the environment."""
        self._knife.prepare(host, password=password,
                            omnibus_version=omnibus_version,
                            identity_file=identity_file)

    def fetch_cookbooks(self):
        """Fetches cookbooks."""
        if os.path.exists(os.path.join(self._kitchen_path, 'Berksfile')):
            ChefEnvironment._ensure_berkshelf_environment()
            utils.run_ruby_command(self._kitchen_path, 'berks',
                                   ['install', '--path', os.path.join(
                                       self._kitchen_path,
                                       'cookbooks')], lock=True)
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
        self._knife.init()
        secret_key_path = self._knife.write_config()

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
            os.link(self._knife.config_path, knife_file)
            LOG.debug("Linked knife.rb: %s", knife_file)

        # Copy blueprint files to kitchen
        if source_repo:
            cache = BlueprintCache(source_repo)
            cache.update()
            utils.copy_contents(cache.cache_path, self._kitchen_path,
                                with_overwrite=True, create_path=True)

        LOG.debug("Finished creating kitchen: %s", self._kitchen_path)
        return {"kitchen": self._kitchen_path}

    def write_node_attributes(self, host, attributes, run_list=None):
        """Merge node attributes into existing ones in node file."""
        node_path = self._knife.get_node_path(host)
        if not os.path.exists(node_path):
            raise exceptions.CheckmateException(
                "Node '%s' is not registered in %s" % (host,
                                                       self._kitchen_path))
        if attributes:
            lock = threading.Lock()
            lock.acquire()
            try:
                with file(node_path, 'r') as node_file_r:
                    node = json.load(node_file_r)
                if 'run_list' not in node:
                    node['run_list'] = []
                if run_list:
                    for entry in run_list:
                        if entry not in node['run_list']:
                            node['run_list'].append(entry)
                if attributes:
                    utils.merge_dictionary(node, attributes)

                with file(node_path, 'w') as node_file_w:
                    json.dump(node, node_file_w)
                LOG.info("Node %s written in %s", node,
                         node_path, extra=dict(data=node))
                return node
            except StandardError as exc:
                raise exc
            finally:
                lock.release()

    def ruby_role_exists(self, name):
        """Checks if a ruby role file exists."""
        ruby_role_path = os.path.join(self.kitchen_path, 'roles',
                                      '%s.rb' % name)
        return os.path.exists(ruby_role_path)

    def write_role(self, name, desc=None, run_list=None,
                   default_attributes=None, override_attributes=None,
                   env_run_lists=None):
        """Write/Update role."""
        role_path = os.path.join(self.kitchen_path, 'roles', '%s.json' % name)

        if os.path.exists(role_path):
            with file(role_path, 'r') as role_file_r:
                role = json.load(role_file_r)
            if run_list is not None:
                role['run_list'] = run_list
            if default_attributes is not None:
                role['default_attributes'] = default_attributes
            if override_attributes is not None:
                role['override_attributes'] = override_attributes
            if env_run_lists is not None:
                role['env_run_lists'] = env_run_lists
        else:
            role = {
                "name": name,
                "chef_type": "role",
                "json_class": "Chef::Role",
                "default_attributes": default_attributes or {},
                "description": desc,
                "run_list": run_list or [],
                "override_attributes": override_attributes or {},
                "env_run_lists": env_run_lists or {}
            }

        LOG.debug("Writing role '%s' to %s", name, role_path)
        with file(role_path, 'w') as role_file_w:
            json.dump(role, role_file_w)
        return role

    def write_data_bag(self, bag_name, item_name, contents, secret_file=None):
        """Writes data bag to the environment."""
        if not os.path.exists(self._knife.data_bags_path):
            msg = ("Data bags path does not exist: %s" %
                   self._knife.data_bags_path)
            raise exceptions.CheckmateException(msg)

        self._knife.create_data_bag(bag_name)

        lock = threading.Lock()
        lock.acquire()
        try:
            self._knife.create_data_bag_item(bag_name, item_name,
                                             contents,
                                             secret_file=secret_file)
        except subprocess.CalledProcessError as exc:
            raise exceptions.CheckmateCalledProcessError(exc.returncode,
                                                         exc.cmd,
                                                         output=str(exc))
        finally:
            lock.release()

    def _create_private_key(self, private_key):
        """Creates the private key for an environment."""
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
        """Creates the public key for an environment."""
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

    @staticmethod
    def _ensure_berkshelf_environment():
        """Checks the Berkshelf environment and sets it up if necessary."""
        berkshelf_path = CONFIG.berkshelf_path
        if not berkshelf_path:
            local_path = CONFIG.deployments_path
            berkshelf_path = os.path.join(os.path.dirname(local_path), "cache")
            LOG.warning("BERKSHELF_PATH variable not set. Defaulting "
                        "to %s", berkshelf_path)
        if 'BERKSHELF_PATH' not in os.environ:
            # Berkshelf relies on this being set as an environent variable
            os.environ["BERKSHELF_PATH"] = berkshelf_path
        if not os.path.exists(berkshelf_path):
            os.makedirs(berkshelf_path)
            LOG.info("Created berkshelf_path: %s", berkshelf_path)
