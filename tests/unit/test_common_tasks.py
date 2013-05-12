# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''

import unittest2 as unittest

import mox

from checkmate.common import tasks


class TestCommonTasks(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_update_operation(self):
        self.mox.StubOutWithMock(tasks.operations, "update_operation")
        tasks.operations.update_operation("DEP1", driver=self, x=1)\
            .AndReturn(True)

        self.mox.ReplayAll()
        tasks.update_operation('DEP1', driver=self, x=1)
        self.mox.VerifyAll()

    def test_update_deployment_status(self):
        self.mox.StubOutWithMock(tasks.deployment, "update_deployment_status")
        tasks.deployment.update_deployment_status("DEP1", "Z", driver=self)\
            .AndReturn(True)

        self.mox.ReplayAll()
        tasks.deployment.update_deployment_status('DEP1', "Z", driver=self)
        self.mox.VerifyAll()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
