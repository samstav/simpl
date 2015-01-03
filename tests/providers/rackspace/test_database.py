# pylint: disable=C0103,W0212,R0904

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

"""Tests for Rackspace Database provider."""

import logging
import unittest

import mock
import mox

from checkmate import deployment
from checkmate.deployments import tasks
from checkmate import exceptions
from checkmate import middleware
from checkmate.providers import base
from checkmate.providers.rackspace.database import provider
from checkmate.providers.rackspace.database import tasks as dbtasks
from checkmate import test
from checkmate import utils
from checkmate import workflow as cm_wf
from checkmate import workflow_spec

LOG = logging.getLogger(__name__)


class TestDatabase(test.ProviderTester):
    def setUp(self):
        self.mox = mox.Mox()
        self.deployment = self.mox.CreateMockAnything()

    @mock.patch.object(tasks, 'postback')
    def test_create_instance(self, mock_postback):
        # Mock instance
        instance = self.mox.CreateMockAnything()
        instance.id = 'fake_instance_id'
        instance.name = 'fake_instance'
        instance.status = 'BUILD'
        instance.hostname = 'fake.cloud.local'
        instance.volume = self.mox.CreateMockAnything()
        instance.volume.size = 1

        # Stub out postback call
        self.mox.StubOutWithMock(tasks.reset_failed_resource_task, 'delay')

        # Stub out wait_on_build
        self.mox.StubOutWithMock(dbtasks.wait_on_build, 'delay')

        # Create clouddb mock
        clouddb_api_mock = self.mox.CreateMockAnything()
        clouddb_api_mock.create(
            instance.name,
            flavor=1,
            volume=1,
            databases=[{'name': 'db1'}]
        ).AndReturn(instance)

        expected = {
            'resources': {
                '1': {
                    'status': instance.status,
                    'instance': {
                        'id': instance.id,
                        'name': instance.name,
                        'status': instance.status,
                        'region': 'NORTH',
                        'flavor': 1,
                        'disk': 1,
                        'interfaces': {
                            'mysql': {
                                'host': instance.hostname,
                            },
                        },
                        'databases': {
                            'db1': {
                                'name': 'db1',
                                'interfaces': {
                                    'mysql': {
                                        'host': instance.hostname,
                                        'database_name': 'db1',
                                    },
                                }
                            }
                        }
                    }
                }
            }
        }
        context = middleware.RequestContext(deployment_id='DEP_ID',
                                            resource_key='1',
                                            region='NORTH')

        self.mox.ReplayAll()
        results = dbtasks.create_instance(context, instance.name, 1, 1,
                                          [{'name': 'db1'}], 'NORTH',
                                          api=clouddb_api_mock)

        self.assertEqual(results, expected)
        self.mox.VerifyAll()

    def test_create_database_fail_building(self):
        context = middleware.RequestContext(**{
            'deployment_id': 'DEP',
            'resource_key': '1'
        })

        # Mock instance
        instance = self.mox.CreateMockAnything()
        instance.id = 'fake_instance_id'
        instance.name = 'fake_instance'
        instance.status = 'BUILD'
        instance.hostname = 'fake.cloud.local'

        # Stub out postback call
        self.mox.StubOutWithMock(dbtasks.create_database, 'callback')
        self.mox.StubOutWithMock(tasks.reset_failed_resource_task, 'delay')

        dbtasks.create_database.callback(context, {'status': 'BUILD'})
        # Create clouddb mock
        clouddb_api_mock = self.mox.CreateMockAnything()
        clouddb_api_mock.get(instance.id).AndReturn(instance)
        self.mox.ReplayAll()
        # Should throw exception when instance.status="BUILD"
        self.assertRaises(exceptions.CheckmateException,
                          dbtasks.create_database,
                          context, 'db1', instance_id=instance.id,
                          api=clouddb_api_mock)

        self.mox.UnsetStubs()
        self.mox.VerifyAll()

    @mock.patch.object(tasks, 'postback')
    def test_create_database(self, mock_postback):
        context = middleware.RequestContext(**{
            'deployment_id': 'DEP',
            'resource_key': '1',
            'region': 'NORTH'
        })

        # Mock instance
        instance = self.mox.CreateMockAnything()
        instance.id = 'fake_instance_id'
        instance.flavor = self.mox.CreateMockAnything()
        instance.flavor.id = '1'
        instance.name = 'fake_instance'
        instance.status = 'ACTIVE'
        instance.hostname = 'fake.cloud.local'

        # Create clouddb mock
        clouddb_api_mock = self.mox.CreateMockAnything()
        clouddb_api_mock.get(instance.id).AndReturn(instance)
        instance.create_database('db1', None, None).AndReturn(None)

        expected = {
            'resources': {
                '1': {
                    'status': 'BUILD',
                    'instance': {
                        'host_instance': instance.id,
                        'interfaces': {
                            'mysql': {
                                'host': instance.hostname,
                                'database_name': 'db1'
                            }
                        },
                        'name': 'db1',
                        'id': 'db1',
                        'host_region': 'NORTH',
                        'flavor': '1',
                        'status': 'BUILD',
                    }
                }
            }
        }
        self.mox.ReplayAll()
        results = dbtasks.create_database(context, 'db1',
                                          instance_id=instance.id,
                                          api=clouddb_api_mock)
        self.assertEqual(results, expected)
        self.mox.VerifyAll()

    def test_template_generation_database(self):
        self.deployment.get_setting('domain', default='checkmate.local',
                                    provider_key='rackspace.database',
                                    resource_type='database',
                                    service_name='master'). \
            AndReturn("test.checkmate")
        self.deployment._constrained_to_one('master').AndReturn(True)

        catalog = {
            'database': {
                'mysql_database': {
                    'id': 'mysql_database',
                    'is': 'database',
                }
            }
        }
        dbprovider = provider.Provider({'catalog': catalog})

        # Mock Base Provider, context and deployment
        context = self.mox.CreateMockAnything()
        context.kwargs = {}

        expected = [{
            'instance': {},
            'dns-name': 'master.test.checkmate',
            'type': 'database',
            'provider': dbprovider.key,
            'service': 'master',
            'desired-state': {},
        }]

        self.mox.ReplayAll()
        results = dbprovider.generate_template(self.deployment, 'database',
                                               'master', context, 1,
                                               dbprovider.key, None)

        self.assertListEqual(results, expected)
        self.mox.VerifyAll()

    def test_template_generation_compute_sizing(self):
        catalog = {
            'compute': {
                'mysql_instance': {
                    'id': 'mysql_instance',
                    'is': 'compute',
                },
            },
            'lists': {
                'sizes': {
                    '1': {
                        'memory': 1024
                    },
                    '2': {
                        'memory': 2048
                    }
                }
            }
        }
        dbprovider = provider.Provider({'catalog': catalog})

        # Mock Base Provider, context and deployment
        self.deployment.get_setting(
            'domain',
            default='checkmate.local',
            provider_key='rackspace.database',
            resource_type='compute',
            service_name='master'
        ).AndReturn("test.domain")
        self.deployment._constrained_to_one('master').AndReturn(True)
        context = self.mox.CreateMockAnything()
        context.kwargs = {}

        self.deployment.get_setting(
            'memory', resource_type='compute',
            service_name='master',
            provider_key=dbprovider.key
        ).AndReturn(1025)
        self.deployment.get_setting(
            'disk',
            resource_type='compute',
            service_name='master',
            provider_key=dbprovider.key,
            default=1
        ).AndReturn(2)
        self.deployment.get_setting(
            'region',
            resource_type='compute',
            service_name='master',
            provider_key=dbprovider.key
        ).AndReturn('North')
        expected = [{
            'instance': {},
            'dns-name': 'master.test.domain',
            'type': 'compute',
            'provider': dbprovider.key,
            'service': 'master',
            'desired-state': {
                'region': 'North',
                'disk': 2,
                'flavor': '2',
            },
        }]

        self.mox.ReplayAll()
        results = dbprovider.generate_template(
            self.deployment, 'compute', 'master',
            context, 1, dbprovider.key, None
        )

        self.assertListEqual(results, expected)
        self.mox.VerifyAll()

    def verify_limits(self, volume_size_used):
        """Helper method to verify limits."""
        context = middleware.RequestContext()
        resources = [
            {
                'component': 'mysql_database',
                'dns-name': 'backend01.wordpress.cldsrvr.com',
                'hosted_on': '6',
                'index': '5',
                'instance': {},
                'provider': 'database',
                'relations': {
                    'host': {
                        'interface': 'mysql',
                        'name': 'compute',
                        'relation': 'host',
                        'requires-key': 'compute',
                        'state': 'planned',
                        'target': '6'
                    },
                    'master-backend-1': {
                        'interface': 'mysql',
                        'name': 'master-backend',
                        'relation': 'reference',
                        'relation-key': 'backend',
                        'source': '1',
                        'state': 'planned'
                    },
                    'web-backend-3': {
                        'interface': 'mysql',
                        'name': 'web-backend',
                        'relation': 'reference',
                        'relation-key': 'backend',
                        'source': '3',
                        'state': 'planned'
                    }
                },
                'service': 'backend',
                'status': 'PLANNED',
                'type': 'database',
                'desired-state': {},
            },
            {
                'component': 'mysql_instance',
                'dns-name': 'backend01.wordpress.cldsrvr.com',
                'hosts': ['5'],
                'index': '6',
                'instance': {},
                'provider': 'database',
                'service': 'backend',
                'status': 'NEW',
                'type': 'compute',
                'desired-state': {
                    'disk': 1,
                    'region': 'ORD',
                    'flavor': '1',
                },
            }
        ]
        instance1 = self.mox.CreateMockAnything()
        instance1.volume = self.mox.CreateMockAnything()
        instance1.volume.size = volume_size_used
        instance2 = self.mox.CreateMockAnything()
        instance2.volume = self.mox.CreateMockAnything()
        instance2.volume.size = volume_size_used
        instances = [instance1, instance2]
        self.mox.StubOutWithMock(provider.Provider, 'connect')
        cdb = self.mox.CreateMockAnything()
        provider.Provider.connect(mox.IgnoreArg()).AndReturn(cdb)
        cdb.list().AndReturn(instances)
        self.mox.ReplayAll()
        dbprovider = provider.Provider({})
        result = dbprovider.verify_limits(context, resources)
        self.mox.VerifyAll()
        return result

    def test_verify_limits_negative(self):
        result = self.verify_limits(100)  # Will be 200 total (2 instances)
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")

    def test_verify_limits_positive(self):
        result = self.verify_limits(1)
        self.assertEqual(result, [])

    def test_verify_access_positive(self):
        context = middleware.RequestContext()
        context.roles = 'identity:user-admin'
        dbprovider = provider.Provider({})
        result = dbprovider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'dbaas:admin'
        result = dbprovider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'dbaas:creator'
        result = dbprovider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')

    def test_verify_access_negative(self):
        context = middleware.RequestContext()
        context.roles = 'dbaas:observer'
        dbprovider = provider.Provider({})
        result = dbprovider.verify_access(context)
        self.assertEqual(result['type'], 'NO-ACCESS')


class TestCatalog(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_generation(self):
        dbprovider = provider.Provider({})
        context = self.mox.CreateMockAnything()
        flavor1 = {'id': '1', 'ram': 1024, 'name': 'm1.tiny'}

        context.catalog = [{
            "endpoints": [
                {
                    "publicURL": "https://north.databases.com/v1/55BB",
                    "region": "North",
                    "tenantId": "55BB"
                },
                {
                    "publicURL": "https://south.databases.com/v1/55BB",
                    "region": "South",
                    "tenantId": "55BB"
                }
            ],
            "name": "cloudDatabases",
            "type": "rax:database"
        }]
        context.auth_token = "DUMMY_TOKEN"
        context.region = None
        expected = {
            'compute': {
                'mysql_instance': {
                    'is': 'compute',
                    'id': 'mysql_instance',
                    'provides': [{'compute': 'mysql'}],
                    'options': {
                        'disk': {
                            'type': 'integer',
                            'unit': 'Gb',
                            'constraints': [
                                {'in': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}
                            ]
                        },
                        'memory': {
                            'type': 'integer',
                            'unit': 'Mb',
                            'constraints': [
                                {'in': [512, 1024, 2048, 4096]}
                            ]
                        }
                    }
                }
            },
            'lists': {
                'regions': {
                    'North': 'https://north.databases.com/v1/55BB',
                    'South': 'https://south.databases.com/v1/55BB'
                },
                'sizes': {
                    '1': {
                        'name': 'm1.tiny',
                        'memory': 1024,
                    },
                }
            },
            'database': {
                'redis_database': {
                    'is': 'database',
                    'id': 'redis_database',
                    'provides': [{'database': 'redis'}],
                    'options': {
                        'password': {
                            'required': False,
                            'type': 'string'
                        },
                        'username': {
                            'required': True,
                            'type': 'string'
                        },
                        'disk': {
                            'type': 'integer',
                            'unit': 'Gb',
                            'constraints': [
                                {'in': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}
                            ],
                            'default': 1
                        },
                        'memory': {
                            'type': 'integer',
                            'unit': 'Mb',
                            'constraints': [
                                {'in': [512, 1024, 2048, 4096]}
                            ],
                            'default': 512
                        }
                    }
                },
                'mysql_database': {
                    'is': 'database',
                    'requires': [
                        {
                            'interface': 'mysql',
                            'resource_type': 'compute',
                            'relation': 'host'
                        }
                    ],
                    'id': 'mysql_database',
                    'provides': [{'database': 'mysql'}],
                    'options': {
                        'database/password': {
                            'required': False,
                            'type': 'string'
                        },
                        'database/name': {
                            'default': 'db1',
                            'type': 'string'
                        },
                        'database/username': {
                            'required': True,
                            'type': 'string'
                        }
                    }
                }
            },
            'cache': {
                'redis_cache': {
                    'is': 'cache',
                    'id': 'redis_cache',
                    'provides': [{'cache': 'redis'}],
                    'options': {
                        'password': {
                            'required': False,
                            'type': 'string'
                        },
                        'username': {
                            'required': True,
                            'type': 'string'
                        },
                        'memory': {
                            'type': 'integer',
                            'unit': 'Mb',
                            'constraints': [
                                {'in': [512, 1024, 2048, 4096]}
                            ],
                            'default': 512
                        }
                    }
                }
            }
        }

        self.mox.StubOutWithMock(provider, '_get_flavors')
        provider._get_flavors(context, 'https://north.databases.com/v1/55BB',
                              'DUMMY_TOKEN').AndReturn([flavor1])

        self.mox.ReplayAll()
        results = dbprovider.get_catalog(context)
        self.assertEqual(expected, results, results)
        self.mox.VerifyAll()


class TestDBWorkflow(test.StubbedWorkflowBase):
    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        base.register_providers([provider.Provider, test.TestProvider])
        self.deployment = deployment.Deployment(utils.yaml_to_dict("""
id: 'DEP-ID-1000'
blueprint:
  name: test db
  services:
    db:
      component:
        name: database
        interface: mysql
environment:
  name: test
  providers:
    database:
      vendor: rackspace
      provides:
      - database: mysql
      - compute: mysql
      constraints:
      - region: DFW
      catalog:  # override so we don't need a token to connect
        compute:
          mysql_instance:
            id: mysql_instance
            is: compute
            provides:
            - compute: mysql
        database:
          mysql_database:
            id: mysql_database
            is: database
            provides:
            - database: mysql
            requires:
            - server:
                resource_type: compute
                relation: host
                interface: mysql
        lists:
          regions:
            DFW: https://dfw.databases.api.rackspacecloud.com/v1.0/T1000
            ORD: https://ord.databases.api.rackspacecloud.com/v1.0/T1000
          sizes:
            '1':
              memory: 512
              name: m1.tiny
            '2':
              memory: 1024
              name: m1.small
            '3':
              memory: 2048
              name: m1.medium
            '4':
              memory: 4096
              name: m1.large
    base:
      vendor: test
      provides:
      - compute: linux
      catalog:
        compute:
          linux_instance:
            is: compute
            provides:
            - compute: linux
            """))
        self.deployment['tenantId'] = 'tenantId'
        self.workflow = self._get_stubbed_out_workflow()

    def test_workflow_task_generation(self):
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(context,
                                                               self.deployment)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, self.deployment, context, "w_id", "BUILD")

        task_list = workflow.spec.task_specs.keys()
        expected = [
            'Root',
            'Start',
            'Create Database Server 0',
            'Wait on Database Instance 0',
        ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)

    def test_workflow_completion(self):
        self.mox.ReplayAll()
        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(), "Workflow did not "
                        "complete")


class TestRedisWorkflow(test.StubbedWorkflowBase):
    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        base.register_providers([provider.Provider])
        self.deployment = deployment.Deployment(utils.yaml_to_dict("""
id: 'DEP-ID-1000'
blueprint:
  name: test db
  services:
    db:
      component:
        resource_type: cache
        interface: redis
environment:
  name: test
  providers:
    database:
      vendor: rackspace
      provides:
      - cache: redis
      constraints:
      - region: DFW
      catalog:  # override so we don't need a token to connect
        cache:
          redis_cache:
            id: redis_cache
            is: cache
            provides:
            - cache: redis
        lists:
          regions:
            DFW: https://dfw.databases.api.rackspacecloud.com/v1.0/T1000
            ORD: https://ord.databases.api.rackspacecloud.com/v1.0/T1000
          sizes:
            '1':
              memory: 512
              name: m1.tiny
            '2':
              memory: 1024
              name: m1.small
            '3':
              memory: 2048
              name: m1.medium
            '4':
              memory: 4096
              name: m1.large
"""))
        self.deployment['tenantId'] = 'tenantId'
        self.workflow = self._get_stubbed_out_workflow()

    def test_workflow_task_generation(self):
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(context,
                                                               self.deployment)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, self.deployment, context, "w_id", "BUILD")

        task_list = workflow.spec.task_specs.keys()
        expected = [
            'Root',
            'Start',
            'Create Database Server 0',
            'Wait on Database Instance 0',
        ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)

    def test_workflow_completion(self):
        self.mox.ReplayAll()
        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(), "Workflow did not "
                        "complete")


class TestDatabaseGetResources(unittest.TestCase):
    @mock.patch.object(provider, 'pyrax')
    @mock.patch.object(provider.Provider, 'connect')
    def test_get_resources_returns_db_host_instances(self, mock_connect,
                                                     mock_pyrax):
        request = mock.Mock()
        mock_pyrax.identity.authenticated = True
        mock_pyrax.regions = ["ORD"]

        db_host = mock.Mock()
        db_host.status = 'status'
        db_host.name = 'name'
        db_host.id = 'id'
        db_host.hostname = 'hostname'
        db_host.flavor.id = 8
        db_host.volume.size = 'size'
        db_host.manager.api.region_name = 'region'

        api = mock.Mock()
        api.list.return_value = [db_host]

        mock_connect.return_value = api
        results = provider.Provider.get_resources(request, 'tenant')
        resource = results[0]
        self.assertEqual(len(results), 1)
        self.assertEqual(resource['status'], 'status')
        self.assertEqual(resource['dns-name'], 'name')
        self.assertEqual(resource['instance']['id'], 'id')
        self.assertEqual(resource['instance']['interfaces']['mysql']['host'],
                         'hostname')
        self.assertEqual(resource['instance']['flavor'], 8)
        self.assertEqual(resource['instance']['disk'], 'size')
        self.assertEqual(resource['instance']['region'], 'region')

    @mock.patch.object(provider, 'pyrax')
    @mock.patch.object(provider.Provider, 'connect')
    def test_get_resources_returns_redis_instances(self, mock_connect,
                                                   mock_pyrax):
        request = mock.Mock()
        mock_pyrax.identity.authenticated = True
        mock_pyrax.regions = ["ORD"]

        db_host = mock.Mock()
        db_host.status = 'status'
        db_host.name = 'name'
        db_host.id = 'id'
        db_host.hostname = 'hostname'
        db_host.flavor.id = 106
        db_host.volume.size = 'size'
        db_host.manager.api.region_name = 'region'

        api = mock.Mock()
        api.list.return_value = [db_host]

        mock_connect.return_value = api
        results = provider.Provider.get_resources(request, 'tenant')
        resource = results[0]
        self.assertEqual(len(results), 1)
        self.assertEqual(resource['status'], 'status')
        self.assertEqual(resource['dns-name'], 'name')
        self.assertEqual(resource['instance']['id'], 'id')
        self.assertEqual(resource['instance']['interfaces']['redis']['host'],
                         'hostname')
        self.assertEqual(resource['instance']['flavor'], 106)
        self.assertEqual(resource['instance']['disk'], 'size')
        self.assertEqual(resource['instance']['region'], 'region')

if __name__ == '__main__':
    import sys

    test.run_with_params(sys.argv[:])
