# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''Unit tests for functions in mongodb.py'''
import mock
import unittest

from checkmate.db import mongodb


class TestBuildFilter(unittest.TestCase):

    def test_return_value_if_no_operator_is_used(self):
        query = mongodb._build_filter('foobar')
        self.assertEqual(query, 'foobar')

    def test_recognize_not_equal_operator(self):
        query = mongodb._build_filter('!foobar')
        self.assertEqual(query, {'$ne': 'foobar'})

    def test_recognize_greater_than_operator(self):
        query = mongodb._build_filter('>foobar')
        self.assertEqual(query, {'$gt': 'foobar'})

    def test_recognize_greater_equal_operator(self):
        query = mongodb._build_filter('>=foobar')
        self.assertEqual(query, {'$gte': 'foobar'})

    def test_recognize_less_than_operator(self):
        query = mongodb._build_filter('<foobar')
        self.assertEqual(query, {'$lt': 'foobar'})

    def test_recognize_less_equal_operator(self):
        query = mongodb._build_filter('<=foobar')
        self.assertEqual(query, {'$lte': 'foobar'})

    def test_recognize_like_operator(self):
        query = mongodb._build_filter('%foobar')
        self.assertEqual(query, {'$regex': 'foobar', '$options': 'i'})


class TestMongoDB(unittest.TestCase):

    @mock.patch.object(mongodb.Driver, 'tune')
    def setUp(self, tune_mock):
        self.driver = mongodb.Driver('mongodb://fake.connection.string')

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


class TestGetDeployments(TestMongoDB):

    @mock.patch.object(mongodb.Driver, '_get_objects')
    def test_send_query_to_get_objects(self, __get_objects):
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


class TestGetObjects(TestMongoDB):

    @mock.patch.object(mongodb.Driver, '_get_client')
    @mock.patch.object(mongodb.Driver, '_build_filters')
    def test_send_query_to_build_filters(self, __build_filters, __get_client):
        self.driver._get_objects('deployments', query='fake query')
        __build_filters.assert_called_with(
            'deployments', None, False, None, 'fake query',
        )

    @mock.patch.object(mongodb.Driver, '_get_client')
    @mock.patch.object(mongodb.Driver, '_build_filters')
    @mock.patch.object(mongodb.Driver, '_get_count')
    def test_send_query_to_get_count(self, __get_count, __build_filters,
                                     __get_client):
        self.driver._get_objects('deployments',
                                 with_count=True,
                                 query='fake query')
        __get_count.assert_called_with(
            'deployments', None, False, None, 'fake query',
        )


class TestGetCount(TestMongoDB):

    @mock.patch.object(mongodb.Driver, '_get_client')
    @mock.patch.object(mongodb.Driver, '_build_filters')
    def test_send_query_to_build_filters(self, __build_filters, __get_client):
        self.driver._get_count('deployments', None, False, query='fake query')
        __build_filters.assert_called_with(
            'deployments', None, False, None, 'fake query',
        )


class TestBuildFilters(TestMongoDB):

    def test_create_empty_filter_if_no_query(self):
        filters = self.driver._build_filters('deployments', None, True, None,
                                             query=None)
        self.assertEqual(filters, {})

    def test_create_filter_for_specific_fields(self):
        filters = self.driver._build_filters('deployments', None, True, None,
                                             query={'name': 'foobar'})
        expected_filters = {'name': {'$options': 'i', '$regex': 'foobar'}}
        self.assertEqual(filters, expected_filters)

    def test_create_filter_with_all_fields_when_searching(self):
        query = {'search': 'foobar', 'whitelist': ['foo', 'bar']}
        filters = self.driver._build_filters('deployments', None, True, None,
                                             query=query)
        expected_filters = {
            '$or': [
                {'foo': {'$options': 'i', '$regex': 'foobar'}},
                {'bar': {'$options': 'i', '$regex': 'foobar'}},
            ]
        }
        self.assertEqual(filters, expected_filters)


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
