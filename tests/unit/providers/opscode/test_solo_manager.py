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
import shutil

import mock
import unittest

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

    @mock.patch.object(ChefEnvironment, 'fetch_cookbooks')
    @mock.patch.object(ChefEnvironment, 'create_kitchen')
    @mock.patch.object(ChefEnvironment, 'create_environment_keys')
    @mock.patch.object(ChefEnvironment, 'create_env_dir')
    def test_success(self, mock_create_env, mock_create_keys,
                     mock_create_kitchen, mock_fetch_cookbooks):
        mock_create_keys.return_value = {
            'public_key': '1234'
        }
        mock_create_kitchen.return_value = {
            'kitchen_path': '/tmp'
        }
        shutil.copy = mock.Mock()

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
        shutil.copy.assert_called_once_with(
            "/tmp/DEP_ID/checkmate.pub",
            "/tmp/DEP_ID/kitchen/certificates/checkmate-environment.pub")
        self.assertTrue(mock_fetch_cookbooks.called)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
