#!/usr/bin/env python
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate.providers.rackspace import database
import mox

from checkmate.common import schema
from checkmate.deployments import resource_postback


class TestDatabase(unittest.TestCase):
    """ Test Database Provider """

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_provider(self):
        provider = database.Provider({})
        self.assertEqual(provider.key, 'rackspace.database')

    def test_create_instance(self):
        #Mock instance
        class Instance(object):
            pass
        instance = Instance()
        instance.id = 'fake_instance_id'
        instance.name = 'fake_instance'
        instance.status = 'BUILD'
        instance.hostname = 'fake.cloud.local'

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')

        #Create clouddb mock
        clouddb_api_mock = self.mox.CreateMockAnything()
        clouddb_api_mock.create_instance(instance.name, 1, '1',
                databases=[{'name': 'db1'}]).AndReturn(instance)

        expected = {
                'id': instance.id,
                'instance':  {
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
        canonicalized_results = schema.translate_dict(expected)

        context = dict(deployment='DEP', resource='1')
        resource_postback.delay(context['deployment'], context['resource'],
                canonicalized_results).AndReturn(True)

        self.mox.ReplayAll()
        results = database.create_instance(context, instance.name,  1,  '1',
                [{'name': 'db1'}], 'NORTH', api=clouddb_api_mock)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()


if __name__ == '__main__':
    # Run tests. Handle our paramsters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
