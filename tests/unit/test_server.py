# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest2 as unittest

from checkmate.common import config
from checkmate.exceptions import CheckmateException
from checkmate.server import config_statsd

CONFIG = config.current()


class TestServer(unittest.TestCase):
    def test_config_statsd(self):
        '''Test that statsd config is parsed correctly.'''
        CONFIG.statsd = "111.222.222.111:1234"

        config_statsd()

        self.assertEqual(CONFIG.statsd_host, '111.222.222.111')
        self.assertEqual(CONFIG.statsd_port, '1234')

    def test_config_statsd_no_port(self):
        '''Tests that statsd config defaults port settings.'''
        CONFIG.statsd = "111.222.222.111"

        config_statsd()

        self.assertEqual(CONFIG.statsd_host, '111.222.222.111')
        self.assertEqual(CONFIG.statsd_port, 8125)

    def test_config_statsd_fail(self):
        '''Tests that statsd raises exception with invalid arg.'''
        CONFIG.statsd = '111.222.222.111:1234:1312'
        with self.assertRaises(CheckmateException):
            config_statsd()


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
