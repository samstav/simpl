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

import logging
import os

from checkmate import exceptions, utils

LOG = logging.getLogger(__name__)


class Knife(object):

    """Knife domain object."""

    def __init__(self, kitchen_path, config_path=None):
        self.kitchen_path = kitchen_path
        self._config_path = config_path or os.path.join(
            self.kitchen_path, '.chef', 'knife.rb')
        self._data_bags_path = os.path.join(self.kitchen_path, 'data_bags')

    @property
    def config_path(self):
        """Read only property for config path."""
        return self._config_path

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
            if 'KnifeSolo::::' in last_error or 'Knife::::' in last_error:
                # Get the string after a Knife-Solo error::
                error = last_error.split('Error:')[-1]
                if error:
                    msg = "Knife error encountered: %s" % error
                    raise exceptions.CheckmateCalledProcessError(
                        1, ' '.join(params), output=msg)
                # Don't raise on all errors. They don't all mean failure!
        return result

    def ensure_config_path_exists(self):
        """Check for or Create a new knife config path."""
        path = os.path.dirname(self._config_path)
        if not os.path.exists(path):
            os.mkdir(path, 0o770)
            LOG.debug("Created .chef directory: %s", path)
        else:
            LOG.debug(".chef directory exists: %s", path)

    def write_config(self):
        """Writes a knife.rb config file."""
        self.ensure_config_path_exists()
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
        LOG.debug("Created config file: %s", self.config_path)
        return secret_key_path

    def update_config(self, **kwargs):
        """Update a knife.rb file with new config values.

        Any item with None as the value will be deleted from te file.
        """
        self.ensure_config_path_exists()
        lines = []
        config = {}
        if os.path.exists(self.config_path):
            with file(self.config_path, 'r') as handle:
                lines = handle.readlines()
        for line in lines:
            parts = line.strip().split(' ')
            key = parts[0]
            value = ' '.join(parts[1:])
            config[key] = value
        for key, value in kwargs.items():
            if value is None and key in config:
                del config[key]
            else:
                config[key] = value
        lines = []
        for key, value in config.items():
            lines.append("%s    %s" % (key, value))
        with file(self.config_path, 'w') as handle:
            handle.write("\n".join(lines))
        LOG.debug("Updated config file: %s", self.config_path)
