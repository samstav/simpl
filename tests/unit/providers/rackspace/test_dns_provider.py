# pylint: disable=W0212,R0904
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
"""
Module for testing DNS provider.
"""
import mock
import unittest

from checkmate.providers.rackspace import dns


class TestGetResources(unittest.TestCase):
    """Class to test get_resources function."""

    @mock.patch.object(dns.provider.Provider, 'connect')
    def test_get_resource(self, mock_connect):
        """Verifies returned results."""
        api = mock.Mock()
        dom1 = mock.Mock()
        dom1._info = {'name': 'test1'}
        dom2 = mock.Mock()
        dom2._info = {'name': 'test2'}
        api.list.return_value = [dom1, dom2]
        mock_connect.return_value = api
        expected = [{'name': 'test1'}, {'name': 'test2'}]

        results = dns.provider.Provider.get_resources({})
        self.assertEqual(results, expected)
