#!/usr/bin/env python
import logging
import unittest2 as unittest

from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import test
from checkmate.providers.rackspace import loadbalancer


class TestLoadBalancer(test.ProviderTester):
    """ Test Load-Balancer Provider """
    klass = loadbalancer.Provider

    def test_provider(self):
        provider = loadbalancer.Provider({})
        self.assertEqual(provider.key, 'rackspace.load-balancer')


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
