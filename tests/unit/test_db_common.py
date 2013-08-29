# pylint: disable=C0103,R0904

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

"""Tests for DbCommon."""
import mock
import unittest
import uuid

from checkmate.db import common


class TestDbCommonAnyID(unittest.TestCase):

    def test_any_id_problems_ok(self):
        self.assertIsNone(common.any_id_problems('12'))

    def test_any_tid_problems_uuid_ok(self):
        self.assertIsNone(common.any_id_problems(uuid.uuid4().hex))

    def test_any_id_problems_one_digit(self):
        self.assertIsNone(common.any_id_problems('1'))

    def test_any_id_problems_one_char(self):
        self.assertIsNone(common.any_id_problems('a'))

    def test_any_id_problems_max_char(self):
        self.assertIsNone(common.any_id_problems('x' * 32))

    def test_any_id_problems_too_long(self):
        self.assertEqual(common.any_id_problems('x' * 33), "ID must be 1 to "
                         "32 characters")

    def test_any_id_problems_none(self):
        self.assertEqual(common.any_id_problems(None), 'ID cannot be blank')

    def test_any_id_problems_blank(self):
        self.assertEqual(common.any_id_problems(''), 'ID cannot be blank')

    def test_any_id_problems_space(self):
        self.assertEqual(common.any_id_problems(' '), "Invalid start "
                         "character ' '. ID can start with any of 'abcdefghijk"
                         "lmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'"
                         )

    def test_any_id_problems_start_invalid(self):
        self.assertEqual(common.any_id_problems('_1'), "Invalid start "
                         "character '_'. ID can start with any of 'abcdefghijk"
                         "lmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'"
                         )

    def test_any_id_problems_invalid_char(self):
        self.assertEqual(common.any_id_problems('1^2'), "Invalid character "
                         "'^'. Allowed characters are "
                         "'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWX"
                         "YZ0123456789-_.+~@'")


class TestDbCommonTenantID(unittest.TestCase):

    def test_any_tenant_id_problems_ok(self):
        self.assertIsNone(common.any_tenant_id_problems('12'))

    def test_any_tenant_id_problems_uuid_ok(self):
        self.assertIsNone(common.any_tenant_id_problems(uuid.uuid4().hex))

    def test_any_tenant_id_problems_one_digit(self):
        self.assertIsNone(common.any_tenant_id_problems('1'))

    def test_any_tenant_id_problems_one_char(self):
        self.assertIsNone(common.any_tenant_id_problems('a'))

    def test_any_tenant_id_problems_max_char(self):
        self.assertIsNone(common.any_tenant_id_problems('x' * 255))

    def test_any_tenant_id_problems_too_long(self):
        self.assertEqual(common.any_tenant_id_problems('x' * 256), "Tenant ID "
                         "must be 1 to 255 characters")

    def test_any_tenant_id_problems_none(self):
        self.assertEqual(common.any_tenant_id_problems(None), 'Tenant ID '
                         'cannot be blank')

    def test_any_tenant_id_problems_blank(self):
        self.assertEqual(common.any_tenant_id_problems(''), 'Tenant ID cannot '
                         'be blank')

    def test_any_tenant_id_problems_space(self):
        self.assertEqual(common.any_tenant_id_problems(' '), "Invalid start "
                         "character ' '. Tenant ID can start with any of 'abcd"
                         "efghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123"
                         "456789'")

    def test_any_tenant_id_problems_start_invalid(self):
        self.assertEqual(common.any_tenant_id_problems('_1'), "Invalid start "
                         "character '_'. Tenant ID can start with any of 'abcd"
                         "efghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123"
                         "456789'")

    def test_any_tenant_id_problems_invalid_char(self):
        self.assertEqual(common.any_tenant_id_problems('1|2'), "Invalid "
                         "character '|' in Tenant ID. Allowed charaters are "
                         "'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXY"
                         "Z0123456789-_.+~@()[]*&^=%$#!<>'")


class TestDbCommonGetDriver(unittest.TestCase):
    def setUp(self):
        common.DRIVER_INSTANCES = {}
        common.DRIVERS_AVAILABLE = {}

    @mock.patch.object(common.utils, 'import_class')
    def test_new_driver_instances_are_imported(self, mock_import):
        mock_class = mock.Mock(return_value="driver")
        mock_import.return_value = mock_class

        driver = common.get_driver(connection_string="mongodb://fake")
        mock_import.assert_called_once_with('checkmate.db.mongodb.Driver')
        self.assertEqual('driver', driver)

    @mock.patch.object(common.utils, 'import_class')
    def test_driver_instances_are_cached_once_imported(self, mock_import):
        mock_class = mock.Mock(return_value="driver")
        mock_import.return_value = mock_class

        common.get_driver(connection_string="mongodb://fake")
        self.assertEqual('driver', common.DRIVER_INSTANCES['mongodb://fake'])

    @mock.patch.object(common.utils, 'import_class')
    def test_instantiates_new_driver_with_connection_string(self, mock_import):
        mock_class = mock.Mock(return_value="driver")
        mock_import.return_value = mock_class

        common.get_driver(connection_string="mongodb://fake")
        mock_class.assert_called_once_with(connection_string='mongodb://fake')

    @mock.patch.object(common.utils, 'import_class')
    def test_use_mongo_if_given_mongo_conn_string_and_no_name(self,
                                                              mock_import):
        common.get_driver(connection_string="mongodb://fake")
        mock_import.assert_called_once_with('checkmate.db.mongodb.Driver')

    @mock.patch.object(common.utils, 'import_class')
    def test_use_sql_if_non_mongo_conn_string_and_no_name(self, mock_import):
        common.get_driver(connection_string="notmongo://fakeconnection")
        mock_import.assert_called_once_with('checkmate.db.sql.Driver')

    @mock.patch.object(common.utils, 'import_class')
    def test_import_driver_class_based_on_given_name(self, mock_import):
        common.get_driver(connection_string="test://fakeconnection",
                          name="Cassandra")
        mock_import.assert_called_once_with('Cassandra')

    @mock.patch.object(common.os, 'environ')
    @mock.patch.object(common.utils, 'import_class')
    def test_get_conn_string_from_environ_if_none_given(self,
                                                        mock_import,
                                                        mock_env):
        mock_class = mock.Mock()
        mock_import.return_value = mock_class
        mock_env.get.return_value = 'some://connection'

        common.get_driver()
        mock_env.get.assert_called_with('CHECKMATE_CONNECTION_STRING')
        mock_class.assert_called_with(connection_string='some://connection')

    @mock.patch.object(common.utils, 'import_class')
    def test_default_to_sql_no_conn_no_name_no_environ(self, mock_import):
        common.get_driver()
        mock_import.assert_called_once_with('checkmate.db.sql.Driver')

    @mock.patch.object(common.os, 'environ')
    @mock.patch.object(common.utils, 'import_class')
    def test_look_up_available_driver_if_given_name_and_no_environ(self,
                                                                   mock_import,
                                                                   mock_env):
        mock_class = mock.Mock()
        mock_import.return_value = mock_class
        mock_env.get.return_value = None

        common.DRIVERS_AVAILABLE = {'cassandra': {
            'default_connection_string': 'connect://cassandra'}}
        common.get_driver(name="cassandra")
        mock_import.assert_called_once_with('cassandra')
        mock_class.assert_called_with(connection_string='connect://cassandra')

    @mock.patch.object(common.os, 'environ')
    @mock.patch.object(common.utils, 'is_simulation')
    @mock.patch.object(common.utils, 'import_class')
    def test_use_simulation_db_if_given_simulation_dep_id(self,
                                                          mock_import,
                                                          mock_is_sim,
                                                          mock_env):
        mock_class = mock.Mock()
        mock_import.return_value = mock_class
        mock_env.get.return_value = "simulations"
        mock_is_sim.return_value = True

        common.get_driver(dep_id="123")
        mock_env.get.assert_called_with(
            'CHECKMATE_SIMULATOR_CONNECTION_STRING')

    @mock.patch.object(common.os, 'environ')
    @mock.patch.object(common.utils, 'is_simulation')
    @mock.patch.object(common.utils, 'import_class')
    def test_dont_get_simulator_if_given_connection_string(self,
                                                           mock_import,
                                                           mock_is_sim,
                                                           mock_env):
        mock_class = mock.Mock()
        mock_import.return_value = mock_class
        mock_env.get.return_value = "simulations"
        mock_is_sim.return_value = True

        common.get_driver(dep_id="123", connection_string='mongodb://fake')
        assert not mock_env.get.called, \
            'Unexpected calls %s' % mock_env.get.call_args_list

    @mock.patch.object(common.os, 'environ')
    @mock.patch.object(common.utils, 'is_simulation')
    @mock.patch.object(common.utils, 'import_class')
    def test_dont_get_simulator_db_from_env_if_given_name(self,
                                                          mock_import,
                                                          mock_is_sim,
                                                          mock_env):
        mock_class = mock.Mock()
        mock_import.return_value = mock_class
        mock_env.get.return_value = "simulations"
        mock_is_sim.return_value = True

        common.get_driver(dep_id="123", name='a_driver')
        self.assertEqual([mock.call('CHECKMATE_CONNECTION_STRING')],
                         mock_env.get.call_args_list)

    @mock.patch.object(common.os, 'environ')
    @mock.patch.object(common.utils, 'import_class')
    def test_dont_get_simulator_db_from_env_if_no_dep_id(self,
                                                         mock_import,
                                                         mock_env):
        mock_class = mock.Mock()
        mock_import.return_value = mock_class
        mock_env.get.return_value = "simulations"

        common.get_driver()
        self.assertEqual([mock.call('CHECKMATE_CONNECTION_STRING')],
                         mock_env.get.call_args_list)

    @mock.patch.object(common.os, 'environ')
    @mock.patch.object(common.utils, 'is_simulation')
    @mock.patch.object(common.utils, 'import_class')
    def test_dont_get_simulator_db_if_deploy_is_not_a_sim(self,
                                                          mock_import,
                                                          mock_is_sim,
                                                          mock_env):
        mock_class = mock.Mock()
        mock_import.return_value = mock_class
        mock_env.get.return_value = "simulations"
        mock_is_sim.return_value = False

        common.get_driver(dep_id='123')
        self.assertEqual([mock.call('CHECKMATE_CONNECTION_STRING')],
                         mock_env.get.call_args_list)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
