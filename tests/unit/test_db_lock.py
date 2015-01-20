# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Tests for DB locks."""
import mock
import unittest

from checkmate.db import db_lock as cmdbl


class TestDbLock(unittest.TestCase):
    def setUp(self):
        self.driver = mock.Mock()

    def test_locking_using_a_context(self):
        self.driver.acquire_lock("key", 10)
        self.driver.release_lock("key")

        with(cmdbl.DbLock(self.driver, "key", 10)):
            pass

    def test_locking_without_context(self):
        self.driver.acquire_lock("key", 10)

        cmdbl.DbLock(self.driver, "key", 10)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
