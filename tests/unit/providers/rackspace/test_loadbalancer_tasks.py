# pylint: disable=R0904,C0103,W0212
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

from checkmate.providers.rackspace import loadbalancer


class TestLoadBalancerSyncTask(unittest.TestCase):
    """Class to test sync_resource_task."""

    def setUp(self):
        """Re-use test vars."""
        self.context = {'base_url': 'url', 'tenant': 'T0',
                        'deployment': 'dep_id'}
        self.resource = {'instance': {'id': '1234'}, 'index': '0'}
        self.resource_key = 1
        self.api = mock.MagicMock()

    @mock.patch.object(loadbalancer.LOG, 'info')
    def test_sync_success(self, mock_logger):
        """Verifies methods and return results on sync_resource_task."""
        clb = mock.MagicMock()
        clb.status = 'RESIZING'
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

    def test_metadata_requires_update(self):
        """Verifies that metadata is updated with RAX-CHECKMATE."""
        self.api.get_metadata.return_value = [{'id': 'an_id', 'key': 'a_key',
                                               'value': 'a_value'}]
        loadbalancer._update_metadata(self.context, self.resource, self.api)
        self.api.update_metadata.assert_called_once_with({
            'key': 'RAX-CHECKMATE',
            'value': 'url/T0/deployments/dep_id/resources/0'
        })

    def test_metadata_no_update_required(self):
        """Verifies no change when RAX-CHECKMATE already exists."""
        self.api.get_metadata.return_value = [{
            'key': 'RAX-CHECKMATE',
            'value': 'url/T0/deployments/dep_id/resources/0'}]
        loadbalancer._update_metadata(self.context, self.resource, self.api)
        assert not self.api.update_metadata.called

    def test_metadata_clean_old_key(self):
        """Verifies that the RAX-CHKMATE key is removed if found."""
        self.api.get_metadata.return_value = [{
            'key': 'RAX-CHKMATE',
            'value': 'url/T0/deployments/dep_id/resources/0'}]
        loadbalancer._update_metadata(self.context, self.resource, self.api)
        self.api.delete_metadata.assert_called_once_with('RAX-CHKMATE')


class TestLoadBalancerUpdateNodeStatusTask(unittest.TestCase):
    @mock.patch('checkmate.deployments.tasks.postback')
    @mock.patch(
        'checkmate.providers.rackspace.loadbalancer.provider.Provider.connect')
    def test_update_node_status(self, mock_connect, mock_postback):
        context = {
            'source_resource': '0',
            'target_resource': '1',
            'relation_name': 'lb-web',
            'deployment': 'dep_id',
        }
        lb_id = "LB_ID"
        ip = "IP"
        region = "ORD"
        expected_results = {
            'resources': {
                '0': {
                    "relations": {
                        "lb-web-1": {
                            'state': 'DISABLED'
                        }
                    }
                },
                '1': {
                    "status": "OFFLINE",
                    "relations": {
                        "lb-web-0": {
                            'state': 'DISABLED'
                        }
                    }
                }
            }
        }
        mock_api = mock.Mock()
        mock_node = mock.Mock()
        mock_node.address = ip
        mock_connect.return_value = mock_api
        mock_lb = mock_api.get.return_value
        mock_lb.nodes = [mock_node]
        results = loadbalancer.update_node_status(context, lb_id, ip,
                                                  region, "DISABLED",
                                                  "OFFLINE")
        self.assertTrue(mock_node.update.called)
        self.assertEqual(mock_node.condition, "DISABLED")
        self.assertDictEqual(results, expected_results)
        mock_postback.assert_called_once_with("dep_id", expected_results)

    @mock.patch(
        'checkmate.providers.rackspace.loadbalancer.provider.Provider.connect')
    def test_update_node_status_with_422_client_exception(self, mock_connect):
        context = {
            'source_resource': '0',
            'target_resource': '1',
            'relation_name': 'lb-web',
            'deployment': 'dep_id',
        }
        lb_id = 1234
        ip = "IP"
        region = "ORD"

        mock_api = mock.Mock()
        mock_node = mock.Mock()
        mock_node.address = ip
        mock_connect.return_value = mock_api
        mock_lb = mock_api.get.return_value
        mock_lb.nodes = [mock_node]
        exception = pyrax.exceptions.ClientException("422",
                                                     message="exception")
        mock_node.update.side_effect = exception
        loadbalancer.update_node_status.retry = mock.Mock(
            side_effect=StandardError(""))
        self.assertRaises(StandardError, loadbalancer.update_node_status,
                          context, lb_id, ip, region, "ENABLED", "ACTIVE")
        loadbalancer.update_node_status.retry.assert_called_once_with(
            exc=exception)

    @mock.patch(
        'checkmate.providers.rackspace.loadbalancer.provider.Provider.connect')
    def test_update_node_status_with_client_exception(self, mock_connect):
        context = {
            'source_resource': '0',
            'target_resource': '1',
            'relation_name': 'lb-web',
            'deployment': 'dep_id',
        }
        lb_id = 1234
        ip = "IP"
        region = "ORD"

        mock_api = mock.Mock()
        mock_node = mock.Mock()
        mock_node.address = ip
        mock_connect.return_value = mock_api
        mock_lb = mock_api.get.return_value
        mock_lb.nodes = [mock_node]
        exception = pyrax.exceptions.ClientException("404",
                                                    message="exception")
        mock_node.update.side_effect = exception
        loadbalancer.update_node_status.retry = mock.Mock(
            side_effect=StandardError(""))
        self.assertRaises(StandardError, loadbalancer.update_node_status,
                          context, lb_id, ip, region, "ENABLED", "ACTIVE")
        loadbalancer.update_node_status.retry.assert_called_once_with(
            exc=exception)

    @mock.patch(
        'checkmate.providers.rackspace.loadbalancer.provider.Provider.connect')
    def test_update_node_status_with_standard_error(self, mock_connect):
        context = {
            'source_resource': '0',
            'target_resource': '1',
            'relation_name': 'lb-web',
            'deployment': 'dep_id',
        }
        lb_id = 1234
        ip = "IP"
        region = "ORD"

        mock_api = mock.Mock()
        mock_node = mock.Mock()
        mock_node.address = ip
        mock_connect.return_value = mock_api
        mock_lb = mock_api.get.return_value
        mock_lb.nodes = [mock_node]
        exception = StandardError("exception")
        mock_node.update.side_effect = exception
        loadbalancer.update_node_status.retry = mock.Mock(
            side_effect=StandardError(""))
        self.assertRaises(StandardError, loadbalancer.update_node_status,
                          context, lb_id, ip, region, "ENABLED", "ACTIVE")

        loadbalancer.update_node_status.retry.assert_called_once_with(
            exc=exception)

    @mock.patch('checkmate.deployments.tasks.postback')
    def test_update_node_status_for_simulation(self, mock_postback):
        context = {
            'source_resource': '0',
            'target_resource': '1',
            'relation_name': 'lb-web',
            'deployment': 'dep_id',
            'simulation': True
        }
        expected_results = {
            'resources': {
                '0': {
                    "relations": {
                        "lb-web-1": {
                            'state': 'DISABLED'
                        }
                    }
                },
                '1': {
                    "status": "OFFLINE",
                    "relations": {
                        "lb-web-0": {
                            'state': 'DISABLED'
                        }
                    }
                }
            }
        }
        lb_id = 1234
        ip = "IP"
        region = "ORD"

        results = loadbalancer.update_node_status(context, lb_id, ip,
                                                  region, "DISABLED",
                                                  "OFFLINE")
        self.assertDictEqual(results, expected_results)
        mock_postback.assert_called_once_with("dep_id", expected_results)


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
