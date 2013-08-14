# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
import mock
import unittest

import pyrax

from checkmate.exceptions import (
    CheckmateException,
    CheckmateNoTokenError,
)
from checkmate.providers.rackspace.database import Provider


class TestDatabaseProvider(unittest.TestCase):
    def test_connect_invalid_context(self):
        context = 'invalid'
        try:
            Provider.connect(context)
        except CheckmateException as exc:
            self.assertEqual(str(exc), "Context passed into connect is an "
                             "unsupported type <type 'str'>.")

    def test_connect_no_auth_token(self):
        context = {}
        self.assertRaises(CheckmateNoTokenError, Provider.connect, context)

    def test_connect_region_from_region_map(self):
        context = {'auth_token': 'token', 'tenant': 12345, 'username': 'test'}
        pyrax.get_setting = mock.Mock(return_value=True)
        pyrax.auth_with_token = mock.Mock()
        Provider.connect(context, 'chicago')
        pyrax.auth_with_token.assert_called_with('token', 12345, 'test', 'ORD')

    def test_connect_region_from_context(self):
        context = {
            'auth_token': 'token',
            'tenant': 12345,
            'username': 'test',
            'region': 'SYD'
        }
        pyrax.get_setting = mock.Mock(return_value=True)
        pyrax.auth_with_token = mock.Mock()
        Provider.connect(context)
        pyrax.auth_with_token.assert_called_with('token', 12345, 'test', 'SYD')

    def test_connect_region_from_default(self):
        context = {
            'auth_token': 'token',
            'tenant': 12345,
            'username': 'test',
            'catalog': {}
        }
        pyrax.get_setting = mock.Mock(return_value=True)
        pyrax.auth_with_token = mock.Mock()
        Provider.find_a_region = mock.Mock(return_value=None)
        Provider.connect(context)
        pyrax.auth_with_token.assert_called_with('token', 12345, 'test', 'DFW')


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
