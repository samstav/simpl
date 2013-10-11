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
import os
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

    @mock.patch('__builtin__.file')
    def test_with_no_passed_in_keys(self, mock_file):
        os.path.exists = mock.Mock(side_effect=[False, False])
        os.chmod = mock.Mock()
        subprocess.check_output = mock.Mock(side_effect=[None,
                                                         "public_key_ssh"])
        file_handler = mock_file.return_value.__enter__.return_value
        expected = {
            'public_key_ssh': "public_key_ssh",
            'public_key_path': self.public_key_path,
            'private_key_path': self.private_key_path
        }
        result = self.env.create_environment_keys()

        self.assertDictEqual(result, expected)
        os.chmod.assert_called_once_with(self.private_key_path, 0o600)
        subprocess.check_output.assert_any_call(
            ['openssl', 'genrsa', '-out', self.private_key_path, '2048'])
        subprocess.check_output.assert_any_call(
            ['ssh-keygen', '-y', '-f', self.private_key_path])
        mock_file.assert_called_once_with(self.public_key_path, 'w')
        file_handler.write.assert_called_once_with("public_key_ssh")

    @mock.patch('__builtin__.file')
    def test_with_both_keys_passed_in(self, mock_file):
        os.path.exists = mock.Mock(side_effect=[False, False])
        os.chmod = mock.Mock()
        subprocess.check_output = mock.Mock()
        file_handler = mock_file.return_value.__enter__.return_value
        expected = {
            'public_key_ssh': "public_key",
            'public_key_path': self.public_key_path,
            'private_key_path': self.private_key_path
        }
        result = self.env.create_environment_keys(private_key="private_key",
                                                  public_key_ssh="public_key")

        self.assertDictEqual(result, expected)
        os.chmod.assert_called_once_with(self.private_key_path, 0o600)
        self.assertFalse(subprocess.check_output.called)
        mock_file.assert_any_call(self.private_key_path, 'w')
        mock_file.assert_any_call(self.public_key_path, 'w')
        file_handler.write.assert_any_call("private_key")
        file_handler.write.assert_any_call("public_key")

    @mock.patch('__builtin__.file')
    def test_for_existing_passed_in_keys(self, mock_file):
        os.path.exists = mock.Mock(side_effect=[True, True])
        os.chmod = mock.Mock()
        subprocess.check_output = mock.Mock()
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
        os.chmod.assert_called_once_with(self.private_key_path, 0o600)
        self.assertFalse(subprocess.check_output.called)
        mock_file.assert_any_call(self.private_key_path, 'r')
        mock_file.assert_any_call(self.public_key_path, 'r')
        self.assertTrue(file_handler.read.called)
        file_handler.read.assert_has_calls([mock.call(), mock.call()])

    @mock.patch('__builtin__.file')
    def test_private_key_data_mismatch(self, mock_file):
        os.path.exists = mock.Mock(side_effect=[True, True])
        os.chmod = mock.Mock()
        subprocess.check_output = mock.Mock()
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

    def test_existing_node_files(self):
        nodes_path = "%s/nodes" % self.kitchen_path
        os.path.exists = mock.Mock(side_effect=[True, True])
        os.listdir = mock.Mock(return_value=["foo.json"])
        expected = {"kitchen": self.kitchen_path}
        result = self.env.create_kitchen(self.kitchen_name)
        self.assertDictEqual(result, expected)
        os.path.exists.assert_any_call(self.kitchen_path)
        os.path.exists.assert_any_call(nodes_path)
        os.listdir.assert_called_once_with(nodes_path)

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
                     mock_cache_update, mock_copy_contents, mock_cache_path):
        nodes_path = "%s/nodes" % self.kitchen_path
        bootstrap_path = "%s/bootstrap.json" % self.kitchen_path
        certs_path = "%s/certificates" % self.kitchen_path
        knife_file_path = "%s/knife.rb" % self.kitchen_path
        secret_key_path = "secret_key_path"
        source_repo = "http://foo.git"

        os.path.exists = mock.Mock(side_effect=[False, False, False, False,
                                                False, False])
        os.mkdir = mock.Mock()
        os.link = mock.Mock()
        file_handle = mock_file.return_value.__enter__.return_value
        mock_write_solo_config.return_value = secret_key_path
        Random.atfork = mock.Mock()
        RSA.generate = mock.Mock()
        RSA.generate.return_value.exportKey.return_value = "secret_key"
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
        os.mkdir.assert_has_calls(mkdir_calls)
        os.path.exists.assert_has_calls(path_exists_calls)
        mock_file.assert_any_call(bootstrap_path, 'w')
        mock_file.assert_any_call(secret_key_path, 'w')
        mock_dump.assert_called_once_with({
            "run_list": ["recipe[build-essential]"]
        }, file_handle)
        self.assertTrue(Random.atfork.called)
        RSA.generate.assert_called_once_with(2048)
        RSA.generate.return_value.exportKey.assert_called_once_with('PEM')
        file_handle.write.assert_called_once_with("secret_key")
        os.link.assert_called_once_with(mock_solo_config, knife_file_path)
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

    def test_success(self):
        shutil.rmtree = mock.Mock()
        os.path.exists = mock.Mock(return_value=True)
        self.env.delete_cookbooks()
        shutil.rmtree.assert_called_once_with(
            "/var/local/checkmate/DEP_ID/kitchen/cookbooks")

    def test_missing_cookbook_config(self):
        shutil.rmtree = mock.Mock()
        os.path.exists = mock.Mock(side_effect=[False, False])
        self.env.delete_cookbooks()
        self.assertFalse(shutil.rmtree.called)

    def test_dir_not_found_exc_handling(self):
        os_error = OSError()
        os_error.errno = errno.ENOENT
        shutil.rmtree = mock.Mock(side_effect=os_error)
        os.path.exists = mock.Mock(return_value=True)
        self.env.delete_cookbooks()
        shutil.rmtree.assert_called_once_with(
            "/var/local/checkmate/DEP_ID/kitchen/cookbooks")

    def test_os_error_exc_handling(self):
        shutil.rmtree = mock.Mock(side_effect=OSError())
        os.path.exists = mock.Mock(return_value=True)
        self.assertRaises(exceptions.CheckmateException,
                          self.env.delete_cookbooks)
        shutil.rmtree.assert_called_once_with(
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

    def test_success(self):
        shutil.rmtree = mock.Mock()
        self.env.delete()
        shutil.rmtree.assert_called_once_with("/var/local/checkmate/DEP_ID")

    def test_dir_not_found_exc_handling(self):
        os_error = OSError()
        os_error.errno = errno.ENOENT
        shutil.rmtree = mock.Mock(side_effect=os_error)
        self.env.delete()
        shutil.rmtree.assert_called_once_with("/var/local/checkmate/DEP_ID")

    def test_os_error_exc_handling(self):
        shutil.rmtree = mock.Mock(side_effect=OSError())
        self.assertRaises(exceptions.CheckmateException,
                          self.env.delete)
        shutil.rmtree.assert_called_once_with("/var/local/checkmate/DEP_ID")
