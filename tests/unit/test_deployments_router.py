# pylint: disable=C0103,R0904,W0212,W0613,W0201,C0111

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
from checkmate import exceptions
from checkmate import test
from checkmate import utils
from checkmate import workflows

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
        mock_tasks.process_post_deployment.return_value = None

        res = self.app.post('/T1000/deployments',
                            json.dumps(deployment),
                            content_type='application/json')
        self.assertEqual(res.status, '202 Accepted')
        self.assertEqual(res.content_type, 'application/json')

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


class TestDeploymentRouter(unittest.TestCase):

    def setUp(self):
        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.app = webtest.TestApp(self.filters)

        self.manager = mock.Mock()
        self.router = deployments.Router(self.root_app, self.manager)

    def test_param_whitelist(self):
        whitelist = self.router.param_whitelist
        self.assertEqual(len(whitelist), 6)
        self.assertIn('name', whitelist)
        self.assertIn('search', whitelist)
        self.assertIn('status', whitelist)
        self.assertIn('blueprint.name', whitelist)
        self.assertIn('start_date', whitelist)
        self.assertIn('end_date', whitelist)


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
        with mock.patch.object(self.router, 'param_whitelist', 'fake white'):
            self.router.get_deployments()
            parse.assert_called_with({}, 'fake white')


class TestDeleteNodes(TestDeploymentRouter):

    def setUp(self):
        super(TestDeleteNodes, self).setUp()
        deployment_info = {'id': '99', 'operation': {'workflow-id': 'w999'}}
        self.manager.get_deployment.return_value = deployment_info
        saved_deployment = {'operation': {'workflow-id': 'w99'}, 'id': 'faked'}
        self.manager.save_deployment.return_value = saved_deployment
        mock_context = self.filters.context
        mock_context.get_queued_task_dict = mock.Mock()
        mock_context.get_queued_task_dict.return_value = {'fake_dict': True}

    @mock.patch.object(utils, 'is_simulation')
    @mock.patch.object(workflows.tasks.cycle_workflow, 'delay')
    def setUpSimulation(self, _delay, _is_simulation):
        """setUp: Simulation Context."""
        _is_simulation.return_value = True
        self.router._validate_delete_node_request = mock.Mock()
        url = '/123/deployments/999/+delete-nodes'
        data = {'service_name': 'service', 'count': 2}
        self.app.post(url, json.dumps(data), content_type='application/json')

    def test_sets_simulation_context(self):
        self.setUpSimulation()
        call_args, _ = self.manager.delete_nodes.call_args
        context = call_args[1]
        self.assertEquals(context.simulation, True)

    @mock.patch.object(workflows.tasks.cycle_workflow, 'delay')
    def setUpNoVictimList(self, _delay):
        """setUp: No Victim List."""
        self.router._validate_delete_node_request = mock.Mock()
        url = '/123/deployments/999/+delete-nodes'
        data = {'service_name': 'service', 'count': 2}
        self.app.post(url, json.dumps(data), content_type='application/json')

    def test_accept_empty_victim_list(self):
        self.setUpNoVictimList()
        call_args, _ = self.manager.delete_nodes.call_args
        self.assertEquals(call_args[4], [])

    @mock.patch.object(workflows.tasks.cycle_workflow, 'delay')
    def setUpVictimList(self, _delay):
        """setUp: Victim List."""
        self._delay = _delay
        self.router._validate_delete_node_request = mock.Mock()
        url = '/123/deployments/999/+delete-nodes'
        data = {'service_name': 'faked', 'count': 2, 'victim_list': ['1', '2']}
        self.app.post(url, json.dumps(data), content_type='application/json')

    def test_manager_deletes_nodes(self):
        self.setUpVictimList()
        call_args, _ = self.manager.delete_nodes.call_args
        self.assertEquals(call_args[0]['id'], '99')
        self.assertEquals(call_args[1], {})
        self.assertEquals(call_args[2], 'faked')
        self.assertEquals(call_args[3], 2)
        self.assertEquals(call_args[4], ['1', '2'])
        self.assertEquals(call_args[5], '123')

    def test_manager_saves_deployment(self):
        self.setUpVictimList()
        _, kwargs = self.manager.save_deployment.call_args
        self.assertEquals(kwargs['deployment']['id'], '99')
        self.assertEquals(kwargs['api_id'], '999')
        self.assertEquals(kwargs['tenant_id'], '123')

    def test_workflow_cycles_through_tasks(self):
        self.setUpVictimList()
        call_args, _ = self._delay.call_args
        self.assertEquals(call_args[0], 'w99')
        self.assertEquals(call_args[1], {'fake_dict': True})

    @mock.patch.object(workflows.tasks.cycle_workflow, 'delay')
    def setUpFinalResponse(self, _delay):
        """setUp: Victim List."""
        self._delay = _delay
        self.router._validate_delete_node_request = mock.Mock()
        url = '/123/deployments/999/+delete-nodes'
        data = {'service_name': 'faked', 'count': 2, 'victim_list': ['1', '2']}
        jdata = json.dumps(data)
        response = self.app.post(url, jdata, content_type='application/json')
        self.final_response = response

    def test_server_responds_correctly(self):
        self.setUpFinalResponse()
        response = self.final_response
        deployment = json.loads(response.body)
        self.assertEquals(response.status, '202 Accepted')
        self.assertEquals(deployment['id'], 'faked')


class TestValidateDeleteNodeRequest(TestDeploymentRouter):

    def setUp(self):
        super(TestValidateDeleteNodeRequest, self).setUp()
        self.validate_fn = self.router._validate_delete_node_request

    def test_presence_of_service_name(self):
        api_id = None
        deployment_info = None
        deployment = None
        service_name = None
        count = None
        victim_list = None
        self.assertRaises(exceptions.CheckmateValidationException,
                          self.validate_fn,
                          api_id, deployment_info, deployment,
                          service_name, count, victim_list)

    def test_presence_of_count(self):
        api_id = None
        deployment_info = None
        deployment = None
        service_name = 'service_name'
        count = None
        victim_list = None
        self.assertRaises(exceptions.CheckmateValidationException,
                          self.validate_fn,
                          api_id, deployment_info, deployment,
                          service_name, count, victim_list)

    def test_victim_list_greater_than_zero(self):
        api_id = None
        deployment_info = None
        deployment = None
        service_name = 'service_name'
        count = -5
        victim_list = []
        self.assertRaises(exceptions.CheckmateValidationException,
                          self.validate_fn,
                          api_id, deployment_info, deployment,
                          service_name, count, victim_list)

    def test_victim_list_size_less_or_equal_to_count(self):
        api_id = None
        deployment_info = None
        deployment = None
        service_name = 'service_name'
        count = 3
        victim_list = [1, 2, 3, 4]
        self.assertRaises(exceptions.CheckmateValidationException,
                          self.validate_fn,
                          api_id, deployment_info, deployment,
                          service_name, count, victim_list)

    def test_presence_of_deployment_info(self):
        api_id = None
        deployment_info = None
        deployment = None
        service_name = 'service_name'
        count = 3
        victim_list = [1, 2, 3]
        self.assertRaises(exceptions.CheckmateDoesNotExist,
                          self.validate_fn,
                          api_id, deployment_info, deployment,
                          service_name, count, victim_list)

    def test_deployment_blueprint_contains_service_name(self):
        api_id = '999'
        deployment_info = {'id': '999'}
        deployment = {'blueprint': {'services': {'real_service': {}}}}
        service_name = 'fake_service'
        count = 3
        victim_list = [1, 2, 3]
        self.assertRaises(exceptions.CheckmateValidationException,
                          self.validate_fn,
                          api_id, deployment_info, deployment,
                          service_name, count, victim_list)

    def test_victim_list_only_contains_deployment_resources(self):
        deployment_dict = {'blueprint': {'services': {'fake_service': {}}}}

        def get_item(key1):
            return deployment_dict[key1]

        api_id = '999'
        deployment_info = {'id': '999'}
        available_resources = {'r1': {}, 'r2': {}, 'r3': {}}
        deployment = mock.MagicMock()
        deployment.__getitem__ = mock.Mock(side_effect=get_item)
        deployment.get_resources_for_service.return_value = available_resources
        service_name = 'fake_service'
        count = 4
        victim_list = ['r1', 'r2', 'r3', 'r4']
        self.assertRaises(exceptions.CheckmateValidationException,
                          self.validate_fn,
                          api_id, deployment_info, deployment,
                          service_name, count, victim_list)

    def test_passes_all_validations(self):
        deployment_dict = {'blueprint': {'services': {'fake_service': {}}}}

        def get_item(key1):
            return deployment_dict[key1]

        api_id = '999'
        deployment_info = {'id': '999'}
        available_resources = {'r1': {}, 'r2': {}, 'r3': {}}
        deployment = mock.MagicMock()
        deployment.__getitem__ = mock.Mock(side_effect=get_item)
        deployment.get_resources_for_service.return_value = available_resources
        service_name = 'fake_service'
        count = 3
        victim_list = ['r1', 'r2', 'r3']
        result = self.validate_fn(api_id, deployment_info, deployment,
                                  service_name, count, victim_list)
        self.assertEquals(result, True)

class TestUpdateDeployment(TestDeploymentRouter):

    def setUp(self):
        super(TestUpdateDeployment, self).setUp()
        self.put_body = {
            'api_id': 'fake_id'
        }
        self.tenant_id = 'T333'

        self.fake_deployment = { 'fake_deployment': 'fake_info' }
        content_patcher = mock.patch(
            'checkmate.deployments.router._content_to_deployment')
        self.mock_content_to_deployment = content_patcher.start()
        self.mock_content_to_deployment.return_value = self.fake_deployment
        self.addCleanup(content_patcher.stop)

    def test_manager_saves_deployment(self):
        mock_save = self.manager.save_deployment
        mock_save.return_value = {'id': 'fake_id'}
        self.app.put('/%s/deployments' % self.tenant_id,
                     json.dumps(self.put_body),
                     content_type='application/json')
        api_id = None
        mock_save.assert_called_once_with(self.fake_deployment,
                                          api_id=api_id,
                                          tenant_id=self.tenant_id)

    def test_200_if_update_existing_deployment(self):
        self.manager.save_deployment.return_value = {}
        response = self.app.put('/%s/deployments/123' % self.tenant_id,
                                json.dumps(self.put_body),
                                content_type='application/json')
        self.manager.get_deployment.assert_called_once_with('123')
        self.assertEqual(response.status_code, 200)

    def test_201_if_create_new_deployment(self):
        self.manager.save_deployment.return_value = {'id' :'fake_id'}
        response = self.app.put('/%s/deployments/' % self.tenant_id,
                                json.dumps(self.put_body),
                                content_type='application/json')
        self.assertFalse(self.manager.get_deployment.called)
        self.assertEqual(response.status_code, 201)

    def test_set_location_header_on_new_deployment(self):
        self.manager.save_deployment.return_value = {'id' :'fake_id'}
        response = self.app.put('/%s/deployments/' % self.tenant_id,
                                json.dumps(self.put_body),
                                content_type='application/json')
        self.assertEqual(response.headers.get('Location'),
                         '/%s/deployments/fake_id' % self.tenant_id)


if __name__ == '__main__':
    import sys
    test.run_with_params(sys.argv[:])
