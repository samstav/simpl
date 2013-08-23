"""Tests for DB locks."""
import mock
import unittest

from checkmate.db.db_lock import DbLock


class TestDbLock(unittest.TestCase):
    def setUp(self):
        self.driver = mock.Mock()

    def test_locking_using_a_context(self):
        self.driver.acquire_lock("key", 10)
        self.driver.release_lock("key")

        with(DbLock(self.driver, "key", 10)):
            pass

    def test_locking_without_context(self):
        self.driver.acquire_lock("key", 10)

        DbLock(self.driver, "key", 10)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
