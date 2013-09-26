# pylint: disable=C0103,R0201,R0904,W0212,W0201

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

"""Tests for Rackspace Loadbalancer provider."""
import logging
import re

import mock
import mox
import unittest

from pyrax import exceptions
from SpiffWorkflow import specs
from SpiffWorkflow import Workflow

from checkmate import deployment as cm_dep
from checkmate import deployments
from checkmate.deployments import tasks
from checkmate import middleware
from checkmate import providers
from checkmate.providers import base
from checkmate.providers.rackspace import loadbalancer
from checkmate import test
from checkmate import utils
from checkmate import workflow as cm_wf
from checkmate import workflow_spec

LOG = logging.getLogger(__name__)


class TestLoadBalancer(test.ProviderTester):
    klass = loadbalancer.Provider

    def test_provider(self):
        provider = loadbalancer.Provider({})
        self.assertEqual(provider.key, 'rackspace.load-balancer')

    def test_generate_delete_connection_tasks(self):
        wf_spec = workflow_spec.WorkflowSpec()
        deployment = cm_dep.Deployment({
            'id': 'TEST',

        })
        context = middleware.RequestContext()

        resource_1 = {"index": "1", "region": "ORD"}
        resource_2 = {"index": "2", }

        provider = loadbalancer.Provider({})
        provider.add_delete_connection_tasks(wf_spec,  context, deployment,
                                             resource_1, resource_2)
        workflow = Workflow(wf_spec)

        expected_dump = re.sub(r"\s", "", """
            1/0: Task of Root State: COMPLETED Children: 1
            2/0: Task of Start State: READY Children: 1
            3/0: Task of Remove Node 2 from LB 1 State: FUTURE Children: 0
        """)
        workflow_dump = re.sub(r"\s", "", workflow.get_dump())

        self.assertEqual(expected_dump, workflow_dump)

    def test_disable_connection_tasks(self):
        provider = loadbalancer.Provider({})
        deployment = {'id': "DEP_ID"}
        context = mock.Mock()
        source_resource = {
            'index': '0',
            'service': 'lb',
            'instance': {
                'id': "LB_ID",
            },
            'region': 'ORD',
        }
        target_resource = {
            'index': '1',
            'service': 'web',
            'instance': {
                'private_ip': 'IP',
            },
        }
        relation_name = 'lb-web'
        wf_spec = specs.WorkflowSpec()
        context.get_queued_task_dict.return_value = {}
        exp_call = "checkmate.providers.rackspace.loadbalancer" \
                   ".update_node_status"
        result = provider.disable_connection_tasks(wf_spec, deployment,
                                                   context, source_resource,
                                                   target_resource,
                                                   relation_name)
        root_task = result['root']
        self.assertEqual(len(result), 2)
        self.assertListEqual(result.keys(), ['root', 'final'])
        self.assertIsInstance(root_task, specs.Celery)
        self.assertEqual(root_task.call, exp_call)
        self.assertEqual(root_task.args, [{}, "LB_ID", "IP", "ORD",
                                              "DISABLED", "OFFLINE"])
        self.assertEqual(root_task.properties, {
            'provider': provider.key,
            'resource': '1',
            'estimated_duration': 5
        })
        context.get_queued_task_dict.assert_called_once_with(
            deployment="DEP_ID", source_resource="0", target_resource="1",
            relation_name=relation_name)

    def test_enable_connection_tasks(self):
        provider = loadbalancer.Provider({})
        deployment = {'id': "DEP_ID"}
        context = mock.Mock()
        source_resource = {
            'index': '0',
            'service': 'lb',
            'instance': {
                'id': "LB_ID",
            },
            'region': 'ORD',
        }
        target_resource = {
            'index': '1',
            'service': 'web',
            'instance': {
                'private_ip': 'IP',
            },
        }
        relation_name = 'lb-web'
        wf_spec = specs.WorkflowSpec()
        context.get_queued_task_dict.return_value = {}
        exp_call = "checkmate.providers.rackspace.loadbalancer" \
                   ".update_node_status"
        result = provider.enable_connection_tasks(wf_spec, deployment,
                                                  context, source_resource,
                                                  target_resource,
                                                  relation_name)
        root_task = result['root']
        self.assertEqual(len(result), 2)
        self.assertListEqual(result.keys(), ['root', 'final'])
        self.assertIsInstance(root_task, specs.Celery)
        self.assertEqual(root_task.call, exp_call)
        self.assertEqual(root_task.args, [{}, "LB_ID", "IP", "ORD",
                                              "ENABLED", "ACTIVE"])
        self.assertEqual(root_task.properties, {
            'provider': provider.key,
            'resource': '1',
            'estimated_duration': 5
        })
        context.get_queued_task_dict.assert_called_once_with(
            deployment="DEP_ID", source_resource="0", target_resource="1",
            relation_name=relation_name)

    def verify_limits(self, max_lbs, max_nodes):
        """Test the verify_limits() method."""
        resources = [
            {
                "status": "BUILD",
                "index": "0",
                "service": "lb",
                "region": "DFW",
                "component": "http",
                "relations": {
                    "lb-master-1": {
                        "name": "lb-master",
                        "state": "planned",
                        "requires-key": "application",
                        "relation": "reference",
                        "interface": "http",
                        "relation-key": "master",
                        "target": "1"
                    },
                    "lb-web-3": {
                        "name": "lb-web",
                        "state": "planned",
                        "requires-key": "application",
                        "relation": "reference",
                        "interface": "http",
                        "relation-key": "web",
                        "target": "3"
                    }
                }
            },
            {
                "status": "BUILD",
                "index": "1",
                "service": "lb2",
                "region": "DFW",
                "component": "http",
                "relations": {
                    "lb-master-1": {
                        "name": "lb2-master",
                        "state": "planned",
                        "requires-key": "application",
                        "relation": "reference",
                        "interface": "https",
                        "relation-key": "master",
                        "target": "1"
                    },
                    "lb-web-3": {
                        "name": "lb2-web",
                        "state": "planned",
                        "requires-key": "application",
                        "relation": "reference",
                        "interface": "https",
                        "relation-key": "web",
                        "target": "3"
                    }
                }
            }
        ]
        context = middleware.RequestContext()
        self.mox.StubOutWithMock(loadbalancer.Provider, 'find_a_region')
        self.mox.StubOutWithMock(loadbalancer.Provider, 'find_url')
        self.mox.StubOutWithMock(loadbalancer.provider, '_get_abs_limits')
        limits = {
            "NODE_LIMIT": max_nodes,
            "LOADBALANCER_LIMIT": max_lbs
        }
        loadbalancer.Provider.find_a_region(mox.IgnoreArg()).AndReturn("DFW")
        loadbalancer.Provider.find_url(mox.IgnoreArg(),
                                       mox.IgnoreArg()).AndReturn("fake url")
        (loadbalancer.provider
         ._get_abs_limits(mox.IgnoreArg(),
                          mox.IgnoreArg(),
                          mox.IgnoreArg())
         .AndReturn(limits))
        clb = self.mox.CreateMockAnything()
        clb_lbs = self.mox.CreateMockAnything()
        clb = clb_lbs
        clb_lbs.list().AndReturn([])
        self.mox.StubOutWithMock(loadbalancer.Provider, "connect")
        loadbalancer.Provider.connect(mox.IgnoreArg(),
                                      region=mox.IgnoreArg()).AndReturn(clb)
        self.mox.ReplayAll()
        provider = loadbalancer.Provider({})
        result = provider.verify_limits(context, resources)
        self.mox.VerifyAll()
        return result

    def test_verify_limits_negative(self):
        """Test that verify_limits returns warnings if limits are not okay."""
        result = self.verify_limits(1, 0)
        self.assertEqual(3, len(result))
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")

    def test_verify_access_positive(self):
        """Test that verify_access() returns ACCESS-OK if user has access."""
        context = middleware.RequestContext()
        context.roles = 'identity:user-admin'
        provider = loadbalancer.Provider({})
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'LBaaS:admin'
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'LBaaS:creator'
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')

    def test_verify_access_negative(self):
        """Test that verify_access() returns ACCESS-OK if user has access."""
        context = middleware.RequestContext()
        context.roles = 'LBaaS:observer'
        provider = loadbalancer.Provider({})
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'NO-ACCESS')


class TestCeleryTasks(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    @mock.patch('checkmate.deployments.resource_postback.delay')
    @mock.patch(
        'checkmate.providers.rackspace.loadbalancer.provider.Provider.connect')
    def test_update_node_status(self, mock_connect, mock_delay):
        context = {
            'source_resource': '0',
            'target_resource': '1',
            'relation_name': 'lb-web',
            'deployment': 'dep_id',
        }
        lb_id = "LB_ID"
        ip = "IP"
        region = "ORD"
        expected_results = {
            'instance:0': {
                "relations": {
                    "lb-web-1": {
                        'state': 'DISABLED'
                    }
                }
            },
            'instance:1': {
                "status": "OFFLINE",
                "relations": {
                    "lb-web-0": {
                        'state': 'DISABLED'
                    }
                }
            }
        }
        mock_api = mock.Mock()
        mock_node = mock.Mock()
        mock_node.address = ip
        mock_connect.return_value = mock_api
        mock_lb = mock_api.get.return_value
        mock_lb.nodes = [mock_node]
        results = loadbalancer.update_node_status(context, lb_id, ip,
                                                  region, "DISABLED",
                                                  "OFFLINE")
        self.assertTrue(mock_node.update.called)
        self.assertEqual(mock_node.condition, "DISABLED")
        self.assertDictEqual(results, expected_results)
        mock_delay.assert_called_once_with("dep_id", expected_results)

    @mock.patch(
        'checkmate.providers.rackspace.loadbalancer.provider.Provider.connect')
    def test_update_node_status_with_422_client_exception(self, mock_connect):
        context = {
            'source_resource': '0',
            'target_resource': '1',
            'relation_name': 'lb-web',
            'deployment': 'dep_id',
        }
        lb_id = 1234
        ip = "IP"
        region = "ORD"

        mock_api = mock.Mock()
        mock_node = mock.Mock()
        mock_node.address = ip
        mock_connect.return_value = mock_api
        mock_lb = mock_api.get.return_value
        mock_lb.nodes = [mock_node]
        exception = exceptions.ClientException("422", message="exception")
        mock_node.update.side_effect = exception
        loadbalancer.update_node_status.retry = mock.Mock(
            side_effect=StandardError(""))
        self.assertRaises(StandardError, loadbalancer.update_node_status,
                          context, lb_id, ip, region, "ENABLED", "ACTIVE")
        loadbalancer.update_node_status.retry.assert_called_once_with(
            exc=exception)

    @mock.patch(
        'checkmate.providers.rackspace.loadbalancer.provider.Provider.connect')
    def test_update_node_status_with_client_exception(self, mock_connect):
        context = {
            'source_resource': '0',
            'target_resource': '1',
            'relation_name': 'lb-web',
            'deployment': 'dep_id',
        }
        lb_id = 1234
        ip = "IP"
        region = "ORD"

        mock_api = mock.Mock()
        mock_node = mock.Mock()
        mock_node.address = ip
        mock_connect.return_value = mock_api
        mock_lb = mock_api.get.return_value
        mock_lb.nodes = [mock_node]
        exception = exceptions.ClientException("404", message="exception")
        mock_node.update.side_effect = exception
        loadbalancer.update_node_status.retry = mock.Mock(
            side_effect=StandardError(""))
        self.assertRaises(StandardError, loadbalancer.update_node_status,
                          context, lb_id, ip, region, "ENABLED", "ACTIVE")
        loadbalancer.update_node_status.retry.assert_called_once_with(
            exc=exception)

    @mock.patch(
        'checkmate.providers.rackspace.loadbalancer.provider.Provider.connect')
    def test_update_node_status_with_standard_error(self, mock_connect):
        context = {
            'source_resource': '0',
            'target_resource': '1',
            'relation_name': 'lb-web',
            'deployment': 'dep_id',
        }
        lb_id = 1234
        ip = "IP"
        region = "ORD"

        mock_api = mock.Mock()
        mock_node = mock.Mock()
        mock_node.address = ip
        mock_connect.return_value = mock_api
        mock_lb = mock_api.get.return_value
        mock_lb.nodes = [mock_node]
        exception = StandardError("exception")
        mock_node.update.side_effect = exception
        loadbalancer.update_node_status.retry = mock.Mock(
            side_effect=StandardError(""))
        self.assertRaises(StandardError, loadbalancer.update_node_status,
                          context, lb_id, ip, region, "ENABLED", "ACTIVE")

        loadbalancer.update_node_status.retry.assert_called_once_with(
            exc=exception)

    @mock.patch('checkmate.deployments.resource_postback.delay')
    def test_update_node_status_for_simulation(self, mock_delay):
        context = {
            'source_resource': '0',
            'target_resource': '1',
            'relation_name': 'lb-web',
            'deployment': 'dep_id',
            'simulation': True
        }
        expected_results = {
            'instance:0': {
                "relations": {
                    "lb-web-1": {
                        'state': 'DISABLED'
                    }
                }
            },
            'instance:1': {
                "status": "OFFLINE",
                "relations": {
                    "lb-web-0": {
                        'state': 'DISABLED'
                    }
                }
            }
        }
        lb_id = 1234
        ip = "IP"
        region = "ORD"

        results = loadbalancer.update_node_status(context, lb_id, ip,
                                                  region, "DISABLED",
                                                  "OFFLINE")
        self.assertDictEqual(results, expected_results)
        mock_delay.assert_called_once_with("dep_id", expected_results)

    @mock.patch.object(deployments.tasks.reset_failed_resource_task, 'delay')
    @mock.patch.object(deployments.resource_postback, 'delay')
    def test_create_load_balancer(self, mock_postback_delay,
                                  mock_reset_delay):
        name = 'fake_lb'
        vip_type = 'SERVICENET'
        protocol = 'notHTTP'
        region = 'North'
        fake_id = 121212
        public_ip = 'a.b.c.d'
        servicenet_ip = 'w.x.y.z'
        status = 'BUILD'

        mocklb = mock.Mock()
        mocklb.id = fake_id
        mocklb.port = 80
        mocklb.protocol = protocol
        mocklb.status = status

        ip_data_pub = mock.Mock()
        ip_data_pub.ip_version = 'IPV4'
        ip_data_pub.type = 'PUBLIC'
        ip_data_pub.address = public_ip

        ip_data_svc = mock.Mock()
        ip_data_svc.ip_version = 'IPV4'
        ip_data_svc.type = 'SERVICENET'
        ip_data_svc.address = servicenet_ip

        mocklb.virtual_ips = [ip_data_pub, ip_data_svc]

        node = mock.Mock()
        vip = mock.Mock()

        context = dict(deployment='DEP', resource='1')

        #Stub out postback call
        tasks.reset_failed_resource_task.delay(context['deployment'],
                                               context['resource'])

        #Create appropriate api mocks
        api_mock = mock.Mock()
        api_mock.Node.return_value = node
        api_mock.VirtualIP.return_value = vip
        api_mock.create.return_value = mocklb

        expected = {
            'instance:%s' % context['resource']: {
                'id': fake_id,
                'public_ip': public_ip,
                'port': 80,
                'protocol': protocol,
                'status': status,
                'interfaces': {
                    'vip': {
                        'public_ip': public_ip,
                        'ip': public_ip,
                    },
                }
            }
        }

        mock_postback_delay.return_value = True

        results = loadbalancer.create_loadbalancer(context, name, vip_type,
                                                   protocol, region,
                                                   api=api_mock)

        self.assertDictEqual(results, expected)
        api_mock.create.assert_called_with(name=name, port=80,
                                           protocol=protocol.upper(),
                                           nodes=[node],
                                           virtual_ips=[vip],
                                           algorithm='ROUND_ROBIN')

        mock_reset_delay.assert_called_with('DEP', '1')
        first_postback = mock.call('DEP', {'instance:1': {'id': 121212}})
        second_postback = mock.call('DEP', expected)
        self.assertEqual(mock_postback_delay.mock_calls[0], first_postback)
        self.assertEqual(mock_postback_delay.mock_calls[1], second_postback)

    @mock.patch.object(deployments.resource_postback, 'delay')
    def test_delete_lb_task(self, mock_postback):
        context = {"deployment": "1234"}
        expect = {
            "instance:1": {
                "status": "DELETING",
                "status-message": "Waiting on resource deletion"
            }
        }

        api = mock.Mock()
        m_lb = mock.Mock()
        m_lb.status = 'ACTIVE'
        m_lb.delete.return_value = True
        api.get.return_value = m_lb
        ret = loadbalancer.delete_lb_task(
            context, '1', 'lb14nuai-asfjb', 'ORD', api=api)
        self.assertDictEqual(expect, ret)
        mock_postback.assert_called_with(context['deployment'], expect)

    @mock.patch.object(deployments.resource_postback, 'delay')
    def test_delete_lb_task_for_building_loadbalancer(self, mock_postback):
        context = {"deployment": "1234"}
        expect = {
            "instance:1": {
                "status": "DELETING",
                "status-message": "Cannot delete LoadBalancer load-balancer, "
                                  "as it currently is in BUILD state."
                                  " Waiting for load-balancer status to move "
                                  "to ACTIVE, ERROR or SUSPENDED"
            }
        }
        api = mock.Mock()

        m_lb = mock.Mock()
        m_lb.status = 'BUILD'
        api.get.return_value = m_lb

        ret = loadbalancer.delete_lb_task(
            context, '1', 'load-balancer', 'ORD', api=api)
        self.assertDictEqual(expect, ret)
        mock_postback.assert_called_with(context['deployment'], expect)

    @mock.patch.object(deployments.resource_postback, 'delay')
    def test_wait_on_lb_delete(self, mock_postback):
        context = {"deployment": "1234"}
        expect = {
            'instance:1': {
                'status': 'DELETED',
                'status-message': ''
            }
        }
        api = mock.Mock()
        m_lb = mock.Mock()
        m_lb.status = 'DELETED'
        api.get.return_value = m_lb

        ret = loadbalancer.wait_on_lb_delete_task(context, '1',
                                                  'lb14nuai-asfjb', 'ORD',
                                                  api=api)
        self.assertDictEqual(expect, ret)
        mock_postback.assert_called_with(context['deployment'], expect)

    @mock.patch.object(loadbalancer.exceptions, 'CheckmateException')
    @mock.patch.object(loadbalancer.wait_on_lb_delete_task, 'retry')
    def test_wait_on_lb_delete_still(self, mock_retry, mock_exception):
        context = {'deployment': '1234'}
        api = mock.Mock()
        m_lb = mock.Mock()
        m_lb.status = 'DELETING'

        api.get.return_value = m_lb

        loadbalancer.wait_on_lb_delete_task(
            context, '1', 'lb14nuai-asfjb', 'ORD', api=api)

        mock_exception.assert_called_with('Waiting on state DELETED. Load '
                                          'balancer is in state DELETING',)
        assert mock_retry.called

    def test_lb_sync_resource_task(self):
        mocklb = mock.Mock()
        mocklb.id = 'fake_lb_id'
        mocklb.name = 'fake_lb'
        mocklb.status = 'ERROR'
        mocklb.get_metadata.return_value = {}

        resource_key = "1"

        context = {'deployment': 'DEP',
                   'resource': '1',
                   'base_url': 'blah.com',
                   'tenant': '123'}

        resource = {
            'index': '0',
            'name': 'fake_lb',
            'provider': 'load-balancers',
            'status': 'ERROR',
            'instance': {
                'id': 'fake_lb_id'
            }
        }

        lb_api_mock = mock.Mock()
        lb_api_mock.get.return_value = mocklb

        expected = {'instance:1': {"status": "ERROR"}}

        results = loadbalancer.sync_resource_task(
            context, resource, resource_key, lb_api_mock)

        lb_api_mock.get.assert_called_once_with(mocklb.id)
        self.assertDictEqual(results, expected)
        lb_api_mock.get.assert_called_with(mocklb.id)

    def setUpSyncResourceTask(self):
        self.resource_key = "1"

        self.context = {'deployment': 'DEP',
                        'resource': '1',
                        'base_url': 'blah.com',
                        'tenant': '123'}

        self.resource = {
            'index': '0',
            'instance': {
                'id': 'fake_lb_id'
            }
        }

        self.mocklb = mock.Mock()
        self.mocklb.id = 'fake_lb_id'
        self.mocklb.name = 'fake_lb'
        self.mocklb.status = 'ERROR'

        self.lb_api_mock = mock.Mock()
        self.lb_api_mock.get.return_value = self.mocklb

    @mock.patch.object(loadbalancer.Provider, 'generate_resource_tag')
    def test_sync_resource_task_adds_metadata(self,
                                              mock_generate_resource_tag):
        self.setUpSyncResourceTask()
        mock_generate_resource_tag.return_value = {"test": "me"}
        self.mocklb.metadata = []
        loadbalancer.sync_resource_task(self.context, self.resource,
                                        self.resource_key, self.lb_api_mock)

        self.lb_api_mock.get.assert_called_once_with(self.mocklb.id)
        self.mocklb.set_metadata.assert_called_once_with({"test": "me"})

    @mock.patch.object(loadbalancer.Provider, 'generate_resource_tag')
    def test_sync_resource_task_without_metadata(self,
                                                 mock_generate_resource_tag):
        """Test sync_resource_task adds metadata even if the loadbalancer's
        metadata attribute doesn't even exist
        """
        self.setUpSyncResourceTask()
        del self.mocklb.metadata
        mock_generate_resource_tag.return_value = {"test": "me"}
        loadbalancer.sync_resource_task(self.context, self.resource,
                                        self.resource_key, self.lb_api_mock)

        self.lb_api_mock.get.assert_called_once_with(self.mocklb.id)
        self.mocklb.set_metadata.assert_called_once_with({"test": "me"})


class TestGetAlgorithms(unittest.TestCase):
    def setUp(self):
        self.api = mock.Mock()
        self.context = middleware.RequestContext(**{})

    @mock.patch.object(loadbalancer.provider.LOG, 'debug')
    @mock.patch.object(loadbalancer.provider.LOG, 'info')
    @mock.patch.object(loadbalancer.Provider, 'connect')
    def test_get_algorithms_success(self, mock_connect, mock_log_info,
                                    mock_log_debug):
        """Verifies all method calls and results."""
        mock_connect.return_value = self.api
        self.api.management_url = 'localhost:8080'
        self.api.region_name = 'ORD'
        self.api.algorithms = ['RANDOM', 'ROUND_ROBIN']

        results = loadbalancer.provider._get_algorithms(
            self.context,
            self.context.auth_token,
            self.context.region)
        self.assertEqual(results, self.api.algorithms)
        mock_log_info.assert_called_with('Calling Cloud Load Balancers to get '
                                         'algorithms for %s', 'ORD')
        mock_log_debug.assert_called_with('Found Load Balancer algorithms for '
                                          '%s: %s', 'localhost:8080',
                                          ['RANDOM', 'ROUND_ROBIN'])

    @mock.patch.object(loadbalancer.provider.LOG, 'error')
    @mock.patch.object(loadbalancer.Provider, 'connect')
    def test_get_algorithms_exception(self, mock_connect, mock_logger):
        """Verifies method calls when StandardError raised."""
        mock_exception = StandardError('test error')
        mock_connect.side_effect = mock_exception

        # caching decorator re-raises so not able to assertRaises
        try:
            loadbalancer.provider._get_algorithms(self.context,
                                                  self.context.auth_token,
                                                  self.context.region)
        except StandardError as exc:
            self.assertEqual(str(exc), 'test error')

        mock_logger.assert_called_with('Error retrieving Load Balancer '
                                       'algorithms from %s: %s', None,
                                       mock_exception)


class TestGetProtocols(unittest.TestCase):
    def setUp(self):
        self.api = mock.Mock()
        self.context = middleware.RequestContext(**{})

    @mock.patch.object(loadbalancer.provider.LOG, 'debug')
    @mock.patch.object(loadbalancer.provider.LOG, 'info')
    @mock.patch.object(loadbalancer.Provider, 'connect')
    def test_get_protocols_success(self, mock_connect, mock_log_info,
                                   mock_log_debug):
        """Verifies all method calls and results."""
        mock_connect.return_value = self.api
        self.api.management_url = 'localhost:8080'
        self.api.region_name = 'ORD'
        self.api.protocols = ['HTTP', 'HTTPS']

        results = loadbalancer.provider._get_protocols(
            self.context,
            self.context.auth_token,
            self.context.region)
        self.assertEqual(results, self.api.protocols)
        mock_log_info.assert_called_with('Calling Cloud Load Balancers to get '
                                         'protocols for %s', 'localhost:8080')
        mock_log_debug.assert_called_with('Found Load Balancer protocols for '
                                          '%s: %s', 'localhost:8080',
                                          ['HTTP', 'HTTPS'])

    @mock.patch.object(loadbalancer.provider.LOG, 'error')
    @mock.patch.object(loadbalancer.Provider, 'connect')
    def test_get_protocols_exception(self, mock_connect, mock_logger):
        """Verifies method calls when StandardError raised."""
        mock_exception = StandardError('test error')
        mock_connect.side_effect = mock_exception

        # caching decorator re-raises so not able to assertRaises
        try:
            loadbalancer.provider._get_protocols(self.context,
                                                 self.context.auth_token,
                                                 self.context.region)
        except StandardError as exc:
            self.assertEqual(str(exc), 'test error')

        mock_logger.assert_called_with('Error retrieving Load Balancer '
                                       'protocols from %s: %s', None,
                                       mock_exception)


class TestBasicWorkflow(test.StubbedWorkflowBase):
    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        providers.register_providers(
            [loadbalancer.Provider, test.TestProvider])
        self.deployment = cm_dep.Deployment(utils.yaml_to_dict("""
                id: 'DEP-ID-1000'
                blueprint:
                  name: LB Test
                  services:
                    lb:
                      component:
                        resource_type: load-balancer
                        interface: http
                        constraints:
                          - region: North
                      relations:
                        server: http
                    server:
                      component:
                        resource_type: compute

                environment:
                  name: test
                  providers:
                    load-balancer:
                      vendor: rackspace
                      catalog:
                        load-balancer:
                          rsCloudLB:
                            provides:
                            - load-balancer: http
                            requires:
                            - application: http
                            options:
                              protocol:
                                type: list
                                choice: [http]
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            provides:
                            - application: http
                            - compute: linux
            """))

        self.context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                                 username='MOCK_USER')
        self.deployment['tenantId'] = "tenantId"
        deployments.Manager.plan(self.deployment, self.context)

    def test_workflow_task_generation_for_vip_load_balancer(self):
        vip_deployment = cm_dep.Deployment(utils.yaml_to_dict("""
                id: 'DEP-ID-1000'
                blueprint:
                  name: LB Test
                  services:
                    lb:
                      component:
                        resource_type: load-balancer
                        interface: vip
                        constraints:
                          - region: North
                      relations:
                        master:
                          service: master
                          interface: https
                          attributes:
                            inbound: http/80
                            algorithm: round-robin
                        web:
                          service: web
                          interface: http
                          attributes:
                            inbound: http/80
                            algorithm: random
                    master:
                      component:
                        type: application
                        role: master
                        name: wordpress
                    web:
                      component:
                        type: application
                        role: web
                        name: wordpress
                      relations:
                        master: ssh
                environment:
                  name: test
                  providers:
                    load-balancer:
                      vendor: rackspace
                      catalog:
                        load-balancer:
                          rsCloudLB:
                            provides:
                            - load-balancer: vip
                            requires:
                            - application: http
                            - application: https
                            options:
                              protocol:
                                type: list
                                choice: [http, https]
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            roles:
                            - master
                            - web
                            provides:
                            - application: http
                            - application: https
                            - compute: linux
            """))
        vip_deployment['tenantId'] = "tenantId"
        deployments.Manager.plan(vip_deployment, self.context)
        wf_spec = workflow_spec.WorkflowSpec.create_workflow_spec_deploy(
            vip_deployment, self.context)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, vip_deployment, self.context, "w_id", "BUILD")

        task_list = workflow.spec.task_specs.keys()
        expected = ['Root', 'Start',
                    'Create Resource 3',
                    'Create HTTP Loadbalancer (0)',
                    'Wait for Loadbalancer 0 (lb) build',
                    'Add monitor to Loadbalancer 0 (lb) build',
                    'Create Resource 2',
                    'Create HTTP Loadbalancer (1)',
                    'Wait for Loadbalancer 1 (lb) build',
                    'Add monitor to Loadbalancer 1 (lb) build',
                    'Wait before adding 3 to LB 0',
                    'Add Node 3 to LB 0',
                    'Wait before adding 2 to LB 1',
                    'Add Node 2 to LB 1'
                    ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)

    def test_workflow_task_generation_with_allow_unencrypted_setting(self):
        dep_with_allow_unencrypted = cm_dep.Deployment(
            utils.yaml_to_dict("""
                id: 'DEP-ID-1000'
                blueprint:
                  name: LB Test
                  services:
                    lb:
                      component:
                        resource_type: load-balancer
                        interface: http
                        constraints:
                          - region: North
                          - algorithm: round-robin
                      relations:
                        master: http
                        web: http
                    master:
                      component:
                        type: application
                        role: master
                        name: wordpress
                    web:
                      component:
                        type: application
                        role: web
                        name: wordpress
                inputs:
                  blueprint:
                    protocol: https
                    allow_unencrypted: true
                environment:
                  name: test
                  providers:
                    load-balancer:
                      vendor: rackspace
                      catalog:
                        load-balancer:
                          rsCloudLB:
                            provides:
                            - load-balancer: http
                            requires:
                            - application: http
                            options:
                              protocol:
                                type: list
                                choice: [http, https]
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            roles:
                            - master
                            - web
                            provides:
                            - application: http
                            - compute: linux
            """))
        dep_with_allow_unencrypted['tenantId'] = 'tenantId'
        deployments.Manager.plan(
            dep_with_allow_unencrypted, self.context)
        wf_spec = workflow_spec.WorkflowSpec.create_workflow_spec_deploy(
            dep_with_allow_unencrypted, self.context)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, dep_with_allow_unencrypted, self.context, "w_id",
            "BUILD")

        task_list = workflow.spec.task_specs.keys()
        expected = [
            'Root',
            'Start',
            'Create Resource 3',
            'Create HTTPS Loadbalancer (0)',
            'Wait for Loadbalancer 0 (lb) build',
            'Add monitor to Loadbalancer 0 (lb) build',
            'Create Resource 2',
            'Create HTTP Loadbalancer (1)',
            'Wait for Loadbalancer 1 (lb) build',
            'Add monitor to Loadbalancer 1 (lb) build',
            'Wait before adding 3 to LB 0',
            'Wait before adding 2 to LB 0',
            'Add Node 3 to LB 0',
            'Add Node 3 to LB 1',
            'Wait before adding 2 to LB 1',
            'Wait before adding 3 to LB 1',
            'Add Node 2 to LB 1',
            'Add Node 2 to LB 0',
        ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)

    def test_workflow_task_generation_caching(self):
        """Verifies workflow tasks with caching enabled."""
        deployment = cm_dep.Deployment(utils.yaml_to_dict("""
                id: 'DEP-ID-1000'
                blueprint:
                  name: LB Test
                  services:
                    lb:
                      component:
                        resource_type: load-balancer
                        interface: http
                        constraints:
                          - region: North
                          - caching: true
                      relations:
                        server: http
                    server:
                      component:
                        resource_type: compute

                environment:
                  name: test
                  providers:
                    load-balancer:
                      vendor: rackspace
                      catalog:
                        load-balancer:
                          rsCloudLB:
                            provides:
                            - load-balancer: http
                            requires:
                            - application: http
                            options:
                              protocol:
                                type: list
                                choice: [http]
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            provides:
                            - application: http
                            - compute: linux
        """))
        deployment['tenantId'] = "tenantId"
        deployments.Manager.plan(deployment, self.context)
        wf_spec = workflow_spec.WorkflowSpec.create_workflow_spec_deploy(
            deployment, self.context)
        workflow = cm_wf.init_spiff_workflow(wf_spec, deployment,
                                             self.context, "w_id", "BUILD")

        task_list = workflow.spec.task_specs.keys()
        expected = [
            'Root',
            'Start',
            'Add Node 1 to LB 0',
            'Create HTTP Loadbalancer (0)',
            'Create Resource 1',
            'Wait before adding 1 to LB 0',
            'Add monitor to Loadbalancer 0 (lb) build',
            'Wait for Loadbalancer 0 (lb) build',
            'Enable content caching for Load balancer 0 (lb)'
        ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected)

    def test_workflow_task_generation(self):
        wf_spec = workflow_spec.WorkflowSpec.create_workflow_spec_deploy(
            self.deployment, self.context)
        workflow = cm_wf.init_spiff_workflow(wf_spec, self.deployment,
                                             self.context, "w_id", "BUILD")

        task_list = workflow.spec.task_specs.keys()
        expected = [
            'Root',
            'Start',
            'Add Node 1 to LB 0',
            'Create HTTP Loadbalancer (0)',
            'Create Resource 1',
            'Wait before adding 1 to LB 0',
            'Add monitor to Loadbalancer 0 (lb) build',
            'Wait for Loadbalancer 0 (lb) build'
        ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)

    def test_workflow_completion(self):
        """Verify workflow sequence and data flow."""

        expected = []

        for key, resource in self.deployment['resources'].iteritems():
            if resource.get('type') == 'compute':
                expected.append({
                    'call': 'checkmate.providers.test.create_resource',
                    'args': [mox.IsA(dict), resource],
                    'kwargs': None,
                    'result': {
                        'instance:%s' % key: {
                            'id': 'server9',
                            'status': 'ACTIVE',
                            'ip': '4.4.4.1',
                            'private_ip': '10.1.2.1',
                            'addresses': {
                                'public': [
                                    {
                                        'version': 4,
                                        'addr': '4.4.4.1'
                                    },
                                    {
                                        'version': 6,
                                        'addr': '2001:babe::ff04:36c1'
                                    }
                                ],
                                'private': [{
                                    'version': 4,
                                    'addr': '10.1.2.1'
                                }]
                            },
                        }
                    },
                    'post_back_result': True,
                })
            elif resource.get('type') == 'load-balancer':

                # Create Load Balancer

                expected.append({
                    'call': 'checkmate.providers.rackspace.loadbalancer.'
                            'create_loadbalancer',
                    'args': [
                        mox.IsA(dict),
                        'lb01.checkmate.local',
                        'PUBLIC',
                        'HTTP',
                        'North',
                    ],
                    'kwargs': {
                        'dns': False,
                        'algorithm': 'ROUND_ROBIN',
                        'port': None,
                        'tags': {
                            'RAX-CHECKMATE':
                            'http://MOCK/TMOCK/deployments/'
                            'DEP-ID-1000/resources/0'
                        },
                        'parent_lb': None,
                    },
                    'post_back_result': True,
                    'result': {
                        'instance:0': {
                            'id': 121212,
                            'public_ip': '8.8.8.8',
                            'port': 80,
                            'protocol': 'http',
                            'status': 'ACTIVE'
                        }
                    },
                    'resource': key,
                })

                expected.append({
                    'call': 'checkmate.providers.rackspace.loadbalancer.'
                            'wait_on_build',
                    'args': [mox.IsA(dict), 121212, 'North'],
                    'kwargs': None,
                    'result': None,
                    'resource': key,
                })

                expected.append({
                    'call': 'checkmate.providers.rackspace.loadbalancer.'
                            'set_monitor',
                    'args': [mox.IsA(dict), 121212, mox.IgnoreArg(), 'North'],
                    'kwargs': None,
                    'result': None,
                    'resource': key,
                })

                expected.append({
                    'call': 'checkmate.providers.rackspace.loadbalancer.'
                            'add_node',
                    'args': [
                        mox.IsA(dict),
                        121212,
                        '10.1.2.1',
                        'North',
                        resource
                    ],
                    'kwargs': None,
                    'result': None,
                    'resource': key,
                })

        self.workflow = self._get_stubbed_out_workflow(expected_calls=expected)

        self.mox.ReplayAll()

        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(),
                        'Workflow did not complete')

        self.mox.VerifyAll()


class TestLoadBalancerGetResources(unittest.TestCase):
    @mock.patch.object(loadbalancer.Provider, 'connect')
    @mock.patch('checkmate.providers.rackspace.loadbalancer.provider.pyrax')
    def test_get_resources_returns_load_balancer_resource(self, mock_pyrax,
                                                          mock_connect):
        request = mock.Mock()
        load_balancer = mock.Mock()
        load_balancer.status = 'status'
        load_balancer.name = 'name'
        load_balancer.protocol = 'protocol'
        load_balancer.id = 'id'
        load_balancer.port = 'port'
        load_balancer.virtual_ips = []
        load_balancer.metadata = []
        load_balancer.manager.api.region_name = 'region_name'

        lb_api = mock.Mock()
        lb_api.list.return_value = [load_balancer]
        mock_connect.return_value = lb_api
        mock_pyrax.regions = ["DFW"]

        result = loadbalancer.Provider.get_resources(request, 'tenant')[0]

        self.assertEqual(len(result.keys()), 6)
        self.assertEqual(result['status'], 'status')
        self.assertEqual(result['region'], 'region_name')
        self.assertEqual(result['provider'], 'load-balancer')
        self.assertEqual(result['dns-name'], 'name')
        self.assertEqual(result['instance']['protocol'], 'protocol')
        self.assertEqual(result['instance']['id'], 'id')
        self.assertEqual(result['instance']['port'], 'port')
        self.assertEqual(result['type'], 'load-balancer')

    @mock.patch.object(loadbalancer.Provider, 'connect')
    @mock.patch('checkmate.providers.rackspace.loadbalancer.provider.pyrax')
    def test_get_resources_uses_public_ip(self, mock_pyrax, mock_connect):
        context = mock.Mock()
        load_balancer = mock.Mock()
        vip = mock.Mock()
        vip.type = 'PUBLIC'
        vip.ip_version = 'IPV4'
        vip.address = '1.1.1.1'
        load_balancer.virtual_ips = [vip]
        load_balancer.metadata = []

        lb_api = mock.Mock()
        lb_api.list.return_value = [load_balancer]
        mock_connect.return_value = lb_api
        mock_pyrax.regions = ['DFW']

        result = loadbalancer.Provider.get_resources(context, 'tenant')
        instance = result[0]['instance']
        self.assertEqual(instance['public_ip'], '1.1.1.1')

    @mock.patch.object(loadbalancer.Provider, 'connect')
    @mock.patch('checkmate.providers.rackspace.loadbalancer.provider.pyrax')
    def test_get_resources_dont_return_cm_resources(self, mock_pyrax,
                                                    mock_connect):
        context = mock.Mock()
        load_balancer = mock.Mock()
        load_balancer.virtual_ips = []
        load_balancer.metadata = [{'key': 'RAX-CHECKMATE'}]

        lb_api = mock.Mock()
        lb_api.list.return_value = [load_balancer]
        mock_connect.return_value = lb_api
        mock_pyrax.regions = ['DFW']

        result = loadbalancer.Provider.get_resources(context, 'tenant')
        self.assertEqual(result, [])


if __name__ == '__main__':
    import sys

    test.run_with_params(sys.argv[:])
