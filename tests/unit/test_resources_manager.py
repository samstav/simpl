# pylint: disable=C0103,R0904,W0201,C0111

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

"""Tests for Resources Manager."""

import mock
import unittest

from checkmate import resources


class TestResourcesManagerGetResources(unittest.TestCase):
    def setUp(self):
        driver = mock.Mock()
        get_driver_patcher = mock.patch.object(resources.manager.db,
                                               'get_driver')
        mock_get_driver = get_driver_patcher.start()
        mock_get_driver.return_value = driver
        self.addCleanup(get_driver_patcher.stop)

        manager = resources.Manager()
        manager.get_resources(tenant_id=123, offset=1, limit=3,
                              query='fake query')
        _, self.kwargs = driver.get_resources.call_args

    def test_pass_tenant_id_to_driver(self):
        self.assertEqual(self.kwargs['tenant_id'], 123)

    def test_pass_offset_to_driver(self):
        self.assertEqual(self.kwargs['offset'], 1)

    def test_pass_limit_to_driver(self):
        self.assertEqual(self.kwargs['limit'], 3)

    def test_pass_query_to_driver(self):
        self.assertEqual(self.kwargs['query'], 'fake query')


if __name__ == '__main__':
    import sys
    from checkmate import test
    test.run_with_params(sys.argv[:])
