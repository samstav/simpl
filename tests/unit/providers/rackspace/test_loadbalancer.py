import unittest2 as unittest
import mox

from checkmate.middleware import RequestContext
from checkmate.providers.rackspace import loadbalancer
from mox import IgnoreArg


class TestLoadBalancer(unittest.TestCase):
    """Test Load Balancer Provider's functions"""

    def setUp(self):
        self.deployment_mocker = mox.Mox()
        self.provider = loadbalancer.Provider({})
        self.deployment = self.deployment_mocker.CreateMockAnything()
        self.context = RequestContext()
        self.deployment.get_setting('region', resource_type='load-balancer',
                                    service_name='lb',
                                    provider_key=self.provider.key)\
            .AndReturn('NORTH')

    def tearDown(self):
        self.deployment_mocker.VerifyAll()
        self.deployment_mocker.UnsetStubs()

    def test_generate_template_with_interface_vip(self):
        self.deployment.get('blueprint').AndReturn(
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
                                    default=IgnoreArg()) \
            .AndReturn('test.checkmate')
        self.deployment._constrained_to_one('lb').AndReturn(True)
        self.deployment.get_setting("inbound",
                                    provider_key=self.provider.key,
                                    resource_type='load-balancer',
                                    service_name='lb',
                                    relation='master',
                                    default="http/80").AndReturn('http/80')
        (self.deployment.get_setting('create_dns',
                                     resource_type='load-balancer',
                                     service_name='lb',
                                     default=IgnoreArg())
            .AndReturn('false'))

        expected = {
            'service': 'lb',
            'region': 'NORTH',
            'dns-name': 'lb.test.checkmate',
            'instance': {},
            'type': 'load-balancer',
            'provider': self.provider.key,
            'port': '80',
            'protocol': 'http'
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
                                                  self.context, 1,
                                                  self.provider.key,
                                                  connections)

        self.assertEqual(len(results), 1)
        self.assertDictEqual(results[0], expected)

    def test_should_generate_template_with_allow_unencrypted(self):
        self.deployment.get('blueprint').AndReturn(
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
                                    default=IgnoreArg()) \
            .AndReturn('test.checkmate')
        self.deployment._constrained_to_one('lb').AndReturn(True)
        self.deployment.get_setting('domain', provider_key=self.provider.key,
                                    resource_type='load-balancer',
                                    service_name='lb',
                                    default=IgnoreArg()) \
            .AndReturn('test.checkmate')
        self.deployment._constrained_to_one('lb').AndReturn(True)
        (self.deployment.get_setting('create_dns',
                                     resource_type='load-balancer',
                                     service_name='lb',
                                     default=IgnoreArg())
            .AndReturn('false'))
        self.deployment_mocker.ReplayAll()
        results = self.provider.generate_template(self.deployment,
                                                  'load-balancer', 'lb',
                                                  self.context, 1,
                                                  self.provider.key, {})
        expected_https_lb = {
            'service': 'lb',
            'region': 'NORTH',
            'dns-name': 'lb.test.checkmate',
            'instance': {},
            'type': 'load-balancer',
            'provider': self.provider.key,
        }

        expected_http_lb = {
            'service': 'lb',
            'region': 'NORTH',
            'dns-name': 'lb.test.checkmate',
            'instance': {},
            'type': 'load-balancer',
            'provider': self.provider.key,
            'protocol': 'http'
        }
        self.assertEqual(len(results), 2)
        self.assertDictEqual(results[0], expected_https_lb)
        self.assertDictEqual(results[1], expected_http_lb)


if __name__ == '__main__':
    # Run tests. Handle our parameters seprately
    import sys

    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)