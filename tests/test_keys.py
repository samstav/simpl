#!/usr/bin/env python
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import keys


class TestEnvironments(unittest.TestCase):
    def test_hashSHA512(self):
        """Test the get_setting function"""
        hashed_value = keys.hash_SHA512('test', salt="abcdef")
        self.assertEqual(hashed_value, '$6$abcdef$4bf7fed2ef99ba9306d90239d423'
                'ba85e4a4732293497cbcd8927a2c405e96f18fb454b5204afdf4e1b2591df'
                '883216b9117b8a63010300414bc1abbb92c6641')

    def test_hashMD5(self):
        """Test the get_setting function"""
        hashed_value = keys.hash_MD5('test', salt="abcdef")
        self.assertEqual(hashed_value, '$1$abcdef$307d25203d209e1f7747885dc45c'
                '9b65')


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
