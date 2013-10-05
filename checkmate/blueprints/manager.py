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

"""
Blueprints Manager

Handles blueprint logic
"""

import logging


LOG = logging.getLogger(__name__)


class Manager(object):
    """Contains Blueprints Model and Logic for Accessing Blueprints."""
    def __init__(self, driver):
        """
        :param driver: database driver
        """
        assert driver is not None, "No driver supplied to manager"
        self.driver = driver

    def get_blueprints(self, tenant_id=None, offset=None, limit=None,
                       details=0, roles=None):
        """Get existing blueprints."""
        return self.driver.get_blueprints(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit,
        )
