# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method
'''
import os
import unittest2 as unittest

import mox

os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'
from checkmate import deployments


class TestAPICalls(unittest.TestCase):

    def setUp(self):
        os.environ['CHECKMATE_CONNECTION_STRING'] = 'sqlite://'
        reload(deployments)
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_created_by_assigned(self):
        req = self.mox.CreateMockAnything()
        req.context = self.mox.CreateMockAnything()
        req.context.username = 'john'
        self.mox.StubOutWithMock(deployments, 'read_body')
        deployments.read_body(req).AndReturn({})
        self.mox.ReplayAll()
        result = deployments._content_to_deployment(req, deployment_id="1",
                                                    tenant_id="A")
        self.mox.VerifyAll()
        self.assertIn('created', result)
        expected = {
            'status': 'NEW',
            'tenantId': 'A',
            'created-by': 'john',
            'id': '1',
            'created': result['created'],
        }
        self.assertDictEqual(result._data, expected)

    def test_created_not_overwritten(self):
        req = self.mox.CreateMockAnything()
        req.context = self.mox.CreateMockAnything()
        req.context.username = 'john'
        self.mox.StubOutWithMock(deployments, 'read_body')
        deployments.read_body(req).AndReturn({'created-by': 'tom'})
        self.mox.ReplayAll()
        result = deployments._content_to_deployment(req, deployment_id="1",
                                                    tenant_id="A")
        self.mox.VerifyAll()
        self.assertEqual(result['created-by'], 'tom')


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
