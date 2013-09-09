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

    def create_resource(self, context, deployment_id, resource, host, username,
                        password=None, private_key=None, install_script=None,
                        timeout=60):
        """Creates a script-defined resource.

        :param context: a call context (identity, etc...)
        :param resource: a dict defining the resource to create
        :param host: the address of the compute host to create the resource on

        """
        desired = resource.get('desired') or {}
        if self.simulate is True:
            instance = {'instance': copy.deepcopy(desired)}
        else:
            try:
                results = self.api.remote_execute(host, install_script,
                                                  username, password=password,
                                                  private_key=private_key,
                                                  timeout=timeout)

                instance = {'instance': copy.deepcopy(desired)}
            except Exception as exc:
                raise exceptions.CheckmateRetriableException(
                    str(exc), utils.get_class_name(exc),
                    exceptions.UNEXPECTED_ERROR, '')

        if callable(self.callback):
            self.callback(instance)

        LOG.info("Created %s resource on %s", resource.get('type'), host)

        return results
