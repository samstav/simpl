# pylint: disable=R0904,W0212

# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Tests for common config."""
import unittest

from checkmate.common import config
from checkmate.contrib import config as contrib_config


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
        self.assertEqual(default.organization, 'Blueprints')
        self.assertEqual(default.ref, 'master')
        self.assertIsNone(default.cache_dir)
        self.assertIsNone(default.preview_ref)
        self.assertIsNone(default.preview_tenants)
        self.assertIsNone(default.group_refs)

        self.assertEqual(default.deployments_path,
                         '/var/local/checkmate/deployments')

    def test_update_iterable(self):
        current = config.Config()
        current.update({'quiet': True})
        self.assertTrue(current.quiet)

    def test_update_iterables(self):
        current = config.Config()
        current.update({'quiet': True, 'verbose': True})
        self.assertTrue(current.quiet)
        self.assertTrue(current.verbose)

    def test_update_kwargs(self):
        current = config.Config()
        current.update(verbose=True)
        self.assertTrue(current.verbose)


class TestParsers(unittest.TestCase):
    def test_comma_separated_strs(self):
        expected = ['1', '2', '3']
        result = contrib_config.comma_separated_strings("1,2,3")
        self.assertItemsEqual(result, expected)

    def test_format_comma_separated(self):
        expected = dict(A='1', B='2', C='3')
        result = contrib_config.comma_separated_pairs("A=1,B=2,C=3")
        self.assertEqual(result, expected)


class TestArgParser(unittest.TestCase):

    def setUp(self):
        self.parsed = config.current()

    def tearDown(self):
        del self.parsed
        reload(config)

    def test_default(self):
        self.parsed.update(
            self.parsed.parse_cli(argv=['/prog']))
        self.assertFalse(self.parsed.with_admin)
        self.assertFalse(self.parsed.eventlet)

    def test_flag(self):
        self.parsed.update(
            self.parsed.parse_cli(argv=['/prog', '--with-admin']))
        self.assertTrue(self.parsed.with_admin)

    def test_flag_singlechar(self):
        self.parsed.update(
            self.parsed.parse_cli(argv=['/prog', '-e']))
        self.assertTrue(self.parsed.eventlet)

    def test_ignore_start(self):
        """Ignore unused/old START position."""
        self.parsed.update(
            self.parsed.parse_cli(argv=['/prog', 'START', '-e']))
        self.assertTrue(self.parsed.eventlet)

    def test_start_as_address(self):
        """Ensure START is not picked up as address."""
        self.parsed.update(
            self.parsed.parse_cli(argv=['/prog', 'START', '-e']))
        self.assertEqual(self.parsed.address, '127.0.0.1:8080')

    def test_address(self):
        self.parsed.update(
            self.parsed.parse_cli(argv=['/prog', '10.1.1.1']))
        self.assertEqual(self.parsed.address, '10.1.1.1')

    def test_port(self):
        self.parsed.update(
            self.parsed.parse_cli(argv=['/prog', '10.1.1.1:10000']))
        self.assertEqual(self.parsed.address, '10.1.1.1:10000')

    def test_allow_extras(self):
        self.parsed.update(
            self.parsed.parse_cli(argv=['/prog', '-e', '--concurrency'],
                                  permissive=True))
        self.assertFalse(hasattr(self.parsed, 'concurrency'))


class TestEnvParser(unittest.TestCase):
    def test_blank(self):
        parsed = config.Config().parse_env(env={})
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed, {})

    def test_one_value(self):
        parsed = config.current()
        parsed.update(parsed.parse_env(
            env={'CHECKMATE_CHEF_LOCAL_PATH': '/tmp/not_default'})
        )
        self.assertIn('deployments_path', parsed)
        self.assertEqual(parsed['deployments_path'], '/tmp/not_default')

    def test_applying_config(self):
        """Check that we can take an env and apply it as a config."""
        current = config.current()
        self.assertEqual(current.deployments_path,
                         '/var/local/checkmate/deployments')
        current.update(
            current.parse_env(
                env={'CHECKMATE_CHEF_LOCAL_PATH': '/tmp/not_default'})
        )
        self.assertEqual(current.deployments_path, '/tmp/not_default')

    @unittest.skip('No conflicts yet')
    def test_argument_wins(self):
        """Check that command-line arguments win over environemnt variables."""
        pass  # TODO(any): write this test when we start the first conflict


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
