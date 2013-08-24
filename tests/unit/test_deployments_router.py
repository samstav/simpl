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

"""Tests for Deployments Router."""
import json
import mock
import os
import unittest

import bottle
import webtest

from checkmate import deployments
from checkmate import test
from checkmate import utils

os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'


class TestAPICalls(unittest.TestCase):

    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.app = webtest.TestApp(self.filters)

        self.manager = mock.Mock()
        self.router = deployments.Router(self.root_app, self.manager)

    def _assert_good_count(self, ret, expected_count):
        """Helper method to assert count matches expected count."""
        self.assertIsNotNone(ret, "No count returned")
        self.assertIn("count", ret, "Return does not contain count")
        self.assertEqual(expected_count, ret.get("count", -1),
                         "Wrong count returned")

    @mock.patch.object(utils, 'read_body')
    def test_created_by_assigned(self, mock_read):
        req = mock.Mock()
        req.context = mock.Mock()
        req.context.username = 'john'
        req.headers = {}
        mock_read.return_value = {}
        result = deployments.router._content_to_deployment(request=req,
                                                           deployment_id="1",
                                                           tenant_id="A")
        self.assertIn('created', result)
        expected = {
            'status': 'NEW',
            'tenantId': 'A',
            'created-by': 'john',
            'id': '1',
            'created': result['created'],
        }
        self.assertDictEqual(result, expected)
        mock_read.assert_called_once_with(req)

    @mock.patch.object(utils, 'read_body')
    def test_created_not_overwritten(self, mock_read):
        req = mock.Mock()
        req.context = mock.Mock()
        req.context.username = 'john'
        req.headers = {}
        mock_read.return_value = {'created-by': 'tom'}
        result = deployments.router._content_to_deployment(request=req,
                                                           deployment_id="1",
                                                           tenant_id="A")
        self.assertEqual(result['created-by'], 'tom')
        mock_read.assert_called_once_with(req)

    def test_get_count(self):
        self.manager.count.return_value = 3
        res = self.app.get('/123/deployments/count')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 3)

    @mock.patch.object(deployments.router, 'tasks')
    def test_post_asynchronous(self, mock_tasks):
        """Test that POST /deployments?asynchronous=1 returns a 202."""
        deployment = {
            'id': '1234',
            'tenantId': 'T1000',
            'environment': {},
            'blueprint': {
                'name': 'Test',
                'services': {}
            }
        }
        self.manager.save_deployment.return_value = None

        mock_tasks.process_post_deployment = mock.Mock()
        mock_tasks.process_post_deployment.delay.return_value = None

        res = self.app.post('/T1000/deployments?asynchronous=1',
                            json.dumps(deployment),
                            content_type='application/json')
        self.assertEqual(res.status, '202 Accepted')
        self.assertEqual(res.content_type, 'application/json')
        self.manager.save_deployment.assert_called_once_with(
            mock.ANY,
            api_id='1234',
            tenant_id='T1000'
        )

    @mock.patch.object(deployments.router, 'tasks')
    def test_post_synchronous(self, mock_tasks):
        """Test that POST /deployments returns a 202."""
        deployment = {
            'id': '1234',
            'tenantId': 'T1000',
            'environment': {},
            'blueprint': {
                'name': 'Test',
                'services': {}
            }
        }
        self.manager.select_driver.return_value = self.manager
        mock_tasks.process_post_deployment.return_value = None

        res = self.app.post('/T1000/deployments',
                            json.dumps(deployment),
                            content_type='application/json')
        self.assertEqual(res.status, '202 Accepted')
        self.assertEqual(res.content_type, 'application/json')
        self.manager.select_driver.assert_called_once_with('1234')

    @mock.patch.object(utils, 'write_body')
    @mock.patch('bottle.request')
    def test_get_deployment_secrets_ok(self, mock_request, mock_write_body):
        deployment = {
            'id': '1234',
            'tenantId': 'T1000',
        }
        self.manager.get_deployment.return_value = deployment

        context = mock.Mock()
        context.is_admin = True
        mock_request.context = context
        data = {'foo': 1}
        self.manager.get_deployment_secrets.return_value = data
        mock_write_body.return_value = 42

        result = self.router.get_deployment_secrets('1234', tenant_id="T1000")
        self.manager.get_deployment.assert_called_once_with('1234',
                                                            tenant_id='T1000')
        self.manager.get_deployment_secrets.assert_called_once_with(
            '1234',
            tenant_id='T1000'
        )
        self.assertEqual(42, result)

    @mock.patch.object(utils, 'write_body')
    @mock.patch('bottle.request')
    def test_get_deployment_secrets_not_admin(self, mock_request, mock_write):
        deployment = {
            'id': '1234',
            'tenantId': 'T1000',
        }
        self.manager.get_deployment.return_value = deployment

        context = mock.Mock()
        context.is_admin = False
        mock_request.context = context
        data = {'foo': 1}
        self.manager.get_deployment_secrets.return_value = data
        mock_write.return_value = 42

        with self.assertRaises(bottle.HTTPError):
            self.router.get_deployment_secrets('1234', tenant_id="T1000")

            self.manager.get_deployment.assert_called_once_with(
                '1234', tenant_id='T1000'
            )
            mock_write.assert_called_once_with(data, bottle.request,
                                               bottle.response)
            self.manager.get_deployment_secrets.assert_called_once_with(
                '1234',
                tenant_id='T1000'
            )

    @mock.patch.object(utils, 'write_body')
    def test_update_deployment_wont_get_deployment_if_no_api_id(self,
                                                                mock_write):
        '''Test that update does not make an unnecessary database call
        when no api_id is given.
        '''
        self.router.update_deployment(None)
        assert not self.manager.get_deployment.called, \
            'get_deploment should not be called'


class TestDeploymentRouter(unittest.TestCase):

    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.app = webtest.TestApp(self.filters)

        self.manager = mock.Mock()
        self.router = deployments.Router(self.root_app, self.manager)

    def test_params_whitelist(self):
        whitelist = self.router.params_whitelist
        self.assertEqual(len(whitelist), 4)
        self.assertIn('name', whitelist)
        self.assertIn('search', whitelist)
        self.assertIn('status', whitelist)
        self.assertIn('blueprint.name', whitelist)


class TestGetDeployments(TestDeploymentRouter):

    def setUp(self):
        super(TestGetDeployments, self).setUp()
        results = {'_links': {}, 'results': {}, 'collection-count': 0}
        self.manager.get_deployments.return_value = results

    def test_pass_query_to_manager(self):
        self.router.get_deployments()
        self.manager.get_deployments.assert_called_with(
            status=mock.ANY,
            tenant_id=mock.ANY,
            with_deleted=mock.ANY,
            limit=mock.ANY,
            offset=mock.ANY,
            query=mock.ANY
        )

    @mock.patch.object(utils.QueryParams, 'parse')
    def test_query_is_properly_parsed(self, parse):
        parse.return_value = 'fake query'
        self.router.get_deployments()
        self.manager.get_deployments.assert_called_with(
            status=mock.ANY,
            tenant_id=mock.ANY,
            with_deleted=mock.ANY,
            limit=mock.ANY,
            offset=mock.ANY,
            query='fake query',
        )

    @mock.patch.object(utils.QueryParams, 'parse')
    def test_pass_whitelist_to_query_parser(self, parse):
        with mock.patch.object(self.router, 'params_whitelist', 'fake white'):
            self.router.get_deployments()
            parse.assert_called_with({}, 'fake white')


if __name__ == '__main__':
    import sys

    test.run_with_params(sys.argv[:])
