# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232,W0613
from __future__ import absolute_import

import logging
import mock
import os
import statsd as py_statsd
import unittest

from checkmate.common import config
from checkmate.common import statsd

CONFIG = config.current()
LOG = logging.getLogger(__name__)


def return_success(*args, **kwargs):
    return True


def return_failure(*args, **kwargs):
    raise StandardError()


class TestCollect(unittest.TestCase):
    '''Verifies the functionallity of statsd.collect.'''

    @mock.patch.object(os.environ, 'get')
    def test_collect_no_config(self, mock_get):
        '''Test that statsd.collect does nothing if not configured.'''
        mock_get.return_value = False
        self.assertTrue(statsd.collect(return_success)())

    @mock.patch.object(py_statsd.timer, 'Timer')
    @mock.patch.object(py_statsd.counter, 'Counter')
    @mock.patch.object(py_statsd.connection, 'Connection')
    @mock.patch.object(os, 'environ')
    def test_no_counter_no_timer(self, mock_environ, mock_conn, mock_counter,
                                 mock_timer):
        '''Verifies method calls with no counter or timer passed in.'''
        mock_environ.get = mock.MagicMock(return_value=True)
        mock_environ['STATSD_HOST'] = '111.222.222.111'
        mock_environ['STATSD_PORT'] = None
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
    @mock.patch.object(os, 'environ')
    def test_counter_timer(self, mock_environ, mock_conn):
        '''Verifies method calls with counter and timer passed in.'''
        mock_environ.get = mock.MagicMock(return_value=True)
        mock_environ['STATSD_HOST'] = '111.222.222.111'
        mock_environ['STATSD_PORT'] = None
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
    @mock.patch.object(os, 'environ')
    def test_exception_raised(self, mock_environ, mock_conn):
        '''Verifies method calls when exception raised during original run.'''
        mock_environ.get = mock.MagicMock(return_value=True)
        mock_environ['STATSD_HOST'] = '111.222.222.111'
        mock_environ['STATSD_PORT'] = None
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
