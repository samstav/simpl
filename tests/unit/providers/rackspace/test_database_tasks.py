# pylint: disable=C0103,C0111,R0201,R0903,R0904,W0212,W0232
'Tests to exercise database celery tasks.'
import functools
import mock
import unittest

import pyrax

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
                'disk': 1,
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
                'disk': 1,
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
        instance.volume.size = 1
        expected = {
            'instance:0': {
                'status': 'BUILD',
                'name': 'test_instance',
                'region': 'DFW',
                'id': 1234,
                'databases': {},
                'flavor': 1,
                'disk': 1,
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
        instance.volume.size = 1
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
                'disk': 1,
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
    @mock.patch.object(database.reset_failed_resource_task, 'delay')
    @mock.patch.object(database.wait_on_build, 'delay')
    def test_create_database_no_api_no_sim_no_iid_no_attrs(
            self, mock_wob, mock_rfrt, mock_connect, mock_create_instance):
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

        results = database.create_database(context, name, region)

        mock_connect.assert_called_once_with(context, region)
        mock_rfrt.assert_called_once_with(context['deployment'],
                                          context['resource'])

        mock_create_instance.assert_called_once_with(
            context, ('%s_instance' % (name)), 1, '1',
            [{'name': name}], region, api=mock_connect.return_value)

        mock_wob.assert_called_once_with(context, '12345', region,
                                         api=mock_connect.return_value)
        self.assertEqual(expected, results)

    def test_add_user_assert_instance_id(self):
        '''Verifies AssertionError raised when invalid instance_id passed.'''
        self.assertRaises(AssertionError, database.add_user, {}, None, [], '',
                          '', '')

    @mock.patch.object(database.resource_postback, 'delay')
    def test_add_user_sim(self, mock_postback):
        '''Validates add_user simulation return.'''
        instance_id = '12345'
        context = {'resource': '0', 'simulation': True, 'deployment': 0}
        username = 'test_user'
        password = 'test_pass'
        databases = ['blah']
        region = 'ORD'
        expected = {
            'instance:0': {
                'username': 'test_user',
                'status': 'ACTIVE',
                'interfaces': {
                    'mysql': {
                        'username': 'test_user',
                        'host': 'srv0.rackdb.net',
                        'password': 'test_pass',
                        'database_name': 'blah'
                    }
                },
                'password': 'test_pass'
            }
        }
        results = database.add_user(context, instance_id, databases, username,
                                    password, region)
        mock_postback.assert_called_with(0, expected)
        self.assertEqual(results, expected)

    @mock.patch.object(database, 'current')
    @mock.patch.object(database.Provider, 'connect')
    @mock.patch.object(database.resource_postback, 'delay')
    def test_add_user_no_api_create_exc_retry(self, mock_postback,
                                              mock_connect, mock_current):
        '''Validates methods and retry called on add_user ClientException.'''
        context = {'resource': '0', 'deployment': '123'}
        instance_id = '12345'
        databases = [123]
        username = 'test_user'
        password = 'test_pass'
        region = 'ORD'
        api = mock.Mock()
        instance = mock.Mock()
        mock_exception = pyrax.exceptions.ClientException(code=422)
        instance.create_user = mock.MagicMock(side_effect=mock_exception)
        api.get = mock.Mock(return_value=instance)
        mock_connect.return_value = api
        mock_current.retry = mock.MagicMock(
            side_effect=AssertionError('retry'))

        self.assertRaises(AssertionError, database.add_user, context,
                          instance_id, databases, username, password, region)

        mock_postback.assert_called_with(
            '123', {'instance:0': {'status': 'CONFIGURE'}})
        mock_connect.assert_called_with(context, region)
        api.get.assert_called_with(instance_id)
        instance.create_user.assert_called_with(username, password, databases)
        mock_current.retry.assert_called_with(exc=mock_exception)

    @mock.patch.object(database.Provider, 'connect')
    @mock.patch.object(database.resource_postback, 'delay')
    def test_add_user_no_api_create_raise_exc(self, mock_postback,
                                              mock_connect):
        '''Validates methods and exc raised on add_user ClientException.'''
        context = {'resource': '0', 'deployment': '123'}
        instance_id = '12345'
        databases = [123]
        username = 'test_user'
        password = 'test_pass'
        region = 'ORD'
        api = mock.Mock()
        instance = mock.Mock()
        mock_exception = pyrax.exceptions.ClientException(code=400)
        instance.create_user = mock.MagicMock(side_effect=mock_exception)
        api.get = mock.Mock(return_value=instance)
        mock_connect.return_value = api

        self.assertRaises(pyrax.exceptions.ClientException, database.add_user,
                          context, instance_id, databases, username, password,
                          region)

        mock_postback.assert_called_with(
            '123', {'instance:0': {'status': 'CONFIGURE'}})
        mock_connect.assert_called_with(context, region)
        api.get.assert_called_with(instance_id)
        instance.create_user.assert_called_with(username, password, databases)

    @mock.patch.object(database.resource_postback, 'delay')
    def test_add_user_api_success(self, mock_postback):
        '''Validates methods and results called on add_user success.'''
        context = {'resource': '0', 'deployment': '123'}
        instance_id = '12345'
        databases = [123]
        username = 'test_user'
        password = 'test_pass'
        region = 'ORD'
        api = mock.Mock()
        instance = mock.Mock()
        api.get = mock.Mock(return_value=instance)
        instance.create_user = mock.Mock()
        instance.hostname = 'test_hostname'
        expected = {
            'instance:0': {
                'interfaces': {
                    'mysql': {
                        'database_name': 123,
                        'host': 'test_hostname',
                        'password': 'test_pass',
                        'username': 'test_user'
                    }
                },
                'password': 'test_pass',
                'status': 'ACTIVE',
                'username': 'test_user'
            }
        }

        results = database.add_user(context, instance_id, databases, username,
                                    password, region, api)
        mock_postback.assert_called_with('123', expected)
        self.assertEqual(results, expected)

    #@mock.patch.object(database.resource_postback, 'delay')
    def test_delete_instance_task_on_failure_dep_id_key(self):
        '''Test on_failure code with dep_id and key.'''
        context = {'deployment_id': '123', 'resource_key': '0'}
        args = [context]
        kwargs = {}
        exc = Exception('test exception')
        task_id = 4321
        
        database.delete_instance_task.on_failure(exc, task_id, args, kwargs,
                                                 '')
        #mock_postback.assert_called_with('123', {})

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
