# pylint: disable=R0904,C0103,W0212,E1103
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

"""
Module for testing loadbalancer manager
"""
import mock
import unittest
import logging
from novaclient.exceptions import OverLimit
from requests import ConnectionError
from checkmate import exceptions as cmexc, utils
from checkmate.exceptions import CheckmateException
from checkmate.providers.rackspace import compute

from checkmate.providers.rackspace.compute.manager import Manager
from checkmate.providers.rackspace.compute.provider import Provider

LOG = logging.getLogger(__name__)


class TestCreateServer(unittest.TestCase):

    @mock.patch.object(Provider, "connect")
    def test_create_server(self, connect):
        manager = Manager()
        context = {
            "deployment_id": "DEP1001",
            "resource_key": "0",
            "simulation": False,
        }
        mock_api = mock.MagicMock()

        mock_image = mock.MagicMock()
        mock_image.name = "IMAGE"

        mock_flavor = mock.MagicMock()
        mock_flavor.name = "FLAVOR"

        mock_server = mock.MagicMock()
        mock_server.id = "SERVER_ID"
        mock_server.adminPass = "PASSWORD"

        connect.return_value = mock_api
        mock_api.images.find = mock.MagicMock(return_value=mock_image)
        mock_api.flavors.find = mock.MagicMock(return_value=mock_flavor)
        mock_api.servers.create = mock.MagicMock(return_value=mock_server)
        mock_api.client.region_name = "REGION"

        results = manager.create_server(
            context, "Name", "ORD", api=None, image="image_id",
            flavor="flavor_id", tags="SERVER_TAG")

        self.assertDictEqual(results,{
            "id": "SERVER_ID",
            "password": "PASSWORD",
            "status": "NEW",
            "flavor": "flavor_id",
            "image": "image_id",
            "error-message": "",
            "status-message": "",
            "region": "REGION"
        })

        mock_api.images.find.assert_called_once_with(id="image_id")
        mock_api.flavors.find.assert_called_once_with(id="flavor_id")
        mock_api.servers.create.assert_called_once_with("Name", mock_image,
                                                       mock_flavor,
                                                       meta="SERVER_TAG",
                                                       files=None,
                                                       disk_config='AUTO')

    @mock.patch.object(Provider, "connect")
    def test_create_server_overlimit_error(self, connect):
        manager = Manager()
        context = {
            "deployment_id": "DEP1001",
            "resource_key": "0",
            "simulation": False,
        }
        mock_api = mock.MagicMock()

        mock_image = mock.MagicMock()
        mock_image.name = "IMAGE"

        mock_flavor = mock.MagicMock()
        mock_flavor.name = "FLAVOR"

        mock_server = mock.MagicMock()
        mock_server.id = "SERVER_ID"
        mock_server.adminPass = "PASSWORD"

        connect.return_value = mock_api
        mock_api.images.find = mock.MagicMock(return_value=mock_image)
        mock_api.flavors.find = mock.MagicMock(return_value=mock_flavor)
        mock_api.servers.create = mock.MagicMock(side_effect=OverLimit("",""))
        mock_api.client.region_name = "REGION"

        try:
            manager.create_server(context, "Name", "ORD", api=None,
                                  image="image_id",flavor="flavor_id",
                                  tags="SERVER_TAG")
            self.fail("Should have thrown an exception!")
        except cmexc.CheckmateException as exc:
            self.assertTrue(exc.options, cmexc.CAN_RESET)

        mock_api.servers.create.assert_called_once_with("Name", mock_image,
                                                       mock_flavor,
                                                       meta="SERVER_TAG",
                                                       files=None,
                                                       disk_config='AUTO')

    @mock.patch.object(Provider, "connect")
    def test_create_server_connection_error(self, connect):
        manager = Manager()
        context = {
            "deployment_id": "DEP1001",
            "resource_key": "0",
            "simulation": False,
        }
        mock_api = mock.MagicMock()

        mock_image = mock.MagicMock()
        mock_image.name = "IMAGE"

        mock_flavor = mock.MagicMock()
        mock_flavor.name = "FLAVOR"

        mock_server = mock.MagicMock()
        mock_server.id = "SERVER_ID"
        mock_server.adminPass = "PASSWORD"

        connect.return_value = mock_api
        mock_api.images.find = mock.MagicMock(return_value=mock_image)
        mock_api.flavors.find = mock.MagicMock(return_value=mock_flavor)
        mock_api.servers.create = mock.MagicMock(
            side_effect=ConnectionError())
        mock_api.client.region_name = "REGION"

        try:
            manager.create_server(context, "Name", "ORD", api=None,
                                  image="image_id",flavor="flavor_id",
                                  tags="SERVER_TAG")
            self.fail("Should have thrown an exception!")
        except cmexc.CheckmateException as exc:
            self.assertTrue(exc.options, cmexc.CAN_RESUME)

        mock_api.servers.create.assert_called_once_with("Name", mock_image,
                                                       mock_flavor,
                                                       meta="SERVER_TAG",
                                                       files=None,
                                                       disk_config='AUTO')

class TestWaitOnBuild(unittest.TestCase):

    @mock.patch.object(Provider, "connect")
    @mock.patch.object(utils, "get_ips_from_server")
    def test_wait_on_build_active(self, ips_from_server, connect):
        context = {
            "resource_key": "0",
            "roles": {}
        }
        mock_api = mock.MagicMock()
        callback = mock.MagicMock()
        update_task = mock.MagicMock()
        mock_server = mock.MagicMock()

        mock_server.status = "ACTIVE"
        mock_server.addresses = ["127.0.0.1", "192.168.412.11"]
        connect.return_value = mock_api

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        results = Manager.wait_on_build(context, "SERVER_ID", "REGION",
                                      callback, update_task, "IP_ADDRESS",
                                      api=None)

        self.assertDictEqual(results,{
            "id": "SERVER_ID",
            "status": "ACTIVE",
            "addresses": ["127.0.0.1", "192.168.412.11"],
            "region": "ORD",
            "ip": "SOME_IP_ADDRESS",
            "public_ip": "PUBLIC_IP_ADDRESS",
            "status": "ACTIVE",
            "status-message": ''
        })

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")


    @mock.patch.object(Provider, "connect")
    def test_wait_on_build_error(self, connect):
        context = {
            "resource_key": "0",
            "roles": {}
        }

        mock_api = mock.MagicMock()
        callback = mock.MagicMock()
        update_task = mock.MagicMock()
        mock_server = mock.MagicMock()

        mock_server.status = "ERROR"
        connect.return_value = mock_api

        mock_api.servers.find.return_value = mock_server

        try:
            Manager.wait_on_build(context, "SERVER_ID", "REGION",
                                      callback, update_task, "IP_ADDRESS",
                                      api=None)
            self.fail("Should have thrown an exception!")
        except cmexc.CheckmateException as exception:
            self.assertEquals(exception.options, cmexc.CAN_RESET)
        callback.assert_called_once_with({
            "status": "ERROR",
            "status-message": 'Server SERVER_ID build failed'
        })

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")


    @mock.patch.object(Provider, "connect")
    def test_wait_on_build_build(self, connect):
        context = {
            "resource_key": "0",
            "roles": {}
        }

        mock_api = mock.MagicMock()
        callback = mock.MagicMock()
        update_task = mock.MagicMock()
        mock_server = mock.MagicMock()

        mock_server.status = "BUILD"
        mock_server.progress = "72"
        mock_server.addresses = ["127.0.0.1", "192.168.412.11"]

        connect.return_value = mock_api

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        try:
            Manager.wait_on_build(context, "SERVER_ID", "REGION",
                                  callback, update_task, "IP_ADDRESS",
                                  api=None)
            self.fail("Should have thrown an exception!")
        except cmexc.CheckmateException as exception:
            self.assertEquals(exception.options, cmexc.CAN_RESUME)
        callback.assert_called_once_with({
            "id": "SERVER_ID",
            "status": "BUILD",
            "addresses": ["127.0.0.1", "192.168.412.11"],
            "region": "ORD",
            "progress": "72",
            "status-message": '72% Complete'
        })

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")
        update_task.assert_called_once_with(state="PROGRESS", meta={
            'id': "SERVER_ID",
            "status": "BUILD",
            "addresses": ["127.0.0.1", "192.168.412.11"],
            "region": "ORD",
            "progress": "72",
            "status-message": '72% Complete'
        })

    @mock.patch.object(Provider, "connect")
    @mock.patch.object(utils, "get_ips_from_server")
    @mock.patch.object(utils, "is_rackconnect_account")
    def test_wait_on_build_rackconnect_ready(self, is_rackconnect_account,
                                             ips_from_server, connect):
        context = {
            "resource_key": "0",
        }
        mock_api = mock.MagicMock()
        callback = mock.MagicMock()
        update_task = mock.MagicMock()
        mock_server = mock.MagicMock()

        is_rackconnect_account.return_value = True
        mock_server.status = "ACTIVE"
        mock_server.metadata = {'rackconnect_automation_status': 'DEPLOYED'}
        mock_server.addresses = ["127.0.0.1", "192.168.412.11"]
        connect.return_value = mock_api

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        results = Manager.wait_on_build(context, "SERVER_ID", "REGION",
                                        callback, update_task, "IP_ADDRESS",
                                        api=None)

        self.assertDictEqual(results, {
            "id": "SERVER_ID",
            "status": "ACTIVE",
            "addresses": ["127.0.0.1", "192.168.412.11"],
            "region": "ORD",
            "ip": "SOME_IP_ADDRESS",
            "public_ip": "PUBLIC_IP_ADDRESS",
            "status-message": '',
            "rackconnect-automation-status": "DEPLOYED"
        })

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")

    @mock.patch.object(Provider, "connect")
    @mock.patch.object(utils, "get_ips_from_server")
    @mock.patch.object(utils, "is_rackconnect_account")
    def test_wait_on_build_rackconnect_failed(self, is_rackconnect_account,
                                              ips_from_server, connect):
        context = {
            "resource_key": "0",
        }
        mock_api = mock.MagicMock()
        callback = mock.MagicMock()
        update_task = mock.MagicMock()
        mock_server = mock.MagicMock()

        is_rackconnect_account.return_value = True
        mock_server.status = "ACTIVE"
        mock_server.metadata = {'rackconnect_automation_status': 'FAILED'}
        mock_server.addresses = ["127.0.0.1", "192.168.412.11"]
        connect.return_value = mock_api

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        try:
            Manager.wait_on_build(context, "SERVER_ID", "REGION",
                                  callback, update_task, "IP_ADDRESS",
                                  api=None)
            self.fail("Should have thrown an exception!")
        except cmexc.CheckmateException as exc:
            self.assertEquals(exc.options, 0)

        callback.assert_called_once_with({
            "id": "SERVER_ID",
            "status": "ERROR",
            "addresses": ["127.0.0.1", "192.168.412.11"],
            "region": "ORD",
            "status-message": "Rackconnect server metadata has "
                              "\'rackconnect_automation_status\' set to "
                              "FAILED.",
            "rackconnect-automation-status": "FAILED",
        })

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")

    @mock.patch.object(Provider, "connect")
    @mock.patch.object(utils, "get_ips_from_server")
    @mock.patch.object(utils, "is_rackconnect_account")
    @mock.patch.object(compute.manager.LOG, "warn")
    def test_wait_on_build_rackconnect_unprocessable(self,
                                                     logger,
                                                     is_rackconnect_account,
                                                     ips_from_server,
                                                     connect):
        context = {
            "resource_key": "0",
        }
        mock_api = mock.MagicMock()
        callback = mock.MagicMock()
        update_task = mock.MagicMock()
        mock_server = mock.MagicMock()

        is_rackconnect_account.return_value = True
        mock_server.status = "ACTIVE"
        mock_server.metadata = {'rackconnect_automation_status':
                                    'UNPROCESSABLE',
                                'rackconnect_unprocessable_reason':
                                    'Somewhere something went very wrong'
        }
        mock_server.addresses = ["127.0.0.1", "192.168.412.11"]
        connect.return_value = mock_api

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        results = Manager.wait_on_build(context, "SERVER_ID", "REGION",
                                        callback, update_task, "IP_ADDRESS",
                                        api=None)

        self.assertDictEqual(results, {
            "id": "SERVER_ID",
            "status": "ACTIVE",
            "addresses": ["127.0.0.1", "192.168.412.11"],
            "region": "ORD",
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS',
            "status-message": "",
            "rackconnect-automation-status": "UNPROCESSABLE",
        })
        logger.assert_called_once_with("RackConnect server metadata has "
                                      "'rackconnect_automation_status' is "
                                      "set to UNPROCESSABLE. "
                                      "Reason: Somewhere something went very "
                                      "wrong. RackConnect will not be enabled"
                                      " for this server(#SERVER_ID).")
        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")


    @mock.patch.object(Provider, "connect")
    @mock.patch.object(utils, "get_ips_from_server")
    @mock.patch.object(utils, "is_rackconnect_account")
    @mock.patch.object(compute.manager.LOG, "warn")
    def test_wait_on_build_rackconnect_unprocessable(self,
                                                     logger,
                                                     is_rackconnect_account,
                                                     ips_from_server,
                                                     connect):
        context = {
            "resource_key": "0",
        }
        mock_api = mock.MagicMock()
        callback = mock.MagicMock()
        update_task = mock.MagicMock()
        mock_server = mock.MagicMock()

        is_rackconnect_account.return_value = True
        mock_server.status = "ACTIVE"
        mock_server.metadata = {
            'rackconnect_automation_status':
                'STATUS'
        }
        mock_server.addresses = ["127.0.0.1", "192.168.412.11"]
        connect.return_value = mock_api

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        try:
            Manager.wait_on_build(context, "SERVER_ID", "REGION",
                                        callback, update_task, "IP_ADDRESS",
                                        api=None)
            self.fail("Should have thrown an exception!")
        except CheckmateException as exc:
            self.assertEquals(exc.options, cmexc.CAN_RESUME)
        callback.assert_called_once_with({
            "id": "SERVER_ID",
            "status": "ACTIVE",
            "addresses": ["127.0.0.1", "192.168.412.11"],
            "region": "ORD",
            "status-message": "Rack Connect server "
                              "'rackconnect_automation_status' metadata tag "
                              "is still not 'DEPLOYED'. It is "
                              "'STATUS'",
        })

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")


    @mock.patch.object(Provider, "connect")
    @mock.patch.object(utils, "get_ips_from_server")
    @mock.patch.object(utils, "is_rackconnect_account")
    def test_wait_on_build_rackconnect_waiting_for_tag(
            self, is_rackconnect_account, ips_from_server, connect):
        context = {
            "resource_key": "0",
        }
        mock_api = mock.MagicMock()
        callback = mock.MagicMock()
        update_task = mock.MagicMock()
        mock_server = mock.MagicMock()

        is_rackconnect_account.return_value = True
        mock_server.status = "ACTIVE"
        mock_server.metadata = {}
        mock_server.addresses = ["127.0.0.1", "192.168.412.11"]
        connect.return_value = mock_api

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        try:
            Manager.wait_on_build(context, "SERVER_ID", "REGION",
                                        callback, update_task, "IP_ADDRESS",
                                        api=None)
            self.fail("Should have thrown an exception")
        except CheckmateException as exc:
            self.assertEquals(exc.options, cmexc.CAN_RESUME)
        callback.assert_called_once_with({
            "id": "SERVER_ID",
            "status": "ACTIVE",
            "addresses": ["127.0.0.1", "192.168.412.11"],
            "region": "ORD",
            "status-message": "RackConnect server still does not have the "
                              "'rackconnect_automation_status' metadata tag",
        })

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")

    @mock.patch.object(Provider, "connect")
    @mock.patch.object(utils, "get_ips_from_server")
    def test_wait_on_build_ip_is_not_available(
            self, ips_from_server, connect):
        context = {
            "resource_key": "0",
            "roles": []
        }
        mock_api = mock.MagicMock()
        callback = mock.MagicMock()
        update_task = mock.MagicMock()
        mock_server = mock.MagicMock()

        mock_server.status = "ACTIVE"
        mock_server.metadata = {}
        mock_server.addresses = ["127.0.0.1", "192.168.412.11"]
        connect.return_value = mock_api

        ips_from_server.return_value = {
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        try:
            Manager.wait_on_build(context, "SERVER_ID", "REGION",
                                        callback, update_task, "IP_ADDRESS",
                                        api=None)
            self.fail("Should have thrown an exception")
        except CheckmateException as exc:
            self.assertEquals(exc.options, cmexc.CAN_RESUME)
            self.assertEquals(exc.message, "Could not find IP of server "
                                           "SERVER_ID")

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")




