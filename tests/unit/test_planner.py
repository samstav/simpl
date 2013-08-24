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

"""Tests for Planner."""
import unittest

import mox

from checkmate import deployment as cmdep
from checkmate import deployments as cmdeps
from checkmate import providers as cmprov
from checkmate.providers import base
from checkmate.providers.opscode import solo
from checkmate.providers.rackspace import loadbalancer


class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()

    def test_add_resource(self):
        plan = cmdeps.Planner(
            cmdep.Deployment({'blueprint': {'services': {}}}))
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
        cmprov.register_providers([loadbalancer.Provider, solo.Provider])
        context = self.mox.CreateMockAnything()
        deployment = cmdep.Deployment({
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
        planner = cmdeps.Planner(deployment, False, deployment['plan'])
        planner.plan_additional_nodes(context, "web", 2)
        self.assertEquals(len(planner.resources), 4)
        self.assertDictEqual(planner.resources, expected_resources)

    def test_add_resource_updates_vip(self):
        deployment = cmdep.Deployment({
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
        plan = cmdeps.Planner(deployment)
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
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
