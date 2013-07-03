# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
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


class TestStatsd(unittest.TestCase):
    def test_collect_no_config(self):
        '''Test that statsd.collect does nothing if not configured.'''
        self.assertTrue(statsd.collect(return_success)())

    def test_collect_exception(self):
        '''Tests that statsd raises exception with invalid arg.'''
        CONFIG.statsd = '111.222.222.111:1234'
        CONFIG.statsd_host = '111.222.222.111'
        CONFIG.statsd_port = 1234

        mock_counter = py_statsd.counter.Counter('test')
        mock_counter.increment = mock.MagicMock()

        mock_timer = py_statsd.timer.Timer('test')
        mock_timer.start = mock.MagicMock()

        with self.assertRaises(StandardError):
            statsd.collect(return_failure)(statsd_counter=mock_counter,
                                           statsd_timer=mock_timer)

        mock_counter.increment.assert_called_with('return_failure.exceptions')

        mock_timer.start.assert_called_with()

        # counter increment within except StandardError block
        mock_counter.increment.assert_called_with('return_failure.exceptions')


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
