import mock
import unittest

from checkmate.providers.rackspace import database
from checkmate.providers.rackspace.database import provider
from checkmate import test


class TestDatabaseProvider(unittest.TestCase):
    def setUp(self):
        pass


class TestGetResourceStatus(TestDatabaseProvider):
    def setUp(self):
        self.context = {}
        self.dep_id = '123'
        self.resource = {}
        self.key = 'foo'
        self.api = None
        self.mock_sync_resource_task = test.mock_object(self, database,
                                                        'sync_resource_task')
        self.mock_connect = test.mock_object(self, provider.Provider,
                                             'connect')
        self.db_provider = provider.Provider({})

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
                                                             self.key,
                                                             api=self.api)

if __name__ == '__main__':
    test.run_with_params()
