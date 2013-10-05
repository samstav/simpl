# pylint: disable=R0904

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

"""Tests for Blueprints Router."""
import unittest

import bottle
import mock
import webtest

from checkmate import blueprints
from checkmate import test
from checkmate import utils


class TestAPICalls(unittest.TestCase):

    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.roles = []
        self.app = webtest.TestApp(self.filters)

        self.manager = mock.Mock()
        self.cache_manager = mock.Mock()
        self.router = blueprints.Router(self.root_app, self.manager,
                                        cache_manager=self.cache_manager)

    def test_get_blueprints_local(self):
        """Test that GET /blueprints returns local blueprints."""
        self.router.cache_manager = None
        data = {
            'results': {
                '1234': {
                    'id': '1234',
                    'tenantId': 'T1000',
                }
            },
            'collection-count': 1
        }
        self.manager.get_blueprints.return_value = data

        res = self.app.get('/T1000/blueprints',
                           headers={'accept': 'application/json'})
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(res.json, data)

    def test_get_blueprints_both(self):
        """Test that GET /blueprints returns local blueprints."""
        data = {
            'results': {
                '1234': {
                    'id': '1234',
                    'tenantId': 'T1000',
                }
            },
            'collection-count': 1
        }
        cache = {
            'results': {
                '5678': {
                    'id': '5678',
                }
            },
            'collection-count': 1
        }
        self.manager.get_blueprints.return_value = data
        self.cache_manager.get_blueprints.return_value = cache

        res = self.app.get('/T1000/blueprints',
                           headers={'accept': 'application/json'})
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        combined = utils.merge_dictionary(data, cache)
        combined['collection-count'] = 2
        self.assertEqual(res.json, data)

    def test_get_blueprints_cached(self):
        """Test that GET /blueprints returns local blueprints."""
        data = {
            'results': {},
            'collection-count': 0
        }
        cache = {
            'results': {
                '5678': {
                    'id': '5678',
                }
            },
            'collection-count': 1
        }
        self.manager.get_blueprints.return_value = data
        self.cache_manager.get_blueprints.return_value = cache

        res = self.app.get('/T1000/blueprints',
                           headers={'accept': 'application/json'})
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(res.json, cache)


if __name__ == '__main__':
    test.run_with_params()
