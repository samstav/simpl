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

"""Unit Tests for the Rackspace Provider's database tasks."""

import functools
import logging
import mock
import unittest

import pyrax

from checkmate.deployments import tasks
from checkmate import exceptions
from checkmate import middleware
from checkmate.providers.rackspace.database import manager
from checkmate.providers.rackspace.database import provider
from checkmate.providers.rackspace.database import tasks as dbtasks

LOG = logging.getLogger(__name__)


class TestDatabaseTasks(unittest.TestCase):

    """Class to test rackspace.database celery tasks."""

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(dbtasks.create_instance, 'provider')
    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    def test_create_instance_sim_no_dbs(self, mock_reset,
                                        mock_provider,
                                        mock_postback,
                                        mock_partial):
        'Create instance with simulation and no databases.'
        partial = mock.Mock()
        mock_partial.return_value = partial
        mock_provider.translate_status.side_effect = lambda x: x
        context = {
            'simulation': True,
            'resource_key': '0',
            'deployment_id': 'D1',
            'region': 'DFW'
        }
        context = middleware.RequestContext(**context)
        expected = {
            'resources': {
                '0': {
                    'instance': {
                        'status': 'BUILD',
                        'name': 'test_instance',
                        'flavor': 1,
                        'disk': 1,
                        'region': 'DFW',
                        'databases': {},
                        'interfaces': {'mysql': {'host': 'db1.rax.net'}},
                        'id': 'DBS0'
                    },
                    'status': 'BUILD'
                }
            }
        }
        results = dbtasks.create_instance(
            context, 'test_instance', 1, 1, None, None)
        self.assertEqual(expected, results)
        partial.assert_called_with({'id': 'DBS0'})
        mock_postback.assert_called_with(context['deployment_id'], expected)

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(dbtasks.create_instance, 'provider')
    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    def test_create_instance_sim_with_dbs(self, mock_reset,
                                          mock_provider,
                                          mock_postback,
                                          mock_partial):
        """Create instance with simulation and databases."""
        mock_provider.translate_status.side_effect = lambda x: x
        partial = mock.Mock()
        mock_partial.return_value = partial
        context = {
            'simulation': True,
            'resource_key': '0',
            'deployment_id': 'DEP_ID',
            'region': 'DFW'
        }
        context = middleware.RequestContext(**context)
        expected_result = {
            'resources': {
                '0': {
                    'instance': {
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
                    },
                    'status': 'BUILD'
                }
            }
        }
        databases = [{'name': 'db1'}, {'name': 'db2'}]
        results = dbtasks.create_instance(
            context, 'test_instance', 1, 1, databases, None)
        self.assertEqual(expected_result, results)
        partial.assert_called_with({'id': 'DBS0'})
        mock_postback.assert_called_with(
            context['deployment_id'], expected_result)

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(dbtasks.create_instance, 'provider')
    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    def test_create_instance_no_sim_no_dbs(self, mock_reset,
                                           mock_provider,
                                           mock_postback,
                                           mock_partial):
        """Create instance no databases."""
        context = {'resource_key': '0', 'deployment_id': 'D1', 'region': 'DFW'}
        context = middleware.RequestContext(**context)
        api = mock.Mock()
        mock_provider.connect = mock.Mock(return_value=api)
        mock_provider.translate_status.side_effect = lambda x: x
        partial = mock.Mock()
        mock_partial.return_value = partial
        instance = mock.Mock()
        instance.id = 1234
        instance.name = 'test_instance'
        instance.hostname = 'test.hostname'
        instance.volume.size = 1
        expected = {
            'resources': {
                '0': {
                    'instance': {
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
                    },
                    'status': 'BUILD'
                }
            }
        }
        api.create = mock.Mock(return_value=instance)

        results = dbtasks.create_instance(context, 'test_instance', '1', '1',
                                          None, 'DFW')

        mock_provider.connect.assert_called_with(context)
        api.create.assert_called_with('test_instance', flavor=1, volume=1,
                                      databases=[])
        partial.assert_called_with({'id': 1234})
        mock_postback.assert_called_with(context['deployment_id'], expected)
        self.assertEqual(results, expected)

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(dbtasks.create_instance, 'provider')
    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    def test_create_instance_no_sim_with_dbs(self, mock_reset,
                                             mock_provider,
                                             mock_postback,
                                             mock_partial):
        """Create instance with databases."""
        context = {'resource_key': '0', 'deployment_id': 'DEP_ID',
                   'region': 'DFW'}
        context = middleware.RequestContext(**context)
        api = mock.Mock()
        instance = mock.Mock()
        mock_provider.connect = mock.Mock(return_value=api)
        mock_provider.translate_status.side_effect = lambda x: x
        partial = mock.Mock()
        mock_partial.return_value = partial
        instance.id = 1234
        instance.name = 'test_instance'
        instance.hostname = 'test.hostname'
        instance.volume.size = 1
        databases = [{'name': 'db1'}, {'name': 'db2'}]
        expected = {
            'resources': {
                '0': {
                    'instance': {
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
                    },
                    'status': 'BUILD',
                }
            }
        }
        api.create = mock.Mock(return_value=instance)

        results = dbtasks.create_instance(context, 'test_instance', '1', '1',
                                          databases, 'DFW')

        mock_provider.connect.assert_called_with(context)
        api.create.assert_called_with('test_instance', volume=1, flavor=1,
                                      databases=databases)
        partial.assert_called_with({'id': 1234})
        mock_postback.assert_called_with(
            context['deployment_id'], expected)
        self.assertEqual(results, expected)

    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    def test_create_instance_invalid_api(self, mock_reset):
        context = {'resource': '0', 'deployment_od': 0}
        context = middleware.RequestContext(**context)
        try:
            dbtasks.create_instance(context, 'test_instance', '1', '1', None,
                                    'DFW', api='invalid')
        except exceptions.CheckmateException as exc:
            self.assertEqual(exc.message, "'str' object has no attribute "
                             "'create'")


class TestAddUser(unittest.TestCase):
    def setUp(self):
        self.context = middleware.RequestContext(**{
            'resource_key': '0',
            'deployment_id': '0'
        })

        self.instance_id = '12345'
        self.databases = ['blah']
        self.username = 'test_user'
        self.password = 'test_pass'
        self.region = 'ORD'

    def test_assert_instance_id(self):
        self.assertRaises(AssertionError, dbtasks.add_user,
                          self.context, None, self.databases, self.username,
                          self.password, api="api")

    @mock.patch.object(manager.LOG, 'info')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(dbtasks.add_user.provider, 'connect')
    def test_add_user_sim(self, mock_connect, mock_postback, mock_LOG):
        self.context['simulation'] = True
        expected = {
            'resources': {
                '0': {
                    'instance': {
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
                    },
                    'status': 'ACTIVE',
                }
            }
        }
        results = dbtasks.add_user(self.context, self.instance_id,
                                   self.databases, self.username,
                                   self.password, self.region)

        mock_LOG.assert_called_with('Added user %s to %s on instance %s',
                                    'test_user', ['blah'], '12345')
        mock_postback.assert_called_with(
            self.context['deployment_id'], expected)
        self.assertEqual(results, expected)

    @mock.patch.object(dbtasks.add_user, 'retry')
    def test_api_get_exc_retry(self, mock_retry):
        api = mock.Mock()
        mock_exception = pyrax.exceptions.ClientException(code='422')
        api.get = mock.MagicMock(side_effect=mock_exception)
        mock_retry.side_effect = AssertionError('retry')

        self.assertRaisesRegexp(AssertionError, 'retry',
                                dbtasks.add_user, self.context,
                                self.instance_id, self.databases,
                                self.username, self.password, api=api)

        api.get.assert_called_with(self.instance_id)

    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(dbtasks.add_user, 'retry')
    def test_instance_status_exc_retry(self, mock_retry, mock_postback):
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'ERROR'
        api.get = mock.Mock(return_value=instance)
        mock_retry.side_effect = AssertionError('retry')

        self.assertRaisesRegexp(AssertionError, 'retry',
                                dbtasks.add_user, self.context,
                                self.instance_id, self.databases,
                                self.username, self.password,
                                api=api)

        expected = {
            'resources': {
                '0': {
                    'status': 'ERROR',
                    'instance': {'status': 'ERROR'}
                }
            }
        }
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

        api.get.assert_called_with(self.instance_id)

    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(dbtasks.add_user, 'retry')
    def test_instance_create_user_exc_retry(self, mock_retry, mock_postback):
        mock_exception = pyrax.exceptions.ClientException(code='422')
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'ACTIVE'
        instance.create_user = mock.MagicMock(side_effect=mock_exception)
        api.get = mock.Mock(return_value=instance)

        mock_retry.side_effect = AssertionError('retry')

        expected = {
            'resources': {
                '0': {
                    'status': 'ACTIVE',
                    'instance': {'status': 'ACTIVE'}
                }
            }
        }
        self.assertRaisesRegexp(AssertionError, 'retry',
                                dbtasks.add_user, self.context,
                                self.instance_id, self.databases,
                                self.username, self.password, api=api)

        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)
        api.get.assert_called_with(self.instance_id)
        instance.create_user.assert_called_with(self.username, self.password,
                                                self.databases)

    @mock.patch.object(tasks, 'postback')
    def test_instance_create_user_gen_exc(self, mock_postback):
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'ACTIVE'
        instance.create_user = mock.MagicMock(side_effect=Exception)
        api.get = mock.Mock(return_value=instance)

        self.assertRaises(exceptions.CheckmateException,
                          dbtasks.add_user, self.context,
                          self.instance_id, self.databases, self.username,
                          self.password, api=api)

        expected = {
            'resources': {
                '0': {
                    'status': 'ACTIVE',
                    'instance': {'status': 'ACTIVE'}
                }
            }
        }
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)
        api.get.assert_called_with(self.instance_id)
        instance.create_user.assert_called_with(self.username, self.password,
                                                self.databases)

    @mock.patch.object(manager.LOG, 'info')
    @mock.patch.object(tasks, 'postback')
    def test_add_user(self, mock_postback, mock_LOG):
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'ACTIVE'
        instance.create_user = mock.MagicMock()
        instance.hostname = 'srv0.rackdb.net'
        api.get = mock.Mock(return_value=instance)

        expected = {
            'resources': {
                '0': {
                    'instance': {
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
                    },
                    'status': 'ACTIVE'
                }
            }
        }
        results = dbtasks.add_user(self.context, self.instance_id,
                                   self.databases, self.username,
                                   self.password, api=api)
        api.get.assert_called_with(self.instance_id)
        instance.create_user.assert_called_with(self.username,
                                                self.password,
                                                self.databases)
        mock_LOG.assert_called_with('Added user %s to %s on instance %s',
                                    'test_user', ['blah'], '12345')
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)
        self.assertEqual(results, expected)


class TestDeleteDatabaseItems(unittest.TestCase):
    def test_delete_database_no_context_region(self):
        context = {}
        self.assertRaisesRegexp(AssertionError, 'Region not supplied in '
                                'context', dbtasks.delete_database,
                                context)

    def test_delete_database_no_context_resource(self):
        context = {'region': 'ORD'}
        self.assertRaisesRegexp(AssertionError, 'Resource not supplied in '
                                'context', dbtasks.delete_database,
                                context)

    def test_delete_database_no_resource_index(self):
        context = {'region': 'ORD', 'resource': {}}
        self.assertRaisesRegexp(AssertionError, 'Resource does not have an '
                                'index', dbtasks.delete_database,
                                context)

    @mock.patch.object(dbtasks.resource_postback, 'delay')
    @mock.patch.object(provider.Provider, 'connect')
    def test_delete_database_no_api_no_instance_host_instance(self,
                                                              mock_connect,
                                                              mock_postback):
        context = {
            'region': 'ORD',
            'resource': {
                'index': '1'
            },
            'deployment_id': '123',
            'resource_key': '1'
        }
        message = ('Cannot find instance/host-instance for database to '
                   'delete. Skipping delete_database call for resource %s in '
                   'deployment %s - Instance Id: %s, Host Instance Id: %s',
                   ('1', '123', None, None))
        expected = {
            'resources': {
                '1': {
                    'status': 'DELETED',
                    'status-message': message
                }
            }
        }

        results = dbtasks.delete_database(context)

        self.assertEqual(results, None)
        mock_connect.assert_called_with(context, 'ORD')
        mock_postback.assert_called_with('123', expected)

    @mock.patch.object(dbtasks.delete_database, 'retry')
    def test_delete_database_api_get_exception(self, mock_retry):
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
        mock_exception = pyrax.exceptions.ClientException(code='400')
        api.get = mock.MagicMock(
            side_effect=mock_exception)
        mock_retry.side_effect = AssertionError('retry')
        self.assertRaisesRegexp(AssertionError, 'retry',
                                dbtasks.delete_database, context, api)

        mock_retry.assert_called_with(
            exc=mock_exception)

    def test_delete_database_api_get_no_instance(self):
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
            'resources': {
                '1': {
                    'status': 'DELETED',
                    'status-message': 'Host 3 was deleted'
                }
            }
        }

        results = dbtasks.delete_database(context, api)

        self.assertEqual(results, expected)

    def test_delete_database_api_get_instance_build(self):
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
                                dbtasks.delete_database, context, api)

    def test_delete_database_api_delete_exception_retry(self):
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
        mock_exception = pyrax.exceptions.ClientException(code='400')
        instance = mock.Mock()
        instance.delete_database = mock.MagicMock(side_effect=mock_exception)
        instance.status = 'ACTIVE'
        api = mock.Mock()
        api.get = mock.Mock(return_value=instance)

        try:
            dbtasks.delete_database(context, api)
        except pyrax.exceptions.ClientException as exc:
            self.assertEqual(exc.code, '400')

        instance.delete_database.assert_called_with('test_name')

    @mock.patch.object(dbtasks.resource_postback, 'delay')
    def test_delete_database_success(self, mock_postback):
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
        expected = {'resources': {'1': {'status': 'DELETED'}}}

        results = dbtasks.delete_database(context, api)
        self.assertEqual(expected, results)
        mock_postback.assert_called_with('123', expected)

    @mock.patch.object(provider.Provider, 'connect')
    def test_delete_user_no_api(self, mock_connect):
        context = {}
        instance_id = 12345
        username = 'test_user'
        region = 'ORD'
        instance = mock.Mock()
        instance.delete_user = mock.Mock()
        api = mock.Mock()
        api.get = mock.Mock(return_value=instance)
        mock_connect.return_value = api

        dbtasks.delete_user(context, instance_id, username, region)
        mock_connect.assert_called_with(context, region)

    def test_delete_user_api_success(self):
        context = {}
        instance_id = 12345
        username = 'test_user'
        region = 'ORD'
        instance = mock.Mock()
        instance.delete_user = mock.Mock()
        api = mock.Mock()
        api.get = mock.Mock(return_value=instance)

        dbtasks.delete_user(context, instance_id, username, region, api)
        api.get.assert_called_with(instance_id)
        instance.delete_user.assert_called_with(username)


class TestDeleteInstanceTask(unittest.TestCase):
    def setUp(self):
        self.context = {
            'deployment_id': '12345',
            'region': 'ORD',
            'resource_key': '0',
            'resource': {
                'instance': {
                    'id': '4321'
                },
                'hosts': []
            }
        }

    def test_delete_instance_no_dep_id(self):
        self.context.pop('deployment_id')
        self.assertRaisesRegexp(AssertionError, 'No deployment id in context',
                                dbtasks.delete_instance_task,
                                self.context)

    def test_delete_instance_no_region(self):
        self.context.pop('region')
        self.assertRaisesRegexp(AssertionError, 'No region defined in context',
                                dbtasks.delete_instance_task,
                                self.context)

    def test_delete_instance_no_resource_key(self):
        self.context.pop('resource_key')
        self.assertRaisesRegexp(AssertionError, 'No resource key in context',
                                dbtasks.delete_instance_task,
                                self.context)

    def test_delete_instance_no_resource(self):
        self.context.pop('resource')
        self.assertRaisesRegexp(AssertionError, 'No resource defined in '
                                'context', dbtasks.delete_instance_task,
                                self.context)

    @mock.patch.object(dbtasks.LOG, 'info')
    @mock.patch.object(dbtasks.resource_postback, 'delay')
    def test_no_instance_id_no_hosts(self, mock_postback, mock_logger):
        self.context['resource']['instance']['id'] = None
        expected = {'resources': {'0': {'status': 'DELETED'}}}
        results = dbtasks.delete_instance_task(self.context)
        self.assertEqual(results, None)
        mock_logger.assert_called_with(('Instance ID is not available for '
                                        'Database server Instance, skipping '
                                        'delete_instance_task for resource %s '
                                        'in deployment %s', ('0', '12345')))
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(dbtasks.resource_postback, 'delay')
    def test_no_instance_id_with_hosts(self, mock_postback):
        self.context['resource']['instance']['id'] = None
        self.context['resource']['hosts'] = ['1', '2']
        expected = {
            'resources': {
                '1': {
                    'status': 'DELETED'
                },
                '0': {
                    'status': 'DELETED'
                },
                '2': {
                    'status': 'DELETED'
                }
            }
        }
        dbtasks.delete_instance_task(self.context)
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(dbtasks.resource_postback, 'delay')
    def test_simulation_no_hosts(self, mock_postback):
        self.context['simulation'] = True
        expected = {'resources': {'0': {'status': 'DELETED'}}}
        results = dbtasks.delete_instance_task(self.context)
        self.assertEqual(results, expected)
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(dbtasks.resource_postback, 'delay')
    def test_simulation_with_hosts(self, mock_postback):
        self.context['simulation'] = True
        self.context['resource']['hosts'] = ['1', '2']
        expected = {
            'resources': {
                '0': {'status': 'DELETED'},
                '1': {'status': 'DELETED', 'status-message': ''},
                '2': {'status': 'DELETED', 'status-message': ''},
            }
        }
        results = dbtasks.delete_instance_task(self.context)
        self.assertEqual(results, expected)
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(dbtasks.LOG, 'info')
    @mock.patch.object(dbtasks.resource_postback, 'delay')
    @mock.patch.object(provider.Provider, 'connect')
    def test_no_api_no_hosts_success(self, mock_connect, mock_postback,
                                     mock_logger):
        api = mock.Mock()
        api.delete = mock.Mock()
        mock_connect.return_value = api
        expected = {'resources': {'0': {'status': 'DELETING'}}}
        results = dbtasks.delete_instance_task(self.context)
        self.assertEqual(results, expected)
        mock_connect.assert_called_with(self.context, self.context['region'])
        api.delete.assert_called_with(
            self.context['resource']['instance']['id'])
        mock_logger.assert_called_with('Database instance %s deleted.', '4321')
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(dbtasks.resource_postback, 'delay')
    @mock.patch.object(dbtasks.delete_instance_task, 'retry')
    def test_api_client_exception_400(self, mock_retry, mock_postback):
        api = mock.Mock()
        mock_exception = pyrax.exceptions.NotFound(code='400')
        api.delete = mock.MagicMock(side_effect=mock_exception)
        dbtasks.delete_instance_task(self.context, api)
        mock_retry.assert_called_with(exc=mock_exception)

    @mock.patch.object(dbtasks.resource_postback, 'delay')
    def test_api_client_exception_404_no_hosts(self, mock_postback):
        api = mock.Mock()
        mock_exception = pyrax.exceptions.NotFound(code='404')
        api.delete = mock.MagicMock(side_effect=mock_exception)
        expected = {
            'resources': {
                '0': {
                    'status': 'DELETED',
                    'status-message': ''
                }
            }
        }
        results = dbtasks.delete_instance_task(self.context, api)
        self.assertEqual(results, expected)
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(dbtasks.resource_postback, 'delay')
    def test_api_client_exception_404_with_hosts(self, mock_postback):
        self.context['resource']['hosts'] = ['1', '2']
        api = mock.Mock()
        mock_exception = pyrax.exceptions.NotFound(code='404')
        api.delete = mock.MagicMock(side_effect=mock_exception)
        expected = {
            'resources': {
                '0': {'status': 'DELETED', 'status-message': ''},
                '1': {'status': 'DELETED', 'status-message': ''},
                '2': {'status': 'DELETED', 'status-message': ''},
            }
        }
        results = dbtasks.delete_instance_task(self.context, api)
        self.assertEqual(results, expected)
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(dbtasks.resource_postback, 'delay')
    @mock.patch.object(dbtasks.delete_instance_task, 'retry')
    def test_api_client_exception_retry(self, mock_retry, mock_postback):
        api = mock.Mock()
        mock_exception = Exception('retry')
        api.delete = mock.MagicMock(side_effect=mock_exception)
        dbtasks.delete_instance_task(self.context, api)
        mock_retry.assert_called_with(exc=mock_exception)


class TestWaitOnDelInstance(unittest.TestCase):
    def setUp(self):
        self.context = {
            'deployment_id': '1234',
            'region': 'DFW',
            'resource_key': '4',
            'resource': {
                'instance': {
                    'id': '4321'
                },
                'hosts': []
            }
        }

    def test_region_assert(self):
        self.context.pop('region')
        self.assertRaisesRegexp(AssertionError, 'No region defined in context',
                                dbtasks.wait_on_del_instance,
                                self.context)

    def test_resource_key_assert(self):
        self.context.pop('resource_key')
        self.assertRaisesRegexp(AssertionError, 'No resource key in context',
                                dbtasks.wait_on_del_instance,
                                self.context)

    def test_resource_assert(self):
        self.context.pop('resource')
        self.assertRaisesRegexp(AssertionError, 'No resource defined in '
                                'context', dbtasks.wait_on_del_instance,
                                self.context)

    @mock.patch.object(dbtasks.LOG, 'info')
    @mock.patch.object(dbtasks.resource_postback, 'delay')
    def test_no_instance_id(self, mock_postback, mock_logger):
        self.context['resource']['instance']['id'] = None
        message = ('Instance ID is not available for Database, skipping '
                   'wait_on_delete_instance_task for resource 4 in deployment '
                   '1234')
        expected = {
            'resources': {
                '4': {
                    'status': 'DELETED',
                    'status-message': message
                }
            }
        }
        results = dbtasks.wait_on_del_instance(self.context)
        self.assertEqual(results, None)
        mock_logger.assert_called_with('Instance ID is not available for '
                                       'Database, skipping '
                                       'wait_on_delete_instance_task for '
                                       'resource 4 in deployment 1234')
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(dbtasks.LOG, 'info')
    @mock.patch.object(dbtasks.resource_postback, 'delay')
    def test_simulation(self, mock_postback, mock_logger):
        self.context['simulation'] = True
        message = ('Instance ID is not available for Database, skipping '
                   'wait_on_delete_instance_task for resource 4 in deployment '
                   '1234')
        expected = {
            'resources': {
                '4': {
                    'status': 'DELETED',
                    'status-message': message
                }
            }
        }
        results = dbtasks.wait_on_del_instance(self.context)
        self.assertEqual(results, None)
        mock_logger.assert_called_with('Instance ID is not available for '
                                       'Database, skipping '
                                       'wait_on_delete_instance_task for '
                                       'resource 4 in deployment 1234')
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(dbtasks.resource_postback, 'delay')
    @mock.patch.object(provider.Provider, 'connect')
    def test_no_api_get_client_exception_no_hosts(self, mock_connect,
                                                  mock_postback):
        api = mock.Mock()
        mock_exception = pyrax.exceptions.NotFound(code='404')
        api.get = mock.MagicMock(side_effect=mock_exception)
        mock_connect.return_value = api
        expected = {
            'resources': {
                '4': {
                    'status': 'DELETED',
                    'status-message': ''
                }
            }
        }
        results = dbtasks.wait_on_del_instance(self.context)
        self.assertEqual(results, expected)
        mock_connect.assert_called_with(self.context, self.context['region'])
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(dbtasks.resource_postback, 'delay')
    def test_api_instance_status_deleted_with_hosts(self, mock_res_postback):
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'DELETED'
        api.get = mock.Mock(return_value=instance)
        self.context['resource']['hosts'] = ['2', '3']
        expected = {
            'resources': {
                '3': {
                    'status': 'DELETED',
                    'status-message': ''
                },
                '2': {
                    'status': 'DELETED',
                    'status-message': ''
                },
                '4': {
                    'status': 'DELETED',
                    'status-message': ''
                }
            }
        }
        results = dbtasks.wait_on_del_instance(self.context, api=api)
        self.assertEqual(results, expected)
        api.get.assert_called_with(self.context['resource']['instance']['id'])
        mock_res_postback.assert_called_with(self.context['deployment_id'],
                                             expected)

    @mock.patch.object(dbtasks.wait_on_del_instance, 'retry')
    @mock.patch.object(dbtasks.resource_postback, 'delay')
    def test_api_task_retry(self, mock_postback, mock_retry):
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'ACTIVE'
        api.get = mock.Mock(return_value=instance)
        expected = {
            'resources': {
                '4': {
                    'status': 'DELETING',
                    'status-message': 'Waiting on state DELETED. Instance 4 '
                                      'is in state ACTIVE'
                }
            }
        }
        dbtasks.wait_on_del_instance(self.context, api)
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)
        assert mock_retry.called


class TestCreateDatabase(unittest.TestCase):
    def setUp(self):
        self.context = middleware.RequestContext(**{
            'resource_key': '2',
            'deployment_id': '0',
            'region': 'ORD'
        })
        self.name = 'test_database'
        self.region = 'ORD'
        self.instance_id = '12345'

    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(dbtasks.create_database.provider, 'connect')
    def test_create_database_sim_no_instance_id(self, mock_connect,
                                                mock_postback,
                                                mock_reset_failed_task):
        self.context.simulation = True
        expected = {
            'resources': {
                '2': {
                    'instance': {
                        'status': 'BUILD',
                        'host_instance': self.instance_id,
                        'host_region': self.region,
                        'flavor': '1',
                        'id': self.name,
                        'interfaces': {
                            'mysql': {
                                'database_name': self.name,
                                'host': 'srv2.rackdb.net'
                            }
                        },
                        'name': 'test_database'
                    },
                    'status': 'BUILD'
                }
            }
        }

        results = dbtasks.create_database(self.context, self.name, self.region,
                                          instance_id=self.instance_id)
        self.assertEqual(expected, results)

    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(dbtasks.create_database.provider, 'connect')
    def test_create_database_sim_instance_id(self, mock_connect,
                                             mock_postback,
                                             mock_reset_failed_task):
        self.context.simulation = True
        expected = {
            'resources': {
                '2': {
                    'instance': {
                        'id': self.name,
                        'flavor': '1',
                        'status': 'BUILD',
                        'host_instance': self.instance_id,
                        'host_region': self.region,
                        'interfaces': {
                            'mysql': {
                                'database_name': self.name,
                                'host': 'srv2.rackdb.net'
                            }
                        },
                        'name': 'test_database'
                    },
                    'status': 'BUILD',
                }
            }
        }

        results = dbtasks.create_database(self.context, self.name, self.region,
                                          instance_id=self.instance_id)
        self.assertEqual(expected, results)

    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(manager.Manager, 'wait_on_build')
    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(manager.Manager, 'create_instance')
    @mock.patch.object(dbtasks.create_database.provider, 'connect')
    def test_create_databaseno_api_no_iid_no_attrs(self, mock_connect,
                                                   mock_create,
                                                   mock_reset, mock_wob,
                                                   mock_postback):
        instance = {
            'id': '12345',
            'databases': {
                self.name: {},
            },
            'region': 'ORD',
            'status': 'BUILD'
        }

        expected = {
            'resources': {
                '2': {
                    'instance': {
                        'flavor': '1',
                        'disk': 1,
                        'host_instance': '12345',
                        'host_region': 'ORD'
                    }
                }
            }
        }

        mock_create.return_value = instance
        mock_wob.return_value = {'status': 'ACTIVE'}

        results = dbtasks.create_database(self.context, self.name, self.region)

        mock_connect.assert_called_once_with(self.context)

        mock_create.assert_called_once_with(
            self.name+'_instance', '1', 1,
            [{'name': self.name}],
            self.context,
            mock_connect.return_value,
            dbtasks.create_database.partial
        )

        mock_wob.assert_called_once_with(
            '12345', mock_connect.return_value,
            dbtasks.create_database.partial
        )
        self.assertEqual(expected, results)

    # pylint: disable=R0913
    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(manager.Manager, 'wait_on_build')
    @mock.patch.object(manager.Manager, 'create_instance')
    @mock.patch.object(dbtasks.create_database.provider, 'connect')
    def test_create_database_no_api_no_iid_no_attrs_charset(self, mock_connect,
                                                            mock_create,
                                                            mock_wob,
                                                            mock_postback,
                                                            mock_reset):
        instance = {
            'id': '12345',
            'databases': {
                self.name: {'character_set': 'latin'},
            },
            'region': 'ORD',
            'status': 'BUILD'
        }

        expected = {
            'resources': {
                '2': {
                    'instance': {
                        'character_set': 'latin',
                        'flavor': '1',
                        'disk': 1,
                        'host_instance': '12345',
                        'host_region': 'ORD'
                    }
                }
            }
        }

        mock_create.return_value = instance
        mock_wob.return_value = {'status': 'ACTIVE'}

        results = dbtasks.create_database(self.context, self.name, self.region,
                                          character_set='latin')

        mock_connect.assert_called_once_with(self.context)

        mock_create.assert_called_with(self.name+'_instance', '1', 1,
                                       [{'name': self.name,
                                         'character_set': 'latin'}],
                                       self.context, mock_connect.return_value,
                                       dbtasks.create_database.partial)

        mock_wob.assert_called_once_with(
            '12345', mock_connect.return_value,
            dbtasks.create_database.partial
        )
        self.assertEqual(expected, results)

    # pylint: disable=R0913
    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(manager.Manager, 'wait_on_build')
    @mock.patch.object(manager.Manager, 'create_instance')
    @mock.patch.object(dbtasks.create_database.provider, 'connect')
    def test_create_database_no_api_no_iid_no_attrs_collate(self, mock_connect,
                                                            mock_create,
                                                            mock_wob,
                                                            mock_postback,
                                                            mock_reset):
        instance = {
            'id': '12345',
            'databases': {
                self.name: {'collate': True},
            },
            'region': 'ORD',
            'status': 'BUILD'
        }

        expected = {
            'resources': {
                '2': {
                    'instance': {
                        'collate': True,
                        'flavor': '1',
                        'disk': 1,
                        'host_instance': '12345',
                        'host_region': 'ORD'
                    }
                }
            }
        }

        mock_create.return_value = instance
        mock_wob.return_value = {'status': 'ACTIVE'}

        results = dbtasks.create_database(self.context, self.name, self.region,
                                          character_set='latin')

        mock_connect.assert_called_once_with(self.context)

        mock_create.assert_called_with(self.name+'_instance', '1', 1,
                                       [{'name': self.name,
                                         'character_set': 'latin'}],
                                       self.context, mock_connect.return_value,
                                       dbtasks.create_database.partial)

        mock_wob.assert_called_once_with(
            '12345', mock_connect.return_value,
            dbtasks.create_database.partial
        )
        self.assertEqual(expected, results)

    # pylint: disable=R0913
    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(manager.Manager, 'wait_on_build')
    @mock.patch.object(manager.Manager, 'create_instance')
    @mock.patch.object(dbtasks.create_database.provider, 'connect')
    def test_create_database_no_api_no_iid_with_attrs(self, mock_connect,
                                                      mock_create, mock_wob,
                                                      mock_postback,
                                                      mock_reset):
        instance = {
            'id': '12345',
            'databases': {
                self.name: {},
            },
            'region': 'ORD',
            'status': 'BUILD'
        }

        expected = {
            'resources': {
                '2': {
                    'instance': {
                        'flavor': '3',
                        'disk': 5,
                        'host_instance': '12345',
                        'host_region': 'ORD'
                    }
                }
            }
        }
        attrs = {'flavor': '3', 'size': 5}
        mock_create.return_value = instance
        mock_wob.return_value = {'status': 'ACTIVE'}

        results = dbtasks.create_database(self.context, self.name, self.region,
                                          instance_attributes=attrs)

        mock_connect.assert_called_once_with(self.context)

        mock_create.assert_called_with(self.name+'_instance', '3', 5,
                                       [{'name': self.name}], self.context,
                                       mock_connect.return_value,
                                       dbtasks.create_database.partial)

        mock_wob.assert_called_once_with(
            '12345', mock_connect.return_value,
            dbtasks.create_database.partial
        )
        self.assertEqual(expected, results)

    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(dbtasks.create_database, 'retry')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(dbtasks.create_database.provider, 'connect')
    def test_instance_not_active_retry(self, mock_connect, mock_postback,
                                       mock_retry, mock_reset):
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'BUILD'
        api.get = mock.Mock(return_value=instance)
        mock_connect.return_value = api
        expected = {
            'resources': {
                '2': {
                    'status': 'BUILD',
                    'instance': {'status': 'BUILD'}
                }
            }
        }
        dbtasks.create_database(self.context, self.name, self.region,
                                instance_id=self.instance_id, api=api)
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)
        assert mock_retry.called

    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(dbtasks.create_database.provider, 'connect')
    @mock.patch.object(manager.LOG, 'info')
    @mock.patch.object(tasks, 'postback')
    def test_success_char_set(self, mock_postback, mock_logger,
                              mock_connect, mock_reset):
        api = mock.Mock()
        instance = mock.Mock()
        instance.id = self.instance_id
        instance.name = self.name
        instance.status = 'ACTIVE'
        instance.hostname = 'test_hostname'
        instance.flavor = mock.Mock()
        instance.flavor.id = '2'
        instance.create_database = mock.Mock()
        api.get = mock.Mock(return_value=instance)
        mock_connect.return_value = api
        expected = {
            'resources': {
                '2': {
                    'instance': {
                        'name': 'test_database',
                        'interfaces': {
                            'mysql': {
                                'host': 'test_hostname',
                                'database_name': 'test_database'
                            }
                        },
                        'host_instance': '12345',
                        'flavor': '2',
                        'id': self.name,
                        'host_region': 'ORD',
                        'status': 'BUILD'
                    },
                    'status': 'BUILD'
                }
            }
        }
        results = dbtasks.create_database(self.context, self.name, self.region,
                                          character_set='latin',
                                          instance_id=self.instance_id,
                                          api=api)
        self.assertEqual(results, expected)
        instance.create_database.assert_called_with(self.name, 'latin', None)
        mock_logger.assert_called_with('Created database %s on instance %s',
                                       'test_database', '12345')
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(manager.LOG, 'exception')
    @mock.patch.object(dbtasks.create_database.provider, 'connect')
    @mock.patch.object(tasks, 'postback')
    def test_client_exception_400(self, mock_postback, mock_connect,
                                  mock_logger, mock_reset):
        api = mock.Mock()
        mock_exception = pyrax.exceptions.ClientException(code='400')
        instance = mock.Mock()
        instance.status = 'ACTIVE'
        instance.create_database = mock.MagicMock(side_effect=mock_exception)
        api.get = mock.Mock(return_value=instance)
        mock_connect.return_value = api
        self.assertRaises(pyrax.exceptions.ClientException,
                          dbtasks.create_database, self.context,
                          self.name, self.region, instance_id=self.instance_id,
                          api=api)
        mock_logger.assert_called_with(mock_exception)

    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(manager.LOG, 'exception')
    @mock.patch.object(dbtasks.create_database.provider, 'connect')
    @mock.patch.object(tasks, 'postback')
    def test_client_exception_not_400(self, mock_postback,
                                      mock_connect,
                                      mock_logger, mock_reset):
        api = mock.Mock()
        mock_exception = pyrax.exceptions.ClientException(code='402')
        instance = mock.Mock()
        instance.status = 'ACTIVE'
        instance.create_database = mock.MagicMock(side_effect=mock_exception)
        api.get = mock.Mock(return_value=instance)
        mock_connect.return_value = api
        self.assertRaises(exceptions.CheckmateException,
                          dbtasks.create_database, self.context,
                          self.name, self.region, instance_id=self.instance_id,
                          api=api)
        mock_logger.assert_called_with(mock_exception)

    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(dbtasks.create_database.provider, 'connect')
    @mock.patch.object(tasks, 'postback')
    def test_exception_on_create_database(self, mock_postback, mock_connect,
                                          mock_reset):
        api = mock.Mock()
        mock_exception = Exception('testing')
        instance = mock.Mock()
        instance.status = 'ACTIVE'
        instance.create_database = mock.MagicMock(side_effect=mock_exception)
        api.get = mock.Mock(return_value=instance)
        mock_connect.return_value = api
        self.assertRaises(exceptions.CheckmateException,
                          dbtasks.create_database, self.context,
                          self.name, self.region, instance_id=self.instance_id,
                          api=api)

    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(manager.LOG, 'info')
    @mock.patch.object(manager.Manager, 'wait_on_build')
    @mock.patch.object(manager.Manager, 'create_instance')
    def test_no_instance_id_wob_resumable(self, mock_create, mock_wob,
                                          mock_logger, mock_reset):
        data = {'status': 'BUILD'}
        mock_create.return_value = data
        mock_logger.side_effect = Exception('testing')
        mock_wob.side_effect = exceptions.CheckmateException(
            '', options=exceptions.CAN_RESUME)
        self.assertRaisesRegexp(Exception, 'testing',
                                dbtasks.create_database, self.context,
                                self.name, self.region, api='api')


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
