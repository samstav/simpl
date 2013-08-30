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
