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
