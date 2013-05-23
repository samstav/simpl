#!/usr/bin/env python
import logging
import unittest2 as unittest

import mox

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import test
from checkmate.exceptions import CheckmateException
from checkmate.deployments import Deployment, resource_postback
from checkmate.providers import base, register_providers
from checkmate.providers.rackspace import database
from checkmate.test import StubbedWorkflowBase, ProviderTester
from checkmate import utils

from celery.task import task



class TestDatabase(ProviderTester):
    """ Test Database Provider """

    def setUp(self):
        self.mox = mox.Mox()
        self.deployment = self.mox.CreateMockAnything()

    def test_create_instance(self):
        #Mock instance
        instance = self.mox.CreateMockAnything()
        instance.id = 'fake_instance_id'
        instance.name = 'fake_instance'
        instance.status = 'BUILD'
        instance.hostname = 'fake.cloud.local'

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')

        #Stub out wiat_on_build
        self.mox.StubOutWithMock(database.wait_on_build, 'delay')

        #Create clouddb mock
        clouddb_api_mock = self.mox.CreateMockAnything()
        clouddb_api_mock.create_instance(instance.name, 1, 1,
                                         databases=[{'name': 'db1'}])\
            .AndReturn(instance)

        expected = {
            'instance:1':  {
                'status': 'BUILD',
                'id': instance.id,
                'name': instance.name,
                'status': instance.status,
                'region': 'NORTH',
                'flavor': 1,
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
            },
        }
        context = dict(deployment='DEP', resource='1')
        instance_id = {
            'instance:1': {
                'id': instance.id
            }
        }
        resource_postback.delay(context['deployment'], instance_id).AndReturn(
            True)
        resource_postback.delay(context['deployment'], expected).AndReturn(
            True)

        self.mox.ReplayAll()
        results = database.create_instance(context, instance.name, 1, 1,
                                           [{'name': 'db1'}], 'NORTH',
                                           api=clouddb_api_mock)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()


    def test_create_database_fail_building(self):
        context = dict(deployment='DEP', resource='1')

        #Mock instance
        instance = self.mox.CreateMockAnything()
        instance.id = 'fake_instance_id'
        instance.name = 'fake_instance'
        instance.status = 'BUILD'
        instance.hostname = 'fake.cloud.local'

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')

        #Create clouddb mock
        clouddb_api_mock = self.mox.CreateMockAnything()
        clouddb_api_mock.get_instance(instance.id).AndReturn(instance)
        self.mox.ReplayAll()
        #Should throw exception when instance.status="BUILD"
        self.assertRaises(CheckmateException, database.create_database,
                          context, 'db1', 'NORTH', instance_id=instance.id,
                          api=clouddb_api_mock)

        self.mox.UnsetStubs()
        self.mox.VerifyAll()

    def test_create_database_error_delete(self):
        context = dict(deployment='DEP', resource='1')

        #Mock instance
        instance = self.mox.CreateMockAnything()
        instance.id = 'fake_instance_id'
        instance.name = 'fake_instance'
        instance.status = 'ERROR'
        instance.hostname = 'fake.cloud.local'

        expected = {
            'instance:1': {
                'status': 'ERROR',
                'errmessage': 'Instance fake_instance_id build failed'
                }
            }

        expected_resource = {
            '0' : {
                'status': 'ERROR'
            }
        }
        instance_key = "instance:%s" % context['resource']

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')

        database_api_mock = self.mox.CreateMockAnything()
        database_api_mock.get_instance(instance.id).AndReturn(instance)

        #expect resource postback to be called
        resource_postback.delay(context['deployment'], expected)

        self.mox.StubOutWithMock(database, 'get_resource_by_id')
        database.get_resource_by_id(context['deployment'], context['resource'])\
                                    .AndReturn(expected_resource)

        class FakeTask():
            def apply_async(self):
                pass

        self.mox.StubOutWithMock(database.Provider, 'delete_resource_tasks')
        database.Provider({}).delete_resource_tasks(context, context['deployment'],
                                                    expected_resource, instance_key)\
                                    .AndReturn(FakeTask())

        self.mox.ReplayAll()

        self.assertRaises(CheckmateException,
            database.wait_on_build,
            context, instance.id, 'NORTH', database_api_mock
        )
        self.mox.UnsetStubs()
        self.mox.VerifyAll()

    def test_create_database(self):
        context = dict(deployment='DEP', resource='1')

        #Mock instance
        instance = self.mox.CreateMockAnything()
        instance.id = 'fake_instance_id'
        instance.flavor = {'id': '1'}
        instance.name = 'fake_instance'
        instance.status = 'ACTIVE'
        instance.hostname = 'fake.cloud.local'

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')

        #Create clouddb mock
        clouddb_api_mock = self.mox.CreateMockAnything()
        clouddb_api_mock.get_instance(instance.id).AndReturn(instance)
        instance.create_databases([{'name': 'db1'}]).AndReturn(True)

        expected = {
            'instance:1': {
                'status': 'BUILD',
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
                'flavor': '1'
            }
        }
        resource_postback.delay(context['deployment'], expected).AndReturn(
            True)

        self.mox.ReplayAll()
        results = database.create_database(context, 'db1', 'NORTH',
                                           instance_id=instance.id,
                                           api=clouddb_api_mock)

        self.assertDictEqual(results, expected)
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
        provider = database.Provider({'catalog': catalog})

        #Mock Base Provider, context and deployment
        context = self.mox.CreateMockAnything()
        context.kwargs = {}

        expected = [{
            'instance': {},
            'dns-name': 'master.test.checkmate',
            'type': 'database',
            'provider': provider.key,
            'service': 'master',
        }]

        self.mox.ReplayAll()
        results = provider.generate_template(self.deployment, 'database', 'master',
                                             context, 1, provider.key, None)

        self.assertListEqual(results, expected)
        self.mox.VerifyAll()



    def test_template_generation_compute_sizing(self):
        """Test that flavor and volume selection pick >-= sizes"""
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
        provider = database.Provider({'catalog': catalog})

        #Mock Base Provider, context and deployment
        self.deployment.get_setting('domain', default='checkmate.local',
                                    provider_key='rackspace.database',
                                    resource_type='compute',
                                    service_name='master')\
            .AndReturn("test.domain")
        self.deployment._constrained_to_one('master').AndReturn(True)
        context = self.mox.CreateMockAnything()
        context.kwargs = {}

        self.deployment.get_setting('memory', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key).AndReturn(1025)
        self.deployment.get_setting('disk', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key,
                               default=1).AndReturn(2)
        self.deployment.get_setting('region', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key).AndReturn('North')
        expected = [{
            'instance': {},
            'dns-name': 'master.test.domain',
            'type': 'compute',
            'provider': provider.key,
            'service': 'master',
            'region': 'North',
            'disk': 2,
            'flavor': '2'
        }]

        self.mox.ReplayAll()
        results = provider.generate_template(self.deployment, 'compute', 'master',
                                             context, 1, provider.key, None)

        self.assertListEqual(results, expected)
        self.mox.VerifyAll()
        
    def test_db_sync_resource_task(self):
        """Tests db sync_resource_task via mox"""
        #Mock instance
        instance = self.mox.CreateMockAnything()
        instance.id = 'fake_instance_id'
        instance.name = 'fake_instance'
        instance.status = 'ERROR'

        resource_key = "1"

        context = dict(deployment='DEP', resource='1')

        resource = {
                    'name': 'fake_instance',
                    'provider': 'database',
                    'status': 'ERROR',
                    'instance': {
                                 'id': 'fake_instance_id'
                            }
                    }

        database_api_mock = self.mox.CreateMockAnything()
        database_api_mock.get_instance = self.mox.CreateMockAnything()

        database_api_mock.get_instance(instance.id).AndReturn(instance)

        expected = {
                    'instance:1': {
                                   "status": "ERROR"
                                   }
                    }

        self.mox.ReplayAll()
        results = database.sync_resource_task(context, resource, resource_key,
                                             database_api_mock)

        self.assertDictEqual(results, expected)


class TestCatalog(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_generation(self):
        provider = database.Provider({})
        context = self.mox.CreateMockAnything()
        flavor1 = self.mox.CreateMockAnything()
        flavor1.id = '1'
        flavor1.ram = 1024
        flavor1.name = 'm1.tiny'

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
                            'choice': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
                        },
                        'memory': {
                            'type': 'integer',
                            'unit': 'Mb',
                            'choice': [512, 1024, 2048, 4096]
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
                'mysql_database': {
                    'is': 'database',
                    'requires': [{
                        'compute': {
                            'interface': 'mysql',
                            'type': 'compute',
                            'relation': 'host'
                        }
                    }],
                    'id': 'mysql_database',
                    'provides': [{'database': 'mysql'}],
                    'options': {
                        'database/password': {
                            'required': 'false',
                            'type': 'string'
                        },
                        'database/name': {
                            'default': 'db1',
                            'type': 'string'
                        },
                        'database/username': {
                            'required': 'true',
                            'type': 'string'
                        }
                    }
                }
            }
        }

        self.mox.StubOutWithMock(database, '_get_flavors')
        database._get_flavors('https://north.databases.com/v1/55BB',
                              'DUMMY_TOKEN').AndReturn([flavor1])

        self.mox.ReplayAll()
        results = provider.get_catalog(context)
        self.assertDictEqual(expected, results, results)
        self.mox.VerifyAll()


class TestDBWorkflow(StubbedWorkflowBase):
    """ Test MySQL and DBaaS Resource Creation Workflow """

    def setUp(self):
        StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        register_providers([database.Provider, test.TestProvider])
        self.deployment = Deployment(utils.yaml_to_dict("""
id: 'DEP-ID-1000'
blueprint:
  name: test db
  services:
    db:
      component:
        is: database
        type: database
        requires:
        - host: 'linux'
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
            - compute:  # FIXME: this syntax needs to be deprecated
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
            id: linux_instance
            is: compute
            provides:
            - compute: linux
            """))
        self.workflow = self._get_stubbed_out_workflow()

    def test_workflow_completion(self):
        """Verify workflow sequence and data flow"""

        self.mox.ReplayAll()

        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(), "Workflow did not "
                        "complete")


if __name__ == '__main__':
    # Run tests. Handle our parameters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
