# pylint: disable=W0613,R0904

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

"""Tests for statsd decorator."""

import mock
import unittest

from checkmate.common import config
from checkmate.common import statsd

CONFIG = config.current()


def return_success(*args, **kwargs):
    """Helper method to simulate success."""
    return True


def return_failure(*args, **kwargs):
    """Helper method to mock a StandardError."""
    raise StandardError()


class TestCollect(unittest.TestCase):
    """Verifies the functionallity of statsd.collect."""

    @mock.patch.object(statsd, 'LOG')
    @mock.patch.object(statsd, 'CONFIG')
    def test_collect_no_config(self, mock_config, mock_log):
        """Test that statsd.collect does nothing if not configured."""
        mock_config.statsd_host = None
        self.assertTrue(statsd.collect(return_success)())
        mock_log.assertEqual(len(mock_log.debug.calls), 1)

    @mock.patch.object(statsd, 'CONFIG')
    @mock.patch.object(statsd.statsd.timer, 'Timer')
    @mock.patch.object(statsd.statsd.counter, 'Counter')
    @mock.patch.object(statsd.statsd.connection, 'Connection')
    def test_no_counter_no_timer(self, mock_conn, mock_counter, mock_timer,
                                 mock_config):
        """Verifies method calls with no counter or timer passed in."""
        mock_config.statsd_host = '111.222.222.111'
        connection = mock.Mock()
        mock_conn.return_value = connection
        counter = mock.Mock()
        mock_counter.return_value = counter
        timer = mock.Mock()
        mock_timer.return_value = timer

        self.assertTrue(statsd.collect(return_success)())

        mock_counter.assert_called_with("%s.status" % __name__, connection)
        assert counter.increment.mock_calls == [
            mock.call('return_success.started'),
            mock.call('return_success.success')
        ]
        mock_timer.assert_called_with("%s.duration" % __name__, connection)
        timer.start.assert_called_with()
        timer.stop.assert_called_with('return_success.success')

    @mock.patch.object(statsd.statsd.connection, 'Connection')
    @mock.patch.object(statsd, 'CONFIG')
    def test_counter_timer(self, mock_config, mock_conn):
        """Verifies method calls with counter and timer passed in."""
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

    @mock.patch.object(statsd.statsd.connection, 'Connection')
    @mock.patch.object(statsd, 'CONFIG')
    def test_exception_raised(self, mock_config, mock_conn):
        """Verifies method calls when exception raised during original run."""
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
    from checkmate import test
    test.run_with_params()
