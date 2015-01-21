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

"""Module for testing script.manager."""

import mock
import mox

from checkmate import deployment
from checkmate.deployments import Planner
from checkmate import providers
from checkmate.providers.core import script
from checkmate import test
from checkmate import utils
from checkmate import workflow as cm_wf
from checkmate import workflow_spec


class TestDeployment(test.StubbedWorkflowBase):

    """A simple deployment parses and executes the right scripts."""

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        providers.base.PROVIDER_CLASSES = {}
        providers.register_providers([script.Provider, test.TestProvider])
        self.deployment = deployment.Deployment(utils.yaml_to_dict('''
                id: 'DEP-ID-1000'
                tenantId: T1000
                blueprint:
                  name: MySQL Database
                  services:
                    db:
                      component:
                        resource_type: database
                        interface: mysql
                environment:
                  name: test
                  providers:
                    script:
                      vendor: core
                      catalog:
                        database:
                          mysql:
                            provides:
                            - database: mysql
                            requires:
                            - host: linux
                            properties:
                              scripts:
                                install:
                                  template: 'test {{something}} on {{test}}'
                                  parameters:
                                    something:
                                      value: 1
                                    test:
                                      value: inputs://test
                                    # TODO:
                                    # host_ip:
                                    #   value: requirements://host/ip
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            provides:
                            - compute: linux
                inputs:
                  test: x
            '''))

    def tearDown(self):
        pass

    def test_resource_creation(self):
        provider = script.Provider({})
        context = mock.Mock()

        expected = [{
            'service': 'db',
            'provider': 'core.script',
            'dns-name': 'db01.checkmate.local',
            'instance': {},
            'desired-state': {},
            'type': 'application',
        }]

        results = provider.generate_template(self.deployment, 'application',
                                             'db', context, 1, provider.key,
                                             None)

        self.assertItemsEqual(results, expected)

    def test_workflow_resource_task_generation(self):
        """Test Add Task"""
        context = dict(auth_token='MOCK_TOKEN', username='MOCK_USER',
                       region="North")
        planner = Planner(self.deployment)
        resources = planner.plan(context)
        print resources
        wf_spec = workflow_spec.WorkflowSpec.create_build_spec(
            context, self.deployment)
        workflow = cm_wf.init_spiff_workflow(
            wf_spec, self.deployment, context, "w_id", "BUILD")

        task_list = workflow.spec.task_specs.keys()
        expected = ['Root', 'Start', 'Create Resource 1',
                    'Execute Script 0 (1)']
        self.assertItemsEqual(task_list, expected, msg=task_list)

    def test_workflow_completion(self):
        """."""
        expected = []

        expected = [{
            # Create Chef Environment
            'call': 'checkmate.deployments.workspaces.create_workspace',
            'args': [mox.ContainsKeyValue('auth_token', mox.IgnoreArg()),
                     self.deployment['id']],
            'kwargs': mox.IgnoreArg(),
            'result': {
                'workspace': '/var/tmp/%s/' % self.deployment['id'],
            }
        }]

        for key, resource in self.deployment['resources'].iteritems():
            if resource['type'] == 'compute':
                expected.append({
                    'call': 'checkmate.providers.test.create_resource',
                    'args': [mox.IsA(dict), resource],
                    'kwargs': None,
                    'result': {
                        'resources': {
                            key: {
                                'instance': {
                                    'status': 'ACTIVE',
                                    'ip': '4.4.4.1',
                                    'private_ip': '10.1.2.1',
                                    'addresses': {
                                        'public': [
                                            {'version': 4, 'addr': '4.4.4.1'},
                                            {
                                                'version': 6,
                                                'addr': '2001:babe::ff04:36c1'
                                            }
                                        ],
                                        'private': [{
                                            'version': 4,
                                            'addr': '10.1.2.1'
                                        }]
                                    },
                                }
                            }
                        }
                    },
                    'post_back_result': True,
                })
            else:
                # Run script
                expected.append({
                    'call': 'checkmate.providers.core.script.tasks'
                            '.create_resource',
                    'args': [
                        mox.ContainsKeyValue('auth_token', "MOCK_TOKEN"),
                        self.deployment['id'],
                        mox.And(
                            mox.ContainsKeyValue('index', '0'),
                            mox.ContainsKeyValue('hosted_on', '1')
                        ),
                        '4.4.4.1',
                        'root'
                    ],
                    'kwargs': mox.And(
                        mox.In('password'),
                        mox.ContainsKeyValue(
                            'identity_file',
                            '/var/tmp/%s/private.pem' % self.deployment['id']
                        )
                    ),
                    'result': None,
                    'resource': key,
                })

        workflow = self._get_stubbed_out_workflow(expected_calls=expected)
        self.mox.ReplayAll()
        workflow.complete_all()
        self.assertTrue(workflow.is_completed(), 'Workflow did not complete')
        self.mox.VerifyAll()

if __name__ == '__main__':
    test.run_with_params()
