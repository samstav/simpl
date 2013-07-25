# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''Unit tests for functions in sql.py'''
import mock
import unittest

from checkmate.db import sql


class TestSqlDB(unittest.TestCase):

    def setUp(self):
        self.driver = sql.Driver('sqlite://')

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


class TestGetDeployments(TestSqlDB):

    @mock.patch.object(sql.Driver, '_get_objects')
    def test_send_query_to_get_objects(self, __get_objects):
        self.driver.get_deployments(query='fake query')
        __get_objects.assert_called_with(
            mock.ANY,
            mock.ANY,
            with_secrets=mock.ANY,
            offset=mock.ANY,
            limit=mock.ANY,
            with_count=mock.ANY,
            with_deleted=mock.ANY,
            status=mock.ANY,
            query='fake query',
        )


class TestGetObjects(TestSqlDB):

    @mock.patch.object(sql.Driver, '_add_filters')
    def test_send_query_to_add_filters(self, _add_filters):
        self.driver._get_objects('deployments', query='fake query')
        _add_filters.assert_called_with(
            'deployments',
            mock.ANY, mock.ANY, mock.ANY, mock.ANY,
            'fake query',
        )

    @mock.patch.object(sql.Driver, '_add_filters')
    @mock.patch.object(sql.Driver, '_get_count')
    def test_send_query_to_get_count(self, _get_count, _add_filters):
        self.driver._get_objects('deployments', with_count=True,
                                 query='fake query')
        _get_count.assert_called_with(
            mock.ANY, mock.ANY, mock.ANY, mock.ANY,
            'fake query',
        )


class TestAddFilters(TestSqlDB):

    def setUp(self):
        super(TestAddFilters, self).setUp()
        self.query = mock.Mock()
        self.query.filter.return_value = self.query
        self.klass = sql.Deployment

    def test_create_empty_filter_if_no_query(self):
        filters = self.driver._add_filters(self.klass, self.query, None, True,
                                           None, query_params=None)
        self.assertEqual(self.query.call_count, 0)

    @mock.patch.object(sql, '_parse_comparison')
    def test_create_filter_for_specific_fields(self, _parse_comparison):
        filters = self.driver._add_filters(self.klass, self.query,
                                           None, True, None,
                                           query_params={'name': 'foobar'})
        _parse_comparison.assert_called_with('deployments_name', 'foobar')
        self.assertEqual(self.query.filter.call_count, 1)

    @mock.patch.object(sql, 'or_')
    def test_create_filter_with_all_fields_when_searching(self, or_):
        query_params = {'search': 'foobar', 'whitelist': ['name', 'tenantId']}
        filters = self.driver._add_filters(self.klass, self.query,
                                           None, True, None,
                                           query_params=query_params)
        expected_filters = [
            "name LIKE '%foobar%'",
            "tenantId LIKE '%foobar%'",
        ]
        or_.assert_called_with(*expected_filters)


class TestGetCount(TestSqlDB):

    @mock.patch.object(sql.Driver, '_add_filters')
    def test_send_query_to_add_filters(self, _add_filters):
        self.driver.session = mock.Mock()
        self.driver._get_count(mock.ANY, mock.ANY, mock.ANY,
                               query='fake query')
        _add_filters.assert_called_with(
            mock.ANY, mock.ANY, mock.ANY, mock.ANY, mock.ANY,
            'fake query',
        )


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys
    test.run_with_params(sys.argv[:])
