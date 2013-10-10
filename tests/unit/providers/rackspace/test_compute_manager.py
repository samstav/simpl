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
from checkmate import exceptions as cmexc

from checkmate.providers.rackspace.compute.manager import Manager
from checkmate.providers.rackspace.compute.provider import Provider

LOG = logging.getLogger(__name__)


class TestComputeManager(unittest.TestCase):

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