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

"""Module for testing Rackspace compute provider interactions."""

from checkmate import consts
from checkmate import deployment
from checkmate.deployments import Planner, Manager
from checkmate.middleware import RequestContext
from checkmate.providers import base
from checkmate.providers.rackspace.compute import provider as compute
from checkmate import test
from checkmate import utils
from checkmate import workflow as cm_wf
from checkmate import workflow_spec


class TestOnMetalKeyPairs(test.StubbedWorkflowBase):

    """An OnMetal compute node gets a nova key-pair."""

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        base.register_providers([compute.Provider])
        self.deployment = deployment.Deployment(utils.yaml_to_dict('''
                id: 'DEP-ID-1000'
                tenantId: T1000
                blueprint:
                  name: Test
                  services:
                    screaming:
                      component:
                        resource_type: compute
                        interface: ssh
                      constraints:
                      - virtualization-mode: metal
                      - os: Ubuntu 14.04
                      - count: 2
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
                        lists:
                          regions:
                            North: https://north.servers./v2/T1000
                          sizes:
                            onmetal-compute1:
                              cores: 20
                              disk: 32
                              extra:
                                class: onmetal
                                policy_class: onmetal_flavor
                              memory: 32768
                              name: OnMetal Compute v1
                              network: 10000.0
                          types:
                            1f097471-f0f4-4c3b-ac24-fdb1d897b8c0:
                              constraints:
                                auto_disk_config: disabled
                                flavor_classes: onmetal
                                vm_mode: metal
                              name: OnMetal - Ubuntu 14.04 LTS (Trusty Tahr)
                              os: Ubuntu 14.04
                              type: linux
                inputs:
                  region: North
            '''))

    def tearDown(self):
        pass

    def test_workflow_resource_generation(self):
        """Test Resources Added"""
        context = RequestContext(auth_token='MOCK_TOKEN', username='MOCK_USER',
                                 region="North", tenant="T1000")
        planner = Planner(self.deployment, parse_only=True)
        resources = planner.plan(context)
        types = []
        server = None
        keypair = None
        expected_name = 'Public Key for Deployment DEP-ID-1000'
        for resource in resources.values():
            if resource['type'] == 'compute':
                server = resource
            if resource['type'] == 'key-pair':
                keypair = resource
            types.append(resource['type'])
        self.assertItemsEqual(types, ['key-pair', 'compute', 'compute'])
        self.assertEqual(server['desired-state']['key_name'], expected_name)
        self.assertEqual(server['component'], 'linux_instance')
        self.assertEqual(server['provider'], 'nova')
        self.assertEqual(keypair['component'], 'rax:key-pair')
        self.assertEqual(keypair['provider'], 'nova')
        self.assertEqual(keypair['desired-state']['region'], 'North')
        dep_key = self.deployment.get_keypair(
            consts.DEFAULT_KEYPAIR)
        self.assertEqual(keypair['desired-state']['public_key_ssh'],
                         dep_key['public_key_ssh'])

    def test_workflow_resource_task_generation(self):
        """Test Task Addition and Dependencies.

        - Ensure all tasks are there for key and server creation.
        - Ensure only one key-pair upload tasks exists.
        - Ensure all servers will wait for key-pair to be loaded.
        """
        context = RequestContext(auth_token='MOCK_TOKEN', username='MOCK_USER',
                                 region="North", tenant="T1000")
        Manager.plan(self.deployment, context)
        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(
            context, self.deployment)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, self.deployment, context, "w_id", "BUILD")

        task_list = workflow.spec.task_specs.keys()
        expected = [
            'Root',
            'Start',

            'Upload Keypair to North',

            'Create Server 0 (screaming)',
            'Wait for Server 0 (screaming) build',
            'Verify server 0 (screaming) ssh connection',

            'Create Server 1 (screaming)',
            'Wait for Server 1 (screaming) build',
            'Verify server 1 (screaming) ssh connection',
        ]
        self.assertItemsEqual(task_list, expected, msg=task_list)
        upload_spec = workflow.spec.task_specs['Upload Keypair to North']
        self.assertIn(
            upload_spec,
            workflow.spec.task_specs['Create Server 0 (screaming)'].inputs)
        self.assertIn(
            upload_spec,
            workflow.spec.task_specs['Create Server 1 (screaming)'].inputs)


if __name__ == '__main__':
    test.run_with_params()
