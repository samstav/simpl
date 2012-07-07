#!/usr/bin/env python
import copy
import unittest2 as unittest

from checkmate.deployments import plan
from checkmate.providers.base import PROVIDER_CLASSES, ProviderBase
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
        parsed = plan(deployment)
        self.assertDictEqual(original, parsed)

    def test_resource_generator(self):
        """Test the parser generates the right number of resources"""
        deployment = yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    back:
                      components: &widget
                        id: widget
                        provides:
                          widget: foo
                    front:
                      components: *widget
                      relations:
                        middle: foo
                    middle:
                      components: *widget
                      relations:
                        back: foo
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      vendor: test
                    common:
                      credentials:
                      - password: secret
                        username: tester
                inputs:
                  services:
                    middle:
                      widget:
                        count: 4
            """)

        PROVIDER_CLASSES['test.base'] = ProviderBase

        parsed = plan(deployment)
        services = parsed['blueprint']['services']
        self.assertEqual(len(services['front']['instances']), 1)
        self.assertEqual(len(services['middle']['instances']), 4)
        self.assertEqual(len(services['back']['instances']), 1)
        #import json
        #print json.dumps(parsed, indent=2)


if __name__ == '__main__':
    unittest.main()