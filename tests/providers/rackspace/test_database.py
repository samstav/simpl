#!/usr/bin/env python
import logging
import unittest2 as unittest

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


class TestDatabase(ProviderTester):
    """ Test Database Provider """

    klass = database.Provider

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
        clouddb_api_mock.create_instance(instance.name, 1, '1',
                                         databases=[{'name': 'db1'}])\
            .AndReturn(instance)

        expected = {
            'instance:1':  {
                'status': 'BUILD',
                'id': instance.id,
                'name': instance.name,
                'status': instance.status,
                'region': 'NORTH',
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
        resource_postback.delay(context['deployment'], expected).AndReturn(
            True)

        self.mox.ReplayAll()
        results = database.create_instance(context, instance.name, 1, '1',
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

    def test_create_database(self):
        context = dict(deployment='DEP', resource='1')

        #Mock instance
        instance = self.mox.CreateMockAnything()
        instance.id = 'fake_instance_id'
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
                'host_region': 'NORTH'
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
            1:
              memory: 512
              name: m1.tiny
            2:
              memory: 1024
              name: m1.small
            3:
              memory: 2048
              name: m1.medium
            4:
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
