# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Blueprints Manager.

Handles blueprint logic
"""

import logging
import uuid

from checkmate import exceptions
from checkmate import utils

LOG = logging.getLogger(__name__)


class Manager(object):

    """Blueprints Model and Logic for Accessing Blueprints."""

    def __init__(self, driver):
        """Initialize manager with driver.

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

    def get_all_blueprints(self, offset=None, limit=None):
        """Get a full list of all blueprints."""
        return self.driver.get_blueprints(
            offset=offset,
            limit=limit,
        )

    def get_blueprint(self, api_id, tenant_id=None):
        """Get an existing blueprint."""
        blueprint = self.driver.get_blueprint(api_id)
        if blueprint:
            if blueprint.get("tenantId") != tenant_id:
                raise exceptions.CheckmateDoesNotExist(
                    friendly_message="Blueprint does not exist for this "
                    "tenant")
        return blueprint

    def save_blueprint(self, entity, api_id=None, tenant_id=None):
        """Save a blueprint.

        :returns: saved blueprint
        """
        if not api_id:
            if 'id' not in entity:
                api_id = uuid.uuid4().hex
                entity['id'] = api_id
            else:
                api_id = entity['id']
        else:
            if 'id' not in entity:
                entity['id'] = api_id
            else:
                assert api_id == entity['id'], ("Blueprint ID (%s) does not "
                                                "match entityId (%s)",
                                                (api_id, entity['id']))
        if 'tenantId' in entity:
            if tenant_id:
                assert entity['tenantId'] == tenant_id, (
                    "tenantId must match with current tenant ID")
            else:
                tenant_id = entity['tenantId']
        else:
            assert tenant_id, "Tenant ID must be specified in entity"
            entity['tenantId'] = tenant_id

        body, secrets = utils.extract_sensitive_data(entity)
        results = self.driver.save_blueprint(
            api_id, body, secrets=secrets, tenant_id=tenant_id
        )
        LOG.info("Saved blueprint %s to tenant %s", api_id, tenant_id)
        return results
