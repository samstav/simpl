#!/usr/bin/python
# -*- coding: utf-8 -*-
# pylint: disable=R0904,C0103

# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Tests for script provider."""

import logging
import unittest

from checkmate import deployment
from checkmate import deployments
from checkmate import middleware
from checkmate.providers import base
from checkmate.providers.core import script
from checkmate import test
from checkmate import utils
from checkmate import workflow
from checkmate import workflow_spec as cmwfspec

LOG = logging.getLogger(__name__)


class TestScriptProvider(test.ProviderTester):

    klass = script.Provider


class TestResources(unittest.TestCase):

    def setUp(self):
        base.PROVIDER_CLASSES = {}
        base.register_providers([script.Provider, test.TestProvider])
        self.deployment = deployment.Deployment(utils.yaml_to_dict("""
                id: 'DEP-ID-1000'
                tenantId: T1000
                environment:
                  name: Rackspace Open Cloud
                  providers:
                    script:
                      vendor: core
                      catalog:
                        application:
                          foo:
                            provides:
                            - application: http
                            requires:
                            - host: linux
                            properties:
                              scripts:
                                install: |
                                    apt-get update
                                    apt-get install -y git
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
                  description: "Simple Blueprint."
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
            """))

    def test_resource_creation(self):
        planner = deployments.Planner(self.deployment, parse_only=True)
        resources = planner.plan(middleware.RequestContext())
        self.assertEqual(len(resources), 2)

        apps = [r for r in resources.values() if 'hosts' not in r]
        self.assertEqual(len(apps), 1)
        app = apps[0]

        self.assertEqual(app['type'], 'application')
        self.assertEqual(app['provider'], 'script')
        self.assertEqual(app['component'], 'foo')


class TestScriptTasks(unittest.TestCase):

    def setUp(self):
        self.context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                                 username='MOCK_USER')
        base.PROVIDER_CLASSES = {}
        base.register_providers([script.Provider, test.TestProvider])

        self.deployment = deployment.Deployment(utils.yaml_to_dict("""
            id: 'DEP-ID-1000'
            tenantId: T1000
            environment:
              name: Rackspace Open Cloud
              providers:
                script:
                  vendor: core
                  constraints:
                  - timeout: 600
                  catalog:
                    application:
                      openstack:
                        provides:
                        - application: http
                        requires:
                        - host: linux
                        properties:
                          scripts:
                            install: |
                                apt-get update
                                apt-get install -y git
                                git clone git://github.com/openstack-dev/\
devstack.git
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
        """))

    def test_install_script(self):
        """Verify workflow includes the supplied install script run."""
        deployments.Manager.plan(self.deployment, self.context)
        workflow_spec = cmwfspec.WorkflowSpec\
            .create_build_spec(self.context, self.deployment)
        spec = workflow_spec.task_specs['Execute Script 0 (1)']
        provider = self.deployment['environment']['providers']['script']
        component = provider['catalog']['application']['openstack']
        script_body = component['properties']['scripts']['install']
        self.assertEqual(spec.kwargs['install_script'], script_body)

    def test_timeout_constraint(self):
        """Verify workflow PICKED UP TIMEOUT CONSTRAINT."""
        deployments.Manager.plan(self.deployment, self.context)
        workflow_spec = cmwfspec.WorkflowSpec\
            .create_build_spec(self.context, self.deployment)
        spec = workflow_spec.task_specs['Execute Script 0 (1)']
        self.assertEqual(spec.kwargs['timeout'], 600)


class TestScriptParameters(unittest.TestCase):
    """Test script parameter resolution."""

    def setUp(self):
        self.context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                                 username='MOCK_USER')
        base.PROVIDER_CLASSES = {}
        base.register_providers([script.Provider, test.TestProvider])

        self.deployment = deployment.Deployment(utils.yaml_to_dict("""
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
                              template: '{{something}}/{{test}}/{{seek}}'
                              parameters:
                                something:
                                  value: 1
                                test:
                                  value: inputs://test
                                seek:
                                  value: settings://other
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
              other: y
        """))

    def test_install_script(self):
        """Verify workflow includes the supplied install script run."""
        deployments.Manager.plan(self.deployment, self.context)
        workflow_spec = cmwfspec.WorkflowSpec\
            .create_build_spec(self.context, self.deployment)
        spec = workflow_spec.task_specs['Execute Script 0 (1)']
        self.assertEqual(spec.kwargs['install_script'], "1/x/y")


class TestSingleWorkflow(test.StubbedWorkflowBase):
    """Test workflow for a single service works."""
    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        base.register_providers([script.Provider, test.TestProvider])
        self.deployment = \
            deployment.Deployment(utils.yaml_to_dict("""
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
                            properties:
                              scripts:
                                install: |
                                    apt-get update
                                    apt-get install -y git
                                    git clone git://github.com/openstack-dev/\
devstack.git
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
            """))
        self.deployment['tenantId'] = 'tenantId'

    def test_workflow_task_creation(self):
        """Verify workflow sequence and data flow."""
        context = middleware.RequestContext(auth_token='MOCK_TOKEN',
                                            username='MOCK_USER')
        deployments.Manager.plan(self.deployment, context)
        workflow_spec = cmwfspec.WorkflowSpec.create_build_spec(
            context, self.deployment)
        wflow = workflow.init_spiff_workflow(
            workflow_spec, self.deployment, context, "w_id", "BUILD")
        task_list = wflow.spec.task_specs.keys()
        expected = [
            'Root',
            'Start',
            'Create Resource 1',
            'Execute Script 0 (1)',
        ]
        self.assertItemsEqual(task_list, expected, msg=task_list)
        self.mox.VerifyAll()


if __name__ == '__main__':
    test.run_with_params()
