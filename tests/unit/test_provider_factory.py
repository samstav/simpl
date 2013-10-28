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
# pylint: disable=R0903,C0111,W0613,R0904

import mock
import unittest

from checkmate import workflow_spec as wfspec


class TestProviderFactory(unittest.TestCase):

    def test_get_provider_for_resource(self):
        deployment = mock.MagicMock()
        environment = mock.MagicMock()
        expected_provider = mock.MagicMock()

        environment.get_provider.return_value = expected_provider
        deployment.get_non_deleted_resources.return_value = {
            "1": {
                "provider": "nova"
            }
        }

        factory = wfspec.ProviderFactory(deployment, environment)
        actual_provider = factory.get_provider({"provider": "nova"})
        environment.get_provider.assert_called_once_with("nova")
        self.assertEqual(actual_provider, expected_provider)

    def test_get_all_provider_keys(self):
        deployment = mock.MagicMock()
        environment = mock.MagicMock()
        expected_provider1 = mock.MagicMock()
        expected_provider2 = mock.MagicMock()

        def return_providers(*args, **kwargs):
            if args[0] == "provider1":
                return expected_provider1
            if args[0] == "provider2":
                return expected_provider2
            self.fail("Unexpected argument!")

        environment.get_provider.side_effect = return_providers

        deployment.get_non_deleted_resources.return_value = {
            "1": {
                "provider": "provider1"
            },
            "2": {
                "provider": "provider2"
            },
            "connections": {},
            "keys": {}
        }

        factory = wfspec.ProviderFactory(deployment, environment)
        all_providers = factory.get_all_providers()

        environment.get_provider.assert_any_call("provider1")
        environment.get_provider.assert_any_call("provider2")
        self.assertEqual(2, environment.get_provider.call_count)
        self.assertDictEqual(
            {"provider1": expected_provider1,
             "provider2": expected_provider2},
            all_providers)
