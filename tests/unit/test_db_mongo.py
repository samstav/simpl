# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''Unit tests for functions in mongodb.py'''
import mock
import unittest

from checkmate.db import mongodb


class TestMongoDB(unittest.TestCase):
    def test_parse_comparison_handles_simple_single_param(self):
        self.assertEqual('ACTIVE', mongodb._parse_comparison('ACTIVE'))

    def test_parse_comparison_handles_bang(self):
        self.assertEqual({'$ne': 'UP'}, mongodb._parse_comparison('!UP'))

    def test_parse_comparison_handles_greater_than(self):
        self.assertEqual({'$gt': '4'}, mongodb._parse_comparison('>4'))

    def test_parse_comparison_handles_less_than(self):
        self.assertEqual({'$lt': '234'}, mongodb._parse_comparison('<234'))

    def test_parse_comparison_handles_greater_than_or_equal(self):
        self.assertEqual({'$gte': '555'}, mongodb._parse_comparison('>=555'))

    def test_parse_comparison_handles_less_than_or_equal(self):
        self.assertEqual({'$lte': '321'}, mongodb._parse_comparison('<=321'))

    def test_parse_comparison_handles_tuple_of_multiple_statuses(self):
        self.assertEqual(
            {'$in': ['ACTIVE', 'UP']},
            mongodb._parse_comparison(('ACTIVE', 'UP'))
        )

    def test_parse_comparison_handles_list_of_multiple_statuses(self):
        self.assertEqual(
            {'$in': ['GREEN', 'BLUE', 'NO_YELLOW']},
            mongodb._parse_comparison(['GREEN', 'BLUE', 'NO_YELLOW'])
        )

    def test_parse_comparison_handles_single_status_in_list(self):
        self.assertEqual(
            {'$ne': 'KNOT'},
            mongodb._parse_comparison(['!KNOT'])
        )

    def test_parse_comparison_fails_with_multiple_statuses_and_operator(self):
        with self.assertRaises(Exception) as expected:
            mongodb._parse_comparison(['UP', '!ACTIVE'])
        self.assertEqual(
            'Operators cannot be used when specifying multiple filters.',
            str(expected.exception)
        )


class TestGetDeployments(unittest.TestCase):

    def setUp(self):
        self.driver = mongodb.Driver('mongodb://fake.connection.string')

    def test_send_query_to_get_objects(self):
        with mock.patch.object(self.driver, '_get_objects') as __get_objects:
            self.driver.get_deployments(query='fake query')
            __get_objects.assert_called_with(
                'deployments',
                None,
                with_secrets=mock.ANY,
                offset=mock.ANY,
                limit=mock.ANY,
                with_count=mock.ANY,
                with_deleted=mock.ANY,
                status=mock.ANY,
                query='fake query',
            )


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
