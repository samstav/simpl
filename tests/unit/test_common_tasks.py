# pylint: disable=C0103,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
"""Tests for common tasks."""
import logging
from checkmate.db.mongodb import Driver
import mock
import unittest

try:
    from mongobox import MongoBox

    SKIP = False
    REASON = None
except ImportError as exc:
    SKIP = True
    REASON = "'mongobox' not installed: %s" % exc
    MongoBox = object

from checkmate.common import tasks

LOG = logging.getLogger(__name__)


class TestCommonTasks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Fire up a sandboxed mongodb instance"""
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
        """Stop the sanboxed mongodb instance"""
        if hasattr(cls, 'box') and isinstance(cls.box, MongoBox):
            if cls.box.running() is True:
                cls.box.stop()
                cls.box = None

    def setUp(self):
        self.driver = Driver(self._connection_string)

    @mock.patch.object(tasks.operations, 'update_operation')
    def test_update_operation(self, mock_update):
        tasks.operations.update_operation.return_value = True

        tasks.update_operation.lock_db = self.driver
        tasks.update_operation('DEP1', "WID", driver=self, x=1)
        tasks.operations.update_operation.assert_called_once_with(
            'DEP1', 'WID', driver=self, deployment_status=None, x=1
        )

    @mock.patch.object(tasks.operations, 'update_operation')
    def test_update_operation_with_deployment_status(self, mock_update):
        tasks.operations.update_operation.return_value = True

        tasks.update_operation.lock_db = self.driver
        tasks.update_operation('DEP1', "WID", driver=self,
                               deployment_status="UP",
                               x=1)
        tasks.operations.update_operation.assert_called_once_with(
            'DEP1', 'WID', driver=self, deployment_status='UP', x=1
        )


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
