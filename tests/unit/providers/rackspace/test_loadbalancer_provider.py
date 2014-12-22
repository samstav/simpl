# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
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
import mock
import mox
import re
import unittest

from SpiffWorkflow import specs
from SpiffWorkflow import Workflow

from checkmate import deployment as cm_dep
from checkmate import middleware
from checkmate.providers.rackspace import loadbalancer
from checkmate import test
from checkmate import workflow_spec


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
        relation = {'lb-web-1': {'target': '1'}}
        wf_spec = specs.WorkflowSpec()
        context.get_queued_task_dict.return_value = {}
        exp_call = "checkmate.providers.rackspace.loadbalancer.tasks" \
                   ".update_node_status"
        result = provider.disable_connection_tasks(wf_spec, deployment,
                                                   context, source_resource,
                                                   target_resource,
                                                   relation)
        root_task = result['root']
        self.assertEqual(len(result), 2)
        self.assertListEqual(result.keys(), ['root', 'final'])
        self.assertIsInstance(root_task, specs.Celery)
        self.assertEqual(root_task.call, exp_call)
        self.assertEqual(root_task.args, [{}, relation, "LB_ID", "IP",
                                          "DISABLED", "OFFLINE"])
        self.assertEqual(root_task.properties, {
            'provider': provider.key,
            'resource': '1',
            'estimated_duration': 5
        })
        context.get_queued_task_dict.assert_called_once_with(
            deployment_id="DEP_ID", resource_key="0", region="ORD")

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
        relation = {'lb-web-1': {'target': '1'}}
        wf_spec = specs.WorkflowSpec()
        context.get_queued_task_dict.return_value = {}
        exp_call = "checkmate.providers.rackspace.loadbalancer.tasks" \
                   ".update_node_status"
        result = provider.enable_connection_tasks(wf_spec, deployment,
                                                  context, source_resource,
                                                  target_resource,
                                                  relation)
        root_task = result['root']
        self.assertEqual(len(result), 2)
        self.assertListEqual(result.keys(), ['root', 'final'])
        self.assertIsInstance(root_task, specs.Celery)
        self.assertEqual(root_task.call, exp_call)
        self.assertEqual(root_task.args, [{}, relation, "LB_ID", "IP",
                                          "ENABLED", "ACTIVE"])
        self.assertEqual(root_task.properties, {
            'provider': provider.key,
            'resource': '1',
            'estimated_duration': 5
        })
        context.get_queued_task_dict.assert_called_once_with(
            deployment_id="DEP_ID", resource_key="0", region="ORD")

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


class TestLoadBalancerProvider(unittest.TestCase):

    """Test Load Balancer Provider's functions."""

    def setUp(self):
        self.deployment_mocker = mox.Mox()
        self.provider = loadbalancer.Provider({})
        self.deployment = self.deployment_mocker.CreateMockAnything()
        self.context = middleware.RequestContext()
        self.deployment.get_setting('region', resource_type='load-balancer',
                                    service_name='lb',
                                    provider_key=self.provider.key)\
            .AndReturn('NORTH')

    def tearDown(self):
        self.deployment_mocker.VerifyAll()
        self.deployment_mocker.UnsetStubs()

    def test_generate_template_with_interface_vip(self):
        self.deployment.get('blueprint', {}).AndReturn(
            {'services': {'lb': {'component': {'interface': 'vip'}}}})

        self.deployment.get_setting("protocol",
                                    resource_type='load-balancer',
                                    service_name='lb',
                                    provider_key=self.provider.key,
                                    default="http") \
            .AndReturn('http')
        self.deployment.get_setting('domain',
                                    provider_key=self.provider.key,
                                    resource_type='load-balancer',
                                    service_name='lb',
                                    default=mox.IgnoreArg()) \
            .AndReturn('test.checkmate')
        self.deployment._constrained_to_one('lb').AndReturn(True)
        self.deployment.get_setting("inbound",
                                    provider_key=self.provider.key,
                                    resource_type='load-balancer',
                                    service_name='lb',
                                    relation='master',
                                    default="http/80").AndReturn('http/80')
        self.deployment.get_setting('create_dns',
                                    resource_type='load-balancer',
                                    service_name='lb',
                                    default=mox.IgnoreArg()
                                    ).AndReturn('false')

        expected = {
            'service': 'lb',
            'region': 'NORTH',
            'dns-name': 'lb.test.checkmate',
            'instance': {},
            'type': 'load-balancer',
            'provider': self.provider.key,
            'port': '80',
            'protocol': 'http',
            'desired-state': {'protocol': 'http', 'region': 'NORTH'},
        }

        connections = {
            'connections': {
                'master': {
                    'relation-key': 'master',
                },
            },
        }
        self.deployment_mocker.ReplayAll()
        results = self.provider.generate_template(self.deployment,
                                                  'load-balancer', 'lb',
                                                  self.context, '1',
                                                  self.provider.key,
                                                  connections)

        self.assertEqual(len(results), 1)
        self.assertDictEqual(results[0], expected)

    def test_should_generate_template_with_allow_unencrypted(self):
        self.deployment.get('blueprint', {}).AndReturn(
            {'services': {'lb': {'component': {'interface': 'https'}}}})

        self.deployment.get_setting("protocol",
                                    resource_type='load-balancer',
                                    service_name='lb',
                                    provider_key=self.provider.key,
                                    default="http") \
            .AndReturn('https')
        self.deployment.get_setting('allow_insecure',
                                    provider_key=self.provider.key,
                                    resource_type='load-balancer',
                                    service_name='lb',
                                    default=False) \
            .AndReturn(True)
        self.deployment.get_setting('allow_unencrypted',
                                    provider_key=self.provider.key,
                                    resource_type='load-balancer',
                                    service_name='lb',
                                    default=False) \
            .AndReturn(True)
        self.deployment.get_setting('domain', provider_key=self.provider.key,
                                    resource_type='load-balancer',
                                    service_name='lb',
                                    default=mox.IgnoreArg()) \
            .AndReturn('test.checkmate')
        self.deployment._constrained_to_one('lb').AndReturn(True)
        self.deployment.get_setting('domain', provider_key=self.provider.key,
                                    resource_type='load-balancer',
                                    service_name='lb',
                                    default=mox.IgnoreArg()) \
            .AndReturn('test.checkmate')
        self.deployment._constrained_to_one('lb').AndReturn(True)
        (self.deployment.get_setting('create_dns',
                                     resource_type='load-balancer',
                                     service_name='lb',
                                     default=mox.IgnoreArg())
            .AndReturn('false'))
        self.deployment_mocker.ReplayAll()
        results = self.provider.generate_template(self.deployment,
                                                  'load-balancer', 'lb',
                                                  self.context, '1',
                                                  self.provider.key, {})
        expected_https_lb = {
            'service': 'lb',
            'region': 'NORTH',
            'dns-name': 'lb.test.checkmate',
            'instance': {},
            'type': 'load-balancer',
            'provider': self.provider.key,
            'desired-state': {'protocol': 'https', 'region': 'NORTH'},
        }

        expected_http_lb = {
            'service': 'lb',
            'region': 'NORTH',
            'dns-name': 'lb.test.checkmate',
            'instance': {},
            'type': 'load-balancer',
            'provider': self.provider.key,
            'protocol': 'http',
            'desired-state': {'protocol': 'http', 'region': 'NORTH'},
        }
        self.assertEqual(len(results), 2)
        self.assertDictEqual(results[0], expected_https_lb)
        self.assertDictEqual(results[1], expected_http_lb)


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
    from checkmate import test
    test.run_with_params()
