# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''

import unittest2 as unittest
import mox
from mox import IgnoreArg

from checkmate import utils

class TestDeployments(unittest.TestCase):
    """Functional tests for the deployments module"""

    mox = mox.Mox()

    def test_sync_deployments(self):
        """Tests the deployments.sync_deployments method"""
        context = dict(deployment='DEP', resource='0')
        entity = self.mox.CreateMockAnything()
        env = self.mox.CreateMockAnything()
        deployment = self.mox.CreateMockAnything()
        deployment.id = "1234bcdedfed4134b8db7295603c1def"

        driver = self.mox.CreateMockAnything()
        driver.get_deployment(deployment.id).AndReturn(entity)

        Deployment = self.mox.CreateMockAnything()
        Deployment(entity).AndReturn(deployment)

        deployment.environment().AndReturn(env)

        resources = {
                     "0": {
                     'name': 'fake_lb',
                     'provider': 'load-balancer',
                     'type': 'load-balancer',
                     'status': 'ACTIVE',
                     'instance': {
                                  'id': 'fake_lb_id'
                             }
                      }
                     }

        entity.resources = resources

        expected1 = {
                    'instnace:0': {
                                   "status": "ACTIVE"
                                   }
                    }

        expected2 = {
                    "instance:0": {
                                   "status": "ACTIVE",
                                   "instance": {
                                                "statusmsg": ""
                                                }
                                   }
                    }

        provider = self.mox.CreateMockAnything()
        env.select_provider(context, resource=resources["0"].get('type'))\
                                              .AndReturn(provider)
        result = provider.get_resource_status(context, deployment.id,
                                              resources["0"], "0")\
                                              .AndReturn(expected1)

        deployments = self.mox.CreateMockAnything()                      
        results = deployments.write_body(IgnoreArg(), IgnoreArg(),
                                         IgnoreArg()).AndReturn(expected2)
        
        self.mox.ReplayAll()                                 
        self.assertDictEqual(expected2, results)


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])

