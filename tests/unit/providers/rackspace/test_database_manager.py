# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
import mock
import unittest

from pyrax import exceptions as cdb_errors

from checkmate.exceptions import (
    CheckmateResumableException,
    CheckmateRetriableException,
)
from checkmate.providers.rackspace.database import Manager


class TestDatabaseManager(unittest.TestCase):
    '''Test Rackspace Database Manager functions.'''

    def test_wait_on_build_success(self):
        '''Verifies method calls and returns instance data.'''
        instance_id = 1234
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'ACTIVE'
        expected = {
            'status': 'ACTIVE',
            'status-message': ''
        }
        #Mock methods
        api.get = mock.MagicMock(return_value=instance)
        callback = mock.MagicMock(return_value=True)

        results = Manager.wait_on_build(instance_id, api, callback)

        api.get.assert_called_with(instance_id)
        #callback.assert_called_with({'status': 'ACTIVE'})

        self.assertEqual(results, expected)

    def test_wait_on_build_resumable(self):
        '''Verifies method calls and raises CheckmateResumableException.'''
        instance_id = 1234
        api = mock.Mock()

        #Mock methods
        api.get = mock.MagicMock(side_effect=cdb_errors.ClientException(
                                 123, "message"))
        callback = mock.MagicMock(return_value=True)
        try:
            Manager.wait_on_build(instance_id, api, callback)
        except CheckmateResumableException as exc:
            self.assertEqual(exc.error_message, 'message (HTTP 123)')
            self.assertEqual(exc.friendly_message, 'Error occurred in db '
                                                   'provider')

    def test_wait_on_build_error(self):
        '''Verifies method calls and raises StandardError after callback.'''
        instance_id = 1234
        api = mock.Mock()
        expected = {
            'status': 'ERROR',
            'status-message': 'Error waiting on resource to build',
            'error-message': ''
        }
        #Mock methods
        api.get = mock.MagicMock(side_effect=StandardError())
        callback = mock.MagicMock()
        try:
            Manager.wait_on_build(instance_id, api, callback)
        except StandardError:
            callback.assert_called_with(expected)

    def test_wait_on_build_retriable(self):
        '''Verifies method calls and raises CheckmateRetriableException.'''
        instance_id = 1234
        api = mock.Mock()
        instance = mock.Mock()
        instance.status = 'ERROR'
        expected = {
            'status': 'ERROR',
            'status-message': 'Instance went into status ERROR'
        }

        #Mock methods
        api.get = mock.MagicMock(return_value=instance)
        callback = mock.MagicMock()

        self.assertRaises(CheckmateRetriableException, Manager.wait_on_build,
                          instance_id, api, callback)

        api.get.assert_called_with(instance_id)
        callback.assert_called_with(expected)

    def test_sync_resource_success(self):
        '''Verifies method calls and returns success results.'''
        resource = {
            'instance': {
                'id': '123'
            }
        }
        api = mock.Mock()
        database = mock.Mock()
        database.status = 'ACTIVE'
        expected = {'status': 'ACTIVE'}
        api.get = mock.MagicMock(return_value=database)

        results = Manager.sync_resource(resource, api)
        api.get.assert_called_with('123')
        self.assertEqual(results, expected)

    def test_sync_resource_not_found(self):
        '''Verifies method calls and returns deleted results.'''
        resource = {
            'instance': {
                'id': '123'
            }
        }
        api = mock.Mock()
        expected = {'status': 'DELETED'}
        api.get = mock.MagicMock(side_effect=cdb_errors.ClientException(
                                 "test", "message"))
        results = Manager.sync_resource(resource, api)
        api.get.assert_called_with('123')
        self.assertEqual(results, expected)

    def test_sync_resource_missing_id(self):
        '''Verifies method calls and returns deleted results for missing id.'''
        resource = {
            'instance': {}
        }
        api = mock.Mock()
        expected = {'status': 'DELETED'}
        results = Manager.sync_resource(resource, api)
        self.assertEqual(results, expected)


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
