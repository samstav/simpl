# pylint: disable=C0103,C0111,E1101,E1103,R0201,R0903,R0904,W0201,W0212,W0232
import sys

from tests.integration import base
import unittest
import checkmate.db.sql
from checkmate.db.sql import Deployment
from checkmate.db.sql import Tenant


class TestDBSQL(base.DBDriverTests, unittest.TestCase):
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
    from checkmate import cmtest
    cmtest.run_with_params(sys.argv[:])
