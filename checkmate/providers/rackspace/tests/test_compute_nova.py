#!/usr/bin/env python
import logging
import unittest2 as unittest

from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

import mox
from novaclient.v1_1 import client

from checkmate.exceptions import CheckmateException
from checkmate.deployments import Deployment, resource_postback
from checkmate.providers.base import PROVIDER_CLASSES
from checkmate.providers.rackspace import compute
from checkmate.test import StubbedWorkflowBase, TestProvider
from checkmate.utils import yaml_to_dict


class TestNovaCompute(unittest.TestCase):
    """ Test Nova Compute Provider """

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_provider(self):
        provider = compute.Provider({})
        self.assertEqual(provider.key, 'rackspace.nova')

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
        image.id = compute.UBUNTU_12_04_IMAGE_ID

        #Mock flavor
        flavor = self.mox.CreateMockAnything()
        flavor.id = '2'

        context = dict(deployment='DEP', resource='1')

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')

        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.images = self.mox.CreateMockAnything()
        openstack_api_mock.flavors = self.mox.CreateMockAnything()
        openstack_api_mock.client = self.mox.CreateMockAnything()

        openstack_api_mock.images.find(id=image.id).AndReturn(image)
        openstack_api_mock.flavors.find(id=flavor.id).AndReturn(flavor)
        openstack_api_mock.servers.create('fake_server', image, flavor,
                                          files=None).AndReturn(server)
        openstack_api_mock.client.region_name = "NORTH"

        expected = {
            'instance:1': {
                'id': server.id,
                'password': server.adminPass,
                'region': "NORTH",
            }
        }

        resource_postback.delay(context['deployment'],
                                expected).AndReturn(True)

        self.mox.ReplayAll()
        results = compute.create_server(context, 'fake_server', "North",
                                        api_object=openstack_api_mock,
                                        flavor='2', files=None,
                                        image=compute.UBUNTU_12_04_IMAGE_ID)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

class TestNovaGenerateTemplate(unittest.TestCase):
    """Test Nova Compute Provider's region functions"""

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
                    compute.UBUNTU_12_04_IMAGE_ID: {
                        'os': 'Ubuntu 12.04',
                        'name': 'Ubuntu 12.04 LTS'
                    }
                },
                'regions': {
                    'ORD': 'http://some.endpoint'
                }
            }
        }
        provider = compute.Provider({})
       
        #Mock Base Provider, context and deployment
        RackspaceComputeProviderBase = self.mox.CreateMockAnything()
        context = self.mox.CreateMockAnything()
        deployment = self.mox.CreateMockAnything()


        RackspaceComputeProviderBase.generate_template.AndReturn(True)

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')

        deployment.get_setting('region', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key).AndReturn('ORD')
        deployment.get_setting('os', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key,
                               default="Ubuntu 12.04")\
                .AndReturn("Ubuntu 12.04")
        deployment.get_setting('memory', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key, default=512)\
                .AndReturn('512')

        expected = {
            'instance': {},
            'dns-name': 'fake_name',
            'type': 'compute',
            'provider': provider.key,
            'flavor': '2',
            'service': 'master',
            'image': compute.UBUNTU_12_04_IMAGE_ID,
            'region': 'ORD'
        }

        provider.get_catalog(context).AndReturn(catalog)


        self.mox.ReplayAll()
        results = provider.generate_template(deployment, 'compute', 'master',
                                             context, name='fake_name')

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_catalog_and_deployment_diff(self):
        """Catalog and Deployment have different regions"""
        catalog = {
            'lists': {
                'sizes': {
                    '2': {
                        'disk': 20,
                        'name': '512server',
                        'memory': 512
                    }
                },
                'regions': {
                    'ORD': 'http://some.endpoint'
                },
                'types': {
                    compute.UBUNTU_12_04_IMAGE_ID: {
                        'os': 'Ubuntu 12.04',
                        'name': 'Ubuntu 12.04 LTS'
                    }
                }
            }
        }
        provider = compute.Provider({})
       
        #Mock Base Provider, context and deployment
        RackspaceComputeProviderBase = self.mox.CreateMockAnything()
        context = self.mox.CreateMockAnything()
        deployment = self.mox.CreateMockAnything()

        RackspaceComputeProviderBase.generate_template.AndReturn(True)

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')

        deployment.get_setting('region', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key).AndReturn('dallas')
        deployment.get_setting('os', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key,
                               default="Ubuntu 12.04")\
                .AndReturn("Ubuntu 12.04")
        deployment.get_setting('memory', resource_type='compute',
                               service_name='master',
                               provider_key=provider.key, default=512)\
                .AndReturn('512')

        provider.get_catalog(context).AndReturn(catalog)

        self.mox.ReplayAll()
        try:
            provider.generate_template(deployment, 'compute',
                                       'master', context, name='fake_name')
        except CheckmateException:
            #pass
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
