# pylint: disable=C0103

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

"""Tests for Environment class."""
import os
import unittest

from checkmate import environment as cmenv
from checkmate import exceptions as cmexc
from checkmate import middleware as cmmid
from checkmate import providers as cmprv
from checkmate.providers import base
from checkmate.providers.rackspace import loadbalancer
from checkmate import test
from checkmate import utils


class TestEnvironment(unittest.TestCase):
    def setUp(self):
        base.PROVIDER_CLASSES = {}
        cmprv.register_providers([loadbalancer.Provider, test.TestProvider])
        self.context = cmmid.RequestContext()
        with open(os.path.dirname(
                __file__) + '/../data/environment_test.yaml') as data:
            self.env_data = utils.yaml_to_dict(data)

    def test_get_provider(self):
        environment = cmenv.Environment(self.env_data.get('valid'))
        provider = environment.get_provider('load-balancer')
        self.assertIsInstance(provider, loadbalancer.Provider,
                              "Provider is not a instance of "
                              "rackspace.load-balancer")

    def test_get_provider_exception_handling(self):
        self.assertRaises(cmexc.CheckmateException,
                          cmenv.Environment({}).get_provider, 'foo', )

        environment = cmenv.Environment(self.env_data.get('no_vendor'))
        self.assertRaises(
            cmexc.CheckmateException, environment.get_provider, 'base')

    def test_get_providers(self):
        environment = cmenv.Environment(self.env_data.get('valid'))
        providers = environment.get_providers(self.context)
        self.assertEqual(len(providers), 2)
        self.assertIsInstance(
            providers.get('load-balancer'), loadbalancer.Provider)
        self.assertIsInstance(
            providers.get('base'), test.TestProvider)

    def test_get_providers_for_no_providers(self):
        self.assertEqual(cmenv.Environment({}).get_providers(self.context), {})

    def test_get_providers_when_no_vendor_specified(self):
        environment = cmenv.Environment(self.env_data.get('no_vendor'))
        self.assertRaises(cmexc.CheckmateException, environment.get_providers,
                          self.context)

    def test_get_providers_with_common_vendor(self):
        environment = cmenv.Environment(self.env_data.get('common_vendor'))
        providers = environment.get_providers(self.context)
        self.assertEqual(len(providers), 1)
        self.assertIsInstance(
            providers.get('load-balancer'), loadbalancer.Provider)

    def test_select_provider_for_given_resource_and_interface(self):
        environment = cmenv.Environment(self.env_data.get('valid'))
        provider = environment.select_provider(self.context,
                                               resource='load-balancer',
                                               interface='http')
        self.assertIsInstance(provider, loadbalancer.Provider)

    def test_select_provider_for_given_resource(self):
        environment = cmenv.Environment(self.env_data.get('valid'))
        provider = environment.select_provider(self.context,
                                               resource='load-balancer')
        self.assertIsInstance(provider, loadbalancer.Provider)

    def test_select_provider_for_given_interface(self):
        environment = cmenv.Environment(self.env_data.get('valid'))
        provider = environment.select_provider(self.context,
                                               interface='http')
        self.assertIsInstance(provider, loadbalancer.Provider)

    def test_select_provider_without_resource_and_interface(self):
        environment = cmenv.Environment(self.env_data.get('valid'))
        provider = environment.select_provider(self.context)
        self.assertIsNone(provider)

    def test_find_component(self):
        blueprint_entry = {'resource_type': 'load-balancer',
                           'interface': 'http'}
        environment = cmenv.Environment(self.env_data.get('valid'))
        component = environment.find_component(blueprint_entry, self.context)
        self.assertIsInstance(component.provider, loadbalancer.Provider)

    def test_find_component_for_no_matching_components(self):
        blueprint_entry = {'resource_type': 'load-balancer',
                           'interface': 'vip'}
        environment = cmenv.Environment(self.env_data.get('valid'))
        component = environment.find_component(blueprint_entry, self.context)
        self.assertIsNone(component)

    def test_find_component_for_mutiple_matching_components(self):
        blueprint_entry = {'resource_type': 'load-balancer',
                           'interface': 'http'}
        environment = cmenv.Environment(
            self.env_data.get('valid_with_multiple_lb_providers'))
        component = environment.find_component(blueprint_entry, self.context)
        self.assertIsInstance(component.provider, test.TestProvider)


if __name__ == '__main__':
    import sys

    test.run_with_params(sys.argv[:])
