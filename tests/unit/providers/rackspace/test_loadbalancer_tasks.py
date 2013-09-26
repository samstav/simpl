# pylint: disable=R0904,C0103
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
Module for testing loadbalancer.tasks
"""
import mock
import unittest

import pyrax

from checkmate import exceptions
from checkmate.providers.rackspace import loadbalancer
from checkmate.providers.rackspace.loadbalancer import manager


class TestEnableContentCaching(unittest.TestCase):
    """Class for testing enable_content_caching task."""

    def setUp(self):
        """Setup vars for re-use."""
        self.lbid = '12345'
        self.api = mock.MagicMock()

    def test_sim_success(self):
        """Verifies results on simulation."""
        expected = {
            'id': '12345',
            'status': 'ACTIVE',
            'caching': True
        }
        results = manager.Manager.enable_content_caching(self.lbid, 'api',
                                                         simulate=True)
        self.assertEqual(expected, results)

    def test_success(self):
        """Verifies method calls and results."""
        clb = mock.Mock()
        clb.status = 'ACTIVE'
        self.api.get.return_value = clb
        expected = {
            'id': '12345',
            'status': 'ACTIVE',
            'caching': True
        }
        results = manager.Manager.enable_content_caching(self.lbid, self.api)
        self.assertEqual(results, expected)
        self.api.get.assert_called_with(self.lbid)

    def test_api_get_exception(self):
        """Verifies CheckmateException raised when caught ClientException."""
        self.api.get.side_effect = pyrax.exceptions.ClientException('testing')
        expected = 'ClientException occurred enabling content caching on lb '
        self.assertRaisesRegexp(exceptions.CheckmateException, expected,
                                manager.Manager.enable_content_caching,
                                self.lbid, self.api)


class TestLoadBalancerSyncTask(unittest.TestCase):
    """Class to test sync_resource_task."""

    def setUp(self):
        """Re-use test vars."""
        self.context = {}
        self.resource = {'instance': {'id': '1234'}}
        self.resource_key = 1
        self.api = mock.MagicMock()

    @mock.patch.object(loadbalancer.LOG, 'info')
    def test_sync_success(self, mock_logger):
        """Verifies methods and return results on sync_resource_task."""
        clb = mock.MagicMock()
        clb.status = 'RESIZING'
        clb.metadata.side_effect = StandardError('testing')
        self.api.get.return_value = clb
        expected = {'instance:1': {'status': 'RESIZING'}}

        results = loadbalancer.sync_resource_task(self.context, self.resource,
                                                  self.resource_key, self.api)
        self.assertEqual(expected, results)
        mock_logger.assert_called_with('Marking load balancer instance %s as '
                                       '%s', '1234', 'RESIZING')

    def test_sync_ClientException_return(self):
        """Verifies methods and results on sync_resource_task with
        ClientException raised not 404 or 422.
        """
        self.api.get.side_effect = pyrax.exceptions.ClientException(code='500')
        expected = None

        results = loadbalancer.sync_resource_task(self.context, self.resource,
                                                  self.resource_key, self.api)
        self.assertEqual(expected, results)

    @mock.patch.object(loadbalancer.LOG, 'info')
    def test_sync_ClientException(self, mock_logger):
        """Verifies methods and results on sync_resource_task with
        ClientException raised with 404 or 422.
        """
        self.api.get.side_effect = pyrax.exceptions.ClientException(code='422')
        expected = {'instance:1': {'status': 'DELETED'}}

        results = loadbalancer.sync_resource_task(self.context, self.resource,
                                                  self.resource_key, self.api)
        self.assertEqual(expected, results)
        mock_logger.assert_called_with('Marking load balancer instance %s as '
                                       '%s', '1234', 'DELETED')

    @mock.patch.object(loadbalancer.LOG, 'info')
    def test_CheckmateException(self, mock_logger):
        """Verifies method calls and results when no instance id found."""
        del self.resource['instance']
        expected = {'instance:1': {'status': 'DELETED'}}

        results = loadbalancer.sync_resource_task(self.context, self.resource,
                                                  self.resource_key, self.api)
        self.assertEqual(expected, results)
        mock_logger.assert_called_with('Marking load balancer instance %s as '
                                       '%s', None, 'DELETED')
