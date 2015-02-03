# pylint: disable=C0103,R0201,R0904,W0212,W0613

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

"""Unit Tests for Cloud Block Storage instance management."""

import json
import unittest

import mock

from checkmate.providers.rackspace.block import cbs


class TestCreateBlockInstance(unittest.TestCase):

    """Exercise Block Storage Volume Creation."""

    @mock.patch.object(cbs.requests, 'post')
    def test_api_call_uses_passed_in_data(self, mock_post):
        """Call uses passed-in data."""
        expected_url = ('https://iad.blockstorage.api.rackspacecloud.com/v1.0/'
                        '825642/')
        expected_headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'X-Auth-Token': 'VALID'
        }
        expected_data = json.dumps({
            'volume': {
                'size': 101
            }
        })
        catalog = {
            'auth_token': 'VALID',
            'catalog': [{
                'name': 'cloudBlockStorage',
                'type': 'volume',
                'endpoints': [{
                    'publicURL': expected_url,
                    'region': 'IAD',
                }]
            }]
        }
        cbs.create_volume(catalog, u'IAD', 101)
        mock_post.assert_called_with(expected_url + 'volumes',
                                     headers=expected_headers,
                                     data=expected_data)


if __name__ == '__main__':
    unittest.main()
