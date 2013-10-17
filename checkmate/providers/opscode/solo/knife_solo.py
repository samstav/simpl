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
    def __init__(self, kitchen_path, solo_config_path=None):
        self.kitchen_path = kitchen_path
        self._config_path = solo_config_path or os.path.join(
            self.kitchen_path, 'solo.rb')
        self._data_bags_path = os.path.join(self.kitchen_path, 'data_bags')

    @property
    def config_path(self):
        return self._config_path

    @property
    def data_bags_path(self):
        return self._data_bags_path

    def init(self):
        """Initializes solo provider
        :return:
        """
        params = ['knife', 'solo', 'init', '.']
        self.run_command(params)

    def prepare(self, host, password=None, omnibus_version=None,
                identity_file=None):
        """Calls knife solo prepare to register a node and install chef
        client on the node
        :return:
        """
        # Calculate node path and check for prexistance
        node_path = self.get_node_path(host)
        if os.path.exists(node_path):
            LOG.info("Node is already registered: %s", node_path)
        else:
            # Build and execute command 'knife prepare' command
            params = ['knife', 'solo', 'prepare', 'root@%s' % host,
                      '-c', os.path.join(self.kitchen_path, 'solo.rb')]
            if password:
                params.extend(['-P', password])
            if omnibus_version:
                params.extend(['--omnibus-version', omnibus_version])
            if identity_file:
                params.extend(['-i', identity_file])
            self.run_command(params)

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
        bag already exists"""
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
                            "and pointing to solo.rb")
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
        """Writes a solo.rb config file and links a knife.rb file too."""
        secret_key_path = os.path.join(self.kitchen_path, 'certificates',
                                       'chef.pem')
        knife_config = """# knife -c knife.rb
    file_cache_path  "%s"
    cookbook_path    ["%s", "%s"]
    role_path  "%s"
    data_bag_path  "%s"
    log_level        :info
    log_location     "%s"
    verbose_logging  true
    ssl_verify_mode  :verify_none
    encrypted_data_bag_secret "%s"
    """ % (self.kitchen_path,
           os.path.join(self.kitchen_path, 'cookbooks'),
           os.path.join(self.kitchen_path, 'site-cookbooks'),
           os.path.join(self.kitchen_path, 'roles'),
           os.path.join(self.kitchen_path, 'data_bags'),
           os.path.join(self.kitchen_path, 'knife-solo.log'),
           secret_key_path)
        # knife kitchen creates a default solo.rb, so the file already exists
        with file(self.config_path, 'w') as handle:
            handle.write(knife_config)
        LOG.debug("Created solo file: %s", self.config_path)
        return secret_key_path
