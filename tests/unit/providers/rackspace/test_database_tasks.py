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

"""Unit Tests for the Rackspace Provider's database tasks."""

import functools
import logging
import mock
import unittest

from checkmate.deployments import tasks
from checkmate import exceptions
from checkmate import middleware
from checkmate.providers.rackspace import base
from checkmate.providers.rackspace.database import dbaas
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
                        'interfaces': {
                            'mysql': {
                                'host': 'mysql0.rax.net',
                                'port': 3306,
                            }
                        },
                        'id': 'MYSQL0'
                    },
                    'status': 'BUILD'
                }
            }
        }
        desired_state = {
            'flavor': '1',
            'disk': '1',
        }
        results = dbtasks.create_instance(
            context, 'test_instance', desired_state)
        self.assertEqual(results, expected)
        partial.assert_called_with({'id': 'MYSQL0'})
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
                        'id': 'MYSQL0',
                        'databases': [
                            {'name': 'db1'},
                            {'name': 'db2'}
                        ],
                        'flavor': 1,
                        'disk': 2,
                        'interfaces': {
                            'mysql': {
                                'host': 'mysql0.rax.net',
                                'port': 3306,
                            }
                        }
                    },
                    'status': 'BUILD'
                }
            }
        }
        desired_state = {
            'flavor': '1',
            'disk': '2',
            'databases': [{'name': 'db1'}, {'name': 'db2'}]
        }
        results = dbtasks.create_instance(
            context, 'test_instance', desired_state)
        self.assertEqual(results, expected_result)
        partial.assert_called_with({'id': 'MYSQL0'})
        mock_postback.assert_called_with(
            context['deployment_id'], expected_result)

    @unittest.skip('Failing after refactoring Pyrax out of create_instance')
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
                        'flavor': 1,
                        'disk': 1,
                        'interfaces': {
                            'mysql': {
                                'host': 'test.hostname',
                            }
                        }
                    },
                    'status': 'BUILD'
                }
            }
        }
        api.create = mock.Mock(return_value=instance)
        desired_state = {'flavor': 1, 'disk': 1}

        results = dbtasks.create_instance(context, 'test_instance',
                                          desired_state)

        mock_provider.connect.assert_called_with(context)
        api.create.assert_called_with('test_instance', flavor=1, volume=1,
                                      databases=[])
        partial.assert_called_with({'id': 1234})
        mock_postback.assert_called_with(context['deployment_id'], expected)
        self.assertEqual(results, expected)

    @unittest.skip('Failing after refactoring Pyrax out of create_instance')
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
                                'host': 'test.hostname',
                            }
                        }
                    },
                    'status': 'BUILD',
                }
            }
        }
        api.create = mock.Mock(return_value=instance)
        desired_state = {'flavor': 1, 'disk': 1, 'databases': databases}

        results = dbtasks.create_instance(context, 'test_instance',
                                          desired_state)

        mock_provider.connect.assert_called_with(context)
        api.create.assert_called_with('test_instance', volume=1, flavor=1,
                                      databases=databases)
        partial.assert_called_with({'id': 1234})
        mock_postback.assert_called_with(context['deployment_id'], expected)
        self.assertEqual(results, expected)

    @unittest.skip('Failing after refactoring Pyrax out of create_instance')
    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    def test_create_instance_invalid_api(self, mock_reset):
        context = {'resource': '0', 'deployment_od': 0}
        context = middleware.RequestContext(**context)
        desired_state = {'flavor': 1, 'disk': 1, 'simulate': True}
        try:
            dbtasks.create_instance(context, 'test_instance', desired_state)
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

    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_add_user_sim(self, mock_connect, mock_postback):
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

        mock_postback.assert_called_with(
            self.context['deployment_id'], expected)
        self.assertEqual(results, expected)

    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_instance_status_exc_retry(self, mock_connect, mock_get,
                                       mock_postback):
        mock_get.return_value = {
            'instance': {'status': 'ERROR', 'id': self.instance_id}
        }
        expected = {
            'resources': {
                '0': {
                    'status': 'ERROR',
                    'instance': {'status': 'ERROR'}
                }
            }
        }
        self.assertRaisesRegexp(exceptions.CheckmateException,
                                'Database instance is not active.',
                                dbtasks.add_user, self.context,
                                self.instance_id, self.databases,
                                self.username, self.password)
        mock_connect.assert_called()
        mock_get.assert_called_with(self.context, self.instance_id)
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(dbaas, 'create_user',
                       side_effect=Exception())
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_instance_create_user_exc_retry(self, mock_connect, mock_get,
                                            mock_create, mock_partial):
        mock_get.return_value = {
            'instance': {'status': 'ACTIVE', 'id': self.instance_id}
        }
        create_user_info = {
            'password': 'test_pass',
            'name': 'test_user',
            'databases': [{'name': 'blah'}]
        }
        self.assertRaisesRegexp(exceptions.CheckmateException, '',
                                dbtasks.add_user, self.context,
                                self.instance_id, self.databases,
                                self.username, self.password)
        mock_connect.assert_called()
        mock_get.assert_called_with(self.context, self.instance_id)
        mock_create.assert_called_with(self.context, self.instance_id,
                                       create_user_info)
        mock_partial.assert_called()

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(dbaas, 'create_user',
                       side_effect=dbaas.CDBException())
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_instance_create_user_gen_exc(self, mock_connect, mock_get,
                                          mock_create, mock_partial):
        mock_get.return_value = {
            'instance': {'status': 'ACTIVE', 'id': self.instance_id}
        }
        create_user_info = {
            'password': 'test_pass',
            'name': 'test_user',
            'databases': [{'name': 'blah'}]
        }
        self.assertRaises(exceptions.CheckmateException,
                          dbtasks.add_user, self.context,
                          self.instance_id, self.databases, self.username,
                          self.password)
        mock_connect.assert_called()
        mock_get.assert_called_with(self.context, self.instance_id)
        mock_create.assert_called_with(self.context, self.instance_id,
                                       create_user_info)
        mock_partial.assert_called()

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(dbaas, 'create_user')
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_add_user(self, mock_connect, mock_postback, mock_get, mock_create,
                      mock_partial):
        mock_get.return_value = {
            'instance': {
                'status': 'ACTIVE',
                'id': self.instance_id,
                'hostname': 'srv0.rackdb.net'
            }
        }
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
        create_user_info = {
            'password': 'test_pass',
            'name': 'test_user',
            'databases': [{'name': 'blah'}]
        }
        results = dbtasks.add_user(self.context, self.instance_id,
                                   self.databases, self.username,
                                   self.password)
        self.assertEqual(results, expected)
        mock_connect.assert_called()
        mock_postback.assert_called_with('0', expected)
        mock_get.assert_called_with(self.context, self.instance_id)
        mock_create.assert_called_with(self.context, self.instance_id,
                                       create_user_info)
        mock_partial.assert_called()


class TestDeleteDatabaseItems(unittest.TestCase):

    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_delete_database_no_instance_host_instance(self, mock_connect,
                                                       mock_delay, mock_get):
        context = {
            'region': 'ORD',
            'resource': {
                'index': '1'
            },
            'deployment_id': '123',
            'resource_key': '1'
        }
        message = ('Cannot find instance/host-instance for database to '
                   'delete. Skipping delete_database call for resource 1 in '
                   'deployment 123 - Instance Id: None, Host Instance Id: '
                   'None')
        expected = {
            'resources': {
                '1': {
                    'status': 'DELETED',
                    'status-message': message
                }
            }
        }
        results = dbtasks.delete_database(context, '123', expected, '1')
        self.assertEqual(results, None)
        mock_connect.assert_called()
        mock_delay.assert_called_with('123', expected)

    @mock.patch.object(dbaas, 'get_instance',
                       side_effect=dbaas.CDBException('Some error'))
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_delete_database_api_get_exception(self, mock_connect, mock_get):
        deployment_id = '123'
        resource = {
            'index': '1',
            'instance': {
                'name': 'test_name',
                'host_instance': '2'
            },
            'host_instance': '2'
        }
        key = '1'
        context = middleware.RequestContext(**{
            'region': 'ORD',
            'resource': resource,
            'deployment_id': deployment_id,
            'resource_key': key
        })
        self.assertRaisesRegexp(dbaas.CDBException, 'Some error',
                                dbtasks.delete_database, context,
                                deployment_id, resource, key)
        mock_connect.assert_called()
        mock_get.assert_called_with(mock.ANY,
                                    context['resource']['host_instance'])

    @mock.patch.object(dbaas, 'get_instance',
                       side_effect=dbaas.CDBException('404 Not Found'))
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_delete_database_api_get_no_instance(self, mock_connect,
                                                 mock_postback, mock_delete):
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
        expected = {
            'resources': {
                '1': {
                    'status': 'DELETED',
                    'status-message': 'Host 3 was deleted'
                }
            }
        }
        results = dbtasks.delete_database(context, context['deployment_id'],
                                          context['resource'], '1')
        self.assertEqual(results, expected)
        mock_connect.assert_called()
        mock_postback.assert_called_with('123', expected)
        mock_delete.assert_called_with(mock.ANY,
                                       context['resource']['host_instance'])

    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_delete_database_api_get_instance_build(self, mock_connect,
                                                    mock_get):
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
        mock_get.return_value = {'instance': {'status': 'BUILD'}}

        self.assertRaisesRegexp(exceptions.CheckmateException, 'Waiting on '
                                'instance to be out of BUILD status',
                                dbtasks.delete_database, context,
                                context['deployment_id'], context['resource'],
                                '1')
        mock_connect.assert_called()

    @mock.patch.object(dbtasks.delete_database, 'retry')
    @mock.patch.object(dbaas, 'delete_database',
                       side_effect=dbaas.CDBException('400'))
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_delete_database_api_delete_exception_retry(self, mock_connect,
                                                        mock_postback,
                                                        mock_delay, mock_get,
                                                        mock_delete,
                                                        mock_retry):
        mock_get.return_value = {'instance': {'status': 'ACTIVE'}}
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
        dbtasks.delete_database(context,
                                context['deployment_id'], context['resource'],
                                context['resource_key'])
        mock_connect.assert_called()
        mock_postback.assert_called_with(
            '123', {'resources': {'1': {'status': 'DELETED'}}})
        mock_delay.assert_called_with(
            '123', {'resources': {'1': {'status': 'DELETED'}}})
        mock_get.assert_called_with(mock.ANY,
                                    context['resource']['host_instance'])
        mock_delete.assert_called_with(mock.ANY,
                                       context['resource']['host_instance'],
                                       context['resource']['instance']['name'])
        mock_retry.assert_called()

    @mock.patch.object(dbaas, 'delete_database')
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_delete_database_success(self, mock_connect, mock_postback,
                                     mock_delay, mock_get, mock_delete):
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
        expected = {'resources': {'1': {'status': 'DELETED'}}}
        mock_get.return_value = {'instance': {'status': 'ACTIVE'}}

        results = dbtasks.delete_database(context, context['deployment_id'],
                                          context['resource'],
                                          context['resource_key'])
        self.assertEqual(results, expected)
        mock_connect.assert_called()
        mock_postback.assert_called_with(context['deployment_id'], expected)
        mock_delay.assert_called()
        mock_get.assert_called_with(mock.ANY,
                                    context['resource']['host_instance'])
        mock_delete.assert_called_with(mock.ANY,
                                       context['resource']['host_instance'],
                                       context['resource']['instance']['name'])

    @mock.patch.object(dbaas, 'delete_user')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_delete_user_api_success(self, mock_connect, mock_delete):
        context = {}
        instance_id = 12345
        username = 'test_user'

        dbtasks.delete_user(context, instance_id, username)
        mock_connect.assert_called()
        mock_delete.assert_called_with(mock.ANY, instance_id, username)


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

    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_no_instance_id_no_hosts(self, mock_connect, mock_delay):
        self.context['resource']['instance']['id'] = None
        expected = {'resources': {'0': {'status': 'DELETED'}}}
        results = dbtasks.delete_instance_task(self.context,
                                               self.context['deployment_id'],
                                               self.context['resource'],
                                               '0')
        self.assertEqual(results, None)
        mock_connect.assert_called()
        mock_delay.assert_called_with(self.context['deployment_id'],
                                      expected)

    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_no_instance_id_with_hosts(self, mock_connect, mock_delay):
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
        dbtasks.delete_instance_task(self.context,
                                     self.context['deployment_id'],
                                     self.context['resource'],
                                     '0')
        mock_connect.assert_called()
        mock_delay.assert_called_with('12345', expected)

    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_simulation_no_hosts(self, mock_connect, mock_postback,
                                 mock_delay):
        self.context['simulation'] = True
        expected = {'resources': {'0': {'status': 'DELETED'}}}
        results = dbtasks.delete_instance_task(self.context,
                                               self.context['deployment_id'],
                                               self.context['resource'],
                                               '0')
        self.assertEqual(results, expected)
        mock_connect.assert_called()
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)
        mock_delay.assert_called_with(self.context['deployment_id'],
                                      expected)

    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_simulation_with_hosts(self, mock_connect, mock_postback,
                                   mock_delay):
        self.context['simulation'] = True
        self.context['resource']['hosts'] = ['1', '2']
        expected = {
            'resources': {
                '0': {'status': 'DELETED'},
                '1': {'status': 'DELETED', 'status-message': ''},
                '2': {'status': 'DELETED', 'status-message': ''},
            }
        }
        results = dbtasks.delete_instance_task(self.context,
                                               self.context['deployment_id'],
                                               self.context['resource'],
                                               '0')
        self.assertEqual(results, expected)
        mock_connect.assert_called()
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)
        mock_delay.assert_called_with(self.context['deployment_id'],
                                      expected)

    @mock.patch.object(dbaas, 'delete_instance')
    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_no_api_no_hosts_success(self, mock_connect, mock_postback,
                                     mock_delay, mock_delete):
        expected = {'resources': {'0': {'status': 'DELETING'}}}
        results = dbtasks.delete_instance_task(self.context,
                                               self.context['deployment_id'],
                                               self.context['resource'],
                                               '0')
        self.assertEqual(results, expected)
        mock_connect.assert_called()
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)
        mock_delay.assert_called_with(self.context['deployment_id'], expected)
        mock_delete.assert_called_with(
            mock.ANY, self.context['resource']['instance']['id'])

    @mock.patch.object(dbaas, 'delete_instance',
                       side_effect=dbaas.CDBException('400'))
    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(dbtasks.delete_instance_task, 'retry')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_api_client_exception_400(self, mock_connect, mock_retry,
                                      mock_delay, mock_delete):
        dbtasks.delete_instance_task(self.context,
                                     self.context['deployment_id'],
                                     self.context['resource'],
                                     '0')
        mock_connect.assert_called()
        mock_retry.assert_called()
        mock_delay.assert_called_with('12345', {})
        mock_delete.assert_called_with(mock.ANY, '4321')

    @mock.patch.object(dbaas, 'delete_instance',
                       side_effect=dbaas.CDBException('404 Not Found'))
    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_api_client_exception_404_no_hosts(self, mock_connect,
                                               mock_postback, mock_delay,
                                               mock_delete):
        expected = {
            'resources': {
                '0': {
                    'status': 'DELETED',
                    'status-message': ''
                }
            }
        }
        results = dbtasks.delete_instance_task(self.context,
                                               self.context['deployment_id'],
                                               self.context['resource'],
                                               '0')
        self.assertEqual(results, expected)
        mock_connect.assert_called()
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)
        mock_delay.assert_called_with(self.context['deployment_id'],
                                      expected)
        mock_delete.assert_called_with(mock.ANY, '4321')

    @mock.patch.object(dbaas, 'delete_instance',
                       side_effect=dbaas.CDBException('404 Not Found'))
    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_api_client_exception_404_with_hosts(self, mock_connect,
                                                 mock_postback, mock_delay,
                                                 mock_delete):
        self.context['resource']['hosts'] = ['1', '2']
        expected = {
            'resources': {
                '0': {'status': 'DELETED', 'status-message': ''},
                '1': {'status': 'DELETED', 'status-message': ''},
                '2': {'status': 'DELETED', 'status-message': ''},
            }
        }
        results = dbtasks.delete_instance_task(self.context,
                                               self.context['deployment_id'],
                                               self.context['resource'],
                                               '0')
        self.assertEqual(results, expected)
        mock_connect.assert_called()
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)
        mock_delay.assert_called_with(self.context['deployment_id'],
                                      expected)
        mock_delete.assert_called_with(mock.ANY, '4321')

    @mock.patch.object(dbaas, 'delete_instance',
                       side_effect=dbaas.CDBException)
    @mock.patch.object(tasks.resource_postback, 'delay')
    @mock.patch.object(dbtasks.delete_instance_task, 'retry')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_api_client_exception_retry(self, mock_connect, mock_retry,
                                        mock_postback, mock_delete):
        dbtasks.delete_instance_task(self.context,
                                     self.context['deployment_id'],
                                     self.context['resource'],
                                     '0')
        mock_connect.assert_called()
        mock_retry.assert_called()
        mock_postback.assert_called_with('12345', {})
        mock_delete.assert_called_with(mock.ANY, '4321')


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
                'hosts': [],
                'type': 'compute',
            }
        }

    @mock.patch.object(dbtasks, 'wait_on_status',
                       side_effect=dbaas.CDBException('Mock Error'))
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_no_instance_id(self, mock_connect, mock_wait):
        with self.assertRaises(dbaas.CDBException) as expected:
            dbtasks.wait_on_status(self.context)
        self.assertEqual('Mock Error', expected.exception.message)

    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_simulation(self, mock_connect, mock_postback):
        context = middleware.RequestContext(simulation=True, **self.context)
        expected = {
            'resources': {
                '4': {
                    'status': 'ACTIVE',
                    'instance': {'status': 'ACTIVE', 'status-message': ''}
                }
            }
        }
        results = dbtasks.wait_on_status(context)
        self.assertEqual(results, expected)

    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    @mock.patch.object(tasks, 'postback')
    def test_api_instance_status_deleted_with_hosts(self, mock_postback,
                                                    mock_connect, mock_get):
        self.context['resource']['hosts'] = ['2', '3']
        context = middleware.RequestContext(**self.context)
        mock_get.return_value = {'instance': {'status': 'DELETED'}}
        expected = {
            'resources': {
                #'3': {
                #    'status': 'DELETED',
                #    'status-message': ''
                #},
                #'2': {
                #    'status': 'DELETED',
                #    'status-message': ''
                #},
                '4': {
                    'status': 'DELETED',
                    'instance': {
                        'status': 'DELETED',
                        'status-message': ''
                    }
                }
            }
        }
        results = dbtasks.wait_on_status(context, instance={'id': 'blah'},
                                         status='DELETED')
        self.assertEqual(results, expected)
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)

    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    @mock.patch.object(dbtasks.wait_on_status, 'retry')
    @mock.patch.object(tasks, 'postback')
    def test_api_task_retry(self, mock_postback, mock_retry,
                            mock_connect, mock_get):
        context = middleware.RequestContext(**self.context)
        mock_get.return_value = {'instance': {'status': 'SHUTDOWN'}}
        expected = {
            'resources': {
                '4': {
                    'status': 'CONFIGURE',
                    'instance': {
                        'status': 'SHUTDOWN',
                        'status-message': 'DB instance in status SHUTDOWN. '
                                          'Waiting for status DELETED.'
                    }
                }
            }
        }
        dbtasks.wait_on_status(context, instance={'id': 'blah'},
                               status='DELETED')
        mock_postback.assert_called_with(self.context.get('deployment_id'),
                                         expected)
        mock_retry.assert_called()
        mock_connect.assert_called()
        mock_get.assert_called_with(context, 'blah')


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
                        'status': 'ACTIVE',
                        'host_instance': self.instance_id,
                        'host_region': self.region,
                        'flavor': '1',
                        'id': self.name,
                        'interfaces': {
                            'mysql': {
                                'database_name': self.name,
                                'host': 'srv2.rackdb.net',
                                'port': 3306,
                            }
                        },
                        'name': 'test_database'
                    },
                    'status': 'ACTIVE'
                }
            }
        }

        results = dbtasks.create_database(self.context, self.name, self.region,
                                          instance_id=self.instance_id)
        self.assertEqual(results, expected)

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
                        'status': 'ACTIVE',
                        'host_instance': self.instance_id,
                        'host_region': self.region,
                        'interfaces': {
                            'mysql': {
                                'database_name': self.name,
                                'host': 'srv2.rackdb.net',
                                'port': 3306,
                            }
                        },
                        'name': 'test_database'
                    },
                    'status': 'ACTIVE',
                }
            }
        }

        results = dbtasks.create_database(self.context, self.name, self.region,
                                          instance_id=self.instance_id)
        self.assertEqual(results, expected)

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(dbtasks.create_database, 'retry')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_instance_not_active_retry(self, mock_connect, mock_retry,
                                       mock_reset, mock_get,
                                       mock_partial):
        mock_get.return_value = {
            'instance': {'status': 'BUILD', 'id': self.instance_id}}
        dbtasks.create_database(self.context, self.name, self.region,
                                instance_id=self.instance_id)
        mock_retry.assert_called()

    @mock.patch.object(dbaas, 'create_database')
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(tasks, 'postback')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_success_char_set(self, mock_connect, mock_postback, mock_get,
                              mock_create):
        mock_get.return_value = {
            'instance': {
                'status': 'ACTIVE',
                'id': self.instance_id,
                'name': self.name,
                'hostname': 'test_hostname',
                'flavor': {'id': '2'},
                'port': 4000
            }
        }
        expected = {
            'resources': {
                '2': {
                    'instance': {
                        'name': 'test_database',
                        'interfaces': {
                            'mysql': {
                                'host': 'test_hostname',
                                'database_name': 'test_database',
                                'port': 4000,
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
        results = dbtasks.create_database(self.context, self.name,
                                          character_set='latin',
                                          instance_id=self.instance_id)
        self.assertEqual(results, expected)
        mock_postback.assert_called_with(self.context['deployment_id'],
                                         expected)
        mock_create.assert_called_with(
            self.context, self.instance_id,
            [{'name': self.name, 'character_set': 'latin'}]
        )

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(dbaas, 'create_database',
                       side_effect=dbaas.CDBException('400'))
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_client_exception_400(self, mock_connect, mock_get, mock_create,
                                  mock_partial):
        mock_get.return_value = {
            'instance': {'status': 'ACTIVE', 'id': self.instance_id}
        }
        self.assertRaises(dbaas.CDBException,
                          dbtasks.create_database, self.context,
                          self.name, instance_id=self.instance_id)
        mock_connect.assert_called()
        mock_get.assert_called_with(self.context, self.instance_id)
        mock_create.assert_called_with(self.context, self.instance_id,
                                       [{'name': 'test_database'}])
        mock_partial.assert_called()

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(dbaas, 'create_database',
                       side_effect=dbaas.CDBException('402'))
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_client_exception_not_400(self, mock_connect, mock_get,
                                      mock_create, mock_partial):
        mock_get.return_value = {
            'instance': {'status': 'ACTIVE', 'id': self.instance_id}
        }
        self.assertRaises(exceptions.CheckmateException,
                          dbtasks.create_database, self.context,
                          self.name, instance_id=self.instance_id)
        mock_connect.assert_called()
        mock_get.assert_called_with(self.context, self.instance_id)
        mock_create.assert_called_with(self.context, self.instance_id,
                                       [{'name': 'test_database'}])
        mock_partial.assert_called()

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(dbaas, 'create_database',
                       side_effect=dbaas.CDBException('Some error'))
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_exception_on_create_database(self, mock_connect, mock_get,
                                          mock_create, mock_partial):
        mock_get.return_value = {
            'instance': {'status': 'ACTIVE', 'id': self.instance_id}
        }
        self.assertRaises(exceptions.CheckmateException,
                          dbtasks.create_database, self.context,
                          self.name, instance_id=self.instance_id)
        mock_connect.assert_called()
        mock_get.assert_called_with(self.context, self.instance_id)
        mock_create.assert_called_with(self.context, self.instance_id,
                                       [{'name': 'test_database'}])
        mock_partial.assert_called()

    @mock.patch.object(functools, 'partial')
    @mock.patch.object(dbaas, 'get_instance')
    @mock.patch.object(base.RackspaceProviderBase, '_connect')
    def test_no_instance_wait_on_status_resumable(self, mock_conn, mock_get,
                                                  mock_partial):
        mock_get.return_value = {
            'instance': {'status': 'BUILD', 'id': self.instance_id}
        }
        self.assertRaisesRegexp(exceptions.CheckmateException,
                                'Database instance is not active.',
                                dbtasks.create_database, self.context,
                                self.name, instance_id=self.instance_id)
        mock_conn.assert_called()
        mock_get.assert_called_with(self.context, self.instance_id)
        mock_partial.assert_called()


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
