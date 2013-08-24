# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Tests for SQLAlchemy driver."""
import sys
import unittest

from checkmate.db import sql
from tests.integration import base


class TestDBSQL(base.DBDriverTests, unittest.TestCase):
    @property
    def connection_string(self):
        return "sqlite://"

    def setUp(self):
        base.DBDriverTests.setUp(self)
        (self.driver.session.query(sql.Tenant).filter(sql.Tenant.id == '1234')
         .delete())
        (self.driver.session.query(sql.Tenant).filter(sql.Tenant.id == '11111')
         .delete())
        self.driver.session.commit()


if __name__ == '__main__':
    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
