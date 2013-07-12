'Tests to exercise database celery tasks.'
import mock
import unittest

from checkmate.providers.rackspace import database


class TestDatabaseTasks(unittest.TestCase):
    'Class to test rackspace.database celery tasks.'
    def test_create_instance_sim_no_dbs(self):
        'Create instance with simulation and no databases.'
        database.resource_postback.delay = mock.Mock()
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
        database.resource_postback.delay.assert_called_with(0, expected_result)
        self.assertEqual(2, database.resource_postback.delay.call_count)

    def test_create_instance_sim_with_dbs(self):
        'Create instance with simulation and databases.'
        database.resource_postback.delay = mock.Mock()
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
        database.resource_postback.delay.assert_called_with(0, expected_result)
        self.assertEqual(2, database.resource_postback.delay.call_count)

    def test_create_instance_no_sim_no_dbs(self):
        'Create instance no databases.'
        context = {'resource': '0', 'deployment': 0}
        api = mock.Mock()
        instance = mock.Mock()
        instance.id = 1234
        instance.name = 'test_instance'
        instance.hostname = 'test.hostname'
        expected = {
            'instance:0': {
                'status': 'BUILD',
                'name': 'test_instance',
                'region': 'DFW',
                'id': 1234,
                'databases': {},
                'flavor': 1,
                'interfaces': {
                    'mysql': {
                        'host': 'test.hostname'
                    }
                }
            }
        }
        # mock methods
        database.Provider.connect = mock.Mock(return_value=api)
        api.create_instance = mock.Mock(return_value=instance)
        database.resource_postback.delay = mock.Mock()

        results = database.create_instance(context, 'test_instance', '1', '1',
                                           None, 'DFW')

        database.Provider.connect.assert_called_with(context, 'DFW')
        api.create_instance.assert_called_with('test_instance', 1, 1,
                                               databases=[])
        database.resource_postback.delay.assert_called_with_once(0, 1234)
        database.resource_postback.delay.assert_called_with(0, expected)
        self.assertEqual(results, expected)

    def test_create_instance_no_sim_with_dbs(self):
        'Create instance with databases.'
        context = {'resource': '0', 'deployment': 0}
        api = mock.Mock()
        instance = mock.Mock()
        instance.id = 1234
        instance.name = 'test_instance'
        instance.hostname = 'test.hostname'
        databases = [{'name': 'db1'}, {'name': 'db2'}]
        expected = {
            'instance:0': {
                'status': 'BUILD',
                'name': 'test_instance',
                'region': 'DFW',
                'id': 1234,
                'databases': {
                    'db1': {
                        'interfaces': {
                            'mysql': {
                                'host': 'test.hostname',
                                'database_name': 'db1'
                            }
                        },
                        'name': 'db1'
                    },
                    'db2': {
                        'interfaces': {
                            'mysql': {
                                'host': 'test.hostname',
                                'database_name': 'db2'
                            }
                        },
                        'name': 'db2'
                    }
                },
                'flavor': 1,
                'interfaces': {
                    'mysql': {
                        'host': 'test.hostname'
                    }
                }
            }
        }
        # mock methods
        database.Provider.connect = mock.Mock(return_value=api)
        api.create_instance = mock.Mock(return_value=instance)
        database.resource_postback.delay = mock.Mock()

        results = database.create_instance(context, 'test_instance', '1', '1',
                                           databases, 'DFW')

        database.Provider.connect.assert_called_with(context, 'DFW')
        api.create_instance.assert_called_with('test_instance', 1, 1,
                                               databases=databases)
        database.resource_postback.delay.assert_called_with_once(0, 1234)
        database.resource_postback.delay.assert_called_with(0, expected)
        self.assertEqual(results, expected)


if __name__ == '__main__':
    # Run tests. Handle our parameters seprately
    import sys

    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
