#!/usr/bin/env python
import copy
import unittest2 as unittest

from checkmate.deployments import Deployment, plan
from checkmate.exceptions import CheckmateValidationException
from checkmate.providers.base import PROVIDER_CLASSES, ProviderBase
from checkmate.server import RequestContext
from checkmate.utils import yaml_to_dict


class TestDeployments(unittest.TestCase):
    def test_parser(self):
        """Test the parser works on a minimal deployment"""
        deployment = {
                'id': 'test',
                'blueprint': {
                    'name': 'test bp',
                    },
                'environment': {
                    'name': 'environment',
                    'providers': {},
                    },
                }
        original = copy.copy(deployment)
        parsed = plan(Deployment(deployment), RequestContext())
        del parsed['status']  # we expect this to get added
        del parsed['created']  # we expect this to get added
        self.assertDictEqual(original, parsed.__dict__())

    def test_resource_generator(self):
        """Test the parser generates the right number of resources"""
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    back:
                      component: &widget
                        id: widget
                        type: widget
                        interface: foo
                    front:
                      component: *widget
                      relations:
                        middle: foo
                    middle:
                      component: *widget
                      relations:
                        back: foo
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      vendor: test
                      catalog:
                        widget:
                          small_widget:
                            is: widget
                            provides:
                            - widget: foo
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
                    common:
                      credentials:
                      - password: secret
                        username: tester
                inputs:
                  services:
                    middle:
                      widget:
                        count: 4
            """))

        PROVIDER_CLASSES['test.base'] = ProviderBase

        parsed = plan(deployment, RequestContext())
        services = parsed['blueprint']['services']
        self.assertEqual(len(services['front']['instances']), 1)
        self.assertEqual(len(services['middle']['instances']), 4)
        self.assertEqual(len(services['back']['instances']), 1)
        #import json
        #print json.dumps(parsed, indent=2)


class TestComponentSearch(unittest.TestCase):
    """ Test code that finds components """
    def test_component_find_by_type(self):
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      component:
                        type: widget
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      vendor: test
                      catalog:
                        widget:
                          small_widget:
                            is: widget
                            provides:
                            - widget: foo
            """))
        PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        self.assertEquals(deployment['resources'].values()[0]['component'],
                'small_widget')

    def test_component_find_by_type_and_interface(self):
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      component:
                        type: widget
                        interface: foo
                    two:
                      component:
                        type: widget
                        interface: bar
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      - widget: bar
                      vendor: test
                      catalog:
                        widget:
                          small_widget:
                            is: widget
                            provides:
                            - widget: foo
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
            """))
        PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        components = [r['component'] for r in deployment['resources'].values()]
        self.assertIn('big_widget', components)
        self.assertIn('small_widget', components)

    def test_component_finding(self):
        deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      component:
                        type: widget
                        interface: foo
                    two:
                      component:
                        id: big_widget
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      - widget: bar
                      vendor: test
                      catalog:
                        widget:
                          small_widget:
                            is: widget
                            provides:
                            - widget: foo
                          big_widget:
                            is: widget
                            provides:
                            - widget: bar
                    common:
                      credentials:
                      - password: secret
                        username: tester
            """))
        PROVIDER_CLASSES['test.base'] = ProviderBase
        plan(deployment, RequestContext())
        components = [r['component'] for r in deployment['resources'].values()]
        self.assertIn('big_widget', components)
        self.assertIn('small_widget', components)


class TestDeploymentSettings(unittest.TestCase):

    def test_get_setting(self):
        """Test the get_setting function"""
        deployment = Deployment(yaml_to_dict("""
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - compute: foo
                        vendor: bar
                    common:
                      credentials:
                      - password: secret
                      constraints:
                      - region: place
                blueprint:
                  services:
                    web:
                      component:
                      type: compute
                  options:
                    my_server_type:
                      constrains:
                      - type: compute
                        service: web
                        setting: os
                inputs:
                  blueprint:
                    domain: example.com
                    my_server_type: Ubuntu 11.10  # an option with constraint
                  providers:
                    base:
                      compute:
                        memory: 4 Gb
                  services:
                    web:
                      compute:
                        case-whitespace-test: 512mb
                        gigabyte-test: 8 gigabytes
                        mb-test: 512 Mb
                        memory: 2 Gb
                        number-only-test: 512
            """))
        cases = [{
                'case': "Set in blueprint/inputs",
                'name': "domain",
                'expected': "example.com",
                }, {
                'case': "Set in blueprint/inputs with service/provider scope",
                'name': "os",
                'service': "web",
                'expected': "Ubuntu 11.10",
                }, {
                'case': "Set in blueprint/inputs with no service scope",
                'name': "os",
                'expected': None,
                }, {
                'case': "Set in blueprint/service under provider/resource",
                'name': "memory",
                'service': "web",
                'type': 'compute',
                'expected': "2 Gb",
                }, {
                'case': "Set in environments/providers/common",
                'name': "region",
                'provider': "common",
                'service' : "constraints",
                'expected': "place",
                },  {
                'case': "Set in blueprint/providers",
                'name': "memory",
                'type': 'compute',
                'expected': "4 Gb",
                'add': """ - FIXME: broken without env providers
                    environment:
                      name: environment
                      providers:
                        base:
                          provides:
                          - compute: foo
                          vendor: test""",
                }
            ]

        PROVIDER_CLASSES['test.base'] = ProviderBase
        for test in cases[:-1]:  # TODO: last case broken without env providers
            value = deployment.get_setting(test['name'],
                    service_name=test.get('service'),
                    provider_key=test.get('provider'),
                    resource_type=test.get('type'))
            self.assertEquals(value, test['expected'], test['case'])

    def test_get_input_provider_option(self):
        deployment = Deployment(yaml_to_dict("""
                environment:
                  providers:
                    base
                blueprint:
                  services:
                    web:
                  options:
                    my_server_type:
                      constrains:
                      - resource_type: compute
                        service: web
                        setting: os
                inputs:
                  blueprint:
                    domain: example.com
                    my_server_type: Ubuntu 11.10
                  providers:
                    base:
                      compute:
                        os: X
                  services:
                    web:
                      compute:
                        case-whitespace-test: 512mb
                        gigabyte-test: 8 gigabytes
                        mb-test: 512 Mb
                        memory: 2 Gb
                        number-only-test: 512
            """))
        fxn = deployment._get_input_provider_option
        self.assertEqual(fxn('os', 'base', resource_type='compute'), 'X')

    def test_get_bad_options(self):
        self.assertRaises(CheckmateValidationException, Deployment,
                yaml_to_dict("""
                environment:
                  providers:
                    base
                blueprint:
                  services:
                    web:
                  options:
                    my_server_type:
                      constrains:
                      - resource_type: compute
                        service: web
                        setting: os
                inputs:
                  blueprint:
                    domain: example.com
                    my_server_type: Ubuntu 11.10
                  providers:
                    base:
                      compute:
                        # Missing!
                  services:
                    web:
                      compute:
                        case-whitespace-test: 512mb
                        gigabyte-test: 8 gigabytes
                        mb-test: 512 Mb
                        memory: 2 Gb
                        number-only-test: 512
            """))

if __name__ == '__main__':
    unittest.main()
