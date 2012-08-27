#!/usr/bin/env python
import logging
import unittest2 as unittest

from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate.providers.rackspace import compute_legacy
import mox
import openstack.compute

from checkmate.deployments import Deployment, resource_postback
from checkmate.providers.base import PROVIDER_CLASSES
from checkmate.test import StubbedWorkflowBase, TestProvider
from checkmate.utils import yaml_to_dict


class TestLegacyCompute(unittest.TestCase):
    """ Test Legacy Compute Provider """

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_provider(self):
        provider = compute_legacy.Provider({})
        self.assertEqual(provider.key, 'rackspace.legacy')

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
        openstack_api_mock.servers.create(image=119, flavor=2,
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

    catalog1 = {
        'compute': {
            'windows_instance': {
                'is': 'compute'
            }
        },
        'lists': {
            'images': {
                73487664: {
                    'name': 'my_custom_image'
                }
            }
        }
    }

    catalog2 = {
        'compute': {
            'windows_instance': {
                'is': 'compute'
            }
        },
        'lists': {
            'images': {
                73487664: {
                    'name': 'my_custom_image'
                }
            },
            'regions': {
                 'chicago': 'http://some.endpoint'
            }
        }
    }

    
    inputs = {
        'blueprint': {
            'username': 'user', 
            'domain': None, 
            'region': 'chicago'
            }
        }
      
    REGION_MAP = {'dallas': 'DFW',
              'chicago': 'ORD',
              'london': 'LON'}

    resource_type = 'compute'
    name = 'compute_name'

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()


    def test_catalog_and_deployment_set(self):

        #Mock Providers
        provider = compute_legacy.Provider({})    
        RackspaceComputeProviderBase = self.mox.CreateMockAnything()

        template = {
            'instance': {}, 
            'dns-name': self.name, 
            'type': self.resource_type, 
            'provider': 'legacy'
        }
        
        RackspaceComputeProviderBase.generate_template.AndReturn(template)
        
       # provider.get_catalog(context=None).AndReturn(self.catalog2)
 
        deployment = self.mox.CreateMockAnything()
        deployment.get_setting('region', resource_type='master', service_name='web',
                               provider_key='legacy').AndReturn('chicago')

        
        

        self.mox.ReplayAll()
        provider.generate_template(deployment = 'herp', resource_type = self.resource_type, 
                                   service = 'derp', name=self.name, context = None)
               
            

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
