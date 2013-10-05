# pylint: disable=W0613,R0904

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

"""Tests for blueprints manager."""

import unittest

import mock

from checkmate import blueprints
from checkmate import exceptions


class TestManager(unittest.TestCase):

    def setUp(self):
        self.driver = mock.Mock()
        self.manager = blueprints.Manager(self.driver)

    def test_get_blueprints(self):
        self.driver.get_blueprints.return_value = {'dummy': 1}
        results = self.manager.get_blueprints(tenant_id=1, offset=2, limit=3)
        self.assertEqual(results, {'dummy': 1})
        self.driver.get_blueprints.assert_called_with(tenant_id=1, offset=2,
                                                      limit=3)

    def test_get_blueprint(self):
        self.driver.get_blueprint.return_value = {'tenantId': "A"}
        results = self.manager.get_blueprint(1, tenant_id="A")
        self.assertEqual(results, {'tenantId': "A"})
        self.driver.get_blueprint.assert_called_with(1)

    def test_get_blueprint_bad_tenant(self):
        self.driver.get_blueprint.return_value = {'tenantId': "Mr. Wrong"}
        with self.assertRaises(exceptions.CheckmateDoesNotExist):
            self.manager.get_blueprint(1, tenant_id="Mr. Right")
        self.driver.get_blueprint.assert_called_with(1)

    @mock.patch.object(blueprints.manager, 'uuid')
    def test_save_blueprint(self, mock_uuid):
        mock_uuid.uuid4.return_value = mock.Mock(hex="UUID")
        entity = {'tenantId': "A"}
        self.driver.save_blueprint.return_value = entity
        results = self.manager.save_blueprint(entity, tenant_id="A")
        self.assertEqual(results, {'id': 'UUID', 'tenantId': "A"})
        self.driver.save_blueprint.assert_called_with(mock.ANY, entity,
                                                      secrets=None,
                                                      tenant_id="A")

    @mock.patch.object(blueprints.manager, 'uuid')
    def test_save_blueprint_adds_tenant(self, mock_uuid):
        mock_uuid.uuid4.return_value = mock.Mock(hex="UUID")
        entity = {}
        self.driver.save_blueprint.return_value = entity
        results = self.manager.save_blueprint(entity, tenant_id="A")
        self.assertEqual(results, {'id': 'UUID', 'tenantId': "A"})
        self.driver.save_blueprint.assert_called_with(
            mock.ANY, {'id': 'UUID', 'tenantId': "A"}, secrets=None,
            tenant_id="A")

    def test_save_blueprint_id_mismatch(self):
        entity = {'tenantId': "A", 'id': 1}
        with self.assertRaises(AssertionError):
            self.manager.save_blueprint(entity, api_id=2, tenant_id="A")

    def test_save_blueprint_bad_tenant(self):
        entity = {'tenantId': "A", 'id': 1}
        with self.assertRaises(AssertionError):
            self.manager.save_blueprint(entity, api_id=1, tenant_id="B")


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
