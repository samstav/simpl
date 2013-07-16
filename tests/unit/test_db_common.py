# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
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
                         "'^'. Allowed characters are 'abcdefghijklmnopqrstuvwx"
                         "yzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.+~@'")


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
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
