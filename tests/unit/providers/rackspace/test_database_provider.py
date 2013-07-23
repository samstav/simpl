# encoding: utf-8
'''Module for testing Database Provider class.'''
import mock
import unittest

import pyrax

from checkmate.exceptions import (
    CheckmateException,
    CheckmateNoTokenError,
)
from checkmate.providers.rackspace.database import Provider


class TestDatabaseProvider(unittest.TestCase):
    '''Test Rackspace Database Provider functions.'''
    def test_connect_invalid_context(self):
        '''Validates context converted to RequestContext type.'''
        context = 'invalid'
        try:
            Provider.connect(context)
        except CheckmateException as exc:
            self.assertEqual(str(exc), "Context passed into connect is an "
                             "unsupported type <type 'str'>.")

    def test_connect_no_auth_token(self):
        '''Validates NoTokenError raised.'''
        context = {}
        self.assertRaises(CheckmateNoTokenError, Provider.connect, context)

    def test_connect_region_from_region_map(self):
        '''Verifies region pulled from region map from city name.'''
        context = {'auth_token': 'token', 'tenant': 12345, 'username': 'test'}
        pyrax.get_setting = mock.Mock(return_value=True)
        pyrax.auth_with_token = mock.Mock()
        Provider.connect(context, 'chicago')
        pyrax.auth_with_token.assert_called_with('token', 12345, 'test', 'ORD')

    def test_connect_region_from_context(self):
        '''Verifies region pulled from context.'''
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
        '''Verifies region pulled from context.'''
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
