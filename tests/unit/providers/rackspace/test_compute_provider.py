# pylint: disable=C0103,C0111,R0201,R0903,R0904,W0212,W0232
# encoding: utf-8
'''Module for testing Rackspace Compute Provider.'''
import mock
import unittest

from checkmate.providers.rackspace import compute


class TestGetCatalog(unittest.TestCase):
    '''Class for testing get_catalog.'''

    def setUp(self):
        '''Sets up context for reuse in get_catalog testing.'''
        self.context = {'region': 'SYD'}
        self.base = compute.RackspaceComputeProviderBase({})

    @mock.patch.object(compute.ProviderBase, 'get_catalog')
    def test_ProviderBase_catalog_injection(self, mock_get_catalog):
        '''Verifies catalog returned from ProviderBase.'''
        expected = {'catalog': {}}
        mock_get_catalog.return_value = expected
        results = self.base.get_catalog(self.context)
        self.assertEqual(results, expected)

    @mock.patch.object(compute.ProviderBase, 'get_catalog')
    def test_region_not_in_catalog_cache(self, mock_get_catalog):
        '''Verifies None returned if region not in catalog cache.'''
        mock_get_catalog.return_value = None
        results = self.base.get_catalog(self.context)
        self.assertEqual(results, None)

    @mock.patch.object(compute.ProviderBase, 'get_catalog')
    def test_region_in_catalog_cache(self, mock_get_catalog):
        '''Verifies None returned if region not in catalog cache.'''
        expected = {'catalog': {}}
        mock_get_catalog.return_value = None
        self.base._catalog_cache['SYD'] = expected
        results = self.base.get_catalog(self.context)
        self.assertEqual(results, expected)

    @mock.patch.object(compute.ProviderBase, 'get_catalog')
    def test_region_in_catalog_cache_w_filters(self, mock_get_catalog):
        '''Verifies None returned if region not in catalog cache.'''
        expected = {'lists': {'images': {}}}
        catalog = {'compute': {'linux_instance': {}}, 'lists': {'images': {}}}
        mock_get_catalog.return_value = None
        self.base._catalog_cache['SYD'] = catalog
        results = self.base.get_catalog(self.context, type_filter='lists')
        self.assertEqual(results, expected)


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
