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
#
# Author: Ziad Sawalha (http://launchpad.net/~ziad-sawalha)
# Original maintained at: https://github.com/ziadsawalha/Python-tracer

"""
Base Class
"""
from checkmate import utils


# pylint: disable=R0903
class ManagerBase(object):
    """Handles interface between API and database."""

    def __init__(self, drivers):
        self.driver = drivers.get('default')
        self.simulator_driver = drivers.get('simulation')

    def select_driver(self, api_id):
        """Returns driver based on whether or not this is a simulation."""
        if utils.is_simulation(api_id):
            return self.simulator_driver
        else:
            return self.driver
