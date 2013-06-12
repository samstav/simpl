# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest2 as unittest

from checkmate.providers.base import (
    ProviderBasePlanningMixIn,
    ProviderBase,
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

    def test_translate_status_success(self):
        ''' Test checkmate status schema entry returned '''
        class Testing(ProviderBase):
            __status_schema__ = {
                'ACTIVE': 'ACTIVE',
                'BUILD': 'BUILD',
                'DELETED': 'DELETED',
                'ERROR': 'ERROR',
                'PENDING_UPDATE': 'CONFIGURE',
                'PENDING_DELETE': 'DELETING',
                'SUSPENDED': 'ERROR'
                }
        results = Testing.translate_status('SUSPENDED')
        self.assertEqual('ERROR', results)

    def test_translate_status_fail(self):
        ''' Test checkmate status schema UNDEFINED returned '''
        class Testing(ProviderBase):
            __status_schema__ = {
                'ACTIVE': 'ACTIVE',
                'BUILD': 'BUILD',
                'DELETED': 'DELETED',
                'ERROR': 'ERROR',
                'PENDING_UPDATE': 'CONFIGURE',
                'PENDING_DELETE': 'DELETING',
                'SUSPENDED': 'ERROR'
                }
        results = Testing.translate_status('MISSING')
        self.assertEqual('UNDEFINED', results)

if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
