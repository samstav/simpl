#!/usr/bin/env python
import logging
import unittest2 as unittest

import cloudlb
import mox
from mox import IsA

from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import test
from checkmate.deployments import resource_postback
from checkmate.middleware import RequestContext
from checkmate.providers import ProviderBase
from checkmate.providers.rackspace import loadbalancer


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

        #Mock server
        lb = self.mox.CreateMockAnything()
        lb.id = fake_id
        lb.port = 80
        lb.protocol = protocol

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
                'protocol': protocol
            }
        }

        resource_postback.delay(context['deployment'],
                                expected).AndReturn(True)

        self.mox.ReplayAll()
        results = loadbalancer.create_loadbalancer(context, name, vip_type,
                                                   protocol, region,
                                                   api=api_mock)

        self.assertDictEqual(results, expected)
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
        deployment['id'].AndReturn('Mock')
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
