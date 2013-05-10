import unittest2 as unittest
import mox

from checkmate.middleware import RequestContext
from checkmate.providers.rackspace import loadbalancer


class TestLoadBalancer(unittest.TestCase):
    """Test Load Balancer Provider's functions"""

    def setUp(self):
        self.deployment_mocker = mox.Mox()

    def tearDown(self):
        self.deployment_mocker.UnsetStubs()

    def test_generate_template(self):
        """Test template generation"""
        provider = loadbalancer.Provider({})
        deployment = self.deployment_mocker.CreateMockAnything()
        context = RequestContext()

        deployment.get_setting('region', resource_type='load-balancer',
                               service_name='lb',
                               provider_key=provider.key).AndReturn('NORTH')
        deployment.get('blueprint').AndReturn(
            {'services': {'lb': {'component': {'interface': 'vip'}}}})
        deployment.get_setting('domain', provider_key=provider.key,
                                        resource_type='load-balancer',
                                        service_name='lb',
                                        default='checkmate.local')\
            .AndReturn('test.checkmate')
        deployment._constrained_to_one('lb').AndReturn(True)

        expected = {
            'service': 'lb',
            'region': 'NORTH',
            'dns-name': 'lb.test.checkmate',
            'instance': {},
            'type': 'load-balancer',
            'provider': provider.key,
        }

        self.deployment_mocker.ReplayAll()
        results = provider.generate_template(deployment, 'load-balancer', 'lb',
                                             context, 1, provider.key,
                                             {'connections': {'master': {}}})

        self.assertEqual(len(results), 1)
        self.assertDictEqual(results[0], expected)
        self.deployment_mocker.VerifyAll()

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