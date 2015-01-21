# pylint: disable=C0103,C0111,E1103,R0904,W0212

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

"""Tests for Blueprints' GithubManager class."""
import copy
import unittest

from checkmate.blueprints import github
from checkmate.common import config


class TestGitHubManager(unittest.TestCase):
    def setUp(self):
        self.config = config.current()
        self.config.update({
            'github_api': 'http://localhost',
            'organization': 'Blueprints',
            'ref': 'master',
            'cache_dir': '/tmp',
        })
        self.manager = github.GitHubManager(self.config)

    def test_same_source(self):
        trusted = {
            'environment': {
                'providers': {
                    'chef-solo': {
                        'constraints': [
                            {'source': 'http://good'}
                        ]
                    }
                }
            }
        }
        untrusted = copy.deepcopy(trusted)
        self.assertTrue(self.manager._same_source(untrusted, trusted))

    def test_same_source_fail(self):
        trusted = {
            'environment': {
                'providers': {
                    'chef-solo': {
                        'constraints': [
                            {'source': 'http://good'}
                        ]
                    }
                }
            }
        }
        untrusted = {
            'environment': {
                'providers': {
                    'chef-solo': {
                        'constraints': [
                            {'source': 'http://hacked'}
                        ]
                    }
                }
            }
        }
        self.assertFalse(self.manager._same_source(untrusted, trusted))

    def test_same_source_blanks(self):
        """Test that if no sources are specified in both then we're OK."""
        self.assertFalse(self.manager._same_source({}, {}))

    def test_same_source_unequal_nulls(self):
        self.assertFalse(self.manager._same_source(None, {}))
        self.assertFalse(self.manager._same_source({}, None))

    def test_same_source_untrusted_no_env(self):
        trusted = {
            'environment': {
                'providers': {
                    'chef-solo': {
                        'constraints': [
                            {'source': 'http://good'}
                        ]
                    }
                }
            }
        }
        self.assertFalse(self.manager._same_source({'blueprint': {}}, trusted))


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
