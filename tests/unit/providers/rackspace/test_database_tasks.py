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
        except exceptions.CheckmateUserException as exc:
            self.assertEqual(exc.error_message, "'str' object has no "
                                                "attribute 'create'")
            self.assertEqual(exc.error_type, "AttributeError")

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

    def test_delete_database_no_context_region(self):
        '''Validates an assert raised is thrown when region not in context.'''
        context = {}
        self.assertRaisesRegexp(AssertionError, 'Region not supplied in '
                                'context', database.delete_database, context)

    def test_delete_database_no_context_resource(self):
        '''Validates an assert raised is thrown when region not in context.'''
        context = {'region': 'ORD'}
        self.assertRaisesRegexp(AssertionError, 'Resource not supplied in '
                                'context', database.delete_database, context)

    def test_delete_database_no_resource_index(self):
        '''Validates an assert raised is thrown when region not in context.'''
        context = {'region': 'ORD', 'resource': {}}
        self.assertRaisesRegexp(AssertionError, 'Resource does not have an '
                                'index', database.delete_database, context)

    @mock.patch.object(database.resource_postback, 'delay')
    @mock.patch.object(database.Provider, 'connect')
    def test_delete_database_no_api_no_instance_host_instance(self,
                                                              mock_connect,
                                                              mock_postback):
        '''Validates database delete postback when no instance or host_instance
        in context resource.
        '''
        context = {
            'region': 'ORD',
            'resource': {
                'index': '1'
            },
            'deployment_id': '123',
            'resource_key': '1'
        }
        expected = {
            'instance:1': {
                'status': 'DELETED',
                'status-message': ('Cannot find instance/host-instance for '
                                   'database to delete. Skipping '
                                   'delete_database call for resource %s in '
                                   'deployment %s - Instance Id: %s, Host '
                                   'Instance Id: %s', ('1', '123', None, None))
            }
        }

        results = database.delete_database(context)

        self.assertEqual(results, None)
        mock_connect.assert_called_with(context, 'ORD')
        mock_postback.assert_called_with('123', expected)

    @mock.patch.object(database.delete_database, 'retry')
    def test_delete_database_api_get_exception(self, mock_retry):
        '''Validates exception raised and task retried on get.
        '''
        context = {
            'region': 'ORD',
            'resource': {
                'index': '1',
                'instance': {
                    'name': 'test_name',
                    'host_instance': '2'
                },
                'host_instance': '2'
            },
            'deployment_id': '123',
            'resource_key': '1'
        }
        api = mock.Mock()
        mock_exception = pyrax.exceptions.ClientException(code=400)
        api.get = mock.MagicMock(
            side_effect=mock_exception)
        mock_retry.side_effect = AssertionError('retry')
        self.assertRaisesRegexp(AssertionError, 'retry',
                                database.delete_database, context, api)

        mock_retry.assert_called_with(
            exc=mock_exception)

    def test_delete_database_api_get_no_instance(self):
        '''Validates database marked as deleted when get returns None.'''
        context = {
            'region': 'ORD',
            'resource': {
                'index': '1',
                'instance': {
                    'name': 'test_name',
                    'host_instance': '2'
                },
                'host_instance': '2',
                'hosted_on': '3'
            },
            'deployment_id': '123',
            'resource_key': '1'
        }
        api = mock.Mock()
        api.get = mock.Mock(return_value=None)
        expected = {
            'instance:1': {
                'status': 'DELETED',
                'status-message': 'Host 3 was deleted'
            }
        }

        results = database.delete_database(context, api)

        self.assertEqual(results, expected)

    def test_delete_database_api_get_instance_build(self):
        '''Validates task retry on build status.'''
        context = {
            'region': 'ORD',
            'resource': {
                'index': '1',
                'instance': {
                    'name': 'test_name',
                    'host_instance': '2'
                },
                'host_instance': '2',
                'hosted_on': '3'
            },
            'deployment_id': '123',
            'resource_key': '1'
        }
        instance = mock.Mock()
        instance.status = 'BUILD'
        api = mock.Mock()
        api.get = mock.Mock(return_value=instance)

        self.assertRaisesRegexp(exceptions.CheckmateException, 'Waiting on '
                                'instance to be out of BUILD status',
                                database.delete_database, context, api)

    def test_delete_database_api_delete_exception_retry(self):
        '''Validates task retry on delete exception.'''
        context = {
            'region': 'ORD',
            'resource': {
                'index': '1',
                'instance': {
                    'name': 'test_name',
                    'host_instance': '2'
                },
                'host_instance': '2',
                'hosted_on': '3'
            },
            'deployment_id': '123',
            'resource_key': '1'
        }
        mock_exception = pyrax.exceptions.ClientException(code=400)
        instance = mock.Mock()
        instance.delete_database = mock.MagicMock(side_effect=mock_exception)
        instance.status = 'ACTIVE'
        api = mock.Mock()
        api.get = mock.Mock(return_value=instance)

        try:
            database.delete_database(context, api)
        except pyrax.exceptions.ClientException as exc:
            self.assertEqual(exc.code, 400)

        instance.delete_database.assert_called_with('test_name')

    @mock.patch.object(database.resource_postback, 'delay')
    def test_delete_database_success(self, mock_postback):
        '''Validates delete_database success.'''
        context = {
            'region': 'ORD',
            'resource': {
                'index': '1',
                'instance': {
                    'name': 'test_name',
                    'host_instance': '2'
                },
                'host_instance': '2',
                'hosted_on': '3'
            },
            'deployment_id': '123',
            'resource_key': '1'
        }
        instance = mock.Mock()
        instance.delete_database = mock.Mock()
        instance.status = 'ACTIVE'
        api = mock.Mock()
        api.get = mock.Mock(return_value=instance)
        expected = {'instance:1': {'status': 'DELETED'}}

        results = database.delete_database(context, api)
        self.assertEqual(expected, results)
        mock_postback.assert_called_with('123', expected)

    @mock.patch.object(database.Provider, 'connect')
    def test_delete_user_no_api(self, mock_connect):
        '''Verifies Provider connect is called in delete user with no api.'''
        context = {}
        instance_id = 12345
        username = 'test_user'
        region = 'ORD'
        instance = mock.Mock()
        instance.delete_user = mock.Mock()
        api = mock.Mock()
        api.get = mock.Mock(return_value=instance)
        mock_connect.return_value = api

        database.delete_user(context, instance_id, username, region)
        mock_connect.assert_called_with(context, region)

    def test_delete_user_api_success(self):
        '''Verifies all method calls in the delete_user task.'''
        context = {}
        instance_id = 12345
        username = 'test_user'
        region = 'ORD'
        instance = mock.Mock()
        instance.delete_user = mock.Mock()
        api = mock.Mock()
        api.get = mock.Mock(return_value=instance)

        database.delete_user(context, instance_id, username, region, api)
        api.get.assert_called_with(instance_id)
        instance.delete_user.assert_called_with(username)


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
