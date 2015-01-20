# Copyright (c) 2011-2015 Rackspace US, Inc.
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

# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232

import mock
import unittest

from checkmate.providers import base
from checkmate.providers.rackspace import base as rs_base
from checkmate.providers.rackspace import compute


class TestGetCatalog(unittest.TestCase):
    """Class for testing get_catalog."""

    def setUp(self):
        """Sets up context for reuse in get_catalog testing."""
        self.context = {'region': 'SYD'}
        self.base = compute.provider.RackspaceComputeProviderBase({})

    @mock.patch.object(base.ProviderBase, 'get_catalog')
    def test_ProviderBase_catalog_injection(self, mock_get_catalog):
        expected = {'catalog': {}}
        mock_get_catalog.return_value = expected
        results = self.base.get_catalog(self.context)
        self.assertEqual(results, expected)

    @mock.patch.object(base.ProviderBase, 'get_catalog')
    def test_region_not_in_catalog_cache(self, mock_get_catalog):
        mock_get_catalog.return_value = None
        results = self.base.get_catalog(self.context)
        self.assertEqual(results, None)

    @mock.patch.object(base.ProviderBase, 'get_catalog')
    def test_region_in_catalog_cache(self, mock_get_catalog):
        expected = {'catalog': {}}
        mock_get_catalog.return_value = None
        self.base._catalog_cache['SYD'] = expected
        results = self.base.get_catalog(self.context)
        self.assertEqual(results, expected)

    @mock.patch.object(base.ProviderBase, 'get_catalog')
    def test_region_in_catalog_cache_w_filters(self, mock_get_catalog):
        expected = {'lists': {'images': {}}}
        catalog = {'compute': {'linux_instance': {}}, 'lists': {'images': {}}}
        mock_get_catalog.return_value = None
        self.base._catalog_cache['SYD'] = catalog
        results = self.base.get_catalog(self.context, type_filter='lists')
        self.assertEqual(results, expected)


class TestGetRegions(unittest.TestCase):
    def setUp(self):
        self.catalog = [{
            'name': 'test_service',
            'endpoints': [
                {'region': 'SYD'},
                {'region': 'ORD'}
            ]
        }]

    @mock.patch.object(rs_base.LOG, 'warning')
    def test_no_regions(self, mock_logger):
        results = rs_base.RackspaceProviderBase.get_regions(
            self.catalog, service_name='invalid')
        mock_logger.assert_called_with('No regions found for type %s and '
                                       'service name %s', '*', 'invalid')
        self.assertEqual(results, [])

    def test_success(self):
        expected = ['ORD', 'SYD']
        results = rs_base.RackspaceProviderBase.get_regions(
            self.catalog, service_name='test_service')
        self.assertItemsEqual(results, expected)


if __name__ == '__main__':
    # Run tests. Handle our parameters seprately
    import sys

    args = sys.argv[:]
    # Our --debug means --verbose for unittest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
