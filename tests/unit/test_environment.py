# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''

import os
import unittest2 as unittest

from checkmate import test
from checkmate.exceptions import CheckmateException
from checkmate.providers import base, register_providers
from checkmate.providers.rackspace import loadbalancer
from checkmate.environment import Environment
from checkmate.middleware import RequestContext
from checkmate.utils import yaml_to_dict


class EnvironmentTestCase(unittest.TestCase):
    def setUp(self):
        base.PROVIDER_CLASSES = {}
        register_providers([loadbalancer.Provider, test.TestProvider])
        self.context = RequestContext()
        with open(os.path.dirname(
                __file__) + '/../data/environment_test.yaml') as data:
            self.env_data = yaml_to_dict(data)

    def test_get_provider(self):
        environment = Environment(self.env_data.get('valid'))
        provider = environment.get_provider('load-balancer')
        self.assertIsInstance(provider, loadbalancer.Provider,
                              "Provider is not a instance of "
                              "rackspace.load-balancer")

    def test_get_provider_exception_handling(self):
        self.assertRaises(CheckmateException,
                          Environment({}).get_provider, 'foo', )

        environment = Environment(self.env_data.get('no_vendor'))
        self.assertRaises(CheckmateException, environment.get_provider, 'base')

    def test_get_providers(self):
        environment = Environment(self.env_data.get('valid'))
        providers = environment.get_providers(self.context)
        self.assertEqual(len(providers), 2)
        self.assertIsInstance(
            providers.get('load-balancer'), loadbalancer.Provider)
        self.assertIsInstance(
            providers.get('base'), test.TestProvider)

    def test_get_providers_for_no_providers(self):
        self.assertEqual(Environment({}).get_providers(self.context), {})

    def test_get_providers_when_no_vendor_specified(self):
        environment = Environment(self.env_data.get('no_vendor'))
        self.assertRaises(CheckmateException, environment.get_providers,
                          self.context)

    def test_get_providers_with_common_vendor(self):
        environment = Environment(self.env_data.get('common_vendor'))
        providers = environment.get_providers(self.context)
        self.assertEqual(len(providers), 1)
        self.assertIsInstance(
            providers.get('load-balancer'), loadbalancer.Provider)

    def test_select_provider_for_given_resource_and_interface(self):
        environment = Environment(self.env_data.get('valid'))
        provider = environment.select_provider(self.context,
                                               resource='load-balancer',
                                               interface='http')
        self.assertIsInstance(provider, loadbalancer.Provider)

    def test_select_provider_for_given_resource(self):
        environment = Environment(self.env_data.get('valid'))
        provider = environment.select_provider(self.context,
                                               resource='load-balancer')
        self.assertIsInstance(provider, loadbalancer.Provider)

    def test_select_provider_for_given_interface(self):
        environment = Environment(self.env_data.get('valid'))
        provider = environment.select_provider(self.context,
                                               interface='http')
        self.assertIsInstance(provider, loadbalancer.Provider)

    def test_select_provider_without_resource_and_interface(self):
        environment = Environment(self.env_data.get('valid'))
        provider = environment.select_provider(self.context)
        self.assertIsNone(provider)

    def test_find_component(self):
        blueprint_entry = {'resource_type': 'load-balancer',
                           'interface': 'http'}
        environment = Environment(self.env_data.get('valid'))
        component = environment.find_component(blueprint_entry, self.context)
        self.assertIsInstance(component.provider, loadbalancer.Provider)

    def test_find_component_for_no_matching_components(self):
        blueprint_entry = {'resource_type': 'load-balancer',
                           'interface': 'vip'}
        environment = Environment(self.env_data.get('valid'))
        component = environment.find_component(blueprint_entry, self.context)
        self.assertIsNone(component)

    def test_find_component_for_mutiple_matching_components(self):
        blueprint_entry = {'resource_type': 'load-balancer',
                           'interface': 'http'}
        environment = Environment(
            self.env_data.get('valid_with_multiple_lb_providers'))
        component = environment.find_component(blueprint_entry, self.context)
        self.assertIsInstance(component.provider, test.TestProvider)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
