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
        (self.driver.session.query(Tenant).filter(Tenant.id == '1234')
         .delete())
        (self.driver.session.query(Tenant).filter(Tenant.id == '11111')
         .delete())
        self.driver.session.commit()


if __name__ == '__main__':
    # Any change here should be made in all test files
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
