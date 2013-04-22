#!/usr/bin/env python
import logging
import pickle
import unittest2 as unittest

from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate.db import DbBase


class TestDbBase(unittest.TestCase):
    '''Test Database Driver Base Class'''

    def test_instantiation(self):
        '''Make sure initial variables are set'''
        dbb = DbBase("connection-string://")
        self.assertEquals(dbb.connection_string, "connection-string://")

    def test_serialization(self):
        '''Make sure initial variables are set'''
        dbb = DbBase("connection-string://")
        self.assertEqual(str(dbb), "connection-string://")
        self.assertEqual(repr(dbb), "<checkmate.db.base.DbBase "
                         "connection_string='connection-string://'>")
        dbb2 = pickle.loads(pickle.dumps(dbb))
        self.assertEqual(dbb2.connection_string, "connection-string://")


if __name__ == '__main__':
    # Run tests. Handle our parameters seprately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
