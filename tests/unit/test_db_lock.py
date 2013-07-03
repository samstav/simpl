import mox
import unittest

from checkmate.db.db_lock import DbLock


class TestDbLock(unittest.TestCase):
    def setUp(self):
        self.driver_mox = mox.Mox()
        self.driver = self.driver_mox.CreateMockAnything()

    def test_locking_using_a_context(self):
        self.driver.acquire_lock("key", 10)
        self.driver.release_lock("key")
        self.driver_mox.ReplayAll()

        with(DbLock(self.driver, "key", 10)):
            pass

    def test_locking_without_context(self):
        self.driver.acquire_lock("key", 10)
        self.driver_mox.ReplayAll()

        DbLock(self.driver, "key", 10)

    def tearDown(self):
        self.driver_mox.VerifyAll()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
