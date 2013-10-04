# pylint: disable=C0103,C0302,E1101,E1103,R0904,R0201,W0212,W0613

# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Tests for Rackspace Nova compute provider."""
import copy
import json
import logging
import os
import unittest

import mock
import mox
import requests

from checkmate import deployments as cm_deps
from checkmate import exceptions
from checkmate import middleware as cm_mid
from checkmate.providers.rackspace import compute
from checkmate import rdp
from checkmate import ssh
from checkmate import test

LOG = logging.getLogger(__name__)


class TestNovaCompute(test.ProviderTester):
    klass = compute.Provider

    def test_provider(self):
        provider = compute.Provider({})
        self.assertEqual(provider.key, 'rackspace.nova')

    def test_create_server(self):
        provider = compute.Provider({})
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
        image.id = '00000000-0000-0000-0000-000000000000'

        #Mock flavor
        flavor = self.mox.CreateMockAnything()
        flavor.id = '2'

        context = {
            'deployment_id': 'DEP',
            'resource_key': '1',
            'tenant': 'TMOCK',
            'base_url': 'http://MOCK',
            'resource': {
                'index': '1',
                'instance': {},
                'desired-state': {
                    'flavor': flavor.id,
                    'image': image.id,
                },
            },
        }

        #Stub out postback call
        self.mox.StubOutWithMock(cm_deps.resource_postback, 'delay')

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
            },
            disk_config='AUTO'
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
                'error-message': '',
                'status-message': ''
            },
            'resources': {
                '1': {
                    'index': '1',
                    'instance': {},
                    'desired-state': {
                        'flavor': flavor.id,
                        'image': image.id,
                    },
                },
            },
        }

        cm_deps.resource_postback.delay(context['deployment_id'],
                                        expected).AndReturn(True)

        self.mox.ReplayAll()
        results = compute.create_server(context, 'fake_server', "North",
                                        api=openstack_api_mock,
                                        flavor='2', files=None,
                                        image=image.id,
                                        tags=provider.generate_resource_tag(
                                            context['base_url'],
                                            context['tenant'],
                                            context['deployment_id'],
                                            context['resource_key']
                                        ))

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    @mock.patch('checkmate.providers.rackspace.compute.utils')
    def test_create_server_connect_error(self, mock_utils):
        mock_image = mock.Mock()
        mock_image.name = 'image'
        mock_flavor = mock.Mock()
        mock_flavor.name = 'flavor'
        compute.LOG.error = mock.Mock()
        mock_api_obj = mock.Mock()
        mock_api_obj.client.management_url = 'http://test/'
        mock_api_obj.flavors.find.return_value = mock_flavor
        mock_api_obj.images.find.return_value = mock_image
        mock_api_obj.servers.create = mock.MagicMock(
            side_effect=requests.ConnectionError)

        with self.assertRaises(requests.ConnectionError):
            compute.create_server({'deployment_id': '1', 'resource_key': '1'},
                                  None, None, api=mock_api_obj)

        compute.LOG.error.assert_called_with(
            'Connection error talking to http://test/ endpoint', exc_info=True)

    @mock.patch.object(compute.LOG, 'error')
    @mock.patch.object(compute.cmdeps.resource_postback, 'delay')
    def test_create_server_images_connect_error(self, mock_postback,
                                                mock_logger):
        mock_api_obj = mock.Mock()
        mock_api_obj.client.management_url = "test.local"
        mock_exception = requests.ConnectionError()
        mock_api_obj.images.find = mock.MagicMock(
            side_effect=mock_exception)

        with self.assertRaises(requests.ConnectionError):
            compute.create_server({'deployment_id': '1', 'resource_key': '1'},
                                  None, None, api=mock_api_obj)
        mock_logger.assert_called_with('Connection error talking to '
                                       'test.local endpoint', exc_info=True)

    def test_on_failure(self):
        exc = self.mox.CreateMockAnything()
        exc.__str__().AndReturn('some message')
        task_id = "1234"
        args = [{
                'deployment_id': '4321',
                'resource_key': '0'
                }]
        kwargs = {}
        einfo = self.mox.CreateMockAnything()

        #Stub out postback call
        self.mox.StubOutWithMock(cm_deps.resource_postback, 'delay')

        expected = {
            "instance:0": {
                'status': 'ERROR',
                'status-message': (
                    "Unexpected error deleting compute "
                    "instance 0"
                ),
                'error-message': 'some message',
            }
        }

        cm_deps.resource_postback.delay("4321", expected).AndReturn(True)
        self.mox.ReplayAll()
        compute._on_failure(
            exc, task_id, args, kwargs, einfo, "deleting", "method")
        self.mox.VerifyAll()

    def test_wait_on_build_rackconnect_pending(self):
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
        self.mox.StubOutWithMock(cm_deps.resource_postback, 'delay')
        self.mox.StubOutWithMock(ssh, 'test_connection')

        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.client = self.mox.CreateMockAnything()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.servers.find(id=server.id).AndReturn(server)

        context = dict(deployment_id='DEP', resource_key='1',
                       roles=['rack_connect'])
        ssh.test_connection(context, "4.4.4.4", "root", timeout=10,
                            password=None, identity_file=None, port=22,
                            private_key=None).AndReturn(True)
        cm_deps.resource_postback.delay(context['deployment_id'],
                                        mox.IgnoreArg()).AndReturn(True)

        self.mox.ReplayAll()
        self.assertRaises(exceptions.CheckmateException,
                          compute.wait_on_build, context,
                          server.id, 'North', [],
                          api_object=openstack_api_mock)

    def test_wait_on_build_rackconnect_ready(self):
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
        self.mox.StubOutWithMock(cm_deps.resource_postback, 'delay')

        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.client = self.mox.CreateMockAnything()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.servers.find(id=server.id).AndReturn(server)

        context = dict(deployment_id='DEP', resource_key='1',
                       roles=['rack_connect'])

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
                    ],
                },
                'ip': '8.8.8.8',
                'region': 'North',
                'public_ip': '4.4.4.4',
                'private_ip': '10.10.10.10',
                'id': 'fake_server_id',
                'status-message': '',
                'rackconnect-automation-status': 'DEPLOYED'
            }
        }

        cm_deps.resource_postback.delay(context['deployment_id'],
                                        expected).AndReturn(True)

        self.mox.ReplayAll()
        results = compute.wait_on_build(context, server.id, 'North',
                                        api=openstack_api_mock)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_wait_on_build_rackconnect_failed(self):
        server = self.mox.CreateMockAnything()
        server.id = 'fake_server_id'
        server.status = 'ACTIVE'
        server.addresses = {
            "private": [
                {
                    "addr": "10.10.10.10",
                    "version": 4
                }],
            "public": [
                {
                    "addr": "4.4.4.4",
                    "version": 4
                },
                {
                    "addr": "2001:4800:780e:0510:d87b:9cbc:ff04:513a",
                    "version": 6
                }]}
        server.adminPass = 'password'
        server.image = {'id': 1}
        server.metadata = {'rackconnect_automation_status': 'FAILED'}
        server.accessIPv4 = "8.8.8.8"

        #Stub out postback call
        self.mox.StubOutWithMock(cm_deps.resource_postback, 'delay')

        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.client = self.mox.CreateMockAnything()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.servers.find(id=server.id).AndReturn(server)

        context = dict(deployment_id='DEP', resource_key='1',
                       roles=['rack_connect'])

        expected = {
            'instance:1': {
                'status': 'ERROR',
                'addresses': {
                    'public': [
                        {
                            'version': 4,
                            'addr': '4.4.4.4'
                        },
                        {
                            'version': 6,
                            'addr': '2001:4800:780e:0510:d87b:9cbc:ff04:513a'
                        }
                    ],
                    'private': [
                        {
                            'version': 4,
                            'addr': '10.10.10.10'
                        }
                    ],
                },
                'region': 'North',
                'id': 'fake_server_id',
                'status-message': "Rackconnect server metadata has "
                                  "'rackconnect_automation_status' set to "
                                  "FAILED.",
                'rackconnect-automation-status': 'FAILED'
            }
        }

        cm_deps.resource_postback.delay(context['deployment_id'],
                                        expected).AndReturn(True)
        self.mox.ReplayAll()
        try:
            compute.wait_on_build(context, server.id, 'North',
                                  api_object=openstack_api_mock)
            self.fail("Should have thrown a Checkmate Exception!")
        except exceptions.CheckmateException:
            self.mox.VerifyAll()

    def test_wait_on_build_rackconnect_unprocessed(self):
        server = self.mox.CreateMockAnything()
        server.id = 'fake_server_id'
        server.status = 'ACTIVE'
        server.addresses = {
            "private": [
                {
                    "addr": "10.10.10.10",
                    "version": 4
                }],
            "public": [
                {
                    "addr": "4.4.4.4",
                    "version": 4
                },
                {
                    "addr": "2001:4800:780e:0510:d87b:9cbc:ff04:513a",
                    "version": 6
                }]}
        server.adminPass = 'password'
        server.image = {'id': 1}
        server.metadata = {'rackconnect_automation_status': 'UNPROCESSABLE'}
        server.accessIPv4 = "8.8.8.8"

        #Stub out postback call
        self.mox.StubOutWithMock(cm_deps.resource_postback, 'delay')

        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.client = self.mox.CreateMockAnything()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.servers.find(id=server.id).AndReturn(server)

        context = dict(deployment_id='DEP',
                       resource_key='1',
                       roles=['rack_connect'])

        expected = {
            'instance:1': {
                'status': 'ACTIVE',
                'addresses': {
                    'public': [
                        {
                            'version': 4,
                            'addr': '4.4.4.4'
                        },
                        {
                            'version': 6,
                            'addr': '2001:4800:780e:0510:d87b:9cbc:ff04:513a'
                        }
                    ],
                    'private': [
                        {
                            'version': 4,
                            'addr': '10.10.10.10'
                        }]
                },
                'ip': '8.8.8.8',
                'region': 'North',
                'public_ip': '4.4.4.4',
                'private_ip': '10.10.10.10',
                'id': 'fake_server_id',
                'status-message': '',
                'rackconnect-automation-status': 'UNPROCESSABLE'
            }
        }

        cm_deps.resource_postback.delay(context['deployment_id'],
                                        expected).AndReturn(True)
        self.mox.ReplayAll()
        results = compute.wait_on_build(context, server.id,
                                        'North',
                                        api_object=openstack_api_mock)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_wait_on_build(self):
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
        self.mox.StubOutWithMock(cm_deps.resource_postback, 'delay')

        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.client = self.mox.CreateMockAnything()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.servers.find(id=server.id).AndReturn(server)
        openstack_api_mock.images = self.mox.CreateMockAnything()

        context = dict(deployment_id='DEP', resource_key='1', roles=[])

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
                'id': 'fake_server_id',
                'status-message': ''
            }
        }

        cm_deps.resource_postback.delay(context['deployment_id'],
                                        expected).AndReturn(True)

        self.mox.ReplayAll()
        results = compute.wait_on_build(
            context, server.id, 'North', api=openstack_api_mock)

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

    def test_verify_ssh_connection_for_linux(self):
        server = self.mox.CreateMockAnything()
        server.image = {'id': 1}

        #Stub out postback call
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

        context = dict(deployment_id='DEP', resource_key='1')
        ssh.test_connection(context, "4.4.4.4", "root", timeout=10,
                            password=None, identity_file=None, port=22,
                            private_key=None).AndReturn(True)

        self.mox.ReplayAll()
        compute.verify_ssh_connection(context, server.id, 'North', "4.4.4.4",
                                      api_object=openstack_api_mock)
        self.mox.VerifyAll()

    def test_verify_ssh_connection_for_windows(self):
        server = self.mox.CreateMockAnything()
        server.image = {'id': 1}

        #Stub out postback call
        self.mox.StubOutWithMock(rdp, 'test_connection')

        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.client = self.mox.CreateMockAnything()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.servers.find(id=server.id).AndReturn(server)
        openstack_api_mock.images = self.mox.CreateMockAnything()
        image_mock = self.mox.CreateMockAnything()
        image_mock.name = "windows"
        image_mock.metadata = {'os_type': 'windows'}
        openstack_api_mock.images.find(id=1).AndReturn(image_mock)

        context = dict(deployment_id='DEP', resource_key='1')
        rdp.test_connection(context, "4.4.4.4", timeout=10,).AndReturn(True)

        self.mox.ReplayAll()
        compute.verify_ssh_connection(context, server.id, 'North', "4.4.4.4",
                                      api_object=openstack_api_mock)
        self.mox.VerifyAll()

    def test_wait_on_build_connect_error(self):
        server = self.mox.CreateMockAnything()
        server.id = 'fake_server_id'
        #Create appropriate api mocks
        openstack_api_mock = self.mox.CreateMockAnything()
        openstack_api_mock.client = self.mox.CreateMockAnything()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = self.mox.CreateMockAnything()
        openstack_api_mock.servers.find(id=server.id).AndRaise(
            requests.ConnectionError("Mock connection error"))

        context = dict(deployment_id='DEP', resource_key='1', roles=[])

        self.mox.ReplayAll()
        with self.assertRaises(requests.ConnectionError):
            compute.wait_on_build(
                context, server.id, 'North', [], api=openstack_api_mock)

        self.mox.VerifyAll()

    def test_delete_server(self):
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
        self.mox.StubOutWithMock(compute.cmdeps.resource_postback, 'delay')
        compute.cmdeps.resource_postback.delay('1234', expect).AndReturn(None)
        self.mox.ReplayAll()
        ret = compute.delete_server_task(context, api=api)
        self.assertDictEqual(expect, ret)
        self.mox.VerifyAll()

    @mock.patch('checkmate.providers.rackspace.compute.utils')
    @mock.patch('checkmate.providers.rackspace.compute.cmdeps')
    def test_delete_server_get_connect_error(self, mock_cmdeps, mock_utils):
        mock_context = {'deployment_id': '1', 'resource_key': '1',
                        'region': 'ORD', 'resource': {}, 'instance_id': '1'}
        compute.LOG.error = mock.Mock()
        mock_api = mock.Mock()
        mock_api.client.management_url = 'http://test/'
        mock_api.servers.get = mock.MagicMock(
            side_effect=requests.ConnectionError)

        with self.assertRaises(requests.ConnectionError):
            compute.delete_server_task(mock_context, api=mock_api)

        compute.LOG.error.assert_called_with(
            'Connection error talking to http://test/ endpoint', exc_info=True)

    @mock.patch('checkmate.providers.rackspace.compute.utils')
    @mock.patch('checkmate.providers.rackspace.compute.cmdeps')
    def test_delete_server_delete_connect_error(self, mock_cmdeps, mock_utils):
        mock_context = {'deployment_id': '1', 'resource_key': '1',
                        'region': 'ORD', 'resource': {}, 'instance_id': '1'}
        compute.LOG.error = mock.Mock()
        mock_api = mock.Mock()
        mock_api.client.management_url = 'http://test/'
        mock_api.servers.get = mock.MagicMock(
            side_effect=requests.ConnectionError)

        with self.assertRaises(requests.ConnectionError):
            compute.delete_server_task(mock_context, api=mock_api)

        compute.LOG.error.assert_called_with(
            'Connection error talking to http://test/ endpoint', exc_info=True)

    def test_wait_on_delete(self):
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
                'status': 'DELETED',
                'status-message': ''
            },
            'instance:0': {
                'status': 'DELETED',
                'status-message': ''
            }
        }
        api = self.mox.CreateMockAnything()
        mock_servers = self.mox.CreateMockAnything()
        api.servers = mock_servers
        mock_server = self.mox.CreateMockAnything()
        mock_server.status = 'DELETED'
        mock_servers.find(id='abcdef-ghig-1234').AndReturn(mock_server)
        self.mox.StubOutWithMock(compute.cmdeps.resource_postback, 'delay')
        compute.cmdeps.resource_postback.delay('1234', expect).AndReturn(None)
        self.mox.ReplayAll()
        ret = compute.wait_on_delete_server(context, api=api)
        self.assertDictEqual(expect, ret)
        self.mox.VerifyAll()

    @mock.patch('checkmate.providers.rackspace.compute.utils')
    @mock.patch('checkmate.providers.rackspace.compute.cmdeps')
    def test_wait_on_delete_connect_error(self, mock_cmdeps, mock_utils):
        mock_context = {'deployment_id': '1', 'resource_key': '1',
                        'region': 'ORD', 'resource': {}, 'instance_id': '1'}
        compute.LOG.error = mock.Mock()
        mock_api = mock.Mock()
        mock_api.client.management_url = 'http://test/'
        mock_api.servers.find = mock.MagicMock(
            side_effect=requests.ConnectionError)

        with self.assertRaises(requests.ConnectionError):
            compute.wait_on_delete_server(mock_context, api=mock_api)

        compute.LOG.error.assert_called_with(
            'Connection error talking to http://test/ endpoint', exc_info=True)

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
        server = mock.Mock()
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

        openstack_api_mock = mock.Mock()
        openstack_api_mock.servers = mock.Mock()

        openstack_api_mock.servers.get.return_value = server

        expected = {'instance:0': {"status": "ERROR"}}

        results = compute.sync_resource_task(context, resource, resource_key,
                                             openstack_api_mock)

        openstack_api_mock.servers.get.assert_called_once_with(server.id)
        self.assertDictEqual(results, expected)

    def test_compute_sync_resource_task_adds_checkmate_metadata(self):
        server = mock.Mock()
        server.id = 'fake_server_id'
        server.status = "status"
        server.metadata = {}

        resource_key = "0"

        context = {
            'deployment': 'DEP',
            'resource': '0',
            'tenant': 'TMOCK',
            'base_url': 'http://MOCK'
        }

        resource = {
            'index': '0',
            'name': 'svr11.checkmate.local',
            'provider': 'compute',
            'status': 'ERROR',
            'instance': {'id': 'fake_server_id'}
        }

        openstack_api_mock = mock.Mock()
        openstack_api_mock.servers = mock.Mock()

        openstack_api_mock.servers.get.return_value = server

        with mock.patch.object(compute.Provider,
                               'generate_resource_tag',
                               return_value={"test": "me"}):
            compute.sync_resource_task(context, resource, resource_key,
                                       openstack_api_mock)

        server.manager.set_meta.assert_called_once_with(server, {"test": "me"})

    def verify_limits(self, cores_used, ram_used):
        """Helper method to validate constraints."""
        context = cm_mid.RequestContext()
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
        compute._get_flavors(
            mox.IgnoreArg(), mox.IgnoreArg()).AndReturn(flavors)
        compute._get_limits(mox.IgnoreArg(), mox.IgnoreArg()).AndReturn(limits)
        compute.Provider.find_url(
            mox.IgnoreArg(), mox.IgnoreArg()).AndReturn(url)
        compute.Provider.find_a_region(mox.IgnoreArg()).AndReturn('DFW')
        self.mox.ReplayAll()
        provider = compute.Provider({})
        result = provider.verify_limits(context, resources)
        self.mox.VerifyAll()
        return result

    def test_verify_limits_negative(self):
        result = self.verify_limits(15, 1000)
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")
        self.mox.UnsetStubs()
        result = self.verify_limits(5, 100000)
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")
        self.mox.UnsetStubs()
        result = self.verify_limits(15, 100000)
        self.assertEqual(result[0]['type'], "INSUFFICIENT-CAPACITY")

    def test_verify_limits_positive(self):
        result = self.verify_limits(5, 1000)
        self.assertEqual(result, [])
        self.mox.UnsetStubs()
        result = self.verify_limits(0, 0)
        self.assertEqual(result, [])

    def test_verify_access_positive(self):
        context = cm_mid.RequestContext()
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
        context = cm_mid.RequestContext()
        context.roles = 'nova:observer'
        provider = compute.Provider({})
        result = provider.verify_access(context)
        self.assertEqual(result['type'], 'NO-ACCESS')


class TestNovaGenerateTemplate(unittest.TestCase):
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
                    '00000000-0000-0000-0000-000000000000': {
                        'os': 'Ubuntu 12.04',
                        'name': 'Ubuntu 12.04 LTS',
                        'type': 'linux',
                    }
                },
                'regions': {
                    'ORD': 'http://some.endpoint'
                }
            }
        }
        provider = compute.Provider({})

        #Mock Base Provider, context and deployment
        mock_rs_compute_provider_base = self.mox.CreateMockAnything()
        context = cm_mid.RequestContext()
        context2 = cm_mid.RequestContext(region='ORD')
        mock_rs_compute_provider_base.generate_template.AndReturn(True)

        #Stub out provider calls
        self.mox.StubOutWithMock(copy, 'deepcopy')
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
            'image': '00000000-0000-0000-0000-000000000000',
            'region': 'ORD',
            'desired-state': {
                'region': 'ORD',
                'flavor': '2',
                'image': '00000000-0000-0000-0000-000000000000',
                'os-type': 'linux',
                'os': 'Ubuntu 12.04',
            }
        }]

        copy.deepcopy(context).AndReturn(context2)
        provider.get_catalog(context2).AndReturn(catalog)

        self.mox.ReplayAll()
        results = provider.generate_template(self.deployment, 'compute',
                                             'master',
                                             context, 1, provider.key, None)

        self.assertListEqual(results, expected)
        self.mox.VerifyAll()

    def test_catalog_and_deployment_diff(self):
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
                    '00000000-0000-0000-0000-000000000000': {
                        'os': 'Ubuntu 12.04',
                        'name': 'Ubuntu 12.04 LTS',
                        'type': 'linux',
                    }
                }
            }
        }
        provider = compute.Provider({})

        context = cm_mid.RequestContext()
        context2 = cm_mid.RequestContext(**{'region': 'ORD'})

        #Stub out provider calls
        self.mox.StubOutWithMock(provider, 'get_catalog')
        self.mox.StubOutWithMock(copy, 'deepcopy')
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

        copy.deepcopy(context).AndReturn(context2)
        provider.get_catalog(context2).AndReturn(catalog)

        self.mox.ReplayAll()
        try:
            provider.generate_template(self.deployment, 'compute',
                                       'master', context, 1, provider.key,
                                       None)
        except exceptions.CheckmateException:
            #pass
            self.mox.VerifyAll()


class TestNovaProxy(unittest.TestCase):
    @mock.patch('checkmate.providers.rackspace.compute.utils')
    @mock.patch('checkmate.providers.rackspace.compute.pyrax')
    def test_get_resources_returns_compute_instances(self, mock_pyrax,
                                                     mock_utils):
        request = mock.Mock()
        server = mock.Mock()
        server.name = 'server_name'
        server.status = 'server_status'
        server.flavor = {'id': 'server_flavor'}
        server.image = {'id': 'server_image'}
        server.manager.api.client.region_name = 'region_name'
        server.metadata = {}

        servers_response = mock.Mock()
        servers_response.list.return_value = [server]
        mock_pyrax.connect_to_cloudservers.return_value = servers_response
        mock_pyrax.regions = ["ORD"]

        result = compute.Provider.get_resources(request, 'tenant')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['dns-name'], 'server_name')
        self.assertEqual(result[0]['status'], 'server_status')
        self.assertEqual(result[0]['flavor'], 'server_flavor')
        self.assertEqual(result[0]['image'], 'server_image')
        self.assertEqual(result[0]['region'], 'region_name')

    @mock.patch(
        'checkmate.providers.rackspace.compute.utils.get_ips_from_server')
    @mock.patch('checkmate.providers.rackspace.compute.pyrax')
    def test_get_resources_merges_ip_info(self, mock_pyrax, mock_get_ips):
        request = mock.Mock()
        server = mock.Mock()
        server.image = {'id': None}
        server.flavor = {'id': None}
        server.metadata = {}

        servers_response = mock.Mock()
        servers_response.list.return_value = [server]
        mock_pyrax.connect_to_cloudservers.return_value = servers_response
        mock_pyrax.regions = ["DFW"]
        mock_get_ips.return_value = {'ip': '1.1.1.1',
                                     'public_ip': '2.2.2.2',
                                     'private_ip': '3.3.3.3'}
        self.assertEqual(
            compute.Provider.get_resources(request,
                                           'tenant')[0]['instance']['ip'],
            '1.1.1.1'
        )

        self.assertEqual(
            compute.Provider.get_resources(
                request,
                'tenant')[0]['instance']['public_ip'],
            '2.2.2.2'
        )

        self.assertEqual(
            compute.Provider.get_resources(
                request,
                'tenant')[0]['instance']['private_ip'],
            '3.3.3.3'
        )

    @mock.patch(
        'checkmate.providers.rackspace.compute.utils.get_ips_from_server')
    @mock.patch('checkmate.providers.rackspace.compute.pyrax')
    def test_get_resources_returns_servers_not_in_checkmate(self,
                                                            mock_pyrax,
                                                            mock_get_ips):

        request = mock.Mock()
        server = mock.Mock()
        server.image = {'id': 'gotit'}
        server.flavor = {'id': None}
        server.metadata = {}

        server_in_checkmate = mock.Mock(metadata={'RAX-CHECKMATE': 'yeah'})
        mock_get_ips.return_value = {}

        def fake_connect(**kwargs):
            """Helper method to fake a connect."""
            dfw_mock = mock.Mock(
                list=mock.Mock(return_value=[server, server_in_checkmate])
            )
            empty_servers_mock = mock.Mock(
                list=mock.Mock(return_value=[])
            )
            if kwargs['region'] == 'DFW':
                return dfw_mock
            if kwargs['region'] == 'ORD':
                return empty_servers_mock
            if kwargs['region'] == 'SYD':
                return empty_servers_mock

        mock_pyrax.regions = ["ORD", "DFW", "SYD"]
        mock_pyrax.connect_to_cloudservers.side_effect = fake_connect

        servers_response = mock.Mock()
        servers_response.servers.list.return_value = [server]
        mock_pyrax.connect_to_cloudservers.return_value = servers_response

        result = compute.Provider.get_resources(request, 'tenant')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['image'], 'gotit')


if __name__ == '__main__':
    import sys

    test.run_with_params(sys.argv[:])
