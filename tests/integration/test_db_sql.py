# pylint: disable=R0904,C0103
'''
Test SQLAlchemy using sqlite
'''
import sys

import base  # pylint: disable=W0403
import unittest
import checkmate.db.sql
from checkmate.db.sql import Deployment
from checkmate.db.sql import Tenant


class TestDBSQL(base.DBDriverTests, unittest.TestCase):
    '''SQLAlchemy Driver Canned Tests'''

    @property
    def connection_string(self):
        return "sqlite://"

    def setUp(self):
        base.DBDriverTests.setUp(self)
        (self.driver.session.query(Tenant).filter(Tenant.tenant_id == '1234')
         .delete())
        (self.driver.session.query(Tenant).filter(Tenant.tenant_id == '11111')
         .delete())
        self.driver.session.commit()

    def test_not_depleted_deployment_count_filter(self):
        query = self.driver.session.query(Deployment)
        query = checkmate.db.sql.filter_custom_comparison(query,
                                                          'deployments_status',
                                                          '!DELETED')
        self.assertIn("deployments_status != 'DELETED'", str(query))

    def test_active_deployment_count_filter(self):
        query = self.driver.session.query(Deployment)
        query = checkmate.db.sql.filter_custom_comparison(query,
                                                          'deployments_status',
                                                          'ACTIVE')
        self.assertIn("deployments_status == 'ACTIVE'", str(query))


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
