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
"""Knife domain object."""
import json
import logging
import os

from checkmate import exceptions, utils

LOG = logging.getLogger(__name__)


class KnifeSolo(object):
    """Knife domain object."""
    def __init__(self, kitchen_path, solo_config_path=None):
        self.kitchen_path = kitchen_path
        self._config_path = solo_config_path or os.path.join(
            self.kitchen_path, '.chef', 'knife.rb')
        self._data_bags_path = os.path.join(self.kitchen_path, 'data_bags')

    @property
    def config_path(self):
        """Read only property for solo config path."""
        return self._config_path

    @property
    def data_bags_path(self):
        """Read only property for data bags path."""
        return self._data_bags_path

    def init(self):
        """Initializes solo provider
        :return:
        """
        params = ['knife', 'solo', 'init', '.']
        self.run_command(params)

    def prepare(self, host, password=None, bootstrap_version=None,
                identity_file=None):
        """Calls knife solo prepare to register a node and install chef
        client on the node
        :return:
        """
        node_path = self.get_node_path(host)
        if os.path.exists(node_path):
            LOG.info("Node is already registered: %s", node_path)
        else:
            params = ['knife', 'solo', 'prepare', 'root@%s' % host,
                      '-c', self._config_path]
            if password:
                params.extend(['-P', password])
            if bootstrap_version:
                params.extend(['--bootstrap-version', bootstrap_version])
            if identity_file:
                params.extend(['-i', identity_file])
            self.run_command(params)

    def cook(self, host, username='root', password=None, identity_file=None,
             port=22, run_list=None, attributes=None):
        """Runs knife solo cook for a given host."""
        params = ['knife', 'solo', 'cook', '%s@%s' % (username, host),
                  '-c', self._config_path]
        if not (run_list or attributes):
            params.extend(['bootstrap.json'])
        if identity_file:
            params.extend(['-i', identity_file])
        if password:
            params.extend(['-P', password])
        params.extend(['-p', str(port)])

        self.run_command(params)
        LOG.info("Knife cook succeeded for %s", host)

    def get_data_bags(self):
        """Gets all the databags for solo."""
        params = ['knife', 'solo', 'data', 'bag', 'list', '-F', 'json',
                  '-c', self._config_path]
        data = self.run_command(params)
        return json.loads(data) if data else {}

    def get_data_bag(self, bag_name):
        """Gets a databag for solo."""
        params = ['knife', 'solo', 'data', 'bag', 'show', bag_name, '-F',
                  'json', '-c', self._config_path]
        data = self.run_command(params)
        return json.loads(data) if data else {}

    def get_data_bag_item(self, bag_name, item_name, secret_file=None):
        """Gets a particular item from a data bag."""
        params = ['knife', 'solo', 'data', 'bag', 'show', bag_name, item_name,
                  '-F', 'json', '-c', self._config_path]
        if secret_file:
            params.extend(['--secret-file', secret_file])
        data = self.run_command(params)
        return json.loads(data) if data else {}

    def create_data_bag(self, bag_name):
        """Creates new databag for solo. Ignores the request if the data
        bag already exists
        """
        data_bags = self.get_data_bags()
        if bag_name not in data_bags:
            params = ['knife', 'solo', 'data', 'bag', 'create', bag_name,
                      '-c', self._config_path]
            LOG.debug("Creating data bag '%s' in '%s'", bag_name,
                      self._data_bags_path)
            self.run_command(params)
        else:
            LOG.warn("Data bag '%s' in '%s' already exists", bag_name,
                     self._data_bags_path)

    def create_data_bag_item(self, bag_name, item_name, contents,
                             secret_file=None):
        """Creates an item in a data bag."""
        existing_contents = self.get_data_bag(bag_name)
        if item_name in existing_contents:
            item_data = self.get_data_bag_item(bag_name, item_name,
                                               secret_file=secret_file)
            contents = utils.merge_dictionary(item_data, contents)

        if 'id' not in contents:
            contents['id'] = item_name
        elif contents['id'] != item_name:
            message = ("The value of the 'id' field in a "
                       "databag item is reserved by Chef "
                       "and must be set to the name of the "
                       "databag item. Checkmate will set "
                       "this for you if it is missing, but "
                       "the data you supplied included an "
                       "ID that did not match the databag "
                       "item name. The ID was '%s' and the "
                       "databag item name was '%s'" % (contents['id'],
                                                       item_name))
            raise exceptions.CheckmateException(message)

        if isinstance(contents, dict):
            final_contents = json.dumps(contents)
        else:
            final_contents = contents

        params = ['knife', 'solo', 'data', 'bag', 'create', bag_name,
                  item_name, '-d', '-c', self._config_path, '--json',
                  final_contents]
        if secret_file:
            params.extend(['--secret-file', secret_file])
        self.run_command(params)

    def get_node_path(self, host):
        """Gets the node path for a host."""
        return os.path.join(self.kitchen_path, 'nodes', '%s.json' % host)

    def run_command(self, params, lock=True):
        """Runs the 'knife xxx' command.

        This also needs to handle knife command errors, which are returned to
        stderr.

        That needs to be run in a kitchen, so we move current dir and need to
        make sure we stay there, so I added some synchronization code while
        that takes place. However, if code calls in that already has a lock,
        the optional lock param can be set to false so this code does not lock
        """
        LOG.debug("Running: '%s' in path '%s'", ' '.join(params),
                  self.kitchen_path)
        if '-c' not in params:
            if os.path.exists(self.config_path):
                LOG.warning("Knife command called without a '-c' flag. The "
                            "'-c' flag is a strong safeguard in case knife "
                            "runs in the wrong directory. Consider adding it "
                            "and pointing to knife.rb")
                LOG.debug("Defaulting to config file '%s'",
                          self.config_path)
                params.extend(['-c', self.config_path])
        result = utils.run_ruby_command(self.kitchen_path, params[0],
                                        params[1:], lock=lock)

        # Knife succeeds even if there is an error. This code tries to parse
        # the output to return a useful error.
        last_error = ''
        for line in result.split('\n'):
            if 'ERROR:' in line:
                LOG.error(line)
                last_error = line
        if last_error:
            if 'KnifeSolo::::' in last_error:
                # Get the string after a Knife-Solo error::
                error = last_error.split('Error:')[-1]
                if error:
                    msg = "Knife error encountered: %s" % error
                    raise exceptions.CheckmateCalledProcessError(
                        1, ' '.join(params), output=msg)
                # Don't raise on all errors. They don't all mean failure!
        return result

    def write_config(self):
        """Writes a knife.rb config file."""
        secret_key_path = os.path.join(self.kitchen_path, 'certificates',
                                       'chef.pem')
        knife_config = """# knife -c knife.rb
    knife[:provisioning_path] = "%s"

    cookbook_path    ["cookbooks", "site-cookbooks"]
    role_path  "roles"
    data_bag_path  "data_bags"
    encrypted_data_bag_secret "%s"
    """ % (self.kitchen_path, secret_key_path)
        # knife kitchen creates a default knife.rb, so the file already exists
        with file(self.config_path, 'w') as handle:
            handle.write(knife_config)
        LOG.debug("Created solo file: %s", self.config_path)
        return secret_key_path
