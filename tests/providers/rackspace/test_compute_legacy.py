#!/usr/bin/env python
import logging
import unittest2 as unittest

from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

import mox
import openstack.compute

from checkmate.exceptions import CheckmateException
from checkmate.deployments import resource_postback
from checkmate.middleware import RequestContext
from checkmate.providers.rackspace import compute_legacy
from checkmate import test


class TestLegacyCompute(test.ProviderTester):
    """ Test Legacy Compute Provider """
    klass = compute_legacy.Provider

    def test_create_server(self):

        #Mock server
        server = self.mox.CreateMockAnything()
        server.id = 'fake_server_id'
        server.status = 'BUILD'
        server.addresses = {
            'public': [
                '1.2.3.4'
            ],
            'private': [
                '5.6.7.8'
            ]
        }
        server.ip = '1.2.3.4'
        server.private_ip = '5.6.7.8'
        server.adminPass = 'password'

        #Mock image
        image = self.mox.CreateMockAnything()
        image.id = 119

        #Mock flavor
        flavor = self.mox.CreateMockAnything()
        flavor.id = 2

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')

        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.images = self.mox.CreateMockAnything()
        openstack_api_mock.flavors = self.mox.CreateMockAnything()

        openstack_api_mock.images.find(id=image.id).AndReturn(image)
        openstack_api_mock.flavors.find(id=flavor.id).AndReturn(flavor)
        openstack_api_mock.servers.create(image=119, flavor=2, meta=None,
                                          name='fake_server',
                                          files=None).AndReturn(server)

        expected = {
            'instance:1': {
                'id': server.id,
                'ip': server.ip,
                'password': server.adminPass,
                'private_ip': server.private_ip
            }
        }

        context = dict(deployment='DEP', resource='1')
        resource_postback.delay(context['deployment'],
                                expected).AndReturn(True)

        self.mox.ReplayAll()
        results = compute_legacy.create_server(context, name='fake_server',
                                               api_object=openstack_api_mock,
                                               flavor=2, files=None, image=119,
                                               ip_address_type='public')

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()


class TestLegacyGenerateTemplate(unittest.TestCase):
    """Test Legacy Compute Provider's region functions"""

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_catalog_and_deployment_same(self):
        """Catalog and Deployment have matching regions"""
        catalog = {
            'lists': {
                'sizes': {
                    '2': {
                        'disk': 20,
                        'name': '512server',
                        'memory': 512
                    }
                },
                'types': {
                    '119': {
                        'os': 'Ubuntu11.10',
                        'name': 'Ubuntu11.10'
                    }
                },
                'regions': {
                    'ORD': 'http://some.endpoint'
                }
            }
        }
        provider = compute_legacy.Provider({})

        #Mock Base Provider, context and deployment
        RackspaceComputeProviderBase = self.mox.CreateMockAnything()
        context = self.mox.CreateMockAnything()
        deployment = self.mox.CreateMockAnything()
        deployment['id'].AndReturn('Mock')
        context = RequestContext()
        RackspaceComputeProviderBase.generate_template.AndReturn(True)

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')

        deployment.get_setting('region', resource_type='compute', service_name='master',
                               provider_key=provider.key).AndReturn('ORD')
        deployment.get_setting('os', resource_type='compute', service_name='master',
                               provider_key=provider.key, default=119).AndReturn('119')
        deployment.get_setting('memory', resource_type='compute', service_name='master',
                               provider_key=provider.key, default=512).AndReturn('512')

        expected = {
            'instance': {},
            'dns-name': 'fake_name',
            'type': 'compute',
            'provider': 'rackspace.legacy',
            'service': 'master',
            'flavor': '2',
            'image': '119',
            'region': 'ORD'
        }

        provider.get_catalog(context).AndReturn(catalog)
        provider.get_catalog(context, type_filter="regions").AndReturn(catalog)


        self.mox.ReplayAll()
        results = provider.generate_template(deployment, 'compute', 'master',
                                             context, name='fake_name')

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_catalog_and_deployment_diff(self):
        """Catalog and Deployment have different regions"""
        catalog = {
            'lists': {
                'regions': {
                    'ORD': 'http://some.endpoint'
                }
            }
        }
        provider = compute_legacy.Provider({})
       
        #Mock Base Provider, context and deployment
        RackspaceComputeProviderBase = self.mox.CreateMockAnything()
        deployment = self.mox.CreateMockAnything()
        deployment['id'].AndReturn('Mock')
        context = RequestContext()
        RackspaceComputeProviderBase.generate_template.AndReturn(True)

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')
        provider.get_catalog(context).AndReturn(catalog)

        deployment.get_setting('region', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key).AndReturn('dallas')

        provider.get_catalog(context, type_filter="regions").AndReturn(catalog)

        self.mox.ReplayAll()
        try:
            provider.generate_template(deployment, 'compute',
                                       'master', context, name='fake_name')
        except CheckmateException:
            #pass
            self.mox.VerifyAll()

    def test_no_region(self):
        """ No region specified in deployment or catalog"""
        catalog = {
            'lists': {
                'sizes': {
                    '2': {
                        'disk': 20,
                        'name': '512server',
                        'memory': 512
                    }
                },
                'types': {
                    '119': {
                        'os': 'Ubuntu11.10',
                        'name': 'Ubuntu11.10'
                    }
                }
            }
        }
        provider = compute_legacy.Provider({})

        #Mock Base Provider, context and deployment
        RackspaceComputeProviderBase = self.mox.CreateMockAnything()
        context = self.mox.CreateMockAnything()
        deployment = self.mox.CreateMockAnything()
        deployment['id'].AndReturn('Mock')
        context = RequestContext()
        RackspaceComputeProviderBase.generate_template.AndReturn(True)

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')

        deployment.get_setting('region', resource_type='compute', service_name='master',
                               provider_key=provider.key).AndReturn(None)
        deployment.get_setting('os', resource_type='compute', service_name='master',
                               provider_key=provider.key, default=119).AndReturn('119')
        deployment.get_setting('memory', resource_type='compute', service_name='master',
                               provider_key=provider.key, default=512).AndReturn('512')

        expected = {
            'instance': {},
            'dns-name': 'fake_name',
            'type': 'compute',
            'provider': 'rackspace.legacy',
            'flavor': '2',
            'image': '119',
            'service': 'master',
        }

        provider.get_catalog(context).AndReturn(catalog)

        self.mox.ReplayAll()
        results = provider.generate_template(deployment, 'compute', 'master',
                                             context, name='fake_name')

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_deployment_region(self):
        """Region specified in deployment but not catalog"""
        catalog = {
            'lists': {
                'sizes': {
                    '2': {
                        'disk': 20,
                        'name': '512server',
                        'memory': 512
                    }
                },
                'types': {
                    '119': {
                        'os': 'Ubuntu11.10',
                        'name': 'Ubuntu11.10'
                    }
                }
            }
        }
        provider = compute_legacy.Provider({})

        #Mock Base Provider, context and deployment
        RackspaceComputeProviderBase = self.mox.CreateMockAnything()
        context = self.mox.CreateMockAnything()
        deployment = self.mox.CreateMockAnything()
        deployment['id'].AndReturn('Mock')
        context = RequestContext()
        RackspaceComputeProviderBase.generate_template.AndReturn(True)

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')

        deployment.get_setting('region', resource_type='compute',
                service_name='master', provider_key=provider.key).AndReturn(
                'ORD')
        deployment.get_setting('os', resource_type='compute',
                service_name='master', provider_key=provider.key,
                default=119).AndReturn('119')
        deployment.get_setting('memory', resource_type='compute',
                service_name='master', provider_key=provider.key, default=512
                ).AndReturn('512')

        expected = {
            'instance': {},
            'dns-name': 'fake_name',
            'type': 'compute',
            'provider': 'rackspace.legacy',
            'service': 'master',
            'flavor': '2',
            'image': '119',
            'region': 'ORD'
        }


        provider.get_catalog(context).AndReturn(catalog)
        provider.get_catalog(context, type_filter="regions").AndReturn(catalog)

        self.mox.ReplayAll()

        results = provider.generate_template(deployment, 'compute', 'master',
                                             context, name='fake_name')
        self.mox.VerifyAll()
        self.assertDictEqual(results, expected)

    def test_region_supplied_as_airport_code(self):
        """Deployment region listed as airport code"""
        catalog = {
            'lists': {
                'sizes': {
                    '2': {
                        'disk': 20,
                        'name': '512server',
                        'memory': 512
                    }
                },
                'types': {
                    '119': {
                        'os': 'Ubuntu11.10',
                        'name': 'Ubuntu11.10'
                    }
                },
                'regions': {
                    'ORD': 'http://some.endpoint'
                }

            }
        }
        provider = compute_legacy.Provider({})
       
        #Mock Base Provider, context and deployment
        RackspaceComputeProviderBase = self.mox.CreateMockAnything()
        context = self.mox.CreateMockAnything()
        deployment = self.mox.CreateMockAnything()
        deployment['id'].AndReturn('Mock')
        context = RequestContext()
        RackspaceComputeProviderBase.generate_template.AndReturn(True)

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')
        
        deployment.get_setting('region', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key).AndReturn('ORD')
        deployment.get_setting('os', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key, default=119).\
                               AndReturn('119')
        deployment.get_setting('memory', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key, default=512).\
                               AndReturn('512')
        
        expected = {
            'instance': {},
            'dns-name': 'fake_name',
            'type': 'compute',
            'provider': 'rackspace.legacy',
            'service': 'master',
            'flavor': '2',
            'image': '119',
            'region': 'ORD'
        }
      
        provider.get_catalog(context).AndReturn(catalog)
        provider.get_catalog(context, type_filter="regions").AndReturn(catalog)


        self.mox.ReplayAll()
        results = provider.generate_template(deployment, 'compute', 'master',
                                             context, name='fake_name')

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()


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
