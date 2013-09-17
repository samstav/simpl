# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#
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

"""Rackspace Cloud Databases provider manager."""

import copy
import logging

from checkmate import exceptions
from checkmate import utils

LOG = logging.getLogger(__name__)


# pylint: disable=R0903
class Manager(object):
    """Contains script provider model and logic for interaction."""

    def __init__(self, api=None, callback=None, simulate=False):
        """Init a manager with required parameters.

        :param api: an api object used to make remote calls (ssh in this case)
        :param callback: a callable to use for sending updates
        :param simulate: True if this is just a simulation

        """
        self.api = api
        self.callback = callback
        self.simulate = simulate

    # pylint: disable=W0613,R0913
    def create_resource(self, context, deployment_id, resource, host, username,
                        password=None, private_key=None, install_script=None,
                        timeout=60, host_os="linux"):
        """Creates a script-defined resource.

        :param context: a call context (identity, etc...)
        :param resource: a dict defining the resource to create
        :param install_script: a script string or dict
        :param host: the address of the compute host to create the resource on
        :param host_os: 'linux' or 'windows'

        """
        desired = resource.get('desired') or {}
        if self.simulate is True:
            instance = copy.deepcopy(desired)
        else:
            script = Script(install_script)
            try:
                if host_os == 'windows':
                    if username == 'root':
                        username = 'Administrator'
                    (status, results) = self.api.ps_execute(
                        host, script.body, script.name or 'install.ps1',
                        username, password, timeout=timeout)
                    if status != 0:
                        LOG.error("Error while executing powershell command: "
                                  "%s", results)
                        raise exceptions.CheckmateException(
                            "Error executing powershell command: %s", results)
                else:
                    results = self.api.remote_execute(host, install_script,
                                                      username,
                                                      password=password,
                                                      private_key=private_key,
                                                      timeout=timeout)
                LOG.debug("remote execute results: %s", results)

                instance = copy.deepcopy(desired)
            except Exception as exc:
                raise exceptions.CheckmateException(
                    exc, options=exceptions.CAN_RETRY)

        instance['status'] = 'ACTIVE'

        if callable(self.callback):
            self.callback(instance)

        LOG.info("Created %s resource on %s", resource.get('type'), host)

        return instance


class Script(object):
    """Handles script files."""

    extension_map = {
        'ps1': 'powershell',
        'sh': 'bash',
    }

    def __init__(self, script):
        """Accepts a script dict or string."""
        if isinstance(script, basestring):
            self.body = script
            script = {}
        else:
            self.body = script.get('body')
        self.name = script.get('name')
        self.type = script.get('type') or self.detect_type()

    def detect_type(self):
        """Detect script type based on properties such as the name or body."""
        if self.name:
            for extension, _type in self.extension_map.iteritems():
                if self.name.endswith('.' + extension):
                    return _type
