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

"""Tests for Schema module."""
import json
import unittest

import bottle
import webtest
import yaml

import checkmate
from checkmate import test



class TestBaseRESTResponses(unittest.TestCase):
    """Check that error formatting writes correct content and safe data."""

    def setUp(self):
        self.root_app = bottle.app()
        self.root_app.catchall = False
        self.app = webtest.TestApp(self.root_app)
        from checkmate import api  # load bottle route - pylint: disable=W0612
        unittest.TestCase.setUp(self)

    def test_version_json(self):
        from checkmate.common import config
        expected = {
            'version': checkmate.__version__,
            'environment': config.current().app_environment,
            'git-commit': checkmate.__commit__,
            'wadl': './version.wadl',
        }
        res = self.app.get('/version',
                           headers={'Accept': 'application/json'})
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self.assertEqual(json.loads(res.body), expected)

    def test_version_yaml(self):
        from checkmate.common import config
        expected = {
            'version': checkmate.__version__,
            'environment': config.current().app_environment,
            'git-commit': checkmate.__commit__,
            'wadl': './version.wadl',
        }
        res = self.app.get('/version',
                           headers={'Accept': 'application/x-yaml'})
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/x-yaml')
        self.assertEqual(yaml.safe_load(res.body), expected)

    def test_version_wadl(self):
        res = self.app.get('/version',
                           headers={'Accept': 'application/vnd.sun.wadl+xml'})
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/vnd.sun.wadl+xml')
        self.assertIn('<application', res.body)
        self.assertIn('xmlns="http://wadl.dev.java.net/2009/02"', res.body)
        self.assertIn('xmlns:xs="http://www.w3.org/2001/XMLSchema"', res.body)


if __name__ == '__main__':
    test.run_with_params()
