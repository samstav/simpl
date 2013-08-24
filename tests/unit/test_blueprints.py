# pylint: disable=C0103,R0904,W0212

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

"""Tests for Blueprints class."""
import copy
import unittest

import mock

from checkmate import blueprints as cmbps
from checkmate import exceptions as cmexc


class TestBlueprints(unittest.TestCase):

    def test_schema(self):
        """Test the schema validates a blueprint with all possible fields."""
        blueprint = {
            'id': 'test',
            'version': '1.1.0',
            'meta-data': {
                'schema-version': 'v0.7',
            },
            'name': 'test',
            'services': {},
            'options': {},
            'resources': {},
            'display-outputs': {},
            'documentation': {},
        }
        valid = cmbps.Blueprint(blueprint)
        self.assertDictEqual(valid._data, blueprint)

    def test_schema_with_options(self):
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
        valid = cmbps.Blueprint(blueprint)
        self.assertDictEqual(valid._data, expected)

    def test_schema_negative(self):
        blueprint = {
            'nope': None
        }
        self.assertRaises(
            cmexc.CheckmateValidationException, cmbps.Blueprint, blueprint)

    def test_conversion_from_pre_v0_dot_7(self):
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
        converted = cmbps.Blueprint(blueprint)
        self.assertDictEqual(converted._data, expected)

    def test_future_blueprint_version(self):
        blueprint = {
            'meta-data': {
                'schema-version': 'unrecognized',
            },
        }
        self.assertRaisesRegexp(cmexc.CheckmateValidationException,
                                "This server does not support version "
                                "'unrecognized' blueprints",
                                cmbps.Blueprint, blueprint)


class TestGitHubManagerTenantTag(unittest.TestCase):
    def setUp(self):
        self.config = mock.Mock()
        self.config.github_api = 'http://localhost'
        self.config.organization = 'blueprints'
        self.config.cache_dir = 'blah'
        self.config.group_refs = {}
        self.config.preview_tenants = []
        self._manager = cmbps.GitHubManager({}, self.config)

    def test_no_api(self):
        conf = self.config
        conf.github_api = None
        with self.assertRaises(AssertionError):
            cmbps.GitHubManager({}, conf)

    def test_no_org(self):
        conf = self.config
        conf.organization = None
        with self.assertRaises(AssertionError):
            cmbps.GitHubManager({}, conf)

    def test_no_group_refs(self):
        conf = self.config
        conf.group_refs = None
        self.assertIsInstance(
            cmbps.GitHubManager({}, conf), cmbps.GitHubManager)

    def test_failsafe_returns_master(self):
        self._manager._ref = None
        self.assertEqual(self._manager.get_tenant_tag('A', []), 'master')

    def test_default_returns_ref(self):
        self._manager._ref = 'blah'
        self.assertEqual(self._manager.get_tenant_tag('A', []), 'blah')

    def test_preview_falls_back_to_ref(self):
        self._manager._ref = 'safe'
        self._manager._preview_ref = None
        self._manager._preview_tenants = ['X']
        self.assertEqual(self._manager.get_tenant_tag('X', []), 'safe')

    def test_preview_returns_preview_ref(self):
        self._manager._preview_ref = 'coming-soon'
        self._manager._preview_tenants = ['X']
        self.assertEqual(self._manager.get_tenant_tag('X', []), 'coming-soon')

    def test_preview_negative(self):
        self._manager._ref = 'plain'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self.assertEqual(self._manager.get_tenant_tag('Y', []), 'plain')

    def test_groups_no_match(self):
        self._manager._ref = 'ref'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self._manager._group_refs = {'Whacks': 'ouch'}
        self._manager._groups = set(self._manager._group_refs.keys())
        self.assertEqual(self._manager.get_tenant_tag('Y', ['Hacks']), 'ref')

    def test_groups_single_match(self):
        self._manager._ref = 'ref'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self._manager._group_refs = {'Hacks': 'new'}
        self._manager._groups = set(self._manager._group_refs.keys())
        self.assertEqual(self._manager.get_tenant_tag('Y', ['Hacks']), 'new')

    def test_groups_multiple_match(self):
        self._manager._ref = 'ref'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self._manager._group_refs = {'Hacks': 'new', 'Whacks': 'ouch'}
        self._manager._groups = set(self._manager._group_refs.keys())
        self.assertIn(self._manager.get_tenant_tag('Y', ['Hacks', 'Whacks']),
                      ['new', 'ouch'])


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
