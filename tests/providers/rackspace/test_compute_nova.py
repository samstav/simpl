#!/usr/bin/env python
import logging
import unittest2 as unittest

from checkmate.utils import init_console_logging
from mox import IgnoreArg
from checkmate.providers.rackspace.compute import delete_server_task,\
    wait_on_delete_server
init_console_logging()
LOG = logging.getLogger(__name__)

import mox

from checkmate import test
from checkmate.exceptions import CheckmateException
from checkmate.deployments import resource_postback
from checkmate.middleware import RequestContext
from checkmate.providers.rackspace import compute
from checkmate import ssh


class TestNovaCompute(test.ProviderTester):
    """ Test Nova Compute Provider """
    klass = compute.Provider

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
                                          files=None, meta=None
                                          ).AndReturn(server)
        openstack_api_mock.client.region_name = "NORTH"

        expected = {
            'instance:1': {
                'status': 'NEW',
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

    def test_wait_on_build_rackconnect_pending(self):
        """ Test that Rack Connect waits on metadata """

        #Mock server
        server = self.mox.CreateMockAnything()
        server.id = 'fake_server_id'
        server.status = 'ACTIVE'
        server.addresses = {
                        "private": [
                            {
                                "addr": "10.10.10.10",
                                "version": 4
                            }
                        ],
                        "public": [
                            {
                                "addr": "4.4.4.4",
                                "version": 4
                            },
                            {
                                "addr": "2001:4800:780e:0510:d87b:9cbc:ff04:513a",
                                "version": 6
                            }
                        ]
                }
        server.adminPass = 'password'
        server.metadata = {}

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')
        self.mox.StubOutWithMock(ssh, 'test_connection')

        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.client = self.mox.CreateMockAnything()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.servers.find(id=server.id).AndReturn(server)

        context = dict(deployment='DEP', resource='1', roles=['rack_connect'])
        ssh.test_connection(context, "4.4.4.4", "root", timeout=10,
                password=None, identity_file=None, port=22,
                private_key=None).AndReturn(True)
        resource_postback.delay(context['deployment'],
                                IgnoreArg()).AndReturn(True)

        self.mox.ReplayAll()
        self.assertRaises(CheckmateException, compute.wait_on_build, context,
                           server.id, 'North', [], api_object=openstack_api_mock)

    def test_wait_on_build_rackconnect_ready(self):
        """ Test that Rack Connect waits on metadata """

        #Mock server
        server = self.mox.CreateMockAnything()
        server.id = 'fake_server_id'
        server.status = 'ACTIVE'
        server.addresses = {
                        "private": [
                            {
                                "addr": "10.10.10.10",
                                "version": 4
                            }
                        ],
                        "public": [
                            {
                                "addr": "4.4.4.4",
                                "version": 4
                            },
                            {
                                "addr": "2001:4800:780e:0510:d87b:9cbc:ff04:"
                                        "513a",
                                "version": 6
                            }
                        ]
                }
        server.adminPass = 'password'
        server.image = {'id': 1}
        server.metadata = {'rackconnect_automation_status': 'DEPLOYED'}
        server.accessIPv4 = "8.8.8.8"

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')
        self.mox.StubOutWithMock(ssh, 'test_connection')

        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.client = self.mox.CreateMockAnything()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.servers.find(id=server.id).AndReturn(server)
        openstack_api_mock.images = self.mox.CreateMockAnything()
        image_mock = self.mox.CreateMockAnything()
        image_mock.metadata = {'os_type': 'linux'}
        openstack_api_mock.images.find(id=1).AndReturn(image_mock)

        context = dict(deployment='DEP', resource='1', roles=['rack_connect'])
        ssh.test_connection(context, "8.8.8.8", "root", timeout=10,
                password=None, identity_file=None, port=22,
                private_key=None).AndReturn(True)

        expected = {
                'instance:1': {
                        'status': 'ACTIVE',
                        'addresses': {
                                'public': [
                                        {'version': 4, 'addr': '4.4.4.4'},
                                        {'version': 6, 'addr': '2001:4800:780e'
                                                ':0510:d87b:9cbc:ff04:513a'}
                                        ],
                                'private': [
                                        {'version': 4, 'addr': '10.10.10.10'}
                                        ]
                                },
                        'ip': '8.8.8.8',
                        'region': 'North',
                        'public_ip': '4.4.4.4',
                        'private_ip': '10.10.10.10',
                        'id': 'fake_server_id'
                    }
            }

        resource_postback.delay(context['deployment'],
                                expected).AndReturn(True)

        self.mox.ReplayAll()
        results = compute.wait_on_build(context, server.id, 'North',
                                        [], api_object=openstack_api_mock)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_wait_on_build(self):
        """ Test that normal wait finishes """

        #Mock server
        server = self.mox.CreateMockAnything()
        server.id = 'fake_server_id'
        server.status = 'ACTIVE'
        server.addresses = {
                        "private": [
                            {
                                "addr": "10.10.10.10",
                                "version": 4
                            }
                        ],
                        "public": [
                            {
                                "addr": "4.4.4.4",
                                "version": 4
                            },
                            {
                                "addr": "2001:4800:780e:0510:d87b:9cbc:ff04:"
                                        "513a",
                                "version": 6
                            }
                        ]
                }
        server.adminPass = 'password'
        server.image = {'id': 1}
        server.metadata = {}
        server.accessIPv4 = "4.4.4.4"

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')
        self.mox.StubOutWithMock(ssh, 'test_connection')

        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.client = self.mox.CreateMockAnything()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.servers.find(id=server.id).AndReturn(server)
        openstack_api_mock.images = self.mox.CreateMockAnything()
        image_mock = self.mox.CreateMockAnything()
        image_mock.metadata = {'os_type': 'linux'}
        openstack_api_mock.images.find(id=1).AndReturn(image_mock)

        context = dict(deployment='DEP', resource='1', roles=[])
        ssh.test_connection(context, "4.4.4.4", "root", timeout=10,
                password=None, identity_file=None, port=22,
                private_key=None).AndReturn(True)

        expected = {
                'instance:1': {
                        'status': 'ACTIVE',
                        'addresses': {
                                'public': [
                                        {'version': 4, 'addr': '4.4.4.4'},
                                        {'version': 6, 'addr': '2001:4800:780e'
                                                ':0510:d87b:9cbc:ff04:513a'}
                                        ],
                                'private': [
                                        {'version': 4, 'addr': '10.10.10.10'}
                                        ]
                                },
                        'ip': '4.4.4.4',
                        'region': 'North',
                        'public_ip': '4.4.4.4',
                        'private_ip': '10.10.10.10',
                        'id': 'fake_server_id'
                    }
            }

        resource_postback.delay(context['deployment'],
                                expected).AndReturn(True)

        self.mox.ReplayAll()
        results = compute.wait_on_build(context, server.id, 'North',
                                        [],api_object=openstack_api_mock)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_delete_server(self):
        """ Test delete server task """
        context = {
            'deployment_id': "1234",
            'resource_key': '1',
            'region': 'ORD',
            'instance_id': 'abcdef-ghig-1234',
            'resource': {
                'index': '1',
                'status': 'ACTIVE',
                'instance': {
                    'id': 'abcdef-ghig-1234'
                },
                'hosts': ['0']
            }
        }
        expect = {
            "instance:1": {
                'status': 'DELETING',
                "statusmsg": "Waiting on resource deletion"
            },
            'instance:0': {
                'status': 'DELETING',
                'statusmsg': 'Host 1 is being deleted.'
            }
        }
        api = self.mox.CreateMockAnything()
        mock_servers = self.mox.CreateMockAnything()
        api.servers = mock_servers
        mock_server = self.mox.CreateMockAnything()
        mock_server.status = 'ACTIVE'
        mock_server.delete().AndReturn(True)
        mock_servers.find(id='abcdef-ghig-1234').AndReturn(mock_server)
        self.mox.ReplayAll()
        ret = delete_server_task(context, api=api)
        self.assertDictEqual(expect, ret)
        self.mox.VerifyAll()

    def test_wait_on_delete(self):
        """ Test wait on delete server task """
        context = {
            'deployment_id': "1234",
            'resource_key': '1',
            'region': 'ORD',
            'instance_id': 'abcdef-ghig-1234',
            'resource': {
                'index': '1',
                'status': 'DELETING',
                'instance': {
                    'id': 'abcdef-ghig-1234'
                },
                'hosts': ['0']
            }
        }
        expect = {
            "instance:1": {
                'status': 'DELETED'
            },
            'instance:0': {
                'status': 'DELETED',
                'statusmsg': 'Host 1 was deleted'
            }
        }
        api = self.mox.CreateMockAnything()
        mock_servers = self.mox.CreateMockAnything()
        api.servers = mock_servers
        mock_server = self.mox.CreateMockAnything()
        mock_server.status = 'DELETED'
        mock_servers.find(id='abcdef-ghig-1234').AndReturn(mock_server)
        self.mox.ReplayAll()
        ret = wait_on_delete_server(context, api=api)
        self.assertDictEqual(expect, ret)
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
        deployment = self.mox.CreateMockAnything()
        deployment['id'].AndReturn('Mock')
        context = RequestContext()
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
    # Run tests. Handle our parameters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
