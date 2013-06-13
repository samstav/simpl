# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import copy
import unittest2 as unittest

import mox

from checkmate.common import config
from checkmate.blueprints import Blueprint, GitHubManager
from checkmate.exceptions import CheckmateValidationException


class TestBlueprints(unittest.TestCase):

    def test_schema(self):
        """Test the schema validates a blueprint with all possible fields"""
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
        valid = Blueprint(blueprint)
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
        valid = Blueprint(blueprint)
        self.assertDictEqual(valid._data, expected)

    def test_schema_negative(self):
        """Test the schema validates a blueprint with bad fields"""
        blueprint = {
            'nope': None
        }
        self.assertRaises(CheckmateValidationException, Blueprint, blueprint)

    def test_conversion_from_pre_v0_dot_7(self):
        """Test that blueprints syntax from pre v0.7 gets converted"""
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
        converted = Blueprint(blueprint)
        self.assertDictEqual(converted._data, expected)

    def test_future_blueprint_version(self):
        """Test the an unsupported blueprint version is rejected"""
        blueprint = {
            'meta-data': {
                'schema-version': 'unrecognized',
            },
        }
        self.assertRaisesRegexp(CheckmateValidationException, "This server "
                                "does not support version 'unrecognized' "
                                "blueprints", Blueprint, blueprint)


class TestGitHubManagerTenantTag(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()
        self.config = self.mox.CreateMock(config.current())
        self.config.github_api = 'http://localhost'
        self.config.organization = 'blueprints'
        self._manager = GitHubManager({}, self.config)

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_failsafe_returns_master(self):
        '''Retrun master by default'''
        self._manager._ref = None
        self.assertEqual(self._manager.get_tenant_tag('A', []), 'master')

    def test_default_returns_ref(self):
        '''Retrun master by default'''
        self._manager._ref = 'blah'
        self.assertEqual(self._manager.get_tenant_tag('A', []), 'blah')

    def test_preview_falls_back_to_ref(self):
        '''Retrun master by default'''
        self._manager._ref = 'safe'
        self._manager._preview_ref = None
        self._manager._preview_tenants = ['X']
        self.assertEqual(self._manager.get_tenant_tag('X', []), 'safe')

    def test_preview_returns_preview_ref(self):
        '''Retrun master by default'''
        self._manager._preview_ref = 'coming-soon'
        self._manager._preview_tenants = ['X']
        self.assertEqual(self._manager.get_tenant_tag('X', []), 'coming-soon')

    def test_preview_negative(self):
        '''Retrun master by default'''
        self._manager._ref = 'plain'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self.assertEqual(self._manager.get_tenant_tag('Y', []), 'plain')

    def test_groups_no_match(self):
        '''Retrun master by default'''
        self._manager._ref = 'ref'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self._manager._group_refs = {'Whacks': 'ouch'}
        self._manager._groups = set(self._manager._group_refs.keys())
        self.assertEqual(self._manager.get_tenant_tag('Y', ['Hacks']), 'ref')

    def test_groups_single_match(self):
        '''Retrun master by default'''
        self._manager._ref = 'ref'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self._manager._group_refs = {'Hacks': 'new'}
        self._manager._groups = set(self._manager._group_refs.keys())
        self.assertEqual(self._manager.get_tenant_tag('Y', ['Hacks']), 'new')

    def test_groups_multiple_match(self):
        '''Retrun master by default'''
        self._manager._ref = 'ref'
        self._manager._preview_ref = 'preview'
        self._manager._preview_tenants = ['X']
        self._manager._group_refs = {'Hacks': 'new', 'Whacks': 'ouch'}
        self._manager._groups = set(self._manager._group_refs.keys())
        self.assertIn(self._manager.get_tenant_tag('Y', ['Hacks', 'Whacks']),
                      ['new', 'ouch'])


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
