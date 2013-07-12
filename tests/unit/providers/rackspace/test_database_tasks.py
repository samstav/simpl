import unittest
import mock

from checkmate.providers.rackspace import database
from checkmate.providers.rackspace.database import resource_postback

class TestDatabaseTasks(unittest.TestCase):
    def test_simulation_with_no_databases(self):
        resource_postback_mock = mock.Mock()
        resource_postback_mock.delay = mock.Mock()
        database.resource_postback = resource_postback_mock
        context = {'simulation': True, 'resource': 0, 'deployment': 0}
        expected_result = {
            'instance:0': {
                'status': 'ACTIVE',
                'name': None,
                'region': None,
                'databases': {},
                'interfaces': {'mysql': {'host': 'srv0.rackdb.net'}},
                'id': 'DBS0'
            }
        }
        results = database.create_instance(
            context, None, None, None, None, None)
        self.assertEqual(expected_result, results)
        resource_postback_mock.delay.assert_called_with(0, expected_result)
        self.assertEqual(2, resource_postback_mock.delay.call_count)

    def test_simulation_with_databases(self):
        resource_postback_mock = mock.Mock()
        resource_postback_mock.delay = mock.Mock()
        database.resource_postback = resource_postback_mock
        context = {'simulation': True, 'resource': '0', 'deployment': 0}
        expected_result = {
            'instance:0': {
                'status': 'ACTIVE',
                'name': None,
                'region': None,
                'databases': {
                    'db1': {
                        'interfaces': {
                            'mysql': {
                                'database_name': 'db1',
                                'host': 'srv0.rackdb.net'
                            }
                        },
                        'name': 'db1'
                    },
                    'db2': {
                        'interfaces': {
                            'mysql': {
                                'database_name': 'db2',
                                'host': 'srv0.rackdb.net'
                            }
                        },
                        'name': 'db2'
                    }
                },
                'id': 'DBS0',
                'interfaces': {'mysql': {'host': 'srv0.rackdb.net'}},
            }
        }
        databases = [{'name': 'db1'}, {'name': 'db2'}]
        results = database.create_instance(
            context, None, None, None, databases, None)
        self.assertEqual(expected_result, results)
        resource_postback_mock.delay.assert_called_with(0, expected_result)
        self.assertEqual(2, resource_postback_mock.delay.call_count)

    def test_no_simulation_no_databases(self):
        context = {'resource': '0', 'deployment': 0}
        results = database.create_instance(
            context, None, None, None, None, None)
