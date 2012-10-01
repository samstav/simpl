#!/usr/bin/env python
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate.environments import Environment
from checkmate.providers.base import PROVIDER_CLASSES, ProviderBase
from checkmate.utils import yaml_to_dict


class TestEnvironments(unittest.TestCase):
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
        self.assertIn('base', environment.get_providers(None))
        self.assertIsInstance(environment.select_provider(None,
                resource='widget'), ProviderBase)


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
