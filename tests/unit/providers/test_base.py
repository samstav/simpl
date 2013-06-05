# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest2 as unittest

from checkmate.providers.base import (
    ProviderBasePlanningMixIn,
    ProviderBase
)

class TestProviderBasePlanningMixIn(unittest.TestCase):
    # Tests for generate_resource_tag
    def test_no_values_given(self):
        result = ProviderBasePlanningMixIn.generate_resource_tag()
        self.assertEquals(
            {'RAX-CHECKMATE': 'None/None/deployments/None/resources/None'},
            result
        )

    def test_with_good_values(self):
        result = ProviderBasePlanningMixIn.generate_resource_tag(
            base_url='http://blerp.com',
            tenant_id='T1',
            deployment_id='deba8c',
            resource_id='r0'
        )
        self.assertEquals(
                {'RAX-CHECKMATE':
                    'http://blerp.com/T1/deployments/deba8c/resources/r0'},
            result
        )


class TestProviderBase(unittest.TestCase):

    def test_format_postback(self):
        """ Test formatting postback data structure for resources """
        key = "0"
        resource_kwargs = {
            'status': 'ERROR',
            'status-message': 'Unexpected error deleting loadbalancer 0'
        }
        instance_kwargs = resource_kwargs.copy()
        instance_kwargs['trace'] = 'stack trace'
        expected = {
            'resources': {
                '0': {
                    'status': 'ERROR',
                    'instance': {
                        'status': 'ERROR',
                        'status-message': 'Unexpected error deleting loadbalancer 0',
                        'trace': 'stack trace'
                    },
                    'status-message': 'Unexpected error deleting loadbalancer 0'
                }
            }
        }
        results = ProviderBase.format_postback(key, resource_kwargs, instance_kwargs)
        self.assertDictEqual(expected, results)

    def test_get_checkmate_status(self):
        """ Test checkmate status schema entry returned """
        class Testing(ProviderBase):
            __schema__ = {
                'ACTIVE': 'ACTIVE',
                'BUILD': 'BUILD',
                'DELETED': 'DELETED',
                'ERROR': 'ERROR',
                'PENDING_UPDATE': 'CONFIGURE',
                'PENDING_DELETE': 'DELETING',
                'SUSPENDED': 'ERROR'
                }
        results = Testing.get_checkmate_status('SUSPENDED', Testing.__schema__)
        self.assertEqual('ERROR', results)

if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
