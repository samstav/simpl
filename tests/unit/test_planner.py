import unittest
import mox

from checkmate.deployment import Deployment
from checkmate.deployments import Planner
from checkmate.providers.rackspace import loadbalancer
from checkmate.providers.opscode import solo
from checkmate.providers import base, register_providers


class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()

    def test_add_resource(self):
        plan = Planner(Deployment({'blueprint': {'services': {}}}))
        plan.resource_index = 0
        resource = {}
        definition = {}
        plan.add_resource(resource, definition)

        self.assertEqual(len(definition["instances"]), 1)
        self.assertEqual(definition["instances"][0], '0')
        self.assertEqual(len(plan.resources), 1)
        self.assertEqual(plan.resources['0'], resource)

    def test_add_additional_nodes(self):
        base.PROVIDER_CLASSES = {}
        register_providers([loadbalancer.Provider, solo.Provider])
        context = self.mox.CreateMockAnything()
        deployment = Deployment({
            'id': '1001',
            'blueprint': {
                'services': {
                    'lb': {
                        'component': {
                            'provider-key': 'load-balancer'
                        }
                    },
                    'web': {
                        'component': {
                            'provider-key': 'chef-solo'
                        }
                    }
                },
            },
            'resources': {
                '0': {'provider': 'load-balancer', "service": "lb"},
                '1': {'provider': 'chef-solo', "service": "web"}
            },
            'plan': {
                'services': {
                    'web': {
                        'component': {
                            'provider-key': 'chef-solo',
                            'id': "wordpress-web"
                        }
                    }
                }
            },
            'environment': {
                'providers': {
                    'load-balancer': {
                        'vendor': 'rackspace'
                    },
                    'chef-solo': {
                        'vendor': 'opscode',
                        'catalog': {
                            'application': {
                                'wordpress-web': {}
                            }
                        }
                    },
                }
            }
        })
        expected_resources = {
            '0': {
                'service': 'lb',
                'provider': 'load-balancer'
            },
            '1': {
                'service': 'web',
                'provider': 'chef-solo'
            },
            '2': {
                'status': 'PLANNED',
                'index': '2',
                'service': 'web',
                'desired-state': {},
                'component': 'wordpress-web',
                'dns-name': 'web02.checkmate.local',
                'instance': {},
                'provider': 'chef-solo',
                'type': 'application'
            },
            '3': {
                'status': 'PLANNED',
                'index': '3',
                'service': 'web',
                'desired-state': {},
                'component': 'wordpress-web',
                'dns-name': 'web03.checkmate.local',
                'instance': {},
                'provider': 'chef-solo',
                'type': 'application'
            },
        }
        planner = Planner(deployment, False, deployment['plan'])
        planner.plan_additional_nodes(context, "web", 2)
        self.assertEquals(len(planner.resources), 4)
        self.assertDictEqual(planner.resources, expected_resources)

    def test_add_resource_and_update_connections_for_vip(self):
        deployment = Deployment({
            'blueprint': {
                'services': {
                    'lb': {
                        'component': {
                            'interface': 'vip'
                        }
                    }
                }
            }
        })
        plan = Planner(deployment)
        plan.resource_index = 0
        resource = {}
        definition = {'connections': {'master': {}, 'web': {}}}
        plan.add_resource(resource, definition, 'lb')
        master = bool(definition['connections']['master'].get('outbound-from'))
        web = bool(definition['connections']['web'].get('outbound-from'))
        self.assertTrue(master != web)
        if master:
            self.assertEqual(
                definition['connections']['master']['outbound-from'], '0')
        if web:
            self.assertEqual(
                definition['connections']['web']['outbound-from'], '0')


if __name__ == '__main__':
    # Run tests. Handle our parameters separately
    import sys

    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
