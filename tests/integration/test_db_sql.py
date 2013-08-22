"""Tests for SQLAlchemy driver."""
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
    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
