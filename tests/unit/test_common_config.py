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
        self.assertIsNone(default.access_log)

        self.assertFalse(default.newrelic)
        self.assertIsNone(default.statsd)
        self.assertIsNone(default.statsd_host)
        self.assertEqual(default.statsd_port, 8125)

        self.assertFalse(default.with_ui)
        self.assertFalse(default.with_simulator)
        self.assertFalse(default.with_admin)
        self.assertFalse(default.eventlet)
        self.assertIsNone(default.backdoor_port)

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

        self.assertEqual(default.deployments_path,
                         '/var/local/checkmate/deployments')

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
        parsed = config.parse_arguments(['/prog'])
        self.assertFalse(parsed.with_admin)
        self.assertFalse(parsed.eventlet)

    def test_flag(self):
        parsed = config.parse_arguments(['/prog', '--with-admin'])
        self.assertTrue(parsed.with_admin)

    def test_flag_singlechar(self):
        parsed = config.parse_arguments(['/prog', '-e'])
        self.assertTrue(parsed.eventlet)

    def test_ignore_start(self):
        '''Ignore unused/old START position'''
        parsed = config.parse_arguments(['/prog', 'START', '-e'])
        self.assertTrue(parsed.eventlet)

    def test_start_as_address(self):
        '''Ensure START is not picked up as address'''
        parsed = config.parse_arguments(['/prog', 'START', '-e'])
        self.assertEqual(parsed.address, '127.0.0.1:8080')

    def test_address(self):
        parsed = config.parse_arguments(['/prog', '10.1.1.1'])
        self.assertEqual(parsed.address, '10.1.1.1')

    def test_port(self):
        parsed = config.parse_arguments(['/prog', '10.1.1.1:10000'])
        self.assertEqual(parsed.address, '10.1.1.1:10000')


class TestEnvParser(unittest.TestCase):
    def test_blank(self):
        parsed = config.parse_environment({})
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed, {})

    def test_one_value(self):
        parsed = config.parse_environment({
            'CHECKMATE_CHEF_LOCAL_PATH': '/tmp/not_default'})
        self.assertIn('deployments_path', parsed)
        self.assertEqual(parsed['deployments_path'], '/tmp/not_default')

    def test_applying_config(self):
        '''Check that we can take an env and apply it as a config.'''
        current = config.current()
        self.assertEqual(current.deployments_path,
                         '/var/local/checkmate/deployments')
        parsed = config.parse_environment({
            'CHECKMATE_CHEF_LOCAL_PATH': '/tmp/not_default'})
        current.update(parsed)
        self.assertEqual(current.deployments_path, '/tmp/not_default')

    @unittest.skip('No conflicts yet')
    def test_argument_wins(self):
        '''Check that command-line arguments win over environemnt variables.'''
        pass  # TODO: write this test whn we start the first conflict


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
