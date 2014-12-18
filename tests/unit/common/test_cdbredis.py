# pylint: disable=C0103,R0201,R0904,W0212,W0613

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

"""Unit Tests for Cloud Database Redis instance management."""

import json
import unittest

import mock

from checkmate.common import cdbredis


class TestCreateRedisInstance(unittest.TestCase):
    """Exercise Redis Instance Creation."""
    def test_region_cannot_be_none(self):
        """Region cannot be None."""
        with self.assertRaises(AssertionError) as expected:
            cdbredis.create_instance(None, '825642', 'VALID', 'name', 101)
        self.assertEqual('Region must be a string', str(expected.exception))

    def test_region_must_be_valid(self):
        """Region must be a valid region (e.g. 'ORD')."""
        with self.assertRaises(AssertionError) as expected:
            cdbredis.create_instance('ARN', '825642', 'VALID', 'name', 101)
        self.assertEqual('Must be a valid region (e.g. ORD)',
                         str(expected.exception))

    def test_t_id_is_not_a_str(self):
        """t_id must be a string."""
        with self.assertRaises(AssertionError) as expected:
            cdbredis.create_instance('IAD', 825642, 'VALID', 'name', 101)
        self.assertEqual('t_id must be a string',
                         str(expected.exception))

    def test_token_is_invalid(self):
        """Auth Token (token) must be a string."""
        with self.assertRaises(AssertionError) as expected:
            cdbredis.create_instance('IAD', '825642', None, 'name', 101)
        self.assertEqual('A valid token must be provided',
                         str(expected.exception))

    def test_flavor_is_not_an_int(self):
        """Flavor must be an int."""
        with self.assertRaises(AssertionError) as expected:
            cdbredis.create_instance('IAD', '825642', 'VALID', 'name', '101')
        self.assertEqual('flavor must be an int from 101 - 108',
                         str(expected.exception))

    def test_flavor_is_not_in_range(self):
        """Flavor must be in the appropriate range."""
        with self.assertRaises(AssertionError) as expected:
            cdbredis.create_instance('IAD', '825642', 'VALID', 'name', 100)
        self.assertEqual('flavor must be an int from 101 - 108',
                         str(expected.exception))

    @mock.patch.object(cdbredis.requests, 'post')
    @mock.patch.object(cdbredis, 'get_flavor_ref')
    def test_api_call_uses_passed_in_data(self, mock_flavor_ref, mock_post):
        """Call uses passed-in data."""
        expected_flavor_ref = ('https://iad.databases.api.rackspacecloud.com/'
                               'v1.0/825640/flavors/101')
        expected_url = ('https://iad.databases.api.rackspacecloud.com/v1.0/'
                        '825642/instances')
        expected_headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Auth-Token': 'VALID'
        }
        expected_data = json.dumps({
            'instance': {
                'datastore': {'version': '2.8', 'type': 'redis'},
                'name': 'name',
                'flavorRef': expected_flavor_ref
            }
        })
        mock_flavor_ref.return_value = expected_flavor_ref
        cdbredis.create_instance('IAD', '825642', 'VALID', 'name', 101)
        mock_post.assert_called_with(expected_url, headers=expected_headers,
                                     data=expected_data)
