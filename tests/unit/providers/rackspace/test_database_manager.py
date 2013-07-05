#!/usr/bin/env python
# encoding: utf-8
import mock
import unittest

from clouddb import errors as cdb_errors

from checkmate.exceptions import (
    CheckmateException,
    CheckmateResumableException,
)
from checkmate.providers.rackspace.database import Manager


class test_database(unittest.TestCase):
    '''Test Rackspace Database Manager functions.'''

    def setUp(self):
        self.MANAGER = Manager()

    def test_wait_on_build_pop_true(self):
        '''Verifies method calls and returns True.'''
        instance_id = 1234
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'ACTIVE'

        #Mock methods
        api.get_instance = mock.MagicMock(return_value=instance)
        callback = mock.MagicMock(return_value=True)

        results = self.MANAGER.wait_on_build_pop(instance_id, api, callback)

        api.get_instance.assert_called_with(instance_id)
        callback.assert_called_with({'status': 'ACTIVE'})

        self.assertEqual(results, True)

    def test_wait_on_build_pop_false(self):
        '''Verifies method calls and returns False.'''
        instance_id = 1234
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'BUILDING'

        #Mock methods
        api.get_instance = mock.MagicMock(return_value=instance)
        callback = mock.MagicMock(return_value=True)

        results = self.MANAGER.wait_on_build_pop(instance_id, api, callback)

        api.get_instance.assert_called_with(instance_id)
        callback.assert_called_with({'status': 'BUILDING'})

        self.assertEqual(results, False)

    def test_wait_on_build_pop_resumable(self):
        '''Verifies method calls and returns True.'''
        instance_id = 1234
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'ERROR'

        #Mock methods
        api.get_instance = mock.MagicMock(side_effect=cdb_errors.ResponseError(
                                          "test", "message"))
        callback = mock.MagicMock(return_value=True)
        try:
            self.MANAGER.wait_on_build_pop(instance_id, api, callback)
        except CheckmateResumableException as exc:
            self.assertEqual(exc.message, 'message')
            self.assertEqual(exc.error_help, 'test')
            self.assertEqual(exc.error_type, 'RS_DB_ResponseError')

    def test_wait_on_build_pop_error(self):
        '''Verifies method calls and returns False.'''
        instance_id = 1234
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'ERROR'

        #Mock methods
        api.get_instance = mock.MagicMock(return_value=instance)
        callback = mock.MagicMock(return_value=True)

        self.assertRaises(CheckmateException, self.MANAGER.wait_on_build_pop,
                          instance_id, api, callback)


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
