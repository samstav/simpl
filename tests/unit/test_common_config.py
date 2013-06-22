# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
Test cpheckmate.common.config
'''
import unittest2 as unittest

from checkmate.common import config


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        default = config.current()
        self.assertIsInstance(default, config.Config)

        self.assertIsNone(default.logconfig)
        self.assertFalse(default.debug)
        self.assertFalse(default.verbose)
        self.assertFalse(default.trace_calls)

        self.assertFalse(default.newrelic)
        self.assertFalse(default.statsd)
        self.assertIsNone(default.statsd_host)
        self.assertEqual(default.statsd_port, 8125)

        self.assertFalse(default.with_ui)
        self.assertFalse(default.with_simulator)
        self.assertFalse(default.with_admin)
        self.assertFalse(default.eventlet)
        self.assertFalse(default.eager)
        self.assertFalse(default.worker)

        self.assertFalse(default.webhook)
        self.assertIsNone(default.github_api)
        self.assertIsNone(default.organization)
        self.assertEqual(default.ref, 'stable')
        self.assertIsNone(default.cache_dir)
        self.assertEqual(default.preview_ref, 'master')
        self.assertIsNone(default.preview_tenants)
        self.assertEqual(default.group_refs, {})

    def test_update_iterable(self):
        current = config.Config()
        current.update({'quiet': True})
        self.assertTrue(current.quiet)

    def test_update_iterables(self):
        current = config.Config()
        current.update({'quiet': True}, {'verbose': True})
        self.assertTrue(current.quiet)
        self.assertTrue(current.verbose)

    def test_update_kwargs(self):
        current = config.Config()
        current.update(verbose=True)
        self.assertTrue(current.verbose)


class TestParsers(unittest.TestCase):
    def test_comma_separated_strs(self):
        expected = ['1', '2', '3']
        result = config._comma_separated_strs("1,2,3")
        self.assertItemsEqual(result, expected)

    def test_comma_separated_key_value_pairs(self):
        expected = dict(A='1', B='2', C='3')
        result = config._comma_separated_key_value_pairs("A=1,B=2,C=3")
        self.assertEqual(result, expected)


class TestArgParser(unittest.TestCase):
    def test_default(self):
        parsed = config.parse_arguments([])
        self.assertFalse(parsed.with_admin)
        self.assertFalse(parsed.eventlet)

    def test_flag(self):
        parsed = config.parse_arguments(['--with-admin'])
        self.assertTrue(parsed.with_admin)

    def test_flag_singlechar(self):
        parsed = config.parse_arguments(['-e'])
        self.assertTrue(parsed.eventlet)

    def test_ignore_start(self):
        '''Ignore unused/old START position'''
        parsed = config.parse_arguments(['START', '-e'])
        self.assertTrue(parsed.eventlet)

    def test_address(self):
        parsed = config.parse_arguments(['10.1.1.1'])
        self.assertEqual(parsed.address, '10.1.1.1')

    def test_port(self):
        parsed = config.parse_arguments(['10.1.1.1:10000'])
        self.assertEqual(parsed.address, '10.1.1.1:10000')


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
