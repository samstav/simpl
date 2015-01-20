# pylint: disable=R0904,C0103
# Copyright (c) 2011-2015 Rackspace US, Inc.
#
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

"""Tests for Deployment Patterns."""
import unittest

from checkmate import deployment as cmdep
from checkmate import deployments as cmdeps
from checkmate import exceptions
from checkmate import middleware
from checkmate import utils


class TestDeploymentValidation(unittest.TestCase):
    """Deployment validation works as expected."""

    def test_regex_pattern(self):
        """Test regex pattern validation."""
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
            id: test
            blueprint:
              services: {}
              options:
                test:
                  type: string
                  required: true
                  constraints:
                  - regex:
                      value: patterns.regex.linux_user.required
            environment:
              providers: {}
            inputs:
              blueprint:
                test: root
        """))

        planner = cmdeps.Planner(deployment)
        self.assertEqual(planner.plan(middleware.RequestContext()), {})

    def test_regex_pattern_negative(self):
        """Test regex pattern validation blocks invalid value."""
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
            id: test
            blueprint:
              services: {}
              options:
                test:
                  type: string
                  required: true
                  constraints:
                  - regex:
                      value: patterns.regex.linux_user.non_root
            environment:
              providers: {}
            inputs:
              blueprint:
                test: root
        """))

        planner = cmdeps.Planner(deployment)
        with self.assertRaises(exceptions.CheckmateValidationException):
            planner.plan(middleware.RequestContext())

    def test_regex_pattern_not_required(self):
        """Test regex pattern skips if value not required."""
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
            id: test
            blueprint:
              services: {}
              options:
                test:
                  type: string
                  required: false
                  constraints:
                  - regex:
                      value: patterns.regex.linux_user.required
            environment:
              providers: {}
        """))

        planner = cmdeps.Planner(deployment)
        self.assertEqual(planner.plan(middleware.RequestContext()), {})

    def test_regex_pattern_null_inputs(self):
        """Test regex pattern skips if value is None."""
        deployment = cmdep.Deployment(utils.yaml_to_dict("""
            id: test
            blueprint:
              services: {}
              options:
                test:
                  type: string
                  required: false
                  constraints:
                  - regex:
                      value: patterns.regex.linux_user.required
            environment:
              providers: {}
            inputs:
              blueprint:
                test: null
        """))

        planner = cmdeps.Planner(deployment)
        self.assertEqual(planner.plan(middleware.RequestContext()), {})


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
