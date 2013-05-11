# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest2 as unittest

from checkmate.providers.base import ProviderBasePlanningMixIn

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


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
