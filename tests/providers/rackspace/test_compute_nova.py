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


class TestOldNovaTasks(unittest.TestCase):

    @mock.patch.object(compute.tasks.create_server, 'delay')
    def test_create_server(self, task):
        mock_api_obj = mock.MagicMock()
        mock_tags = mock.MagicMock()
        mock_image = mock.MagicMock()
        context = {'deployment_id': '1', 'resource_key': '1'}
        compute.create_server(context, "NAME", "ORD",
                              api=mock_api_obj, files={},
                              image=mock_image, tags=mock_tags)
        task.assert_called_once_with(context, "NAME", region="ORD",
                                     api=mock_api_obj, image=mock_image,
                                     flavor='2', files={}, tags=mock_tags)

    @mock.patch.object(compute.tasks.wait_on_build, 'delay')
    def test_wait_on_build(self, task):
        mock_context = mock.MagicMock()
        mock_api = mock.MagicMock()
        compute.wait_on_build(mock_context, "SERVER_ID", region="ORD",
                              ip_address_type="IP_ADDRESS_TYPE",
                              api=mock_api)
        task.assert_called_once_with(mock_context, "SERVER_ID", region="ORD",
                                     ip_address_type='IP_ADDRESS_TYPE',
                                     api=mock_api)

    @mock.patch.object(compute.tasks.verify_ssh_connection, 'delay')
    def test_verify_ssh_connection(self, task):
        mock_context = mock.MagicMock()
        mock_identity_file = mock.MagicMock()
        mock_api = mock.MagicMock()
        private_key = mock.MagicMock()

        compute.verify_ssh_connection(mock_context, "SERVER_ID", "ORD",
                                      "SERVER_IP", username="USERNAME",
                                      timeout=10, password="PASSWORD",
                                      identity_file=mock_identity_file,
                                      api_object=mock_api,
                                      private_key=private_key)
        task.assert_called_once_with(mock_context, "SERVER_ID", "SERVER_IP",
                                     region="ORD", username="USERNAME",
                                     timeout=10, password="PASSWORD",
                                     identity_file=mock_identity_file,
                                     port=22,
                                     api=mock_api, private_key=private_key)

    @mock.patch.object(compute.tasks.delete_server_task, 'delay')
    def test_delete_server_task(self, task):
        mock_context = mock.MagicMock()
        mock_api = mock.MagicMock()

        compute.delete_server_task(mock_context, api=mock_api)
        task.assert_called_once_with(mock_context, api=mock_api)

    @mock.patch.object(compute.tasks.wait_on_delete_server, 'delay')
    def test_wait_on_delete_server_task(self, task):
        mock_context = mock.MagicMock()
        mock_api = mock.MagicMock()

        compute.wait_on_delete_server(mock_context, api=mock_api)
        task.assert_called_once_with(mock_context, api=mock_api)


class TestNovaCompute(test.ProviderTester):
    klass = compute.Provider

    def test_provider(self):
        provider = compute.Provider({})
        self.assertEqual(provider.key, 'rackspace.nova')

    @mock.patch.object(cm_deps.tasks, 'postback')
    def test_create_server(self, postback):
        provider = compute.Provider({})
        server = mock.MagicMock()
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
        image = mock.MagicMock()
        image.id = '00000000-0000-0000-0000-000000000000'

        #Mock flavor
        flavor = mock.MagicMock()
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

        #Create appropriate api mocks
        openstack_api_mock = mock.MagicMock()
        openstack_api_mock.servers = mock.MagicMock()
        openstack_api_mock.images = mock.MagicMock()
        openstack_api_mock.flavors = mock.MagicMock()
        openstack_api_mock.client = mock.MagicMock()

        openstack_api_mock.images.find.return_value = image
        openstack_api_mock.flavors.find.return_value = flavor
        openstack_api_mock.servers.create.return_value = server

        openstack_api_mock.client.region_name = "NORTH"

        expected = {
            'resources': {
                '1': {
                    'status': 'NEW',
                    'instance': {
                        'status': 'NEW',
                        'flavor': flavor.id,
                        'error-message': '',
                        'image': image.id,
                        'region': 'NORTH',
                        'password': server.adminPass,
                        'id': 'fake_server_id',
                        'status-message': ''
                    }
                }
            }
        }

        results = compute.tasks.create_server(context, 'fake_server',
                                              region="North",
                                              api=openstack_api_mock,
                                              flavor='2', files=None,
                                              image=image.id,
                                              tags=
                                              provider.generate_resource_tag(
                                                  context['base_url'],
                                                  context['tenant'],
                                                  context['deployment_id'],
                                                  context['resource_key']))

        self.assertDictEqual(results, expected)
        self.mox.VerifyAll()

        openstack_api_mock.flavors.find.assert_called_once_with(id=flavor.id)
        openstack_api_mock.images.find.assert_called_once_with(id=image.id)
        openstack_api_mock.servers.create.assert_called_once_with(
            'fake_server', image, flavor, files=None,
            meta={
                'RAX-CHECKMATE':
                'http://MOCK/TMOCK/deployments/DEP/resources/1'
            }
        )

        postback.assert_called_once_with('DEP', expected)

    @mock.patch('checkmate.providers.rackspace.compute.utils')
    @mock.patch('checkmate.providers.rackspace.compute.manager.LOG')
    def test_create_server_connect_error(self, log, mock_utils):
        mock_image = mock.Mock()
        mock_image.name = 'image'
        mock_flavor = mock.Mock()
        mock_flavor.name = 'flavor'
        log.error = mock.MagicMock()
        mock_api_obj = mock.Mock()
        mock_api_obj.client.management_url = 'http://test/'
        mock_api_obj.flavors.find.return_value = mock_flavor
        mock_api_obj.images.find.return_value = mock_image
        mock_api_obj.servers.create = mock.MagicMock(
            side_effect=requests.ConnectionError)

        with self.assertRaises(exceptions.CheckmateException):
            compute.tasks.create_server({'deployment_id': '1',
                                         'resource_key': '1'},
                                        "NAME", api=mock_api_obj)

        log.error.assert_called_with(
            'Connection error talking to http://test/ endpoint', exc_info=True)

    @mock.patch.object(compute.manager.LOG, 'error')
    def test_create_server_images_connect_error(self,
                                                mock_logger):
        mock_api_obj = mock.Mock()
        mock_api_obj.client.management_url = "test.local"
        mock_exception = requests.ConnectionError()
        mock_api_obj.images.find = mock.MagicMock(
            side_effect=mock_exception)

        with self.assertRaises(exceptions.CheckmateException):
            compute.tasks.create_server({'deployment_id': '1',
                                         'resource_key': '1'},
                                        "NAME", api=mock_api_obj)
        mock_logger.assert_called_with('Connection error talking to '
                                       'test.local endpoint', exc_info=True)

    @mock.patch.object(cm_deps.tasks, 'postback')
    def test_wait_on_build_rackconnect_pending(self, postback):
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
        self.mox.StubOutWithMock(cm_deps.tasks.resource_postback, 'delay')
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
        cm_deps.tasks.resource_postback.delay(
            context['deployment_id'], mox.IgnoreArg()).AndReturn(True)

        self.mox.ReplayAll()
        self.assertRaises(exceptions.CheckmateException,
                          compute.tasks.wait_on_build, context,
                          server.id,
                          api=openstack_api_mock)

    @mock.patch.object(cm_deps.tasks, 'postback')
    def test_wait_on_build_rackconnect_ready(self, postback):
        server = mock.MagicMock()
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

        #Create appropriate api mocks
        openstack_api_mock = mock.MagicMock()
        openstack_api_mock.client = mock.MagicMock
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = mock.MagicMock()
        openstack_api_mock.servers.find.return_value = server

        context = dict(deployment_id='DEP', resource_key='1',
                       roles=['rack_connect'])

        expected_resources = {
            '1': {
                'status': 'ACTIVE',
                'instance': {
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
                        }],
                    'private': [
                        {
                            'version': 4,
                            'addr': '10.10.10.10'
                        }]},
                    'ip': '8.8.8.8',
                    'region': 'North',
                    'public_ip': '4.4.4.4',
                    'private_ip': '10.10.10.10',
                    'id': 'fake_server_id',
                    'status-message': '',
                    'rackconnect-automation-status': 'DEPLOYED'
                }
            }
        }

        expected = {
            'resources': expected_resources
        }

        results = compute.tasks.wait_on_build(context, server.id,
                                              api=openstack_api_mock)

        self.assertDictEqual(results, expected)
        openstack_api_mock.servers.find.assert_called_once_with(id=server.id)
        postback.assert_called_once_with("DEP", expected)

    @mock.patch.object(cm_deps.tasks, 'postback')
    def test_wait_on_build_rackconnect_failed(self, postback):
        server = mock.MagicMock()
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

        #Create appropriate api mocks
        openstack_api_mock = mock.MagicMock()
        openstack_api_mock.client = mock.MagicMock()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = mock.MagicMock()
        openstack_api_mock.servers.find.return_value = server
        context = dict(deployment_id='DEP', resource_key='1',
                       roles=['rack_connect'])
        expected_resource = {
            'status': 'ERROR',
            'instance': {
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

        try:
            compute.tasks.wait_on_build(context, server.id,
                                        api=openstack_api_mock)
            self.fail("Should have thrown a Checkmate Exception!")
        except exceptions.CheckmateException:
            pass
        postback.assert_called_once_with("DEP",
                                         {"resources": {
                                             "1": expected_resource}})
        openstack_api_mock.servers.find.assert_called_once_with(
            id=server.id)

    @mock.patch.object(cm_deps.tasks, 'postback')
    def test_wait_on_build_rackconnect_unprocessed(self, postback):
        server = mock.MagicMock()
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

        #Create appropriate api mocks
        openstack_api_mock = mock.MagicMock()
        openstack_api_mock.client = mock.MagicMock()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = mock.MagicMock()
        openstack_api_mock.servers.find.return_value = server

        context = dict(deployment_id='DEP',
                       resource_key='1',
                       roles=['rack_connect'])

        expected_resource = {
            'status': 'ACTIVE',
            'instance': {
                'status': 'ACTIVE',
                'addresses': {
                    'public': [
                        {
                            'version': 4,
                            'addr': '4.4.4.4'
                        },
                        {
                            'version': 6,
                            'addr': '2001:4800:780e:0510'
                                    ':d87b:9cbc:ff04:513a'
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

        expected_result = {'resources': {'1': expected_resource}}

        results = compute.tasks.wait_on_build(context, server.id,
                                              api=openstack_api_mock)

        self.assertDictEqual(results, expected_result)
        postback.assert_called_once_with("DEP", expected_result)
        openstack_api_mock.servers.find.assert_called_once_with(id=server.id)

    @mock.patch.object(cm_deps.tasks, 'postback')
    def test_wait_on_build(self, postback):
        server = mock.MagicMock()
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

        #Create appropriate api mocks
        openstack_api_mock = mock.MagicMock()
        openstack_api_mock.client = mock.MagicMock()
        openstack_api_mock.client.region_name = 'North'
        openstack_api_mock.servers = mock.MagicMock()
        openstack_api_mock.servers.find.return_value = server
        openstack_api_mock.images = mock.MagicMock()

        context = dict(deployment_id='DEP', resource_key='1', roles=[])

        expected_resources = {
            '1': {
                "status": "ACTIVE",
                "instance": {
                    'status': 'ACTIVE',
                    'addresses': {
                        'public': [
                            {
                                'version': 4,
                                'addr': '4.4.4.4'
                            },
                            {
                                'version': 6,
                                'addr': '2001:4800:780e:0510:'
                                        'd87b:9cbc:ff04:513a'
                            }],
                        'private': [
                            {
                                'version': 4,
                                'addr': '10.10.10.10'
                            }
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
        }

        expected = {
            'resources': expected_resources
        }

        results = compute.tasks.wait_on_build(
            context, server.id, api=openstack_api_mock)

        self.assertDictEqual(results, expected)

        openstack_api_mock.servers.find.assert_called_once_with(id=server.id)
        postback.assert_called_once_with("DEP", expected)

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
        ssh.test_connection(mox.IgnoreArg(), "4.4.4.4", "root", timeout=10,
                            password=None, identity_file=None, port=22,
                            private_key=None, proxy_address=None,
                            proxy_credentials=None).AndReturn(True)

        self.mox.ReplayAll()
        compute.tasks.verify_ssh_connection(context, server.id, "4.4.4.4",
                                            api=openstack_api_mock)
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
        rdp.test_connection(mox.IgnoreArg(), "4.4.4.4",
                            timeout=10).AndReturn(True)

        self.mox.ReplayAll()
        compute.tasks.verify_ssh_connection(context, server.id, "4.4.4.4",
                                            region="ORD",
                                            api=openstack_api_mock)
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
        with self.assertRaises(exceptions.CheckmateException):
            compute.tasks.wait_on_build(
                context, server.id, api=openstack_api_mock)

        self.mox.VerifyAll()

    @mock.patch.object(cm_deps.tasks, 'postback')
    def test_delete_server(self, dep_postback):
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
            "resources": {
                "1": {
                    'status': "DELETING",
                    "instance": {
                        "status": "DELETING",
                        "status-message": "Waiting on resource deletion"
                    }
                }
            }
        }
        api = mock.MagicMock()
        mock_servers = mock.MagicMock()
        api.servers = mock_servers
        mock_server = mock.MagicMock()
        mock_server.status = 'ACTIVE'

        mock_server.delete.return_value = True
        mock_servers.get.return_value = mock_server

        ret = compute.tasks.delete_server_task(context, api=api)

        self.assertDictEqual(expect, ret)
        mock_server.delete.assert_called_once_with()
        mock_servers.get.assert_called_once_with('abcdef-ghig-1234')

    @mock.patch('checkmate.providers.rackspace.compute.utils')
    @mock.patch.object(compute.manager.LOG, 'error')
    def test_delete_server_get_connect_error(self, log,
                                             mock_utils):
        mock_context = {'deployment_id': '1', 'resource_key': '1',
                        'region': 'ORD', 'resource': {}, 'instance_id': '1'}
        compute.LOG.error = mock.Mock()
        mock_api = mock.Mock()
        mock_api.client.management_url = 'http://test/'
        mock_api.servers.get = mock.MagicMock(
            side_effect=requests.ConnectionError)

        with self.assertRaises(exceptions.CheckmateException):
            compute.tasks.delete_server_task(mock_context, api=mock_api)

        log.assert_called_with(
            'Connection error talking to http://test/ endpoint', exc_info=True)

    @mock.patch('checkmate.providers.rackspace.compute.utils')
    @mock.patch.object(compute.manager.LOG, 'error')
    def test_delete_server_delete_connect_error(self, log,
                                                mock_utils):
        mock_context = {'deployment_id': '1', 'resource_key': '1',
                        'region': 'ORD', 'resource': {}, 'instance_id': '1'}
        compute.LOG.error = mock.Mock()
        mock_api = mock.Mock()
        mock_api.client.management_url = 'http://test/'
        mock_api.servers.get = mock.MagicMock(
            side_effect=requests.ConnectionError)

        with self.assertRaises(exceptions.CheckmateException):
            compute.tasks.delete_server_task(mock_context, api=mock_api)

        log.assert_called_with(
            'Connection error talking to http://test/ endpoint', exc_info=True)

    @mock.patch.object(cm_deps.tasks, 'postback')
    def test_wait_on_delete(self, dep_postback):
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
            "resources": {
                "1": {
                    "status": "DELETED",
                    "instance": {
                        "status": "DELETED",
                        "status-message": ""
                    }
                }
            }

        }

        api = mock.MagicMock()
        mock_servers = mock.MagicMock()
        mock_server = mock.MagicMock()

        api.servers = mock_servers
        mock_server.status = 'DELETED'
        mock_server.find.return_value = mock_server
        mock_servers.find.return_value = mock_server

        ret = compute.tasks.wait_on_delete_server(context, api=api)

        self.assertDictEqual(expect, ret)
        calls = [
            mock.call('1234', {
                "resources": {
                    '1': {
                        "status": "DELETED",
                        "instance": {
                            "status": "DELETED",
                            "status-message": ""
                        }
                    }
                }}
            )
        ]
        dep_postback.assert_has_calls(calls)

    @mock.patch('checkmate.providers.rackspace.compute.utils')
    @mock.patch.object(compute.manager.LOG, 'error')
    def test_wait_on_delete_connect_error(self, log, mock_utils):
        mock_context = {'deployment_id': '1', 'resource_key': '1',
                        'region': 'ORD', 'resource': {}, 'instance_id': '1'}
        compute.LOG.error = mock.Mock()
        mock_api = mock.Mock()
        mock_api.client.management_url = 'http://test/'
        mock_api.servers.find = mock.MagicMock(
            side_effect=requests.ConnectionError)

        with self.assertRaises(exceptions.CheckmateException):
            compute.tasks.wait_on_delete_server(mock_context,
                                                api=mock_api)

        log.assert_called_with(
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

        expected = {'resources': {'0': {"status": "ERROR"}}}

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
        resources = [{
            'component': 'linux_instance',
            'dns-name': 'master.wordpress.cldsrvr.com',
            'desired-state': {
                'flavor': '3',
                'image': 'e4dbdba7-b2a4-4ee5-8e8f-4595b6d694ce',
                'region': 'ORD',
            },
            'hosts': ['1'],
            'index': '2',
            'instance': {},
            'provider': 'nova',
            'service': 'master',
            'status': 'NEW',
            'type': 'compute',
        }]
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
        self.mox.StubOutWithMock(compute.provider, '_get_flavors')
        self.mox.StubOutWithMock(compute.provider, '_get_limits')
        self.mox.StubOutWithMock(compute.provider.Provider, 'find_url')
        self.mox.StubOutWithMock(compute.provider.Provider, 'find_a_region')
        compute.provider._get_flavors(
            mox.IgnoreArg(), mox.IgnoreArg()).AndReturn(flavors)
        compute.provider._get_limits(mox.IgnoreArg(),
                                     mox.IgnoreArg()).AndReturn(limits)
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
            'service': 'master',
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
    @mock.patch('checkmate.providers.rackspace.compute.provider.utils')
    @mock.patch('checkmate.providers.rackspace.compute.provider.pyrax')
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

        result = compute.provider.Provider.get_resources(request, 'tenant')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['dns-name'], 'server_name')
        self.assertEqual(result[0]['status'], 'server_status')
        self.assertEqual(result[0]['instance']['flavor'], 'server_flavor')
        self.assertEqual(result[0]['instance']['image'], 'server_image')
        self.assertEqual(result[0]['instance']['region'], 'region_name')

    @mock.patch(
        'checkmate.providers.rackspace.compute.utils.get_ips_from_server')
    @mock.patch('checkmate.providers.rackspace.compute.provider.pyrax')
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
    @mock.patch('checkmate.providers.rackspace.compute.provider.pyrax')
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
        self.assertEqual(result[0]['instance']['image'], 'gotit')


if __name__ == '__main__':
    import sys

    test.run_with_params(sys.argv[:])
