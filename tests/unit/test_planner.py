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

import mock

from checkmate import deployment as cmdep
from checkmate import deployments as cmdeps
from checkmate.providers import base
from checkmate.providers.opscode.solo import provider as solo_provider
from checkmate.providers.rackspace import loadbalancer
from checkmate import test
from checkmate import utils


class TestPlanner(unittest.TestCase):

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
        base.register_providers(
            [loadbalancer.Provider, solo_provider.Provider])
        context = mock.Mock()
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
        self.assertEqual(len(planner.resources), 4)
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


class TestPlanningAspects(unittest.TestCase):

    """Test main features of planning.

    Test:
    - component finding
    - component dependency resoution (two levels)
    - 'host' relation
    - allow_unencrypted for load-blancer (gens two resources)
    - vip interface (proxy)
    - supports and requires and prov
    """

    def setUp(self):
        base.PROVIDER_CLASSES = {}
        base.register_providers([loadbalancer.Provider, test.TestProvider])
        self.deployment = cmdep.Deployment(utils.yaml_to_dict("""
            id: test
            blueprint:
              services:
                lb:
                  component:
                    resource_type: load-balancer
                    interface: vip
                  constraints:
                  - allow_unencrypted: true
                  relations:
                  - web: http
                web:
                  component:
                    interface: http
                    resource_type: application
            environment:
              providers:
                load-balancer:
                  vendor: rackspace
                  catalog:
                    load-balancer:
                      rsCloudLB:
                        provides:
                        - load-balancer: http
                        - load-balancer: https
                        - load-balancer: vip
                        supports:
                        - application: http
                        options:
                          protocol:
                            type: list
                            constraints:
                            - in: [http]
                base:
                  vendor: test
                  catalog:
                    application:
                      app_instance:
                        provides:
                        - application: http
                        requires:
                        - host: linux
                    compute:
                      linux_instance:
                        provides:
                        - compute: linux
                        requires:
                        - compute: hardware
                      server_instance:
                        provides:
                        - compute: hardware
            inputs:
              blueprint:
                region: North
        """))
        self.context = {'region': 'North'}

    def test_component_resolution_initial(self):
        """Test that main components are identified."""
        planner = cmdeps.Planner(self.deployment)
        planner.init_service_plans_dict()
        planner.resolve_components(self.context)
        resolved = [r['component']['id'] for r in planner['services'].values()]
        self.assertItemsEqual(resolved, ['app_instance', 'rsCloudLB'])

    def test_dependency_resolution(self):
        """Test that two levels of dependencies are resolved."""
        planner = cmdeps.Planner(self.deployment)
        planner.init_service_plans_dict()
        planner.resolve_components(self.context)
        # Get all main and extra component IDs in a list
        just_resources = []
        for plan in planner['services'].values():
            just_resources.append(plan['component']['id'])
            if 'extra-components' in plan:
                for extra in plan['extra-components'].values():
                    just_resources.append(extra['id'])

        # First level of dependencies
        planner.resolve_remaining_requirements(self.context)
        with_dependencies = []
        for plan in planner['services'].values():
            with_dependencies.append(plan['component']['id'])
            if 'extra-components' in plan:
                for extra in plan['extra-components'].values():
                    with_dependencies.append(extra['id'])

        # Dependencies of dependencies
        planner.resolve_recursive_requirements(self.context, history=[])
        with_recursive = []
        for plan in planner['services'].values():
            with_recursive.append(plan['component']['id'])
            if 'extra-components' in plan:
                for extra in plan['extra-components'].values():
                    with_recursive.append(extra['id'])

        self.assertItemsEqual(just_resources, ['app_instance', 'rsCloudLB'])
        self.assertItemsEqual(
            with_dependencies, just_resources + ['linux_instance'])
        self.assertItemsEqual(
            with_recursive, with_dependencies + ['server_instance'])

if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
