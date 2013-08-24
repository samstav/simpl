# Copyright (c) 2011-2013 Rackspace Hosting
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

"""Tests for the Deployments class."""
import unittest

import mox


class TestDeployments(unittest.TestCase):
    """Functional tests for the deployments module."""

    mox = mox.Mox()

    def test_sync_deployments(self):
        """Tests the deployments.sync_deployments method."""
        context = dict(deployment='DEP', resource='0')
        entity = self.mox.CreateMockAnything()
        env = self.mox.CreateMockAnything()
        deployment = self.mox.CreateMockAnything()
        deployment.id = "1234bcdedfed4134b8db7295603c1def"

        driver = self.mox.CreateMockAnything()
        driver.get_deployment(deployment.id).AndReturn(entity)

        mock_deployment = self.mox.CreateMockAnything()
        mock_deployment(entity).AndReturn(deployment)

        deployment.environment().AndReturn(env)

        resources = {
            "0": {
                'name': 'fake_lb',
                'provider': 'load-balancer',
                'type': 'load-balancer',
                'status': 'ACTIVE',
                'instance': {'id': 'fake_lb_id'}
            }
        }

        entity.resources = resources

        expected1 = {
            'instance:0': {
                "status": "ACTIVE"
            }
        }

        expected2 = {
            "instance:0": {
                "status": "ACTIVE",
                "instance": {
                    "status-message": ""
                }
            }
        }

        provider = self.mox.CreateMockAnything()
        env.select_provider(context, resource=resources["0"].get('type'))\
            .AndReturn(provider)
        provider.get_resource_status(context, deployment.id,
                                     resources["0"], "0").AndReturn(expected1)

        deployments = self.mox.CreateMockAnything()
        results = deployments.write_body(mox.IgnoreArg(), mox.IgnoreArg(),
                                         mox.IgnoreArg()).AndReturn(expected2)

        self.mox.ReplayAll()
        self.assertDictEqual(expected2, results)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
