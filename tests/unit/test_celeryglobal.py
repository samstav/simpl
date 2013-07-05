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

from checkmate.db.common import ObjectLockedError
from checkmate.db.mongodb import Driver

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
        '''Fire up a sandboxed mongodb instance.'''
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
        '''Stop the sanboxed mongodb instance.'''
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


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params

    run_with_params(sys.argv[:])
