# pylint: disable=C0103,R0801
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
"""Test Chef Environment domain object."""
import errno
import json
import shutil
import subprocess

from Crypto.PublicKey import RSA
from Crypto import Random
import mock
import unittest

from checkmate import exceptions, utils
from checkmate.providers.opscode.solo.blueprint_cache import BlueprintCache
from checkmate.providers.opscode.solo.chef_environment import ChefEnvironment
from checkmate.providers.opscode.solo.knife import Knife


class TestCreateEnvironmentKeys(unittest.TestCase):
    def setUp(self):
        self.path = "/tmp"
        self.env_name = "DEP_ID"
        self.private_key_path = "%s/%s/private.pem" % (self.path,
                                                       self.env_name)
        self.public_key_path = "%s/%s/checkmate.pub" % (self.path,
                                                        self.env_name)
        self.env = ChefEnvironment(self.env_name, self.path)

    @mock.patch('subprocess.check_output')
    @mock.patch('os.chmod')
    @mock.patch('os.path.exists')
    @mock.patch('__builtin__.file')
    def test_with_no_passed_in_keys(self, mock_file, mock_path_exists,
                                    mock_chmod, mock_check_output):
        mock_path_exists.side_effect = [False, False]
        mock_check_output.side_effect = [None, "public_key_ssh"]
        file_handler = mock_file.return_value.__enter__.return_value
        expected = {
            'public_key_ssh': "public_key_ssh",
            'public_key_path': self.public_key_path,
            'private_key_path': self.private_key_path
        }
        result = self.env.create_environment_keys()

        self.assertDictEqual(result, expected)
        mock_chmod.assert_called_once_with(self.private_key_path, 0o600)
        subprocess.check_output.assert_any_call(
            ['openssl', 'genrsa', '-out', self.private_key_path, '2048'])
        mock_check_output.assert_any_call(
            ['ssh-keygen', '-y', '-f', self.private_key_path])
        mock_file.assert_called_once_with(self.public_key_path, 'w')
        file_handler.write.assert_called_once_with("public_key_ssh")

    @mock.patch('subprocess.check_output')
    @mock.patch('os.chmod')
    @mock.patch('os.path.exists')
    @mock.patch('__builtin__.file')
    def test_with_both_keys_passed_in(self, mock_file, mock_path_exists,
                                      mock_chmod, mock_check_output):
        mock_path_exists.side_effect = [False, False]
        file_handler = mock_file.return_value.__enter__.return_value
        expected = {
            'public_key_ssh': "public_key",
            'public_key_path': self.public_key_path,
            'private_key_path': self.private_key_path
        }
        result = self.env.create_environment_keys(private_key="private_key",
                                                  public_key_ssh="public_key")

        self.assertDictEqual(result, expected)
        mock_chmod.assert_called_once_with(self.private_key_path, 0o600)
        self.assertFalse(mock_check_output.called)
        mock_file.assert_any_call(self.private_key_path, 'w')
        mock_file.assert_any_call(self.public_key_path, 'w')
        file_handler.write.assert_any_call("private_key")
        file_handler.write.assert_any_call("public_key")

    @mock.patch('subprocess.check_output')
    @mock.patch('os.chmod')
    @mock.patch('os.path.exists')
    @mock.patch('__builtin__.file')
    def test_for_existing_passed_in_keys(self, mock_file, mock_path_exists,
                                         mock_chmod, mock_check_output):
        mock_path_exists.side_effect = [True, True]
        file_handler = mock_file.return_value.__enter__.return_value
        file_handler.read.side_effect = ["private_key", "public_key_ssh"]
        expected = {
            'public_key_ssh': "public_key_ssh",
            'public_key_path': self.public_key_path,
            'private_key_path': self.private_key_path
        }
        result = self.env.create_environment_keys(private_key="private_key",
                                                  public_key_ssh="public_key")

        self.assertDictEqual(result, expected)
        mock_chmod.assert_called_once_with(self.private_key_path, 0o600)
        self.assertFalse(mock_check_output.called)
        mock_file.assert_any_call(self.private_key_path, 'r')
        mock_file.assert_any_call(self.public_key_path, 'r')
        self.assertTrue(file_handler.read.called)
        file_handler.read.assert_has_calls([mock.call(), mock.call()])

    @mock.patch('os.path.exists')
    @mock.patch('__builtin__.file')
    def test_private_key_data_mismatch(self, mock_file, mock_path_exists):
        mock_path_exists.side_effect = [True, True]
        file_handler = mock_file.return_value.__enter__.return_value
        file_handler.read.return_value = "unexpected"

        self.assertRaises(exceptions.CheckmateException,
                          self.env.create_environment_keys,
                          private_key="private_key")


class TestCreateKitchen(unittest.TestCase):
    def setUp(self):
        self.path = "/tmp"
        self.env_name = "DEP_ID"
        self.kitchen_name = "kitchen"
        self.kitchen_path = "%s/%s/%s" % (self.path, self.env_name,
                                          self.kitchen_name)
        self.env = ChefEnvironment(self.env_name, self.path)

    @mock.patch('os.listdir')
    @mock.patch('os.path.exists')
    def test_existing_node_files(self, mock_path_exists, mock_list_dir):
        nodes_path = "%s/nodes" % self.kitchen_path
        mock_path_exists.side_effect = [True, True]
        mock_list_dir.return_value = ["foo.json"]
        expected = {"kitchen": self.kitchen_path}
        result = self.env.create_kitchen(self.kitchen_name)
        self.assertDictEqual(result, expected)
        mock_path_exists.assert_any_call(self.kitchen_path)
        mock_path_exists.assert_any_call(nodes_path)
        mock_list_dir.assert_called_once_with(nodes_path)

    @mock.patch.object(RSA, 'generate')
    @mock.patch.object(Random, 'atfork')
    @mock.patch('os.link')
    @mock.patch('os.mkdir')
    @mock.patch('os.path.exists')
    @mock.patch.object(BlueprintCache, 'cache_path')
    @mock.patch.object(utils, 'copy_contents')
    @mock.patch.object(BlueprintCache, 'update')
    @mock.patch.object(Knife, 'solo_config_path')
    @mock.patch.object(json, 'dump')
    @mock.patch('__builtin__.file')
    @mock.patch.object(Knife, 'write_solo_config')
    @mock.patch.object(Knife, 'init_solo')
    def test_success(self, mock_init_solo, mock_write_solo_config,
                     mock_file, mock_dump, mock_solo_config,
                     mock_cache_update, mock_copy_contents, mock_cache_path,
                     mock_path_exists, mock_mkdir, mock_link, mock_fork,
                     mock_rsa_generate):
        nodes_path = "%s/nodes" % self.kitchen_path
        bootstrap_path = "%s/bootstrap.json" % self.kitchen_path
        certs_path = "%s/certificates" % self.kitchen_path
        knife_file_path = "%s/knife.rb" % self.kitchen_path
        secret_key_path = "secret_key_path"
        source_repo = "http://foo.git"

        mock_path_exists.side_effect = [False, False, False, False, False,
                                        False]
        file_handle = mock_file.return_value.__enter__.return_value
        mock_write_solo_config.return_value = secret_key_path
        mock_rsa_generate.return_value.exportKey.return_value = "secret_key"
        expected = {"kitchen": self.kitchen_path}

        result = self.env.create_kitchen(source_repo=source_repo)

        self.assertDictEqual(result, expected)
        self.assertTrue(mock_init_solo.called)
        self.assertTrue(mock_write_solo_config.called)
        mkdir_calls = [
            mock.call(self.kitchen_path, 0o770),
            mock.call(certs_path, 0o770),
        ]
        path_exists_calls = [
            mock.call(self.kitchen_path),
            mock.call(nodes_path),
            mock.call(bootstrap_path),
            mock.call(certs_path),
            mock.call(secret_key_path),
            mock.call(knife_file_path),
        ]
        mock_mkdir.assert_has_calls(mkdir_calls)
        mock_path_exists.assert_has_calls(path_exists_calls)
        mock_file.assert_any_call(bootstrap_path, 'w')
        mock_file.assert_any_call(secret_key_path, 'w')
        mock_dump.assert_called_once_with({
            "run_list": ["recipe[build-essential]"]
        }, file_handle)
        self.assertTrue(Random.atfork.called)
        mock_rsa_generate.assert_called_once_with(2048)
        mock_rsa_generate.return_value.exportKey.assert_called_once_with('PEM')
        file_handle.write.assert_called_once_with("secret_key")
        mock_link.assert_called_once_with(mock_solo_config, knife_file_path)
        self.assertTrue(mock_cache_update.called)
        mock_copy_contents.assert_called_once_with(mock_cache_path,
                                                   self.kitchen_path,
                                                   with_overwrite=True,
                                                   create_path=True)


class TestDeleteCookbooks(unittest.TestCase):
    def setUp(self):
        self.path = "/var/local/checkmate"
        self.env_name = "DEP_ID"
        self.kitchen_name = "kitchen"
        self.kitchen_path = "%s/%s/%s" % (self.path, self.env_name,
                                          self.kitchen_name)
        self.env = ChefEnvironment(self.env_name, self.path,
                                   kitchen_name=self.kitchen_name)

    @mock.patch('os.path.exists')
    def test_success(self, mock_path_exists):
        shutil.rmtree = mock.Mock()
        mock_path_exists.return_value = True
        self.env.delete_cookbooks()
        shutil.rmtree.assert_called_once_with(
            "/var/local/checkmate/DEP_ID/kitchen/cookbooks")

    @mock.patch('os.path.exists')
    @mock.patch('shutil.rmtree')
    def test_missing_cookbook_config(self, mock_rmtree, mock_path_exists):
        mock_path_exists.side_effect = [False, False]
        self.env.delete_cookbooks()
        self.assertFalse(mock_rmtree.called)

    @mock.patch('os.path.exists')
    @mock.patch('shutil.rmtree')
    def test_dir_not_found_exc_handling(self, mock_rmtree, mock_path_exists):
        os_error = OSError()
        os_error.errno = errno.ENOENT
        mock_rmtree.side_effect = os_error
        mock_path_exists.return_value = True
        self.env.delete_cookbooks()
        mock_rmtree.assert_called_once_with(
            "/var/local/checkmate/DEP_ID/kitchen/cookbooks")

    @mock.patch('os.path.exists')
    @mock.patch('shutil.rmtree')
    def test_os_error_exc_handling(self, mock_rmtree, mock_path_exists):
        mock_rmtree.side_effect = OSError()
        mock_path_exists.return_value = True
        self.assertRaises(exceptions.CheckmateException,
                          self.env.delete_cookbooks)
        mock_rmtree.assert_called_once_with(
            "/var/local/checkmate/DEP_ID/kitchen/cookbooks")


class TestDeleteEnvironment(unittest.TestCase):
    def setUp(self):
        self.path = "/var/local/checkmate"
        self.env_name = "DEP_ID"
        self.kitchen_name = "kitchen"
        self.kitchen_path = "%s/%s/%s" % (self.path, self.env_name,
                                          self.kitchen_name)
        self.env = ChefEnvironment(self.env_name, self.path,
                                   kitchen_name=self.kitchen_name)

    @mock.patch('shutil.rmtree')
    def test_success(self, mock_rmtree):
        self.env.delete()
        mock_rmtree.assert_called_once_with("/var/local/checkmate/DEP_ID")

    @mock.patch('shutil.rmtree')
    def test_dir_not_found_exc_handling(self, mock_rmtree):
        os_error = OSError()
        os_error.errno = errno.ENOENT
        mock_rmtree.side_effect = os_error
        self.env.delete()
        mock_rmtree.assert_called_once_with("/var/local/checkmate/DEP_ID")

    @mock.patch('shutil.rmtree')
    def test_os_error_exc_handling(self, mock_rmtree):
        mock_rmtree.side_effect = OSError()
        self.assertRaises(exceptions.CheckmateException,
                          self.env.delete)
        mock_rmtree.assert_called_once_with("/var/local/checkmate/DEP_ID")


class TestFetchCookbooks(unittest.TestCase):
    def setUp(self):
        self.path = "/var/local/checkmate"
        self.env_name = "DEP_ID"
        self.kitchen_name = "kitchen"
        self.kitchen_path = "%s/%s/%s" % (self.path, self.env_name,
                                          self.kitchen_name)
        self.env = ChefEnvironment(self.env_name, self.path,
                                   kitchen_name=self.kitchen_name)

    @mock.patch('checkmate.utils.run_ruby_command')
    @mock.patch('os.path.exists')
    def test_fetch_with_chef_file(self, mock_path_exists, mock_run_command):
        mock_path_exists.side_effect = [False, True]

        self.env.fetch_cookbooks()

        path_exists_call = [
            mock.call("%s/Berksfile" % self.kitchen_path),
            mock.call("%s/Cheffile" % self.kitchen_path),
        ]
        mock_path_exists.assert_has_calls(path_exists_call)
        mock_run_command.assert_called_once_with(self.kitchen_path,
                                                 'librarian-chef',
                                                 ['install'], lock=True)

    @mock.patch.object(ChefEnvironment, '_ensure_berkshelf_environment')
    @mock.patch('checkmate.utils.run_ruby_command')
    @mock.patch('os.path.exists')
    def test_fetch_with_berks_file(self, mock_path_exists, mock_run_command,
                                   mock_ensure_env):
        mock_path_exists.return_value = True

        self.env.fetch_cookbooks()

        mock_path_exists.assert_called_once_with("%s/Berksfile" %
                                                 self.kitchen_path)
        mock_run_command.assert_called_once_with(self.kitchen_path,
                                                 'berks',
                                                 ['install', '--path',
                                                  "%s/cookbooks" %
                                                  self.kitchen_path],
                                                 lock=True)
        self.assertTrue(mock_ensure_env.called)
