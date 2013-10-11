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
    def __init__(self, kitchen_path, solo_config_path=None):
        self.kitchen_path = kitchen_path
        self._solo_config_path = solo_config_path or os.path.join(
            self.kitchen_path, 'solo.rb')

    @property
    def solo_config_path(self):
        return self._solo_config_path

    def init_solo(self):
        """Initializes solo provider
        :return:
        """
        params = ['knife', 'solo', 'init', '.']
        self.run_command(self.kitchen_path, params)

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
            if os.path.exists(self.solo_config_path):
                LOG.warning("Knife command called without a '-c' flag. The "
                            "'-c' flag is a strong safeguard in case knife "
                            "runs in the wrong directory. Consider adding it "
                            "and pointing to solo.rb")
                LOG.debug("Defaulting to config file '%s'",
                          self.solo_config_path)
                params.extend(['-c', self.solo_config_path])
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

    def write_solo_config(self):
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
        with file(self.solo_config_path, 'w') as handle:
            handle.write(knife_config)
        LOG.debug("Created solo file: %s", self.solo_config_path)
        return secret_key_path
