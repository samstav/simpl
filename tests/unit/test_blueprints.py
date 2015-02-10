# pylint: disable=C0103,R0904,W0212

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

"""Tests for Blueprints class."""
import copy
import os
import unittest

import mock

from checkmate import blueprints
from checkmate import exceptions


class TestBlueprints(unittest.TestCase):
    """Tests for main blueprints module."""

    def test_schema(self):
        """Test the schema validates a blueprint with all possible fields."""
        blueprint = {
            'id': 'test',
            'version': '1.1.0',
            'meta-data': {
                'schema-version': 'v0.7',
                'my-random-metadata': 'woohoooo!!!!',
            },
            'name': 'test',
            'services': {},
            'options': {},
            'resources': {},
            'display-outputs': {},
            'documentation': {},
            'source': {
                'sha': '24438A93485762345',
                'repo-url': 'http://github.com/checkmate/wordpress',
                'ref': 'refs/branch/master',
            }
        }
        valid = blueprints.Blueprint(blueprint)
        self.assertDictEqual(valid._data, blueprint)

    def test_schema_with_options(self):
        """Test schema for blueprint options."""
        blueprint = {
            'id': 'test',
            'name': 'test',
            'services': {},
            'options': {
                "foo": {
                    "type": "integer",
                    "default": 4,
                    "constrains": [
                        {
                            "service": "service1",
                            "type": "application",
                            "interface": "none"
                        }
                    ]
                },
                "bar": {
                    "type": "string",
                    "default": "Empty",
                    "display-hints": {
                        "group": "An option group",
                        "weight": 1
                    },
                    "constrains": [
                        {
                            "service": "service2",
                            "type": "application",
                            "interface": "another"
                        }
                    ]
                },
            },
            'resources': {},
        }
        expected = copy.deepcopy(blueprint)
        expected['meta-data'] = {'schema-version': 'v0.7'}
        valid = blueprints.Blueprint(blueprint)
        self.assertDictEqual(valid._data, expected)

    def test_schema_negative(self):
        """Test schema failsd on bad blueprint."""
        blueprint = {
            'nope': None
        }
        self.assertRaises(exceptions.CheckmateValidationException,
                          blueprints.Blueprint, blueprint)

    def test_conversion_from_pre_v0_dot_7(self):
        """Test schema conversion."""
        blueprint = {
            'id': 'test',
            'name': 'test',
            'services': {},
            'options': {
                'old_format_int': {
                    'type': 'int',
                    'regex': '^[a-zA-Z]$'
                },
                'old_format_select_and_choice': {
                    'type': 'select',
                    'choice': [{'name': 'First', 'value': 'A'},
                               {'name': 'Second', 'value': 'B'}]
                },
                'old_format_combo_and_sample': {
                    'type': 'combo',
                    'choice': [1, 2],
                    'sample': 'like this!',
                },
                'old_format_url': {
                    'type': 'url',
                    'protocols': ['http', 'https'],
                },
                'old_format_region': {
                    'type': 'region',
                },
            },
            'resources': {},
        }
        expected = {
            'id': 'test',
            'meta-data': {
                'schema-version': 'v0.7',
            },
            'name': 'test',
            'services': {},
            'options': {
                'old_format_int': {
                    'type': 'integer',
                    'constraints': [{'regex': '^[a-zA-Z]$'}]
                },
                'old_format_select_and_choice': {
                    'type': 'string',
                    'display-hints': {
                        'choice': [{'name': 'First', 'value': 'A'},
                                   {'name': 'Second', 'value': 'B'}],
                    },
                },
                'old_format_combo_and_sample': {
                    'type': 'string',
                    'display-hints': {
                        'choice': [1, 2],
                        'sample': 'like this!',
                    },
                },
                'old_format_url': {
                    'type': 'url',
                    'constraints': [{'protocols': ['http', 'https']}],
                },
                'old_format_region': {
                    'type': 'string',
                },
            },
            'resources': {},
        }
        converted = blueprints.Blueprint(blueprint)
        self.assertDictEqual(converted._data, expected)

    def test_future_blueprint_version(self):
        """Test future schema is rejected by this version of the server."""
        blueprint = {
            'meta-data': {
                'schema-version': 'unrecognized',
            },
        }
        self.assertRaisesRegexp(exceptions.CheckmateValidationException,
                                "This server does not support version "
                                "'unrecognized' blueprints",
                                blueprints.Blueprint, blueprint)


class TestAnonymousGitHubManager(unittest.TestCase):
    """Test anonymous github manager."""

    def setUp(self):
        self.config = mock.Mock()
        self.config.anonymous_github_base_uri = 'http://localhost'
        self.config.anonymous_github_org = 'checkmate-blueprints'
        self.config.anonymous_github_ref = 'master'
        self.config.cache_dir = '/tmp'

    def test_no_base_uri(self):
        """Verify exception raised if no base uri supplied."""
        conf = self.config
        conf.anonymous_github_base_uri = None
        with self.assertRaises(AssertionError):
            blueprints.GitHubManager(conf)

    def test_no_org(self):
        """"Verify exception raised if no github org supplied."""
        conf = self.config
        conf.anonymous_github_org = None
        with self.assertRaises(AssertionError):
            blueprints.AnonymousGitHubManager(conf)

    def test_no_ref(self):
        """Verify exception raised if no github ref supplied."""
        conf = self.config
        conf.anonymous_github_ref = None
        with self.assertRaises(AssertionError):
            blueprints.AnonymousGitHubManager(conf)

    def test_default_cache_dir(self):
        """Verify cache_root is not None if no cache_dir is supplied."""
        conf = self.config
        conf.cache_dir = None
        gh = blueprints.AnonymousGitHubManager(conf)
        self.assertIsNotNone(gh._cache_root)


class TestGitHubManagerTenantTag(unittest.TestCase):
    """Test github manager filtering by tenants."""

    def setUp(self):
        self.config = mock.Mock()
        self.config.github_api = 'http://localhost'
        self.config.organization = 'blueprints'
        self.config.cache_dir = 'blah'
        self.config.group_refs = {}
        self.config.preview_tenants = []
        self.config.github_token = None
        self._manager = blueprints.GitHubManager(self.config)

    def test_no_api(self):
        """Verify exception raised if no API object supplied."""
        conf = self.config
        conf.github_api = None
        with self.assertRaises(AssertionError):
            blueprints.GitHubManager(conf)

    def test_no_org(self):
        """"Verify exception raised if no gihub org supplied."""
        conf = self.config
        conf.organization = None
        with self.assertRaises(AssertionError):
            blueprints.GitHubManager(conf)

    def test_no_group_refs(self):
        """"Verify exception raised if no group refs supplied."""
        conf = self.config
        conf.group_refs = None
        self.assertIsInstance(
            blueprints.GitHubManager(conf), blueprints.GitHubManager)

    def test_failsafe_returns_master(self):
        """Verify default behaviour is to return master branch."""
        self._manager._ref = None
        self.assertEqual(self._manager.get_tenant_tag('A', []), 'master')

    def test_default_returns_ref(self):
        """Verify default ref is returned when no previews exist."""
        self._manager._ref = 'blah'
        self.assertEqual(self._manager.get_tenant_tag('A', []), 'blah')

    def test_preview_falls_back_to_ref(self):
        """Verify default ref is returned when previews don't have refs."""
        self._manager._ref = 'safe'
        self._manager._preview_ref = None
        self._manager._preview_tenants = ['X']
        self.assertEqual(self._manager.get_tenant_tag('X', []), 'safe')

    def test_preview_returns_preview_ref(self):
        """Verify matching preview tenant returns matching ref."""
        self._manager._preview_ref = 'coming-soon'
        self._manager._preview_tenants = ['X']
        self.assertEqual(self._manager.get_tenant_tag('X', []), 'coming-soon')

    def test_preview_negative(self):
        """Verify default returned with previews and no match."""
        self._manager._ref = 'plain'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self.assertEqual(self._manager.get_tenant_tag('Y', []), 'plain')

    def test_groups_no_match(self):
        """Verify default returned if group does not match any groups."""
        self._manager._ref = 'ref'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self._manager._group_refs = {'Whacks': 'ouch'}
        self._manager._groups = set(self._manager._group_refs.keys())
        self.assertEqual(self._manager.get_tenant_tag('Y', ['Hacks']), 'ref')

    def test_groups_single_match(self):
        """Verify group ref returned if group matches one group."""
        self._manager._ref = 'ref'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self._manager._group_refs = {'Hacks': 'new'}
        self._manager._groups = set(self._manager._group_refs.keys())
        self.assertEqual(self._manager.get_tenant_tag('Y', ['Hacks']), 'new')

    def test_groups_multiple_match(self):
        """Verify all group refs returned if multiple groups match."""
        self._manager._ref = 'ref'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self._manager._group_refs = {'Hacks': 'new', 'Whacks': 'ouch'}
        self._manager._groups = set(self._manager._group_refs.keys())
        self.assertIn(self._manager.get_tenant_tag('Y', ['Hacks', 'Whacks']),
                      ['new', 'ouch'])


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
