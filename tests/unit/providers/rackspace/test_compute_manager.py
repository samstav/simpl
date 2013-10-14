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
import logging
import mock
import requests
import unittest

from checkmate import exceptions as cmexc
from checkmate.providers.rackspace import compute
from checkmate.providers.rackspace.compute import manager as manager
from checkmate.providers.rackspace.compute import provider as provider
from checkmate import rdp
from checkmate import ssh
from checkmate import utils
from novaclient import exceptions as nvexc


LOG = logging.getLogger(__name__)


class TestCreateServer(unittest.TestCase):

    def test_create_server(self):
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

        mock_api.images.find = mock.MagicMock(return_value=mock_image)
        mock_api.flavors.find = mock.MagicMock(return_value=mock_flavor)
        mock_api.servers.create = mock.MagicMock(return_value=mock_server)
        mock_api.client.region_name = "REGION"

        results = manager.Manager.create_server(
            context, "Name", image="image_id",
            flavor="flavor_id", tags="SERVER_TAG", api=mock_api)

        self.assertDictEqual(results, {
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

    def test_create_server_overlimit_error(self):
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

        mock_api.images.find = mock.MagicMock(return_value=mock_image)
        mock_api.flavors.find = mock.MagicMock(return_value=mock_flavor)
        mock_api.servers.create = mock.MagicMock(
            side_effect=nvexc.OverLimit("", ""))
        mock_api.client.region_name = "REGION"

        try:
            manager.Manager.create_server(context, "Name", api=mock_api,
                                          image="image_id", flavor="flavor_id",
                                          tags="SERVER_TAG")
            self.fail("Should have thrown an exception!")
        except cmexc.CheckmateException as exc:
            self.assertTrue(exc.options, cmexc.CAN_RESET)

        mock_api.servers.create.assert_called_once_with("Name", mock_image,
                                                        mock_flavor,
                                                        meta="SERVER_TAG",
                                                        files=None,
                                                        disk_config='AUTO')

    def test_create_server_connection_error(self):
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

        mock_api.images.find = mock.MagicMock(return_value=mock_image)
        mock_api.flavors.find = mock.MagicMock(return_value=mock_flavor)
        mock_api.servers.create = mock.MagicMock(
            side_effect=requests.ConnectionError)
        mock_api.client.region_name = "REGION"

        try:
            manager.Manager.create_server(context, "Name",
                                          image="image_id", flavor="flavor_id",
                                          tags="SERVER_TAG", api=mock_api)
            self.fail("Should have thrown an exception!")
        except cmexc.CheckmateException as exc:
            self.assertTrue(exc.options, cmexc.CAN_RESUME)

        mock_api.servers.create.assert_called_once_with("Name", mock_image,
                                                        mock_flavor,
                                                        meta="SERVER_TAG",
                                                        files=None,
                                                        disk_config='AUTO')


class TestWaitOnBuild(unittest.TestCase):

    @mock.patch.object(utils, "get_ips_from_server")
    def test_wait_on_build_active(self, ips_from_server):
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

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        results = manager.Manager.wait_on_build(context, "SERVER_ID",
                                                callback, update_task,
                                                api=mock_api)

        self.assertDictEqual(results, {
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

    def test_wait_on_build_error(self):
        context = {
            "resource_key": "0",
            "roles": {}
        }

        mock_api = mock.MagicMock()
        callback = mock.MagicMock()
        update_task = mock.MagicMock()
        mock_server = mock.MagicMock()

        mock_server.status = "ERROR"

        mock_api.servers.find.return_value = mock_server

        try:
            manager.Manager.wait_on_build(context, "SERVER_ID",
                                          callback, update_task,
                                          api=mock_api)
            self.fail("Should have thrown an exception!")
        except cmexc.CheckmateException as exception:
            self.assertEquals(exception.options, cmexc.CAN_RESET)
        callback.assert_called_once_with({
            "status": "ERROR",
            "status-message": 'Server SERVER_ID build failed'
        })

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")

    def test_wait_on_build_build_status(self):
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

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        try:
            manager.Manager.wait_on_build(context, "SERVER_ID",
                                          callback, update_task,
                                          api=mock_api)
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

    @mock.patch.object(utils, "get_ips_from_server")
    @mock.patch.object(utils, "is_rackconnect_account")
    def test_wait_on_build_rackconnect_ready(self, is_rackconnect_account,
                                             ips_from_server):
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

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        results = manager.Manager.wait_on_build(context, "SERVER_ID",
                                                callback, update_task,
                                                "IP_ADDRESS", api=mock_api)

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

    @mock.patch.object(utils, "get_ips_from_server")
    @mock.patch.object(utils, "is_rackconnect_account")
    def test_wait_on_build_rackconnect_failed(self, is_rackconnect_account,
                                              ips_from_server):
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

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        try:
            manager.Manager.wait_on_build(context, "SERVER_ID",
                                          callback, update_task,
                                          api=mock_api)
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

    @mock.patch.object(utils, "get_ips_from_server")
    @mock.patch.object(utils, "is_rackconnect_account")
    @mock.patch.object(compute.manager.LOG, "warn")
    def test_wait_on_build_rackconnect_unprocessable(self,
                                                     logger,
                                                     is_rackconnect_account,
                                                     ips_from_server):
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
            'rackconnect_automation_status': 'UNPROCESSABLE',
            'rackconnect_unprocessable_reason': 'Somewhere something went '
                                                'very wrong'
        }
        mock_server.addresses = ["127.0.0.1", "192.168.412.11"]

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        results = manager.Manager.wait_on_build(context, "SERVER_ID",
                                                callback, update_task,
                                                "IP_ADDRESS", api=mock_api)

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
                                       "Reason: Somewhere something went "
                                       "very wrong. RackConnect will not be"
                                       " enabled for this server(#SERVER_ID)"
                                       ".")
        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")

    @mock.patch.object(utils, "get_ips_from_server")
    @mock.patch.object(utils, "is_rackconnect_account")
    @mock.patch.object(compute.manager.LOG, "warn")
    def test_wait_on_build_rackconnect_not_deployed(self, logger,
                                                    is_rackconnect_account,
                                                    ips_from_server):
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
            'rackconnect_automation_status': 'STATUS'
        }
        mock_server.addresses = ["127.0.0.1", "192.168.412.11"]

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        try:
            manager.Manager.wait_on_build(context, "SERVER_ID",
                                          callback, update_task,
                                          api=mock_api)
            self.fail("Should have thrown an exception!")
        except cmexc.CheckmateException as exc:
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

    @mock.patch.object(utils, "get_ips_from_server")
    @mock.patch.object(utils, "is_rackconnect_account")
    def test_wait_on_build_rackconnect_waiting_for_tag(
            self, is_rackconnect_account, ips_from_server):
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

        ips_from_server.return_value = {
            'ip': 'SOME_IP_ADDRESS',
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        try:
            manager.Manager.wait_on_build(context, "SERVER_ID", callback,
                                          update_task, "IP_ADDRESS",
                                          api=mock_api)
            self.fail("Should have thrown an exception")
        except cmexc.CheckmateException as exc:
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

    @mock.patch.object(utils, "get_ips_from_server")
    def test_wait_on_build_ip_is_not_available(
            self, ips_from_server):
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

        ips_from_server.return_value = {
            'public_ip': 'PUBLIC_IP_ADDRESS'
        }

        mock_api.servers.find.return_value = mock_server
        mock_api.client.region_name = "ORD"

        try:
            manager.Manager.wait_on_build(context, "SERVER_ID",
                                          callback, update_task, "IP_ADDRESS",
                                          api=mock_api)
            self.fail("Should have thrown an exception")
        except cmexc.CheckmateException as exc:
            self.assertEquals(exc.options, cmexc.CAN_RESUME)
            self.assertEquals(exc.message, "Could not find IP of server "
                                           "SERVER_ID")

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")


class TestVerifySSHConnectivity(unittest.TestCase):

    @mock.patch.object(ssh, "test_connection")
    def test_verify_ssh_connectivity_linux(self, ssh):
        context = {}

        mock_api = mock.MagicMock()
        mock_server = mock.MagicMock()
        mock_image_details = mock.MagicMock()

        mock_server.image = {"id": "IMAGE_ID"}

        mock_api.servers.find.return_value = mock_server
        mock_image_details.metadata = {"os_type": "linux"}
        mock_api.images.find.return_value = mock_image_details

        ssh.return_value = True

        is_up = manager.Manager.verify_ssh_connection(context, "SERVER_ID",
                                                      "SERVER_IP",
                                                      api=mock_api)

        self.assertEquals(True, is_up["status"])
        self.assertEquals("", is_up["status-message"])

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")
        mock_api.images.find.assert_called_once_with(id="IMAGE_ID")
        ssh.assert_called_once_with(context, "SERVER_IP",
                                    "root", timeout=10,
                                    password=None,
                                    identity_file=None,
                                    port=22,
                                    private_key=None)

    @mock.patch.object(rdp, "test_connection")
    def test_verify_ssh_connectivity_windows(self, rdp):
        context = {}

        mock_api = mock.MagicMock()
        mock_server = mock.MagicMock()
        mock_image_details = mock.MagicMock()

        mock_server.image = {"id": "IMAGE_ID"}

        mock_api.servers.find.return_value = mock_server
        mock_image_details.metadata = None
        mock_image_details.name = "WindowsNT"
        mock_api.images.find.return_value = mock_image_details

        rdp.return_value = True

        is_up = manager.Manager.verify_ssh_connection(context, "SERVER_ID",
                                                      "SERVER_IP",
                                                      api=mock_api)

        self.assertEquals(True, is_up["status"])
        self.assertEquals("", is_up["status-message"])

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")
        mock_api.images.find.assert_called_once_with(id="IMAGE_ID")
        rdp.assert_called_once_with(context, "SERVER_IP", timeout=10)

    @mock.patch.object(ssh, "test_connection")
    def test_verify_ssh_connectivity_linux_failure(self, ssh):
        context = {}

        mock_api = mock.MagicMock()
        mock_server = mock.MagicMock()
        mock_image_details = mock.MagicMock()

        mock_server.image = {"id": "IMAGE_ID"}

        mock_api.servers.find.return_value = mock_server
        mock_image_details.metadata = {"os_type": "linux"}
        mock_api.images.find.return_value = mock_image_details

        ssh.return_value = False

        result = manager.Manager.verify_ssh_connection(context, "SERVER_ID",
                                                       "SERVER_IP",
                                                       api=mock_api)

        self.assertEquals(False, result["status"])
        self.assertEquals("Server 'SERVER_ID' is ACTIVE but 'ssh "
                          "root@SERVER_IP -p 22' is failing to connect.",
                          result["status-message"])

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")
        mock_api.images.find.assert_called_once_with(id="IMAGE_ID")
        ssh.assert_called_once_with(context, "SERVER_IP",
                                    "root", timeout=10,
                                    password=None,
                                    identity_file=None,
                                    port=22,
                                    private_key=None)

    @mock.patch.object(rdp, "test_connection")
    def test_verify_ssh_connectivity_windows_failure(
            self, rdp):
        context = {}

        mock_api = mock.MagicMock()
        mock_server = mock.MagicMock()
        mock_image_details = mock.MagicMock()

        mock_server.image = {"id": "IMAGE_ID"}

        mock_api.servers.find.return_value = mock_server
        mock_image_details.metadata = None
        mock_image_details.name = "WindowsNT"
        mock_api.images.find.return_value = mock_image_details

        rdp.return_value = False

        result = manager.Manager.verify_ssh_connection(context, "SERVER_ID",
                                                       "SERVER_IP",
                                                       api=mock_api)

        self.assertEquals(False, result["status"])
        self.assertEquals("Server 'SERVER_ID' is ACTIVE but is not "
                          "responding to ping attempts",
                          result["status-message"])

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")
        mock_api.images.find.assert_called_once_with(id="IMAGE_ID")
        rdp.assert_called_once_with(context, "SERVER_IP", timeout=10)

    def test_verify_ssh_connectivity_server_not_found(self):
        context = {}

        mock_api = mock.MagicMock()

        mock_api.servers.find.side_effect = nvexc.NotFound(None)

        try:
            manager.Manager.verify_ssh_connection(context, "SERVER_ID",
                                                  "SERVER_IP",
                                                  api=mock_api)
            self.fail("Should have thrown an exception")
        except cmexc.CheckmateException as exc:
            self.assertEquals(exc.options, 0)

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")

    def test_verify_ssh_connectivity_no_connectivity(self):
        context = {}

        mock_api = mock.MagicMock()

        mock_api.servers.find.side_effect = requests.ConnectionError

        try:
            manager.Manager.verify_ssh_connection(context, "SERVER_ID",
                                                  "SERVER_IP",
                                                  api=mock_api)
            self.fail("Should have thrown an exception")
        except cmexc.CheckmateException as exc:
            self.assertEquals(exc.options, cmexc.CAN_RESUME)

        mock_api.servers.find.assert_called_once_with(id="SERVER_ID")


class TestWaitOnDelete(unittest.TestCase):

    def test_wait_on_delete_instance_not_available(self):
        context = {
            "deployment_id": "DEP_ID",
            "resource_key": "1",
            "region": "ORD",
            "resource": {},
        }

        data = manager.Manager.wait_on_delete_server(context, None, None)
        self.assertDictEqual({"status": "DELETED",
                              "status-message":
                                  "Instance ID is not available for Compute"
                                  " Instance, skipping wait_on_delete_task "
                                  "for resource 1 in deployment DEP_ID"},
                             data)

    def test_connection_error(self):
        context = {
            "deployment_id": "DEP_ID",
            "resource_key": "1",
            "region": "ORD",
            "resource": {},
            "instance_id": "INST_ID"
        }
        mock_api = mock.MagicMock()

        mock_api.servers.find.side_effect = requests.ConnectionError

        try:
            manager.Manager.wait_on_delete_server(context, mock_api, None)
            self.fail("Should have thrown an exception!")
        except cmexc.CheckmateException as exc:
            self.assertEqual(exc.options, cmexc.CAN_RESUME)

        mock_api.servers.find.assert_called_once_with(id="INST_ID")

    def test_server_already_deleted(self):
        context = {
            "deployment_id": "DEP_ID",
            "resource_key": "1",
            "region": "ORD",
            "resource": {},
            "instance_id": "INST_ID"
        }
        mock_api = mock.MagicMock()
        mock_server = mock.MagicMock()
        mock_server.status = "DELETED"

        mock_api.servers.find.return_value = mock_server

        data = manager.Manager.wait_on_delete_server(context, mock_api, None)

        self.assertDictEqual({"status": "DELETED",
                              "status-message": ""}, data)

    def test_resource_has_hosts(self):
        context = {
            "deployment_id": "DEP_ID",
            "resource_key": "1",
            "region": "ORD",
            "resource": {"hosts": [3, 5]},
            "instance_id": "INST_ID"
        }
        mock_api = mock.MagicMock()
        mock_server = mock.MagicMock()
        mock_callback = mock.MagicMock()

        mock_server.status = "DELETED"

        mock_api.servers.find.return_value = mock_server

        data = manager.Manager.wait_on_delete_server(context, mock_api,
                                                     mock_callback)

        self.assertEquals(mock_callback.call_count, 2)

        first_call = mock_callback.mock_calls[0]
        second_call = mock_callback.mock_calls[1]
        self.assertEquals("call({'status': 'DELETED', 'status-message': ''}, "
                          "resource_key=3)", first_call.__str__())
        self.assertEquals("call({'status': 'DELETED', 'status-message': ''}, "
                          "resource_key=5)", second_call.__str__())
        self.assertDictEqual({"status": "DELETED",
                              "status-message": ""}, data)

        mock_api.servers.find.assert_called_once_with(id="INST_ID")

    def test_server_wait_for_delete_status(self):
        context = {
            "deployment_id": "DEP_ID",
            "resource_key": "1",
            "region": "ORD",
            "resource": {"hosts": [3, 5]},
            "instance_id": "INST_ID"
         }
        mock_api = mock.MagicMock()
        mock_server = mock.MagicMock()
        mock_callback = mock.MagicMock()

        mock_server.status = 'ACTIVE'

        mock_api.servers.find.return_value = mock_server

        try:
            manager.Manager.wait_on_delete_server(context, mock_api,
                                                         mock_callback)
            self.fail("Should have thrown an exception!")
        except cmexc.CheckmateException as exc:
            self.assertEquals(cmexc.CAN_RESUME, exc.options)

        mock_callback.assert_called_once_with({
            'status': 'DELETING',
            'status-message': 'Instance is in state ACTIVE. Waiting on '
                              'DELETED resource.'
        })
        mock_api.servers.find.assert_called_once_with(id="INST_ID")
