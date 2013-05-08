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

        loadbalancer.set_monitor.delay(context, fake_id, protocol.upper(),
                                       region, '/', 10, 10, 3, '(.*)',
                                       '^[234][0-9][0-9]$').AndReturn(None)
        expected = {
            'instance:%s' % context['resource']: {
                'id': fake_id,
                'public_ip': public_ip,
                'port': 80,
                'protocol': protocol,
                'status': status
            }
        }

        resource_postback.delay(context['deployment'],
                                expected).AndReturn(True)

        self.mox.ReplayAll()
        results = loadbalancer.create_loadbalancer(context, name, vip_type,
                                                   protocol, region,
                                                   api=api_mock)

        self.assertDictEqual(results, expected)
        #self.mox.VerifyAll()

    def test_delete_lb_task(self):
        """ Test delete task """
        context = {}
        expect = {
            "instance:1": {
                "status": "DELETING",
                "status_msg": "Waiting on resource deletion"
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
        expect = {'instance:1': {'status': 'DELETED'}}
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
                "status_msg": IgnoreArg(),
            }
        }
        loadbalancer.resource_postback.delay('1234', content).AndReturn(None)
        self.mox.StubOutWithMock(wait_on_lb_delete, 'retry')
        wait_on_lb_delete.retry(exc=IsA(CheckmateException)).AndReturn(None)

        self.mox.ReplayAll()
        wait_on_lb_delete(context, '1', '1234', 'lb14nuai-asfjb', 'ORD',
                          api=api)
        self.mox.VerifyAll()


class TestLoadBalancerGenerateTemplate(unittest.TestCase):
    """Test Load Balancer Provider's functions"""

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_template_generation(self):
        """Test template generation"""
        provider = loadbalancer.Provider({})

        #Mock Base Provider, context and deployment
        deployment = self.mox.CreateMockAnything()
        context = RequestContext()

        deployment.get_setting('region', resource_type='load-balancer',
                               service_name='lb',
                               provider_key=provider.key).AndReturn('NORTH')

        expected = {
            'service': 'lb',
            'region': 'NORTH',
            'dns-name': 'fake_name',
            'instance': {},
            'type': 'load-balancer',
            'provider': provider.key,
        }

        self.mox.ReplayAll()
        results = provider.generate_template(deployment, 'load-balancer', 'lb',
                                             context, name='fake_name')

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()


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
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        plan(self.deployment, context)

    def test_workflow_task_generation(self):
        """Verify workflow task creation"""
        context = RequestContext(auth_token='MOCK_TOKEN',
                                 username='MOCK_USER')
        workflow = create_workflow_deploy(self.deployment, context)

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

        #resource_postback mock
        #self.mox.StubOutWithMock(resource_postback, 'delay')
        #resource_postback.delay(mox.IgnoreArg(), mox.IgnoreArg())\
        #.AndReturn(True)

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
