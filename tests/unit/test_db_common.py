# pylint: disable=C0103,R0904

# Copyright (c) 2011-2013 Rackspace Hosting
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

"""Tests for DbCommon."""
import unittest
import uuid

from checkmate.db import common


class TestDbCommonAnyID(unittest.TestCase):

    def test_any_id_problems_ok(self):
        self.assertIsNone(common.any_id_problems('12'))

    def test_any_tid_problems_uuid_ok(self):
        self.assertIsNone(common.any_id_problems(uuid.uuid4().hex))

    def test_any_id_problems_one_digit(self):
        self.assertIsNone(common.any_id_problems('1'))

    def test_any_id_problems_one_char(self):
        self.assertIsNone(common.any_id_problems('a'))

    def test_any_id_problems_max_char(self):
        self.assertIsNone(common.any_id_problems('x' * 32))

    def test_any_id_problems_too_long(self):
        self.assertEqual(common.any_id_problems('x' * 33), "ID must be 1 to "
                         "32 characters")

    def test_any_id_problems_none(self):
        self.assertEqual(common.any_id_problems(None), 'ID cannot be blank')

    def test_any_id_problems_blank(self):
        self.assertEqual(common.any_id_problems(''), 'ID cannot be blank')

    def test_any_id_problems_space(self):
        self.assertEqual(common.any_id_problems(' '), "Invalid start "
                         "character ' '. ID can start with any of 'abcdefghijk"
                         "lmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'"
                         )

    def test_any_id_problems_start_invalid(self):
        self.assertEqual(common.any_id_problems('_1'), "Invalid start "
                         "character '_'. ID can start with any of 'abcdefghijk"
                         "lmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'"
                         )

    def test_any_id_problems_invalid_char(self):
        self.assertEqual(common.any_id_problems('1^2'), "Invalid character "
                         "'^'. Allowed characters are "
                         "'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWX"
                         "YZ0123456789-_.+~@'")


class TestDbCommonTenantID(unittest.TestCase):

    def test_any_tenant_id_problems_ok(self):
        self.assertIsNone(common.any_tenant_id_problems('12'))

    def test_any_tenant_id_problems_uuid_ok(self):
        self.assertIsNone(common.any_tenant_id_problems(uuid.uuid4().hex))

    def test_any_tenant_id_problems_one_digit(self):
        self.assertIsNone(common.any_tenant_id_problems('1'))

    def test_any_tenant_id_problems_one_char(self):
        self.assertIsNone(common.any_tenant_id_problems('a'))

    def test_any_tenant_id_problems_max_char(self):
        self.assertIsNone(common.any_tenant_id_problems('x' * 255))

    def test_any_tenant_id_problems_too_long(self):
        self.assertEqual(common.any_tenant_id_problems('x' * 256), "Tenant ID "
                         "must be 1 to 255 characters")

    def test_any_tenant_id_problems_none(self):
        self.assertEqual(common.any_tenant_id_problems(None), 'Tenant ID '
                         'cannot be blank')

    def test_any_tenant_id_problems_blank(self):
        self.assertEqual(common.any_tenant_id_problems(''), 'Tenant ID cannot '
                         'be blank')

    def test_any_tenant_id_problems_space(self):
        self.assertEqual(common.any_tenant_id_problems(' '), "Invalid start "
                         "character ' '. Tenant ID can start with any of 'abcd"
                         "efghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123"
                         "456789'")

    def test_any_tenant_id_problems_start_invalid(self):
        self.assertEqual(common.any_tenant_id_problems('_1'), "Invalid start "
                         "character '_'. Tenant ID can start with any of 'abcd"
                         "efghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123"
                         "456789'")

    def test_any_tenant_id_problems_invalid_char(self):
        self.assertEqual(common.any_tenant_id_problems('1|2'), "Invalid "
                         "character '|' in Tenant ID. Allowed charaters are "
                         "'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXY"
                         "Z0123456789-_.+~@()[]*&^=%$#!<>'")


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
