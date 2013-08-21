# pylint: disable=C0103,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
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
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
