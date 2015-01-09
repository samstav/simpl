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

from checkmate.providers.rackspace.database import cdbredis


class TestCreateRedisInstance(unittest.TestCase):
    """Exercise Redis Instance Creation."""
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
        cdbredis.create_instance(u'IAD', u'825642', u'VALID', u'name', 101)
        mock_post.assert_called_with(expected_url, headers=expected_headers,
                                     data=expected_data)


if __name__ == '__main__':
    unittest.main()
