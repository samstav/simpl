# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232,W0613
from __future__ import absolute_import

import mock
import statsd as py_statsd
import unittest

from checkmate.common import config
from checkmate.common import statsd

CONFIG = config.current()


def return_success(*args, **kwargs):
    return True


def return_failure(*args, **kwargs):
    raise StandardError()


class TestCollect(unittest.TestCase):
    '''Verifies the functionallity of statsd.collect.'''

    @mock.patch.object(statsd, 'CONFIG')
    def test_collect_no_config(self, mock_config):
        '''Test that statsd.collect does nothing if not configured.'''
        mock_config.statsd_host = None
        self.assertTrue(statsd.collect(return_success)())

    @mock.patch.object(statsd, 'CONFIG')
    @mock.patch.object(py_statsd.timer, 'Timer')
    @mock.patch.object(py_statsd.counter, 'Counter')
    @mock.patch.object(py_statsd.connection, 'Connection')
    def test_no_counter_no_timer(self, mock_conn, mock_counter, mock_timer,
                                 mock_config):
        '''Verifies method calls with no counter or timer passed in.'''
        mock_config.statsd_host = '111.222.222.111'
        connection = mock.Mock()
        mock_conn.return_value = connection
        counter = mock.Mock()
        mock_counter.return_value = counter
        timer = mock.Mock()
        mock_timer.return_value = timer

        self.assertTrue(statsd.collect(return_success)())

        mock_counter.assert_called_with('tests.unit.test_statsd.status',
                                        connection)
        assert counter.increment.mock_calls == [
            mock.call('return_success.started'),
            mock.call('return_success.success')
        ]
        mock_timer.assert_called_with('tests.unit.test_statsd.duration',
                                      connection)
        timer.start.assert_called_with()
        timer.stop.assert_called_with('return_success.success')

    @mock.patch.object(py_statsd.connection, 'Connection')
    @mock.patch.object(statsd, 'CONFIG')
    def test_counter_timer(self, mock_config, mock_conn):
        '''Verifies method calls with counter and timer passed in.'''
        mock_config.statsd_host = '111.222.222.111'
        counter = mock.Mock()
        timer = mock.Mock()

        self.assertTrue(statsd.collect(return_success)(statsd_counter=counter,
                                                       statsd_timer=timer))

        assert counter.increment.mock_calls == [
            mock.call('return_success.started'),
            mock.call('return_success.success')
        ]
        timer.start.assert_called_with()
        timer.stop.assert_called_with('return_success.success')

    @mock.patch.object(py_statsd.connection, 'Connection')
    @mock.patch.object(statsd, 'CONFIG')
    def test_exception_raised(self, mock_config, mock_conn):
        '''Verifies method calls when exception raised during original run.'''
        mock_config.statsd_host = '111.222.222.111'
        counter = mock.Mock()
        timer = mock.Mock()

        with self.assertRaises(StandardError):
            statsd.collect(return_failure)(statsd_counter=counter,
                                           statsd_timer=timer)

        assert counter.increment.mock_calls == [
            mock.call('return_failure.started'),
            mock.call('return_failure.exceptions')
        ]


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate import test
    import sys

    test.run_with_params(sys.argv[:])
