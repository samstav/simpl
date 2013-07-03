# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''Unit tests for functions in sql.py'''
import unittest

from checkmate.db import sql


class TestSqlDB(unittest.TestCase):
    def test_parse_comparison_handles_simple_single_param(self):
        self.assertEqual("status == 'ACTIVE'", sql._parse_comparison('status', 'ACTIVE'))

    def test_parse_comparison_handles_bang(self):
        self.assertEqual("status != 'UP'", sql._parse_comparison('status', '!UP'))

    def test_parse_comparison_handles_greater_than(self):
        self.assertEqual("status > '4'", sql._parse_comparison('status', '>4'))

    def test_parse_comparison_handles_less_than(self):
        self.assertEqual("status < '234'", sql._parse_comparison('status', '<234'))

    def test_parse_comparison_handles_greater_than_or_equal(self):
        self.assertEqual("status >= '555'", sql._parse_comparison('status', '>=555'))

    def test_parse_comparison_handles_less_than_or_equal(self):
        self.assertEqual("status <= '321'", sql._parse_comparison('status', '<=321'))

    def test_parse_comparison_handles_tuple_of_multiple_statuses(self):
        self.assertEqual(
            "status in ('ACTIVE', 'UP')",
            sql._parse_comparison('status', ('ACTIVE', 'UP'))
        )

    def test_parse_comparison_handles_list_of_multiple_statuses(self):
        self.assertEqual(
            "status in ('GREEN', 'BLUE', 'NO_YELLOW')",
            sql._parse_comparison('status', ['GREEN', 'BLUE', 'NO_YELLOW'])
        )

    def test_parse_comparison_handles_single_status_in_list(self):
        self.assertEqual(
            "status != 'KNOT'",
            sql._parse_comparison('status', ['!KNOT'])
        )

    def test_parse_comparison_fails_with_multiple_statuses_and_operator(self):
        with self.assertRaises(Exception) as expected:
            sql._parse_comparison('status', ['UP', '!ACTIVE'])
        self.assertEqual(
            'Operators cannot be used when specifying multiple filters.',
            str(expected.exception)
        )


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
