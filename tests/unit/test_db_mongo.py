# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''Unit tests for functions in mongodb.py'''
import unittest

from checkmate.db import mongodb


class TestMongoDB(unittest.TestCase):
    def test_parse_comparison_handles_simple_single_param(self):
        self.assertEqual('ACTIVE', mongodb.parse_comparison('ACTIVE'))

    def test_parse_comparison_handles_bang(self):
        self.assertEqual({'$ne': 'UP'}, mongodb.parse_comparison('!UP'))

    def test_parse_comparison_handles_greater_than(self):
        self.assertEqual({'$gt': '4'}, mongodb.parse_comparison('>4'))

    def test_parse_comparison_handles_less_than(self):
        self.assertEqual({'$lt': '234'}, mongodb.parse_comparison('<234'))

    def test_parse_comparison_handles_greater_than_or_equal(self):
        self.assertEqual({'$gte': '555'}, mongodb.parse_comparison('>=555'))

    def test_parse_comparison_handles_less_than_or_equal(self):
        self.assertEqual({'$lte': '321'}, mongodb.parse_comparison('<=321'))

    def test_parse_comparison_handles_tuple_of_multiple_statuses(self):
        self.assertEqual(
            {'$in': ['ACTIVE', 'UP']},
            mongodb.parse_comparison(('ACTIVE', 'UP'))
        )

    def test_parse_comparison_handles_list_of_multiple_statuses(self):
        self.assertEqual(
            {'$in': ['GREEN', 'BLUE', 'NO_YELLOW']},
            mongodb.parse_comparison(['GREEN', 'BLUE', 'NO_YELLOW'])
        )

    def test_parse_comparison_handles_single_status_in_list(self):
        self.assertEqual(
            {'$ne': 'KNOT'},
            mongodb.parse_comparison(['!KNOT'])
        )

    def test_parse_comparison_fails_with_multiple_statuses_and_operator(self):
        with self.assertRaises(Exception) as expected:
            mongodb.parse_comparison(['UP', '!ACTIVE'])
        self.assertEqual(
            'Operators cannot be used when specifying multiple filters.',
            str(expected.exception)
        )


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
