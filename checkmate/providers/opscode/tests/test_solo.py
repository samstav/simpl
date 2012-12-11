#!/usr/bin/env python
"""Tests for chef-solo provider"""
import logging
import unittest2 as unittest

import mox

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)


class TestChefSolo(unittest.TestCase):
    """Test ChefSolo Module"""

    def setUp(self):
        self.mox = mox.Mox()

    def test_provider_exists(self):
        """Check that module exists"""
        try:
            from checkmate.providers.opscode import solo
        except Exception as exc:
            self.assertFalse(True, msg="Expecting to be able to import solo "
                             "module")

    def test_provider_loads(self):
        """Check that module loads"""
        from checkmate.providers import get_provider_class
        self.assertEqual(get_provider_class('opscode', 'solo').__name__,
                         'checkmate.providers.opscode.solo')

    def test_provider_registers(self):
        """Check that module register"""
        from checkmate.providers import opscode, PROVIDER_CLASSES
        opscode.register()
        self.assertIn('opscode.chef-solo', PROVIDER_CLASSES)
        self.assertEqual(PROVIDER_CLASSES['opscode.chef-solo'].__name__,
                         'Provider')

    def tearDown(self):
        self.mox.UnsetStubs()


if __name__ == '__main__':
    # Run tests. Handle our parameters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
