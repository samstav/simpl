# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
import unittest

from checkmate.providers.rackspace import base


class TestRackspaceProviderBase(unittest.TestCase):
    """Class for testing RackspaceProviderBase."""

    def test_get_regions_none(self):
        regions = base.RackspaceProviderBase.get_regions([])
        self.assertEqual(regions, [])

    def test_get_regions_one(self):
        regions = base.RackspaceProviderBase.get_regions(
            [{'endpoints': [{'region': 'A'}]}])
        self.assertEqual(regions, ['A'])

    def test_get_regions_unique(self):
        '''Only return a region once.'''
        regions = base.RackspaceProviderBase.get_regions(
            [{'endpoints': [{'region': 'A'}, {'region': 'A'}]}])
        self.assertEqual(regions, ['A'])

    def test_get_regions_ignore_blank_or_none(self):
        regions = base.RackspaceProviderBase.get_regions(
            [{'endpoints': [{'region': None}, {'region': ''}, {}]}])
        self.assertEqual(regions, [])

    def test_get_regions_multiple(self):
        regions = base.RackspaceProviderBase.get_regions(
            [{'endpoints': [{'region': 'A'}, {'region': 'B'}]}])
        self.assertEqual(regions, ['A', 'B'])

    def test_get_regions_filter_by_resource(self):
        regions = base.RackspaceProviderBase.get_regions(
            [
                {
                    'type': 'compute',
                    'endpoints': [{'region': 'MATCH'}],
                }, {
                    'type': 'database',
                    'endpoints': [{'region': 'OTHER'}],
                }, {
                    'endpoints': [{'region': 'NONE'}]
                },
            ],
            resource_type='compute')
        self.assertEqual(regions, ['MATCH'])

    def test_get_regions_filter_by_service_name(self):
        regions = base.RackspaceProviderBase.get_regions(
            [
                {
                    'name': 'openCloud',
                    'endpoints': [{'region': 'MATCH'}],
                }, {
                    'name': 'closedCloud',
                    'endpoints': [{'region': 'OTHER'}],
                }, {
                    'endpoints': [{'region': 'NONE'}]
                },
            ],
            service_name='openCloud')
        self.assertEqual(regions, ['MATCH'])

    def test_get_regions_filter_by_both(self):
        regions = base.RackspaceProviderBase.get_regions(
            [
                {
                    'name': 'openCloud',
                    'type': 'compute',
                    'endpoints': [{'region': 'MATCH'}],
                }, {
                    'name': 'openCloud',
                    'type': 'database',
                    'endpoints': [{'region': 'NAMEONLY'}],
                }, {
                    'name': 'closedCloud',
                    'type': 'compute',
                    'endpoints': [{'region': 'TYPEONLY'}],
                }, {
                    'name': 'openCloud',
                    'endpoints': [{'region': 'NOTYPE'}],
                }, {
                    'type': 'compute',
                    'endpoints': [{'region': 'NONAME'}],
                }, {
                    'endpoints': [{'region': 'NONE'}],
                },
            ],
            service_name='openCloud',
            resource_type='compute')
        self.assertEqual(regions, ['MATCH'])


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
