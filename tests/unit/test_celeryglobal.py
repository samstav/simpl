# pylint: disable=W0603
"""Tests for Celery."""
import logging
import unittest

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
        """Fire up a sandboxed mongodb instance."""
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
        """Stop the sanboxed mongodb instance."""
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
    """Placeholder method for the task decorator."""
    return key


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
