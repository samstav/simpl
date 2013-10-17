# pylint: disable=R0201,R0904
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
"""Tests for solo manager."""
import subprocess

import mock
import unittest

from checkmate import exceptions
from checkmate.providers.opscode.solo.chef_environment import ChefEnvironment
from checkmate.providers.opscode.solo.manager import Manager


class TestCreateEnvironment(unittest.TestCase):
    def test_sim(self):
        expected = {
            'environment': '/var/tmp/name/',
            'kitchen': '/var/tmp/name/kitchen',
            'private_key_path': '/var/tmp/name/private.pem',
            'public_key_path': '/var/tmp/name/checkmate.pub',
        }
        results = Manager.create_environment("name", "service_name",
                                             simulation=True)
        self.assertEqual(results, expected)

    @mock.patch('shutil.copy')
    @mock.patch.object(ChefEnvironment, 'fetch_cookbooks')
    @mock.patch.object(ChefEnvironment, 'create_kitchen')
    @mock.patch.object(ChefEnvironment, 'create_environment_keys')
    @mock.patch.object(ChefEnvironment, 'create_env_dir')
    def test_success(self, mock_create_env, mock_create_keys,
                     mock_create_kitchen, mock_fetch_cookbooks, mock_copy):
        mock_create_keys.return_value = {
            'public_key': '1234'
        }
        mock_create_kitchen.return_value = {
            'kitchen_path': '/tmp'
        }

        expected = {
            'environment': '/tmp/DEP_ID',
            'public_key': '1234',
            'kitchen_path': '/tmp'
        }
        results = Manager.create_environment("DEP_ID", "kitchen",
                                             path="/tmp",
                                             private_key="private_key",
                                             public_key_ssh="public_key_ssh",
                                             secret_key="secret_key",
                                             source_repo="source_repo")

        self.assertDictEqual(results, expected)

        self.assertTrue(mock_create_env.called)
        mock_create_keys.assert_called_once_with(
            private_key="private_key", public_key_ssh="public_key_ssh")
        mock_create_kitchen.assert_called_once_with(
            secret_key="secret_key", source_repo="source_repo")
        mock_copy.assert_called_once_with(
            "/tmp/DEP_ID/checkmate.pub",
            "/tmp/DEP_ID/kitchen/certificates/checkmate-environment.pub")
        self.assertTrue(mock_fetch_cookbooks.called)


class TestRegisterNode(unittest.TestCase):
    def test_sim(self):
        expected = {
            'instance:1': {
                'node-attributes': {
                    'run_list': [],
                    'foo': 'bar'
                },
                'status': 'BUILD'
            }
        }
        results = Manager.register_node({"resource_key": "1"}, "1.1.1.1",
                                        "DEP_ID", None,
                                        attributes={"foo": "bar"},
                                        simulate=True)
        self.assertDictEqual(results, expected)

    @mock.patch.object(ChefEnvironment, 'write_node_attributes')
    @mock.patch.object(ChefEnvironment, 'register_node')
    @mock.patch.object(ChefEnvironment, 'kitchen_path')
    @mock.patch('checkmate.ssh.remote_execute')
    def test_success(self, mock_ssh_execute, mock_kitchen_path,
                     mock_register_node, mock_write_attribs):
        expected_callback = {
            'instance:1': {
                'status': 'BUILD'
            }
        }
        mock_ssh_execute.side_effect = [None, {"stdout": "Chef: 11.1.1"}]
        mock_write_attribs.return_value = {"foo": "bar", "version": "1.1"}
        mock_callback = mock.Mock()
        expected = {
            'instance:1': {
                'node-attributes': {
                    'foo': 'bar',
                    'version': '1.1',
                }
            }
        }

        results = Manager.register_node({"resource_key": "1"}, "1.1.1.1",
                                        "DEP_ID", mock_callback,
                                        password="password",
                                        identity_file="identity_file",
                                        attributes={"foo": "bar"},
                                        omnibus_version="1.1")

        self.assertDictEqual(results, expected)
        mock_callback.assert_called_once_with(expected_callback)
        mock_register_node.assert_called_once_with(
            "1.1.1.1", password="password", omnibus_version="1.1",
            identity_file="identity_file")
        ssh_calls = [mock.call("1.1.1.1", "mkdir -p %s" % mock_kitchen_path,
                               "root", password="password",
                               identity_file="identity_file"),
                     mock.call("1.1.1.1", "knife -v", "root",
                               password="password",
                               identity_file="identity_file")]
        mock_ssh_execute.assert_has_calls(ssh_calls)

    @mock.patch.object(ChefEnvironment, 'register_node')
    @mock.patch.object(ChefEnvironment, 'kitchen_path')
    @mock.patch('checkmate.ssh.remote_execute')
    def test_called_process_error(self, mock_ssh_execute, mock_kitchen_path,
                                  mock_register_node):
        expected_callback = {
            'instance:1': {
                'status': 'BUILD'
            }
        }
        mock_register_node.side_effect = subprocess.CalledProcessError(
            500, "cmd")
        mock_callback = mock.Mock()

        self.assertRaises(exceptions.CheckmateException,
                          Manager.register_node, {"resource_key": "1"},
                          "1.1.1.1", "DEP_ID", mock_callback,
                          password="password",
                          identity_file="identity_file",
                          attributes={"foo": "bar"}, omnibus_version="1.1")

        mock_callback.assert_called_once_with(expected_callback)
        mock_register_node.assert_called_once_with(
            "1.1.1.1", password="password", omnibus_version="1.1",
            identity_file="identity_file")
        mock_ssh_execute.assert_called_once_with(
            "1.1.1.1", "mkdir -p %s" % mock_kitchen_path, "root",
            password="password", identity_file="identity_file")

    @mock.patch.object(ChefEnvironment, 'register_node')
    @mock.patch.object(ChefEnvironment, 'kitchen_path')
    @mock.patch('checkmate.ssh.remote_execute')
    def test_chef_install_failure(self, mock_ssh_execute, mock_kitchen_path,
                                  mock_register_node):
        expected_callback = {
            'instance:1': {
                'status': 'BUILD'
            }
        }
        mock_ssh_execute.side_effect = [None, {"stdout": "foo"}]
        mock_callback = mock.Mock()

        self.assertRaises(exceptions.CheckmateException,
                          Manager.register_node, {"resource_key": "1"},
                          "1.1.1.1", "DEP_ID", mock_callback,
                          password="password", identity_file="identity_file",
                          attributes={"foo": "bar"}, omnibus_version="1.1")

        mock_callback.assert_called_once_with(expected_callback)
        mock_register_node.assert_called_once_with(
            "1.1.1.1", password="password", omnibus_version="1.1",
            identity_file="identity_file")
        ssh_calls = [mock.call("1.1.1.1", "mkdir -p %s" % mock_kitchen_path,
                               "root", password="password",
                               identity_file="identity_file"),
                     mock.call("1.1.1.1", "knife -v", "root",
                               password="password",
                               identity_file="identity_file")]
        mock_ssh_execute.assert_has_calls(ssh_calls)


class TestManageRole(unittest.TestCase):
    def test_sim(self):
        self.assertIsNone(Manager.manage_role({'resource_key': '1'}, "web",
                                              "DEP_ID", None, simulate=True))

    @mock.patch.object(ChefEnvironment, 'write_role')
    @mock.patch.object(ChefEnvironment, 'ruby_role_exists')
    @mock.patch.object(ChefEnvironment, 'kitchen_path')
    @mock.patch('os.path.exists')
    def test_success(self, mock_path_exists, mock_kitchen_path,
                     mock_role_exists, mock_write_role):
        mock_callback = mock.Mock()
        mock_path_exists.return_value = True
        mock_role_exists.return_value = False
        mock_write_role.return_value = {'role': 'web'}
        expected = {
            'instance:1': {
                'roles': {
                    'web': {
                        'role': 'web'
                    }
                }
            }
        }

        results = Manager.manage_role({'resource_key': '1'}, "web",
                                      "DEP_ID", mock_callback, "path", "desc",
                                      "run_list", "attribs", "override",
                                      "env_run_lists")

        self.assertDictEqual(results, expected)
        mock_path_exists.assert_called_once_with(mock_kitchen_path)
        mock_role_exists.assert_called_once_with('web')
        mock_write_role.assert_called_once_with(
            'web', desc="desc", run_list="run_list",
            default_attributes="attribs", override_attributes="override",
            env_run_lists="env_run_lists")

    @mock.patch.object(ChefEnvironment, 'kitchen_path')
    @mock.patch('os.path.exists')
    def test_env_existence(self, mock_path_exists, mock_kitchen_path):
        mock_callback = mock.Mock()
        mock_path_exists.return_value = False

        self.assertRaises(exceptions.CheckmateException,
                          Manager.manage_role, {'resource_key': '1'}, "web",
                          "DEP_ID", mock_callback, "path", "desc",
                          "run_list", "attribs", "override", "env_run_lists")

        mock_path_exists.assert_called_once_with(mock_kitchen_path)

    @mock.patch.object(ChefEnvironment, 'ruby_role_exists')
    @mock.patch.object(ChefEnvironment, 'kitchen_path')
    @mock.patch('os.path.exists')
    def test_ruby_role_existence(self, mock_path_exists, mock_kitchen_path,
                                 mock_role_exists):
        mock_callback = mock.Mock()
        mock_path_exists.return_value = True
        mock_role_exists.return_value = True

        self.assertRaises(exceptions.CheckmateException,
                          Manager.manage_role, {'resource_key': '1'}, "web",
                          "DEP_ID", mock_callback, "path", "desc",
                          "run_list", "attribs", "override", "env_run_lists")

        mock_path_exists.assert_called_once_with(mock_kitchen_path)
        mock_role_exists.assert_called_once_with('web')
        mock_callback.assert_called_once_with({
            "instance:1": {
                "status": "ERROR",
                "error-message": "Encountered a chef role in Ruby. Only JSON"
                                 " roles can be manipulated by Checkmate: web"
            }
        })


class TestWriteDataBag(unittest.TestCase):
    def test_sim(self):
        expected = {
            'instance:1': {
                'data-bags': {
                    'web': {
                        'server': {
                            'foo': 'bar'
                        }
                    }
                }
            }
        }
        results = Manager.write_data_bag({'resource_key': '1'}, "DEP_ID",
                                         "web", "server", {"foo": "bar"},
                                         simulate=True)
        self.assertDictEqual(results, expected)

    def test_no_contents(self):
        results = Manager.write_data_bag({'resource_key': '1'}, "DEP_ID",
                                         "web", "server", None)
        self.assertIsNone(results)

    @mock.patch.object(ChefEnvironment, 'write_data_bag')
    def test_success(self, mock_write_bag):
        expected = {
            'instance:1': {
                'data-bags': {
                    'web': {
                        'server': {
                            'foo': 'bar'
                        }
                    }
                }
            }
        }
        results = Manager.write_data_bag({'resource_key': '1'}, "DEP_ID",
                                         "web", "server", {"foo": "bar"},
                                         path="path", kitchen_name="kitchen",
                                         secret_file="secret")
        self.assertDictEqual(results, expected)
        mock_write_bag.assert_called_once_with("web", "server",
                                               {"foo": "bar"},
                                               secret_file="secret")

if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
