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


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
