#!/usr/bin/env python
import json
import logging
import os
import unittest2 as unittest

import mox
from mox import IgnoreArg

from checkmate import ssh
from checkmate import test
from checkmate.deployments import resource_postback
from checkmate.deployments.tasks import reset_failed_resource_task
from checkmate.exceptions import CheckmateException
from checkmate.middleware import RequestContext
from checkmate.providers.rackspace import compute
from checkmate.providers.rackspace.compute import (
    delete_server_task,
    wait_on_delete_server,
    _on_failure
)

LOG = logging.getLogger(__name__)


class TestNovaCompute(test.ProviderTester):
    """ Test Nova Compute Provider """
    klass = compute.Provider

    def test_provider(self):
        provider = compute.Provider({})
        self.assertEqual(provider.key, 'rackspace.nova')

    def test_create_server(self):
        provider = compute.Provider({})

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

        context = {
            'deployment': 'DEP',
            'resource': '1',
            'tenant': 'TMOCK',
            'base_url': 'http://MOCK'
        }
        self.mox.StubOutWithMock(reset_failed_resource_task, 'delay')
        reset_failed_resource_task.delay(context['deployment'],
                                          context['resource'])

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
        openstack_api_mock.servers.create(
            'fake_server',
            image,
            flavor,
            files=None,
            meta={
                'RAX-CHECKMATE':
                'http://MOCK/TMOCK/deployments/DEP/resources/1'
            }
        ).AndReturn(server)
        openstack_api_mock.client.region_name = "NORTH"

        expected = {
            'instance:1': {
                'status': 'NEW',
                'id': server.id,
                'password': server.adminPass,
                'region': "NORTH",
                'flavor': flavor.id,
                'image': image.id,
            }
        }

        resource_postback.delay(context['deployment'],
                                expected).AndReturn(True)

        self.mox.ReplayAll()
        results = compute.create_server(context, 'fake_server', "North",
                                        api_object=openstack_api_mock,
                                        flavor='2', files=None,
                                        image=compute.UBUNTU_12_04_IMAGE_ID,
                                        tags=provider.generate_resource_tag(
                                            context['base_url'],
                                            context['tenant'],
                                            context['deployment'],
                                            context['resource']
                                        ))

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_on_failure(self):
        """
        Test create servrer on failure postback data
        """

        exc = self.mox.CreateMockAnything()
        exc.message = "some message"
        task_id = "1234"
        args = [{
                'deployment_id': '4321',
                'resource_key': '0'
                }]
        kwargs = {}
        einfo = self.mox.CreateMockAnything()
        einfo.traceback = "some traceback"

        #Stub out postback call
        self.mox.StubOutWithMock(resource_postback, 'delay')

        expected = {
            "instance:0": {
                'status': 'ERROR',
                'status-message': (
                    "Unexpected error deleting compute "
                    "instance 0: some message"
                ),
                'trace': 'Task 1234: some traceback'
            }
        }

        resource_postback.delay("4321", expected).AndReturn(True)
        self.mox.ReplayAll()
        _on_failure(exc, task_id, args, kwargs, einfo, "deleting", "method")
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
                          server.id, 'North', [],
                          api_object=openstack_api_mock)

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
        results = compute.wait_on_build(
            context, server.id, 'North', [], api_object=openstack_api_mock)

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
        results = compute.wait_on_build(
            context, server.id, 'North', [], api_object=openstack_api_mock)

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
                "status-message": "Waiting on resource deletion"
            },
            'instance:0': {
                'status': 'DELETING',
                'status-message': 'Host 1 is being deleted.'
            }
        }
        api = self.mox.CreateMockAnything()
        mock_servers = self.mox.CreateMockAnything()
        api.servers = mock_servers
        mock_server = self.mox.CreateMockAnything()
        mock_server.status = 'ACTIVE'
        mock_server.delete().AndReturn(True)
        mock_servers.get('abcdef-ghig-1234').AndReturn(mock_server)
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
                'status-message': 'Host 1 was deleted'
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

    def test_find_url(self):
        path = os.path.join(os.path.dirname(__file__),
                            'test_compute_nova_auth_response.json')
        with file(path, 'r') as _file:
            catalog = json.load(_file)['access']['serviceCatalog']
        self.assertEqual(compute.Provider.find_url(catalog, 'North'),
                         'https://10.1.1.1/v2/T1000')

    def test_find_a_region(self):
        path = os.path.join(os.path.dirname(__file__),
                            'test_compute_nova_auth_response.json')
        with file(path, 'r') as _file:
            catalog = json.load(_file)['access']['serviceCatalog']
        self.assertEqual(compute.Provider.find_a_region(catalog), 'North')

    def test_compute_sync_resource_task(self):
        """Tests compute sync_resource_task via mox"""
        #Mock server
        server = self.mox.CreateMockAnything()
        server.id = 'fake_server_id'
        server.status = "ERROR"

        resource_key = "0"

        context = {
            'deployment': 'DEP',
            'resource': '0',
            'tenant': 'TMOCK',
            'base_url': 'http://MOCK'
        }

        resource = {
            'name': 'svr11.checkmate.local',
            'provider': 'compute',
            'status': 'ERROR',
            'instance': {'id': 'fake_server_id'}
        }

        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.servers = self.mox.CreateMockAnything()

        openstack_api_mock.servers.get(server.id).AndReturn(server)

        expected = {'instance:0': {"status": "ERROR"}}

        self.mox.ReplayAll()
        results = compute.sync_resource_task(context, resource, resource_key,
                                             openstack_api_mock)

        self.assertDictEqual(results, expected)

    def verify_limits(self, cores_used, ram_used):
        """Test the verify_limits() method"""
        context = RequestContext()
        resources = [
            {'component': 'linux_instance',
             'dns-name': 'master.wordpress.cldsrvr.com',
             'flavor': '3',
             'hosts': ['1'],
             'image': 'e4dbdba7-b2a4-4ee5-8e8f-4595b6d694ce',
             'index': '2',
             'instance': {},
             'provider': 'nova',
             'region': 'ORD',
             'service': 'master',
             'status': 'NEW',
             'type': 'compute'}
        ]
        flavors = {
            'flavors': {
                '3': {'cores': 1,
                      'disk': 40,
                      'memory': 1024,
                      'name': u'1GB Standard Instance'},
            }
        }
        limits = {'maxTotalCores': 10,
                  'maxTotalRAMSize': 66560,
                  'totalCoresUsed': cores_used,
                  'totalRAMUsed': ram_used}
        url = "https://dfw.servers.api.rackspacecloud.com/v2/680640"
        self.mox.StubOutWithMock(compute, '_get_flavors')
        self.mox.StubOutWithMock(compute, '_get_limits')
        self.mox.StubOutWithMock(compute.Provider, 'find_url')
        self.mox.StubOutWithMock(compute.Provider, 'find_a_region')
        compute._get_flavors(IgnoreArg(), IgnoreArg()).AndReturn(flavors)
        compute._get_limits(IgnoreArg(), IgnoreArg()).AndReturn(limits)
        compute.Provider.find_url(IgnoreArg(), IgnoreArg()).AndReturn(url)
        compute.Provider.find_a_region(IgnoreArg()).AndReturn('DFW')
        self.mox.ReplayAll()
        provider = compute.Provider({})
        result = provider.verify_limits(context, resources)
        self.mox.VerifyAll()
        return result

    def test_verify_limits_negative(self):
        """Test that verify_limits() returns warnings if limits are not okay"""
        result = self.verify_limits(15, 1000)
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")
        self.mox.UnsetStubs()
        result = self.verify_limits(5, 100000)
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")
        self.mox.UnsetStubs()
        result = self.verify_limits(15, 100000)
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")

    def test_verify_limits_positive(self):
        """Test that verify_limits() returns no results if limits are okay"""
        result = self.verify_limits(5, 1000)
        self.assertEqual(result, [])
        self.mox.UnsetStubs()
        result = self.verify_limits(0, 0)
        self.assertEqual(result, [])

    def test_verify_access_positive(self):
        """Test that verify_access() returns ACCESS-OK if user has access"""
        context = RequestContext()
        context.roles = 'identity:user-admin'
        provider = compute.Provider({})
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'nova:admin'
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')
        context.roles = 'nova:creator'
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'ACCESS-OK')

    def test_verify_access_negative(self):
        """Test that verify_access() returns ACCESS-OK if user has access"""
        context = RequestContext()
        context.roles = 'nova:observer'
        provider = compute.Provider({})
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'NO-ACCESS')


class TestNovaGenerateTemplate(unittest.TestCase):
    """Test Nova Compute Provider's region functions"""

    def setUp(self):
        self.mox = mox.Mox()
        self.deployment = self.mox.CreateMockAnything()
        self.deployment.get_setting('domain', default='checkmate.local',
                                    provider_key='rackspace.nova',
                                    resource_type='compute',
                                    service_name='master').AndReturn("domain")
        self.deployment._constrained_to_one('master').AndReturn(True)

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
        context = RequestContext()
        RackspaceComputeProviderBase.generate_template.AndReturn(True)

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')

        self.deployment.get_setting('region', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key).AndReturn('ORD')
        self.deployment.get_setting('os', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key,
                                    default="Ubuntu 12.04") \
            .AndReturn("Ubuntu 12.04")
        self.deployment.get_setting('memory', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key, default=512) \
            .AndReturn('512')

        expected = [{
            'instance': {},
            'dns-name': 'master.domain',
            'type': 'compute',
            'provider': provider.key,
            'flavor': '2',
            'service': 'master',
            'image': compute.UBUNTU_12_04_IMAGE_ID,
            'region': 'ORD'
        }]

        provider.get_catalog(context).AndReturn(catalog)

        self.mox.ReplayAll()
        results = provider.generate_template(self.deployment, 'compute',
                                             'master',
                                             context, 1, provider.key, None)

        self.assertListEqual(results, expected)
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

        context = RequestContext()

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')

        self.deployment.get_setting(
            'region', resource_type='compute',
            service_name='master', provider_key=provider.key
        ).AndReturn('dallas')
        self.deployment.get_setting('os', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key,
                                    default="Ubuntu 12.04") \
            .AndReturn("Ubuntu 12.04")
        self.deployment.get_setting('memory', resource_type='compute',
                                    service_name='master',
                                    provider_key=provider.key, default=512) \
            .AndReturn('512')

        provider.get_catalog(context).AndReturn(catalog)

        self.mox.ReplayAll()
        try:
            provider.generate_template(self.deployment, 'compute',
                                       'master', context, 1, provider.key,
                                       None)
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
