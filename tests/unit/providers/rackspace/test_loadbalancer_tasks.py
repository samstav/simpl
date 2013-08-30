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
