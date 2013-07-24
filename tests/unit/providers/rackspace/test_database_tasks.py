# pylint: disable=C0103,C0111,R0201,R0903,R0904,W0212,W0232
'Tests to exercise database celery tasks.'
import functools
import mock
import unittest

from checkmate import exceptions
from checkmate import middleware
from checkmate.providers.rackspace import database


# Disable for accessing private attributes, long names, and number public meths
# pylint: disable=W0212,C0103,R0904
class TestDatabaseTasks(unittest.TestCase):
    'Class to test rackspace.database celery tasks.'
    def test_create_instance_sim_no_dbs(self):
        'Create instance with simulation and no databases.'
        api = mock.Mock()
        database._create_instance.provider = mock.Mock(return_value=api)
        database._create_instance.callback = mock.Mock()
        partial = mock.Mock()
        functools.partial = mock.Mock(return_value=partial)
        context = {
            'simulation': True,
            'resource': '0',
            'deployment': 0,
            'region': 'DFW'
        }
        context = middleware.RequestContext(**context)
        expected_result = {
            'instance:0': {
                'status': 'BUILD',
                'name': 'test_instance',
                'flavor': 1,
                'region': 'DFW',
                'databases': {},
                'interfaces': {'mysql': {'host': 'db1.rax.net'}},
                'id': 'DBS0'
            }
        }
        results = database.create_instance(
            context, 'test_instance', 1, 1, None, None)
        self.assertEqual(expected_result, results)
        partial.assert_called_with({'id': 'DBS0'})
        database._create_instance.callback.assert_called_with(
            context, expected_result['instance:0'])

    def test_create_instance_sim_with_dbs(self):
        'Create instance with simulation and databases.'
        api = mock.Mock()
        database._create_instance.provider = mock.Mock(return_value=api)
        database._create_instance.callback = mock.Mock()
        partial = mock.Mock()
        functools.partial = mock.Mock(return_value=partial)
        context = {
            'simulation': True,
            'resource': '0',
            'deployment': 0,
            'region': 'DFW'
        }
        context = middleware.RequestContext(**context)
        expected_result = {
            'instance:0': {
                'status': 'BUILD',
                'name': 'test_instance',
                'region': 'DFW',
                'id': 'DBS0',
                'databases': {
                    'db1': {
                        'interfaces': {
                            'mysql': {
                                'host': 'db1.rax.net',
                                'database_name': 'db1'
                            }
                        },
                        'name': 'db1'
                    },
                    'db2': {
                        'interfaces': {
                            'mysql': {
                                'host': 'db1.rax.net',
                                'database_name': 'db2'
                            }
                        },
                        'name': 'db2'
                    }
                },
                'flavor': 1,
                'interfaces': {
                    'mysql': {
                        'host': 'db1.rax.net'
                    }
                }
            }
        }
        databases = [{'name': 'db1'}, {'name': 'db2'}]
        results = database.create_instance(
            context, 'test_instance', 1, 1, databases, None)
        self.assertEqual(expected_result, results)
        partial.assert_called_with({'id': 'DBS0'})
        database._create_instance.callback.assert_called_with(
            context, expected_result['instance:0'])

    def test_create_instance_no_sim_no_dbs(self):
        'Create instance no databases.'
        context = {'resource': '0', 'deployment': 0, 'region': 'DFW'}
        context = middleware.RequestContext(**context)
        api = mock.Mock()
        database._create_instance.provider = mock.Mock()
        database._create_instance.provider.connect = mock.Mock(
            return_value=api)
        database._create_instance.callback = mock.Mock()
        partial = mock.Mock()
        functools.partial = mock.Mock(return_value=partial)
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
        api.create = mock.Mock(return_value=instance)

        results = database.create_instance(context, 'test_instance', '1', '1',
                                           None, 'DFW')

        database._create_instance.provider.connect.assert_called_with(
            context, 'DFW')
        api.create.assert_called_with('test_instance', flavor=1, volume=1,
                                      databases=[])
        partial.assert_called_with({'id': 1234})
        database._create_instance.callback.assert_called_with(
            context, expected['instance:0'])
        self.assertEqual(results, expected)

    def test_create_instance_no_sim_with_dbs(self):
        'Create instance with databases.'
        context = {'resource': '0', 'deployment': 0, 'region': 'DFW'}
        context = middleware.RequestContext(**context)
        api = mock.Mock()
        instance = mock.Mock()
        database._create_instance.provider = mock.Mock()
        database._create_instance.provider.connect = mock.Mock(
            return_value=api)
        partial = mock.Mock()
        functools.partial = mock.Mock(return_value=partial)
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
        api.create = mock.Mock(return_value=instance)
        database._create_instance.callback = mock.Mock()

        results = database.create_instance(context, 'test_instance', '1', '1',
                                           databases, 'DFW')

        database._create_instance.provider.connect.assert_called_with(
            context, 'DFW')
        api.create.assert_called_with('test_instance', volume=1, flavor=1,
                                      databases=databases)
        partial.assert_called_with({'id': 1234})
        database._create_instance.callback.assert_called_with(
            context, expected['instance:0'])
        self.assertEqual(results, expected)

    def test_create_instance_invalid_api(self):
        '''Verifies exception thrown when invalid api object passed in.'''
        context = {'resource': '0', 'deployment': 0}
        try:
            database.create_instance(context, 'test_instance', '1', '1',
                                     None, 'DFW', api='invalid')
        except exceptions.CheckmateException as exc:
            self.assertEqual(exc.args[0], 'Provider error occurred in '
                             'create_instance.')
            assert isinstance(exc.args[1], AttributeError)
            self.assertEqual(str(exc.args[1]), "'str' object has no attribute "
                             "'create'")

    def test_create_database_sim_no_instance_id(self):
        '''Verifies create database simulation is working.'''
        context = {'resource': '2', 'simulation': True, 'deployment': 0}
        name = 'test_database'
        region = 'ORD'
        database.resource_postback.delay = mock.Mock()
        expected = {
            'instance:2': {
                'host_instance': 'DBS2',
                'host_region': 'ORD',
                'interfaces': {
                    'mysql': {
                        'database_name': 'test_database',
                        'host': 'srv2.rackdb.net'
                    }
                },
                'name': 'test_database'
            }
        }

        results = database.create_database(context, name, region)
        self.assertEqual(expected, results)

    def test_create_database_sim_instance_id(self):
        '''Verifies create database simulation is working.'''
        context = {'resource': '2', 'simulation': True, 'deployment': 0}
        name = 'test_database'
        region = 'ORD'
        instance_id = '12345'
        database.resource_postback.delay = mock.Mock()
        expected = {
            'instance:2': {
                'host_instance': '12345',
                'host_region': 'ORD',
                'interfaces': {
                    'mysql': {
                        'database_name': 'test_database',
                        'host': 'srv2.rackdb.net'
                    }
                },
                'name': 'test_database'
            }
        }

        results = database.create_database(context, name, region,
                                           instance_id=instance_id)
        self.assertEqual(expected, results)

    @mock.patch.object(database, 'create_instance')
    @mock.patch.object(database.Provider, 'connect')
    @mock.patch.object(database, 'reset_failed_resource_task')
    @mock.patch.object(database, 'wait_on_build')
    def test_create_database_no_api_no_sim_no_iid_no_attrs(
            self, mock_create_instance, mock_connect, mock_rfrt, mock_wob):
        '''Verifies create database simulation is working.'''
        context = {'resource': '2', 'deployment': 0}
        name = 'test_database'
        region = 'ORD'

        instance = {
            'instance:2': {
                'id': '12345',
            },
            'instance': {
                'databases': {
                    name: {},
                }
            },
            'region': 'ORD'
        }

        expected = {
            'instance:2': {
                'flavor': '1',
                'host_instance': '12345',
                'host_region': 'ORD'
            }
        }

        mock_connect.return_value = True
        mock_create_instance.return_value = instance

        database.reset_failed_resource_task.delay = mock_rfrt.delay
        database.wait_on_build.delay = mock_wob.delay
        database.Provider.connect = mock_connect
        database.create_instance = mock_create_instance

        results = database.create_database(context, name, region)

        mock_connect.assert_called_once_with(context, region)
        mock_rfrt.delay.assert_called_once_with(context['deployment'],
                                                context['resource'])

        mock_create_instance.assert_called_once_with(
            context, ('%s_instance' % (name)), 1, '1',
            [{'name': name}], region, api=mock_connect.return_value)

        mock_wob.delay.assert_called_once_with(context, '12345', region,
                                               api=mock_connect.return_value)
        self.assertEqual(expected, results)

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