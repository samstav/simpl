#!/usr/bin/env python
import logging
import unittest2 as unittest

import cloudlb
import mox
from mox import IsA, IgnoreArg

from checkmate.utils import init_console_logging
from checkmate.providers.rackspace.loadbalancer import (
    delete_lb_task,
    wait_on_lb_delete,
)
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import test, utils
from checkmate.exceptions import CheckmateException
from checkmate.deployments import resource_postback, Deployment, plan
from checkmate.middleware import RequestContext
from checkmate.providers import base, register_providers
from checkmate.providers.rackspace import loadbalancer
from checkmate.workflow import create_workflow_deploy


class TestLoadBalancer(test.ProviderTester):
    """ Test Load-Balancer Provider """
    klass = loadbalancer.Provider

    def test_provider(self):
        provider = loadbalancer.Provider({})
        self.assertEqual(provider.key, 'rackspace.load-balancer')

    def verify_limits(self, max_lbs, max_nodes):
        """Test the verify_limits() method"""
        resources = [{
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
        }, {
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
        }]
        context = RequestContext()
        self.mox.StubOutWithMock(loadbalancer.Provider, 'find_a_region')
        self.mox.StubOutWithMock(loadbalancer.Provider, 'find_url')
        self.mox.StubOutWithMock(loadbalancer.Provider, '_get_abs_limits')
        limits = {
          "NODE_LIMIT": max_nodes,
          "LOADBALANCER_LIMIT": max_lbs
        }
        loadbalancer.Provider.find_a_region(mox.IgnoreArg()).AndReturn("DFW")
        loadbalancer.Provider.find_url(mox.IgnoreArg(),
                                       mox.IgnoreArg()).AndReturn("fake url")
        (loadbalancer.Provider
         ._get_abs_limits(mox.IgnoreArg(), mox.IgnoreArg())
         .AndReturn(limits))
        clb = self.mox.CreateMockAnything()
        clb_lbs = self.mox.CreateMockAnything()
        clb.loadbalancers = clb_lbs
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
        """Test that verify_limits() returns warnings if limits are not okay"""
        result = self.verify_limits(1, 0)
        self.assertEqual(3, len(result))
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")

    def test_verify_access_positive(self):
        """Test that verify_access() returns ACCESS-OK if user has access"""
        context = RequestContext()
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
        """Test that verify_access() returns ACCESS-OK if user has access"""
        context = RequestContext()
        context.roles = 'LBaaS:observer'
        provider = loadbalancer.Provider({})
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'NO-ACCESS')


class TestCeleryTasks(unittest.TestCase):

    """ Test Celery tasks """

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_create_load_balancer(self):
        name = 'fake_lb'
        vip_type = 'SERVICENET'
        protocol = 'notHTTP'
        region = 'North'
        fake_id = 121212
        public_ip = 'a.b.c.d'
        servicenet_ip = 'w.x.y.z'
        status = 'BUILD'

        #Mock server
        lb = self.mox.CreateMockAnything()
        lb.id = fake_id
        lb.port = 80
        lb.protocol = protocol
        lb.status = status

        ip_data_pub = self.mox.CreateMockAnything()
        ip_data_pub.ipVersion = 'IPV4'
        ip_data_pub.type = 'PUBLIC'
        ip_data_pub.address = public_ip

        ip_data_svc = self.mox.CreateMockAnything()
        ip_data_svc.ipVersion = 'IPV4'
        ip_data_svc.type = 'SERVICENET'
        ip_data_svc.address = servicenet_ip

        lb.virtualIps = [ip_data_pub, ip_data_svc]

        context = dict(deployment='DEP', resource='1')

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')

        #Stub out set_monitor call
        self.mox.StubOutWithMock(loadbalancer, 'set_monitor')

        #Create appropriate api mocks
        api_mock = self.mox.CreateMockAnything()
        api_mock.loadbalancers = self.mox.CreateMockAnything()
        api_mock.loadbalancers.create(name=name, port=80,
                                      protocol=protocol.upper(),
                                      nodes=[IsA(cloudlb.Node)],
                                      virtualIps=[IsA(cloudlb.VirtualIP)],
                                      algorithm='ROUND_ROBIN').AndReturn(lb)

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
        instance_id = {
            'instance:%s' % context['resource']: {
                'id': fake_id
            }
        }

        resource_postback.delay(context['deployment'],
                                instance_id).AndReturn(True)
        resource_postback.delay(context['deployment'],
                                expected).AndReturn(True)

        self.mox.ReplayAll()
        results = loadbalancer.create_loadbalancer(context, name, vip_type,
                                                   protocol, region,
                                                   api=api_mock)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_delete_lb_task(self):
        """ Test delete task """
        context = {}
        expect = {
            "instance:1": {
                "status": "DELETING",
                "status-message": "Waiting on resource deletion"
            }
        }
        api = self.mox.CreateMockAnything()
        api.loadbalancers = self.mox.CreateMockAnything()
        m_lb = self.mox.CreateMockAnything()
        api.loadbalancers.get('lb14nuai-asfjb').AndReturn(m_lb)
        m_lb.status = 'ACTIVE'
        m_lb.__str__().AndReturn("Mock LB")
        m_lb.delete().AndReturn(True)
        self.mox.ReplayAll()
        ret = delete_lb_task(context, '1', 'lb14nuai-asfjb', 'ORD', api=api)
        self.assertDictEqual(expect, ret)
        self.mox.VerifyAll()

    def test_wait_on_lb_delete(self):
        """ Test wait on delete task """
        context = {}
        expect = {
                  'instance:1': {
                                  'status': 'DELETED',
                                  'status-message': 'LB instance:1 was deleted'
                                }
                 }
        api = self.mox.CreateMockAnything()
        api.loadbalancers = self.mox.CreateMockAnything()
        m_lb = self.mox.CreateMockAnything()
        m_lb.status = 'DELETED'
        api.loadbalancers.get('lb14nuai-asfjb').AndReturn(m_lb)
        self.mox.StubOutWithMock(loadbalancer, 'resource_postback')
        self.mox.ReplayAll()
        ret = wait_on_lb_delete(context, '1', '1234', 'lb14nuai-asfjb',
                                'ORD', api=api)
        self.assertDictEqual(expect, ret)
        self.mox.VerifyAll()

    def test_wait_on_lb_delete_still(self):
        """ Test wait on delete task when not deleted """
        context = {}
        api = self.mox.CreateMockAnything()
        api.loadbalancers = self.mox.CreateMockAnything()
        m_lb = self.mox.CreateMockAnything()
        m_lb.status = 'DELETING'
        #m_lb.__str__().MultipleTimes().AndReturn('lb14nuai-asfjb')
        api.loadbalancers.get('lb14nuai-asfjb').AndReturn(m_lb)
        self.mox.StubOutWithMock(loadbalancer.resource_postback, 'delay')
        content = {
            'instance:1': {
                'status': 'DELETING',
                "status-message": IgnoreArg(),
            }
        }
        loadbalancer.resource_postback.delay('1234', content).AndReturn(None)
        self.mox.StubOutWithMock(wait_on_lb_delete, 'retry')
        wait_on_lb_delete.retry(exc=IsA(CheckmateException)).AndReturn(None)

        self.mox.ReplayAll()
        wait_on_lb_delete(context, '1', '1234', 'lb14nuai-asfjb', 'ORD',
                          api=api)
        self.mox.VerifyAll()

    def test_lb_sync_resource_task(self):
        """Tests db sync_resource_task via mox"""
        #Mock instance
        lb = self.mox.CreateMockAnything()
        lb.id = 'fake_lb_id'
        lb.name = 'fake_lb'
        lb.status = 'ERROR'

        resource_key = "1"

        context = dict(deployment='DEP', resource='1')

        resource = {
                    'name': 'fake_lb',
                    'provider': 'load-balancers',
                    'status': 'ERROR',
                    'instance': {
                                 'id': 'fake_lb_id'
                            }
                    }

        lb_api_mock = self.mox.CreateMockAnything()
        lb_api_mock.loadbalancers = self.mox.CreateMockAnything()

        lb_api_mock.loadbalancers.get(lb.id).AndReturn(lb)

        expected = {
                    'instance:1': {
                                   "status": "ERROR"
                                   }
                    }

        self.mox.ReplayAll()
        results = loadbalancer.sync_resource_task(context, resource, resource_key,
                                                  lb_api_mock)

        self.assertDictEqual(results, expected)


class TestBasicWorkflow(test.StubbedWorkflowBase):

    """

    Test that workflow tasks are generated and workflow completes

    """

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        register_providers([loadbalancer.Provider, test.TestProvider])
        self.deployment = Deployment(utils.yaml_to_dict("""
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

        self.context = RequestContext(auth_token='MOCK_TOKEN',
                                      username='MOCK_USER')
        plan(self.deployment, self.context)

    def test_workflow_task_generation_for_vip_load_balancer(self):
        vip_deployment = Deployment(utils.yaml_to_dict("""
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
        plan(vip_deployment, self.context)
        workflow = create_workflow_deploy(vip_deployment, self.context)

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
        deployment_with_allow_unencrypted = Deployment(utils.yaml_to_dict("""
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
        plan(deployment_with_allow_unencrypted, self.context)
        workflow = create_workflow_deploy(deployment_with_allow_unencrypted,
                                          self.context)

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

    def test_workflow_task_generation(self):
        """Verify workflow task creation"""

        workflow = create_workflow_deploy(self.deployment, self.context)

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
        """Verify workflow sequence and data flow"""

        expected = []

        for key, resource in self.deployment['resources'].iteritems():
            if resource.get('type') == 'compute':
                expected.append({
                    'call': 'checkmate.providers.test.create_resource',
                    'args': [IsA(dict), resource],
                    'kwargs': None,
                    'result': {
                        'instance:%s' % key: {
                            'id': 'server9',
                            'status': 'ACTIVE',
                            'ip': '4.4.4.1',
                            'private_ip': '10.1.2.1',
                            'addresses': {
                                'public': [{
                                               'version': 4,
                                               'addr': '4.4.4.1'
                                           }, {
                                               'version': 6,
                                               'addr': '2001:babe::ff04:36c1'
                                           }],
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
                        IsA(dict),
                        'lb01.checkmate.local',
                        'PUBLIC',
                        'HTTP',
                        'North',
                    ],
                    'kwargs': {
                        'dns': False,
                        'algorithm': 'ROUND_ROBIN',
                        'port': None,
                        'tags': {'RAX-CHECKMATE': 'http://MOCK/TMOCK/deployments/DEP-ID-1000/resources/0'},
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
                    'args': [IsA(dict), 121212, 'North'],
                    'kwargs': None,
                    'result': None,
                    'resource': key,
                })

                expected.append({
                    'call': 'checkmate.providers.rackspace.loadbalancer.'
                            'set_monitor',
                    'args': [IsA(dict), 121212, mox.IgnoreArg(), 'North'],
                    'kwargs': None,
                    'result': None,
                    'resource': key,
                })

                expected.append({
                    'call': 'checkmate.providers.rackspace.loadbalancer.'
                            'add_node',
                    'args': [IsA(dict), 121212, '10.1.2.1', 'North', resource],
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


if __name__ == '__main__':
    # Run tests. Handle our parameters separately
    import sys

    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
