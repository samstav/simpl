# pylint: disable=R0904,C0103
# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#
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

"""Module for testing Rackspace interactions."""

from checkmate import deployment
from checkmate.deployments import Planner, Manager
from checkmate.middleware import RequestContext
from checkmate.providers import base
from checkmate.providers.rackspace.compute import provider as compute
from checkmate.providers.rackspace.block import provider as block
from checkmate import test
from checkmate import utils
from checkmate import workflow as cm_wf
from checkmate import workflow_spec


class TestComputeWithBlock(test.StubbedWorkflowBase):

    """A compute node gets attached to block."""

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        base.register_providers([compute.Provider, block.Provider])
        self.deployment = deployment.Deployment(utils.yaml_to_dict('''
                id: 'DEP-ID-1000'
                tenantId: T1000
                blueprint:
                  name: Test
                  services:
                    with_block:
                      component:
                        resource_type: compute
                        interface: ssh
                      constraints:
                      - resource_type: volume
                        setting: dedicated
                        value: true
                environment:
                  name: test
                  providers:
                    nova:
                      vendor: rackspace
                      catalog:
                        compute:
                          linux_instance:
                            is: compute
                            provides:
                            - compute: ssh
                            supports:
                            - volume: iscsi
                        lists:
                          regions:
                            North: https://north.servers./v2/T1000
                          sizes:
                            'compute1-15':
                              cores: 4
                              disk: 0
                              memory: 512
                              name: 512MB Compute Instance
                              extra:
                                class: compute1
                          types:
                            06f917b0-9c0f-4634-8190-e43630bb0000:
                              name: 'Ubuntu 14.04'
                              os: 'Ubuntu 14.04'
                              type: linux
                              constraints:
                                flavor_classes: '*'
                    block:
                      vendor: rackspace
                inputs:
                  region: North
            '''))

    def tearDown(self):
        pass

    def test_workflow_resource_generation(self):
        """Test esources Added"""
        context = RequestContext(auth_token='MOCK_TOKEN', username='MOCK_USER',
                                 region="North")
        planner = Planner(self.deployment, parse_only=True)
        resources = planner.plan(context)
        types = []
        server = None
        volume = None
        for resource in resources.values():
            if resource['type'] == 'compute':
                server = resource
            if resource['type'] == 'volume':
                volume = resource
            types.append(resource['type'])
        self.assertItemsEqual(types, ['volume', 'compute'])
        self.assertIn('cbs-attach-1', server['relations'])
        self.assertTrue(server['desired-state']['boot_from_image'])
        self.assertEqual(server['component'], 'linux_instance')
        self.assertEqual(server['provider'], 'nova')
        self.assertEqual(volume['component'], 'rax:block_volume')
        self.assertEqual(volume['provider'], 'block')

    def test_workflow_resource_task_generation(self):
        """Test Add Task"""
        context = RequestContext(auth_token='MOCK_TOKEN', username='MOCK_USER',
                                 region="North")
        Manager.plan(self.deployment, context)
        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(
            context, self.deployment)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, self.deployment, context, "w_id", "BUILD")

        task_list = workflow.spec.task_specs.keys()
        expected = [
            'Root',
            'Start',

            'Create Volume 1',
            'Wait for Volume 1 (with_block) build',

            'Create Server 0 (with_block)',
            'Wait for Server 0 (with_block) build',

            'Attach (with_block) Wait on 0 and 1',
            'Attach Server 0 to Volume 1',

            'Server Wait on Attach:0 (with_block)',
            'Verify server 0 (with_block) ssh connection',
        ]
        self.assertItemsEqual(task_list, expected, msg=task_list)


if __name__ == '__main__':
    test.run_with_params()
