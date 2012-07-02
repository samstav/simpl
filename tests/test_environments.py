#!/usr/bin/env python
import unittest2 as unittest

from checkmate.environments import Environment
from checkmate.providers.base import PROVIDER_CLASSES, ProviderBase
from checkmate.utils import yaml_to_dict


class TestEnvironments(unittest.TestCase):
    def test_HashSHA512(self):
        """Test the get_setting function"""
        environment = Environment({})
        hashed_value = environment.HashSHA512('test', salt="abcdef")
        self.assertEqual(hashed_value, '$6$abcdef$4bf7fed2ef99ba9306d90239d423'
                'ba85e4a4732293497cbcd8927a2c405e96f18fb454b5204afdf4e1b2591df'
                '883216b9117b8a63010300414bc1abbb92c6641')

    def test_HashMD5(self):
        """Test the get_setting function"""
        environment = Environment({})
        hashed_value = environment.HashMD5('test', salt="abcdef")
        self.assertEqual(hashed_value, '$1$abcdef$307d25203d209e1f7747885dc45c'
                '9b65')

    def test_provider_lookup(self):
        """Test that provider lookup uses environment keys"""
        definition = yaml_to_dict("""
                name: environment
                providers:
                  base:
                    provides:
                    - widget: foo
                    - widget: bar
                    vendor: test
                  common:
                    credentials:
                    - password: secret
                      username: tester
                      """)

        PROVIDER_CLASSES['test.base'] = ProviderBase

        environment = Environment(definition)
        self.assertIn('base', environment.get_providers())
        self.assertIsInstance(environment.select_provider(resource='widget'),
                ProviderBase)

if __name__ == '__main__':
    unittest.main()
