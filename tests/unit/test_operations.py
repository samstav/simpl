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

from checkmate import operations


class TestOperations(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_update_operation(self):
        db = self.mox.CreateMockAnything()
        db.save_deployment('1234', {'operation': {'status': 'NEW'}},
                           partial=True).AndReturn(None)
        self.mox.ReplayAll()
        operations.update_operation('1234', status='NEW', driver=db)
        self.mox.VerifyAll()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
