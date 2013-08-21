#!/usr/bin/python
# -*- coding: utf-8 -*-
# pylint: disable=C0103,R0903,R0904,W0212,W0232
'''Tests for script provider'''

import logging
import unittest

from checkmate import deployment
from checkmate import deployments
from checkmate import middleware
from checkmate import providers
from checkmate.providers.core import script
from checkmate import test
from checkmate import utils
from checkmate import workflow
from checkmate import workflows

LOG = logging.getLogger(__name__)


class TestScriptProvider(test.ProviderTester):

    klass = script.Provider


class TestSingleWorkflow(test.StubbedWorkflowBase):
    '''Test workflow for a single service works.'''
    def setUp(self):
        self.maxDiff = 1000
        test.StubbedWorkflowBase.setUp(self)
        providers.base.PROVIDER_CLASSES = {}
        providers.register_providers([script.Provider, test.TestProvider])
        self.deployment = \
            deployment.Deployment(utils.yaml_to_dict('''
                id: 'DEP-ID-1000'
                environment:
                  name: Rackspace Open Cloud
                  providers:
                    script:
                      vendor: core
                      catalog:
                        application:
                          openstack:
                            provides:
                            - application: http
                            requires:
                            - host: linux
                            dependencies:
                              script: |
                                apt-get update
                                apt-get install -y git
                                git clone git://github.com/openstack-dev/devst\
ack.git
                                cd devstack
                                echo 'DATABASE_PASSWORD=simple' > localrc
                                echo 'RABBIT_PASSWORD=simple' >> localrc
                                echo 'SERVICE_TOKEN=1111' >> localrc
                                echo 'SERVICE_PASSWORD=simple' >> localrc
                                echo 'ADMIN_PASSWORD=simple' >> localrc
                                ./stack.sh > stack.out
                    base:
                      vendor: test
                      catalog:
                        compute:
                          linux_instance:
                            id: linux_instance
                            is: compute
                            provides:
                            - compute: linux
                blueprint:
                  name: "DevStack"
                  description: "Simple Blueprint for deploying DevStack."
                  services:
                    devstack:
                      component:
                        interface: http
                        type: application
                        name: openstack
                      constraints:
                      - setting: memory
                        resource_type: compute
                        value: 2048
            '''))

    def test_workflow_task_creation(self):
        '''Verify workflow sequence and data flow.'''
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)
        workflow_spec = workflows.WorkflowSpec.create_workflow_spec_deploy(
            self.deployment, context)
        wf = workflow.init_spiff_workflow(
            workflow_spec, self.deployment, context)
        task_list = wf.spec.task_specs.keys()
        expected = ['Root',
                    'Start',
                    'Create Resource 1',
                    'Execute Script 0 (1)',
                    ]
        task_list.sort()
        expected.sort()
        self.assertListEqual(task_list, expected, msg=task_list)
        self.mox.VerifyAll()


if __name__ == '__main__':

    # Run tests. Handle our parameters separately

    import sys
    args = sys.argv[:]

    # Our --debug means --verbose for unitest

    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
