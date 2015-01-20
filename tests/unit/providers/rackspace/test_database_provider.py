# pylint: disable=C0111,C0103,R0904
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

import unittest


from checkmate.providers.rackspace.database import tasks
from checkmate.providers.rackspace.database import provider
from checkmate import test


class TestDatabaseProvider(unittest.TestCase):
    def setUp(self):
        self.provider_base = {}
        self.db_provider = provider.Provider(self.provider_base)


class TestGetResourceStatus(TestDatabaseProvider):
    def setUp(self):
        super(TestGetResourceStatus, self).setUp()
        self.context = {}
        self.dep_id = '123'
        self.resource = {}
        self.key = 'foo'
        self.api = None
        self.mock_sync_resource_task = test.mock_object(self, tasks,
                                                        'sync_resource_task')
        self.mock_connect = test.mock_object(self, provider.Provider,
                                             'connect')

    def test_dont_create_api_if_it_exists(self):
        self.api = {'something': True}
        self.db_provider.get_resource_status(self.context, self.dep_id,
                                             self.resource, self.key,
                                             api=self.api)
        assert not self.mock_connect.called

    def test_dont_create_api_if_no_region_on_resource(self):
        self.db_provider.get_resource_status(self.context, self.dep_id,
                                             self.resource, self.key,
                                             api=self.api)
        assert not self.mock_connect.called

    def test_create_api_if_not_existent_and_region_in_resource(self):
        self.resource = {'instance': {'region': 'tibet'}}
        self.db_provider.get_resource_status(self.context, self.dep_id,
                                             self.resource, self.key,
                                             api=self.api)
        self.mock_connect.assert_called_once_with(self.context, region='tibet')

    def test_sync_tasks(self):
        self.db_provider.get_resource_status(self.context, self.dep_id,
                                             self.resource, self.key,
                                             api=self.api)
        self.mock_sync_resource_task.assert_called_once_with(self.context,
                                                             self.resource,
                                                             api=self.api)

if __name__ == '__main__':
    test.run_with_params()
