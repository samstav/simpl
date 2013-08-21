# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
import logging
import mox
import unittest

from checkmate import deployment
from checkmate.exceptions import CheckmateException
from checkmate import middleware
from checkmate import providers
from checkmate.providers import base
from checkmate.providers.rackspace import database
from checkmate.providers.rackspace.database import (
    provider as db_provider
)
from checkmate import test
from checkmate import utils

LOG = logging.getLogger(__name__)


class TestDatabase(test.ProviderTester):
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
        instance.volume = self.mox.CreateMockAnything()
        instance.volume.size = 1

        #Stub out postback call
        self.mox.StubOutWithMock(database._create_instance, 'callback')

        #Stub out wait_on_build
        self.mox.StubOutWithMock(database.wait_on_build, 'delay')

        #Create clouddb mock
        clouddb_api_mock = self.mox.CreateMockAnything()
        clouddb_api_mock.create(
            instance.name,
            flavor=1,
            volume=1,
            databases=[{'name': 'db1'}]
        ).AndReturn(instance)

        expected = {
            'instance:1': {
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
        context = middleware.RequestContext(resource='1')

        database._create_instance.callback(context,
                                           {'id': instance.id}).AndReturn(True)
        database._create_instance.callback(
            context, expected['instance:1']).AndReturn(True)

        self.mox.ReplayAll()
        results = database.create_instance(context, instance.name, 1, 1,
                                           [{'name': 'db1'}], 'NORTH',
                                           api=clouddb_api_mock)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_create_database_fail_building(self):
        context = middleware.RequestContext(**{'deployment': 'DEP',
                                            'resource': '1'})

        #Mock instance
        instance = self.mox.CreateMockAnything()
        instance.id = 'fake_instance_id'
        instance.name = 'fake_instance'
        instance.status = 'BUILD'
        instance.hostname = 'fake.cloud.local'

        #Stub out postback call
        self.mox.StubOutWithMock(database._create_database, 'callback')
        database._create_database.callback(context, {'status': 'BUILD'})
        #Create clouddb mock
        clouddb_api_mock = self.mox.CreateMockAnything()
        clouddb_api_mock.get(instance.id).AndReturn(instance)
        self.mox.ReplayAll()
        #Should throw exception when instance.status="BUILD"
        self.assertRaises(CheckmateException, database.create_database,
                          context, 'db1', 'NORTH', instance_id=instance.id,
                          api=clouddb_api_mock)

        self.mox.UnsetStubs()
        self.mox.VerifyAll()

    def test_create_database(self):
        context = middleware.RequestContext(**{'deployment': 'DEP',
                                            'resource': '1'})

        #Mock instance
        instance = self.mox.CreateMockAnything()
        instance.id = 'fake_instance_id'
        instance.flavor = self.mox.CreateMockAnything()
        instance.flavor.id = '1'
        instance.name = 'fake_instance'
        instance.status = 'ACTIVE'
        instance.hostname = 'fake.cloud.local'

        #Stub out postback call
        self.mox.StubOutWithMock(database._create_database, 'callback')
        #self.mox.StubOutWithMock(tasks.reset_failed_resource_task, 'delay')

        #Create clouddb mock
        clouddb_api_mock = self.mox.CreateMockAnything()
        clouddb_api_mock.get(instance.id).AndReturn(instance)
        instance.create_database('db1', None, None).AndReturn(True)

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
        database._create_database.callback(
            context, {'status': instance.status}).AndReturn(True)
        database._create_database.callback(context, expected['instance:1'])

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
            'desired-state': {},
        }]

        self.mox.ReplayAll()
        results = provider.generate_template(
            self.deployment, 'database', 'master',
            context, 1, provider.key, None
        )

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
        provider = database.Provider({'catalog': catalog})

        #Mock Base Provider, context and deployment
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
            provider_key=provider.key
        ).AndReturn(1025)
        self.deployment.get_setting(
            'disk',
            resource_type='compute',
            service_name='master',
            provider_key=provider.key,
            default=1
        ).AndReturn(2)
        self.deployment.get_setting(
            'region',
            resource_type='compute',
            service_name='master',
            provider_key=provider.key
        ).AndReturn('North')
        expected = [{
            'instance': {},
            'dns-name': 'master.test.domain',
            'type': 'compute',
            'provider': provider.key,
            'service': 'master',
            'region': 'North',
            'disk': 2,
            'flavor': '2',
            'desired-state': {},
        }]

        self.mox.ReplayAll()
        results = provider.generate_template(
            self.deployment, 'compute', 'master',
            context, 1, provider.key, None
        )

        self.assertListEqual(results, expected)
        self.mox.VerifyAll()

    def verify_limits(self, volume_size_used):
        context = middleware.RequestContext()
        resources = [
            {'component': 'mysql_database',
             'dns-name': 'backend01.wordpress.cldsrvr.com',
             'hosted_on': '6',
             'index': '5',
             'instance': {},
             'provider': 'database',
             'relations': {'host': {'interface': 'mysql',
                                    'name': 'compute',
                                    'relation': 'host',
                                    'requires-key': 'compute',
                                    'state': 'planned',
                                    'target': '6'},
                           'master-backend-1': {'interface': 'mysql',
                                                'name': 'master-backend',
                                                'relation': 'reference',
                                                'relation-key': 'backend',
                                                'source': '1',
                                                'state': 'planned'},
                           'web-backend-3': {'interface': 'mysql',
                                             'name': 'web-backend',
                                             'relation': 'reference',
                                             'relation-key': 'backend',
                                             'source': '3',
                                             'state': 'planned'}},
             'service': 'backend',
             'status': 'PLANNED',
             'type': 'database',
             'desired-state': {},
             },
            {'component': 'mysql_instance',
             'disk': 1,
             'dns-name': 'backend01.wordpress.cldsrvr.com',
             'flavor': '1',
             'hosts': ['5'],
             'index': '6',
             'instance': {},
             'provider': 'database',
             'region': 'ORD',
             'service': 'backend',
             'status': 'NEW',
             'type': 'compute',
             'desired-state': {},
             }
        ]
        instance1 = self.mox.CreateMockAnything()
        instance1.volume = self.mox.CreateMockAnything()
        instance1.volume.size = volume_size_used
        instance2 = self.mox.CreateMockAnything()
        instance2.volume = self.mox.CreateMockAnything()
        instance2.volume.size = volume_size_used
        instances = [instance1, instance2]
        self.mox.StubOutWithMock(database.Provider, 'connect')
        cdb = self.mox.CreateMockAnything()
        database.Provider.connect(mox.IgnoreArg()).AndReturn(cdb)
        cdb.list().AndReturn(instances)
        self.mox.ReplayAll()
        provider = database.Provider({})
        result = provider.verify_limits(context, resources)
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
        provider = database.Provider({})
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'dbaas:admin'
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'dbaas:creator'
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')

    def test_verify_access_negative(self):
        context = middleware.RequestContext()
        context.roles = 'dbaas:observer'
        provider = database.Provider({})
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'NO-ACCESS')


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

        self.mox.StubOutWithMock(db_provider, '_get_flavors')
        db_provider._get_flavors('https://north.databases.com/v1/55BB',
                                 'DUMMY_TOKEN').AndReturn([flavor1])

        self.mox.ReplayAll()
        results = provider.get_catalog(context)
        self.assertDictEqual(expected, results, results)
        self.mox.VerifyAll()


class TestDBWorkflow(test.StubbedWorkflowBase):
    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        providers.register_providers([database.Provider, test.TestProvider])
        self.deployment = deployment.Deployment(utils.yaml_to_dict("""
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
        self.mox.ReplayAll()
        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(), "Workflow did not "
                        "complete")


if __name__ == '__main__':
    # Run tests. Handle our parameters separately
    import sys
    ARGS = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in ARGS:
        ARGS.pop(ARGS.index('--debug'))
        if '--verbose' not in ARGS:
            ARGS.insert(1, '--verbose')
    unittest.main(argv=ARGS)
