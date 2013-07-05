# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''

import logging
import unittest2 as unittest

from celery.task import task
import mock

from checkmate.db.common import ObjectLockedError
from checkmate.db.mongodb import Driver
from checkmate.exceptions import CheckmateResumableException
from checkmate.providers.rackspace import database

try:
    from mongobox import MongoBox

    SKIP = False
    REASON = None
except ImportError as exc:
    SKIP = True
    REASON = "'mongobox' not installed: %s" % exc
    MongoBox = object

from checkmate import celeryglobal as celery  # module to be renamed

LOG = logging.getLogger(__name__)


class TestSingleTask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        '''Fire up a sandboxed mongodb instance'''
        try:
            cls.box = MongoBox()
            cls.box.start()
            cls._connection_string = ("mongodb://localhost:%s/test" %
                                      cls.box.port)
        except StandardError as exc:
            LOG.exception(exc)
            if hasattr(cls, 'box'):
                del cls.box
            global SKIP
            global REASON
            SKIP = True
            REASON = str(exc)

    @classmethod
    def tearDownClass(cls):
        '''Stop the sanboxed mongodb instance'''
        if hasattr(cls, 'box') and isinstance(cls.box, MongoBox):
            if cls.box.running() is True:
                cls.box.stop()
                cls.box = None

    def setUp(self):
        self.driver = Driver(self._connection_string)

    def test_concurrent_tasks(self):
        lock_key = "async_dep_writer:DEP_10"
        self.driver.lock(lock_key, 3600)
        do_nothing.lock_db = self.driver
        self.assertRaises(ObjectLockedError, do_nothing, "DEP_10")
        self.driver.unlock(lock_key)
        do_nothing("DEP_10")


@task(base=celery.SingleTask, default_retry_delay=1, max_retries=4,
      lock_db=None, lock_key="async_dep_writer:{args[0]}", lock_timeout=50)
def do_nothing(key):
    pass

class TestProviderTask(unittest.TestCase):
    '''Tests ProviderTask functionality.'''

    def test_provider_task_success(self):
        '''Tests success run.'''
        context = {'region': 'ORD', 'resource': 1, 'deployment': {}}
        expected = {
            'api1': 'test_api',
            'name': 'test',
            'api2': 'test_api',
            'status': 'BLOCKED'
        }
        do_something.callback = mock.MagicMock(return_value=True)
        results = do_something(context, 'test', api='test_api')
        
        do_something.callback.assert_called_with(context, expected)
        self.assertEqual(results, expected)
        assert do_something.partial, 'Partial attr should be set'

    def test_provider_task_retry(self):
        '''Tests retry is called.'''
        context = {'region': 'ORD', 'resource': 1, 'deployment': {}}
        do_something.callback = mock.Mock()
        do_something.callback.side_effect = CheckmateResumableException(1,2,3)
        do_something.retry = mock.MagicMock()
        
        do_something(context, 'test', api='test_api')
        
        do_something.retry.assert_called_with(
            exc=do_something.callback.side_effect)

    @mock.patch('checkmate.deployments.tasks')
    def test_provider_task_callback(self, mocked_lib):
        '''Validates postback data in callback.'''
        context = {'region': 'ORD', 'resource': 1, 'deployment': {}}

        expected_postback = {
            'resources': {
                1: {
                    'status': 'ERROR',
                    'instance': {
                        'status': 'BLOCKED',
                        'api1': 'test_api',
                        'api2': 'test_api',
                        'name': 'test'
                    }
                }
            }
        }
        mocked_lib.postback = mock.MagicMock()
        
        do_something(context, 'test', api='test_api')
        
        mocked_lib.postback.assert_called_with({}, expected_postback)

@task(base=celery.ProviderTask, provider=database.Provider)
def do_something(context, name, api):
    return {
        'api1': do_something.api,
        'name': name,
        'api2': api,
        'status': 'BLOCKED'
    }


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params

    run_with_params(sys.argv[:])
