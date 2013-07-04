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
from checkmate.db.mongodb import Driver
import mox
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
        self.mox = mox.Mox()
        self.driver = Driver(self._connection_string)

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_update_operation(self):
        self.mox.StubOutWithMock(tasks.operations, "update_operation")
        tasks.operations.update_operation("DEP1", "WID", driver=self,
                                          deployment_status=None, x=1) \
            .AndReturn(True)

        self.mox.ReplayAll()

        tasks.update_operation.lock_db = self.driver
        tasks.update_operation('DEP1', "WID", driver=self, x=1)
        self.mox.VerifyAll()

    def test_update_operation_with_deployment_status(self):
        self.mox.StubOutWithMock(tasks.operations, "update_operation")
        tasks.operations.update_operation("DEP1", "WID", driver=self,
                                          deployment_status="UP", x=1) \
            .AndReturn(True)

        self.mox.ReplayAll()

        tasks.update_operation.lock_db = self.driver
        tasks.update_operation('DEP1', "WID", driver=self,
                               deployment_status="UP",
                               x=1)
        self.mox.VerifyAll()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
