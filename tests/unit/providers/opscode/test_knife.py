# pylint: disable=C0103,R0904,W0201
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
"""Test knife_solo.py"""
import mock
import unittest

from checkmate import exceptions
from checkmate.providers.opscode.solo.knife_solo import KnifeSolo


class TestKnife(unittest.TestCase):
    def setUp(self):
        self.kitchen_path = "/tmp/dep/kitchen"
        self.knife = KnifeSolo(self.kitchen_path)

    @mock.patch('os.path.exists')
    @mock.patch('checkmate.utils.run_ruby_command')
    def test_run_command(self, mock_run, mock_path_exists):
        mock_path_exists.return_value = True
        mock_run.return_value = "foo\nbar"

        result = self.knife.run_command(['knife', 'test'])

        self.assertEqual(result, mock_run.return_value)
        mock_path_exists.assert_called_once_with("%s/solo.rb" %
                                                 self.kitchen_path)
        mock_run.assert_called_once_with(
            self.kitchen_path, 'knife',
            ['test', '-c', "%s/solo.rb" % self.kitchen_path], lock=True)

    @mock.patch('os.path.exists')
    @mock.patch('checkmate.utils.run_ruby_command')
    def test_run_command_error_handling(self, mock_run, mock_path_exists):
        mock_path_exists.return_value = True
        mock_run.return_value = "ERROR:KnifeSolo::::Error:KnifeError\nbar"

        self.assertRaises(exceptions.CheckmateCalledProcessError,
                          self.knife.run_command, ['knife', 'test'])

        mock_path_exists.assert_called_once_with("%s/solo.rb" %
                                                 self.kitchen_path)
        mock_run.assert_called_once_with(
            self.kitchen_path, 'knife',
            ['test', '-c', "%s/solo.rb" % self.kitchen_path], lock=True)

    def test_init_solo(self):
        self.knife.run_command = mock.Mock()
        self.knife.init()
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'init', '.'])

    @mock.patch('__builtin__.file')
    def test_write_solo_config(self, mock_file):
        file_handle = mock_file.return_value.__enter__.return_value
        expected_config = """# knife -c knife.rb
    file_cache_path  "%s"
    cookbook_path    ["%s/cookbooks", "%s/site-cookbooks"]
    role_path  "%s/roles"
    data_bag_path  "%s/data_bags"
    log_level        :info
    log_location     "%s/knife-solo.log"
    verbose_logging  true
    ssl_verify_mode  :verify_none
    encrypted_data_bag_secret "%s/certificates/chef.pem"
    """ % (self.kitchen_path, self.kitchen_path, self.kitchen_path,
           self.kitchen_path, self.kitchen_path, self.kitchen_path,
           self.kitchen_path)
        result = self.knife.write_config()

        self.assertEqual(result,
                         "%s/certificates/chef.pem" % self.kitchen_path)
        file_handle.write.assert_called_once_with(expected_config)

    @mock.patch('os.path.exists')
    def test_prepare_solo_success(self, mock_path_exists):
        mock_path_exists.return_value = False
        self.knife.run_command = mock.Mock()
        self.knife.prepare("1.1.1.1", password="password",
                           omnibus_version="0.1",
                           identity_file="identity_file")
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'prepare', 'root@1.1.1.1', '-c',
             "%s/solo.rb" % self.kitchen_path, '-P', 'password',
             '--omnibus-version', '0.1', '-i', 'identity_file'])
        mock_path_exists.assert_called_once_with("%s/nodes/1.1.1.1.json" %
                                                 self.kitchen_path)

    @mock.patch('os.path.exists')
    def test_prep_solo_registered_node(self, mock_path_exists):
        mock_path_exists.return_value = True
        self.knife.run_command = mock.Mock()
        self.knife.prepare("1.1.1.1")
        self.assertFalse(self.knife.run_command.called)
        mock_path_exists.assert_called_once_with("%s/nodes/1.1.1.1.json" %
                                                 self.kitchen_path)

    def test_get_data_bags(self):
        self.knife.run_command = mock.Mock(return_value='{"foo": "bar"}')

        results = self.knife.get_data_bags()

        self.assertDictEqual(results, {'foo': 'bar'})
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'data', 'bag', 'list', '-F', 'json', '-c',
             self.knife.config_path])

    def test_get_empty_data_bags(self):
        self.knife.run_command = mock.Mock(return_value=None)

        results = self.knife.get_data_bags()

        self.assertDictEqual(results, {})
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'data', 'bag', 'list', '-F', 'json', '-c',
             self.knife.config_path])

    def test_get_data_bag(self):
        self.knife.run_command = mock.Mock(return_value='{"foo": "bar"}')

        results = self.knife.get_data_bag("web")

        self.assertDictEqual(results, {'foo': 'bar'})
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'data', 'bag', 'show', 'web', '-F', 'json', '-c',
             self.knife.config_path])

    def test_get_empty_data_bag(self):
        self.knife.run_command = mock.Mock(return_value=None)

        results = self.knife.get_data_bag("web")

        self.assertDictEqual(results, {})
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'data', 'bag', 'show', 'web', '-F', 'json', '-c',
             self.knife.config_path])

    def test_get_data_bag_item(self):
        self.knife.run_command = mock.Mock(return_value='{"foo": "bar"}')

        results = self.knife.get_data_bag_item("web", "server", "secret_file")

        self.assertDictEqual(results, {'foo': 'bar'})
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'data', 'bag', 'show', 'web', 'server', '-F',
             'json', '-c', self.knife.config_path, '--secret-file',
             'secret_file'])

    def test_get_empty_data_bag_item(self):
        self.knife.run_command = mock.Mock(return_value=None)

        results = self.knife.get_data_bag_item("web", "server")

        self.assertDictEqual(results, {})
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'data', 'bag', 'show', 'web', 'server', '-F',
             'json', '-c', self.knife.config_path])

    def test_create_data_bag(self):
        self.knife.get_data_bags = mock.Mock(return_value={})
        self.knife.run_command = mock.Mock(return_value=None)

        self.knife.create_data_bag("web")

        self.assertTrue(self.knife.get_data_bags.called)
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'data', 'bag', 'create', 'web', '-c',
             self.knife.config_path])

    def test_create_for_existing_data_bag(self):
        self.knife.get_data_bags = mock.Mock(return_value={"web": {}})
        self.knife.run_command = mock.Mock(return_value=None)

        self.knife.create_data_bag("web")

        self.assertTrue(self.knife.get_data_bags.called)
        self.assertFalse(self.knife.run_command.called)

    def test_create_data_bag_item(self):
        self.knife.get_data_bag = mock.Mock(return_value={})
        self.knife.run_command = mock.Mock()

        self.knife.create_data_bag_item("web", "server", {"foo": "bar"},
                                        "secret_file")

        self.knife.get_data_bag.assert_called_once_with("web")
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'data', 'bag', 'create', "web", "server",
             '-d', '-c', self.knife.config_path, '--json',
             '{"foo": "bar", "id": "server"}', '--secret-file', 'secret_file']
        )

    def test_create_existing_data_bag_item(self):
        self.knife.get_data_bag = mock.Mock(return_value={'server': {}})
        self.knife.get_data_bag_item = mock.Mock(return_value={'item': 'data'})
        self.knife.run_command = mock.Mock()

        self.knife.create_data_bag_item("web", "server", {"foo": "bar"},
                                        "secret_file")

        self.knife.get_data_bag.assert_called_once_with("web")
        self.knife.get_data_bag_item.assert_called_once_with(
            "web", "server", secret_file="secret_file")
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'data', 'bag', 'create', "web", "server",
             '-d', '-c', self.knife.config_path, '--json',
             '{"item": "data", "foo": "bar", "id": "server"}',
             '--secret-file', 'secret_file']
        )

    def test_create_data_bag_with_id(self):
        self.knife.get_data_bag = mock.Mock(return_value={'server': {}})
        self.knife.get_data_bag_item = mock.Mock(return_value={'item': 'data'})

        self.assertRaises(exceptions.CheckmateException,
                          self.knife.create_data_bag_item, "web", "server",
                          {"foo": "bar", "id": "xyz"}, "secret_file")

        self.knife.get_data_bag.assert_called_once_with("web")
        self.knife.get_data_bag_item.assert_called_once_with(
            "web", "server", secret_file="secret_file")

    def test_cook(self):
        self.knife.run_command = mock.Mock()
        self.knife.cook("1.1.1.1", username="foo", password="password",
                        identity_file="identity", port=20,
                        run_list=['list'], attributes={"foo": "bar"})
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'cook', 'foo@1.1.1.1', '-c',
             self.knife.config_path, '-i', 'identity', '-P', 'password',
             '-p', '20']
        )

    def test_cook_with_no_attribs(self):
        self.knife.run_command = mock.Mock()
        self.knife.cook("1.1.1.1", username="foo", password="password",
                        identity_file="identity", port=20)
        self.knife.run_command.assert_called_once_with(
            ['knife', 'solo', 'cook', 'foo@1.1.1.1', '-c',
             self.knife.config_path, 'bootstrap.json', '-i', 'identity',
             '-P', 'password', '-p', '20']
        )


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    test.run_with_params()
