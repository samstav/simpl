# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''
import json
import os
import unittest2 as unittest

import mox

from checkmate.deployments import Manager


class TestCount(unittest.TestCase):
    """ Tests getting deployment counts """

    def setUp(self):
        self._mox = mox.Mox()
        self._deployments = json.load(open(os.path.join(
            os.path.dirname(__file__), '../data', 'deployments.json')))
        self.db = self._mox.CreateMockAnything()
        self.controller = Manager({'default': self.db})
        unittest.TestCase.setUp(self)

    def tearDown(self):
        self._mox.UnsetStubs()
        unittest.TestCase.tearDown(self)

    def test_get_count_all(self):
        self.db.get_deployments(tenant_id=None).AndReturn(self._deployments)
        self._mox.ReplayAll()
        self.assertEqual(self.controller.count(), 3)

    def test_get_count_tenant(self):
        # remove the extra deployment
        self._deployments.pop("3fgh")
        self.db.get_deployments(tenant_id="12345").AndReturn(
            self._deployments)
        self._mox.ReplayAll()
        self.assertEqual(self.controller.count(tenant_id="12345"), 2)

    def test_get_count_deployment(self):
        self.db.get_deployments(tenant_id=None).AndReturn(
            self._deployments)
        self._mox.ReplayAll()
        result = self.controller.count(blueprint_id="blp-123-aabc-efg")
        self.assertEqual(result, 2)

    def test_get_count_deployment_and_tenant(self):
        raw_deployments = self._deployments.copy()
        raw_deployments.pop("3fgh")
        self._deployments.pop("2def")
        self._deployments.pop("1abc")
        self.db.get_deployments(tenant_id="854673")\
            .AndReturn(self._deployments)
        self.db.get_deployments(tenant_id="12345").AndReturn(raw_deployments)
        self._mox.ReplayAll()
        result = self.controller.count(blueprint_id="blp-123-aabc-efg",
                                       tenant_id="854673")
        self.assertEquals(result, 1)
        result = self.controller.count(blueprint_id="blp123avc",
                                       tenant_id="12345")
        self.assertEquals(result, 1)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
