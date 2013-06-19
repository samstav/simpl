# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232,E1101,E1103
import json
import logging
import unittest2 as unittest

import bottle
import mox
from webtest import TestApp

from checkmate import test
from checkmate.api import admin

LOG = logging.getLogger(__name__)


class TestAdminDeploymentCounts(unittest.TestCase):
    """ Tests getting deployment numbers """

    def setUp(self):
        self._mox = mox.Mox()

        self.root_app = bottle.Bottle()
        self.root_app.catchall = False
        self.filters = test.MockWsgiFilters(self.root_app)
        self.filters.context.is_admin = True
        self.app = TestApp(self.filters)

        self.manager = self._mox.CreateMockAnything()
        self.router = admin.Router(self.root_app, self.manager)

        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_get_count_all(self):
        self.manager.count(tenant_id=None).AndReturn(3)
        self._mox.ReplayAll()
        res = self.app.get('/admin/deployments/count')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 3)

    def test_get_count_tenant(self):
        self.manager.count(tenant_id="12345", status=None).AndReturn(2)
        self._mox.ReplayAll()
        res = self.app.get('/admin/deployments/count?tenant_id=12345')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 2)

    def test_get_count_by_blueprint(self):
        self.manager.count(tenant_id=None, blueprint_id="blp-123-aa")\
            .AndReturn(4)
        self._mox.ReplayAll()
        res = self.app.get('/admin/deployments/count/blp-123-aa')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 4)

    def test_get_count_deployment_and_tenant(self):
        self.manager.count(tenant_id="456", blueprint_id="blp-123-aa")\
            .AndReturn(5)
        self._mox.ReplayAll()
        res = self.app.get('/admin/deployments/count/blp-123-aa?tenant_id=456')
        self.assertEqual(res.status, '200 OK')
        self.assertEqual(res.content_type, 'application/json')
        self._assert_good_count(json.loads(res.body), 5)

    def _assert_good_count(self, ret, expected_count):
        self.assertIsNotNone(ret, "No count returned")
        self.assertIn("count", ret, "Return does not contain count")
        self.assertEqual(expected_count, ret.get("count", -1),
                         "Wrong count returned")


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
