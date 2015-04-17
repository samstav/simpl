# pylint: disable=R0904

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

"""Tests for Blueprints Router."""
import unittest

import bottle
import mock
import webtest

from checkmate import blueprints
from checkmate import server
from checkmate import test


class TestAnonymousAPICalls(unittest.TestCase):

    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.roles = []
        self.app = webtest.TestApp(self.filters)

        self.manager = mock.Mock()
        self.router = blueprints.AnonymousRouter(self.root_app, self.manager)

    def test_get_anon_blueprints(self):
        """Test to ensure we are serving the appropriate blueprints."""
        data = {
            'results': {
                '1234': {
                    'id': '1234',
                }
            },
            'collection-count': 1
        }
        self.manager.get_blueprints.return_value = data

        res = self.app.get('/anonymous/blueprints',
                           headers={'accept': 'application/json'})

        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(res.json, data)


class TestDisabledAnonymousAPICalls(unittest.TestCase):

    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.root_app.error_handler = {404: server.bottle_error_formatter}
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.roles = []
        self.app = webtest.TestApp(self.filters)

        self.manager = mock.Mock()
        self.router = blueprints.AnonymousRouter(self.root_app, None)

    def test_get_anon_blueprints(self):
        """Test to ensure we are not serving data when the anonymous paths are
        disabled.
        """
        data = {
            'results': {
                '1234': {
                    'id': '1234',
                }
            },
            'collection-count': 1
        }
        self.manager.get_blueprints.return_value = data
        res = self.app.get('/anonymous/blueprints',
                           headers={'accept': 'application/json'}, status=404)

        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.content_type, 'application/json')
        self.assertNotEqual(res.json, data)


if __name__ == '__main__':
    test.run_with_params()
