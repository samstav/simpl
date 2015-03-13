# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
import unittest

import mock
import pyrax

from checkmate import deployment as cmdep
from checkmate.deployments import planner
from checkmate import exceptions
from checkmate import middleware
from checkmate.providers.rackspace import base
from checkmate import server


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
        """Only return a region once."""
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
        self.assertItemsEqual(regions, ['A', 'B'])

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


class TestConnect(unittest.TestCase):
    """Verifies logic in connect."""

    def setUp(self):
        """Setup reuse vars."""
        self.context = {
            'auth_token': 'token',
            'tenant': 12345,
            'username': 'test'
        }
        pyrax.regions = ['DFW', 'ORD', 'IAD', 'SYD', 'HKG']

    def tearDown(self):
        pyrax.regions = []

    def test_invalid_context(self):
        context = 'invalid'
        try:
            base.RackspaceProviderBase._connect(context)
        except exceptions.CheckmateException as exc:
            self.assertEqual(str(exc), "Context passed into connect is an "
                             "unsupported type <type 'str'>.")

    def test_connect_no_auth_token(self):
        context = {}
        self.assertRaises(exceptions.CheckmateNoTokenError,
                          base.RackspaceProviderBase._connect, context)

    def test_region_from_region_map(self):
        pyrax.get_setting = mock.Mock(return_value=True)
        pyrax.auth_with_token = mock.Mock()
        base.RackspaceProviderBase._connect(self.context, 'chicago')
        pyrax.auth_with_token.assert_called_with('token', 12345, 'test', 'ORD')

    def test_region_from_context(self):
        self.context['region'] = 'SYD'
        pyrax.get_setting = mock.Mock(return_value=True)
        pyrax.auth_with_token = mock.Mock()
        base.RackspaceProviderBase._connect(self.context)
        pyrax.auth_with_token.assert_called_with('token', 12345, 'test', 'SYD')

    def test_region_from_default(self):
        self.context['catalog'] = {}
        pyrax.get_setting = mock.Mock(return_value=True)
        pyrax.auth_with_token = mock.Mock()
        base.RackspaceProviderBase._connect(self.context)
        pyrax.auth_with_token.assert_called_with('token', 12345, 'test', 'DFW')

    def test_region_mismatch(self):
        self.context['region'] = 'LON'
        pyrax.get_setting = mock.Mock(return_value=True)
        pyrax.auth_with_token = mock.Mock()

        with self.assertRaises(exceptions.CheckmateValidationException) as exc:
            base.RackspaceProviderBase._connect(self.context)

        self.assertEqual(
            ("Specified region 'LON' not available. Available regions: %s" %
             ['DFW', 'ORD', 'IAD', 'SYD', 'HKG']),
            exc.exception.friendly_message
        )

    @mock.patch.object(base, 'pyrax')
    def test_default_auth_source(self, mock_pyrax):
        """Tests connect with rackspace auth_source."""
        self.context['auth_source'] = server.DEFAULT_AUTH_ENDPOINTS[0]
        mock_pyrax.get_setting.return_value = False
        mock_pyrax.regions = ['DFW', 'ORD', 'IAD', 'SYD', 'HKG']
        base.RackspaceProviderBase._connect(self.context)
        mock_pyrax.get_setting.assert_called_with('identity_type')
        mock_pyrax.set_setting.assert_called_with('identity_type', 'rackspace')

    @mock.patch.object(base, 'pyrax')
    def test_keystone_auth_source(self, mock_pyrax):
        """Tests connect with keystone auth_source."""
        self.context['auth_source'] = 'localhost:8080'
        mock_pyrax.get_setting.return_value = False
        mock_pyrax.regions = ['DFW', 'ORD', 'IAD', 'SYD', 'HKG']
        expected = [
            mock.call('identity_type', 'keystone'),
            mock.call('verify_ssl', False),
            mock.call('auth_endpoint', 'localhost:8080')
        ]
        base.RackspaceProviderBase._connect(self.context)
        self.assertItemsEqual(mock_pyrax.set_setting.mock_calls, expected)


class TestValidateRegion(unittest.TestCase):

    def setUp(self):
        blueprint = {
            'id': 'fakeid',
            'blueprint': {'name': 'test blueprint'},
            'inputs': {},
            'environment': {'providers': {}},
            'name': {},
        }
        deployment = cmdep.Deployment(blueprint)
        self.depl_planner = planner.Planner(deployment)

        self.context = middleware.RequestContext()

        self.provider = base.RackspaceProviderBase(dict(vendor='rackspace'))
        self.uk_account_ids = (str(10**7), str(10**7 + 1))
        self.non_uk_account_ids = (str(0), str(1), str(10**7 - 1))

    def test_plan_region_mismatch_uk_user(self):
        # Test the case where a blueprint specifies non-UK resources,
        # but the current user is a UK user.
        self.context.region = 'IAD'
        # UK account numbers begin at 10 million
        for account_id in self.uk_account_ids:
            self.context.tenant = account_id
            with self.assertRaises(
                    exceptions.CheckmateValidationException) as exc:
                self.provider._validate_region(self.context)
            self.assertEqual('UK account cannot access non-UK resources',
                             exc.exception.message)

    def test_plan_region_mismatch_non_uk_user(self):
        # Test the case where a blueprint sepcifies UK resources,
        # but the current user is a non-UK user.
        self.context.region = 'LON'
        for account_id in self.non_uk_account_ids:
            self.context.tenant = account_id
            with self.assertRaises(
                    exceptions.CheckmateValidationException) as exc:
                self.provider._validate_region(self.context)
            self.assertEqual('Non-UK account cannot access UK resources',
                             exc.exception.message)

    def test_plan_no_region_mismatch_uk_user(self):
        self.context.region = 'LON'
        for account_id in self.uk_account_ids:
            self.context.tenant = account_id
            self.provider._validate_region(self.context)

    def test_plan_no_region_mismatch_non_uk_user(self):
        self.context.region = 'DFW'
        for account_id in self.non_uk_account_ids:
            self.context.tenant = account_id
            self.provider._validate_region(self.context)


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
