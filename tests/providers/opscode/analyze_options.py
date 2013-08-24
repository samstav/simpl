#!/usr/bin/env python
# pylint: disable=E0602,E1102,W0703

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

"""Tests for options analysis."""
import argparse
import logging
import os
import string
import sys
import unittest

import prettytable as ptbl
from SpiffWorkflow import specs

import checkmate.common.tracer  # pylint: disable=W0611
from checkmate import deployment as cmdep
from checkmate.deployments import planner
from checkmate import middleware as cmmid
from checkmate.providers import base
from checkmate import test
from checkmate import utils

LOG = logging.getLogger(__name__)

DEPLOYMENT = None

ARGS = None


def main():
    """Entry point."""
    epilog = ["Environment Settings:"]
    for key in os.environ:
        if key.startswith('CHECKMATE_') or key.startswith('CELERY'):
            if key.startswith('CHECKMATE_CLIENT'):
                pass  # used for client/test calls, not the server
            else:
                epilog.append("%s=%s" % (key, os.environ[key]))

    parser = argparse.ArgumentParser(description="Checkmate Chef-Local "
                                     "Options Analyzer",
                                     epilog='\n'.join(epilog))
    parser.add_argument('deployment', type=argparse.FileType('r'),
                        help='the deployment to analyze as a YAML file')
    parser.add_argument('--repo', type=argparse.FileType('r'),
                        help='path to cookbooks repository')
    parser.add_argument('--token', help='Keystone/Rackspace auth token. Also '
                        'needs --tenant to be passed in')
    parser.add_argument('--tenant', help='tenant ID needed with --auth-token')
    parser.add_argument('--username', help='Username. Provide --password or '
                        '--apikey with this parameter')
    parser.add_argument('--apikey', help='Rackspace Auth API key')
    parser.add_argument('--password', help='Password.')
    parser.add_argument('--auth-url', dest='endpoint',
                        help='Keystone/Identity Service URL (include '
                        '.../v2.0/tokens at end)',
                        default='https://identity.api.rackspacecloud.com/'
                        'v2.0/tokens')
    parser.add_argument('--quiet', help='turn down logging to WARN '
                        '(default is INFO)', action='store_true')
    parser.add_argument('--verbose', help='turn up logging to DEBUG '
                        '(default is INFO)', action='store_true')
    parser.add_argument('--debug', help='turn on additional debugging '
                        'inspection and output including full HTTP requests '
                        'and responses. Log output includes source file path '
                        'and line numbers.', action='store_true')
    parser.add_argument('--trace-calls', '-t', help='display call '
                        'hierarchy and errors to stdout', action='store_true')
    return parser.parse_args()


class AnalyzeOptionsLogic(test.StubbedWorkflowBase):
    """Tests the parsing and processing of Chef options

    Requires correctly configured chef-stockton repo
    """
    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        # Set up context (with auth if parameters provided)
        self.context = cmmid.RequestContext()
        if ARGS.username or ARGS.token:
            if ARGS.tenant:
                self.context.tenant = ARGS.tenant
            middleware = cmmid.TokenAuthMiddleware(None, ARGS.endpoint)
            content = middleware.auth_keystone(tenant=self.context,
                                               token=ARGS.token,
                                               username=ARGS.username,
                                               apikey=ARGS.apikey,
                                               auth_url=None)
            self.context.set_context(content)
        # Load deployment
        self.deployment = cmdep.Deployment(utils.yaml_to_dict(DEPLOYMENT))
        if 'id' not in self.deployment:
            self.deployment['id'] = ARGS.deployment.name[0:32]
        # Load providers (register all if authenticated, else use test stubs)
        if self.context.authenticated is True:
            from checkmate.providers import opscode
            from checkmate.providers import rackspace
            rackspace.register()
            opscode.register()
        else:
            providers = self.deployment.get('environment', {}).get('providers',
                                                                   {})
            default_vendor = None
            if 'common' in providers:
                default_vendor = providers['common'].get('vendor')
            for key, provider in providers.iteritems():
                vendor = provider.get('vendor', default_vendor)
                if key == 'chef-local' and vendor == 'opscode':
                    base.PROVIDER_CLASSES['%s.%s' % (vendor, key)] = (
                        local.Provider)
                else:
                    base.PROVIDER_CLASSES['%s.%s' % (vendor, key)] = (
                        test.TestProvider)

    def skip_test_options_parsing(self):
        """Create planner without parsing options."""
        try:
            parsed = planner(self.deployment, self.context)
        except Exception as exc:
            print("Deployment error: %s" % exc)
            return
        self.assertEqual(parsed['status'], "PLANNED")
        workflow_spec = create_workflow_spec_deploy(parsed,
                                                    self.context)
        for spec in workflow_spec.task_specs.values():
            if ((isinstance(spec, specs.TransMerge) or
                    isinstance(spec, specs.Transform)) and
                    'collect_options' in spec.get_property('task_tags', [])):
                self.print_options(spec)

    @staticmethod
    def print_options(collect):
        """Prints out options for a task spec."""
        print(
            "\n*** RUN-TIME OPTIONS ***\n"
            "These values will be evaluated while the workflow runs for "
            "resource %s from provider %s" % (
            collect.get_property('resource'), collect.get_property('provider'))
        )
        columns = ["Component", "Name to find", "Where to put in data bag?"]
        table = ptbl.PrettyTable(columns)
        for column in columns:
            table.align[column] = "l"
        for component, values in (
            collect.properties['options']['run_time_options'].iteritems()
        ):
            for name, target in values:
                table.add_row([component, name, target])
        print(table)

        print("\n*** PLANNING TIME OPTIONS ***\n"
              "These values have already been found and evaluated during "
              "planning.")
        columns = ["Component", "Setting Name", "Value"]
        table = ptbl.PrettyTable(columns)
        for column in columns:
            table.align[column] = "l"
        for component, values in (
            collect.properties['options']['planning_time_options'].iteritems()
        ):
            for name, target in values.iteritems():
                table.add_row([component, name, target])
        print(table)

        print("\n*** REQUIRED OPTIONS ***\n"
              "The workflow will wait for these options to exist before "
              "proceeding any further.")
        columns = ["Component", "Setting Name"]
        table = ptbl.PrettyTable(columns)
        for column in columns:
            table.align[column] = "l"
        for component, values in (
            collect.properties['options']['planning_time_options'].iteritems()
        ):
            if values:
                for value in values:
                    table.add_row([component, value])
        print(table)

        if '--verbose' in sys.argv or '--debug' in sys.argv:
            print(utils.dict_to_yaml(collect.properties['options']))

    def skip_test_options_processing(self):
        """Setup a deployment without processing options."""
        try:
            parsed = planner(
                cmdep.Deployment(self.deployment), cmmid.RequestContext())
        except Exception as exc:
            print("Deployment error: %s" % exc)
            return
        self.assertEqual(parsed['status'], "PLANNED")
        workflow = self._get_stubbed_out_workflow()
        workflow.complete_next()
        workflow.complete_next()
        for task in workflow.get_tasks():
            print(task.id, task.get_state_name(), task.get_name())
        print(workflow.get_task(6).attributes)
        print(workflow.get_task(6).task_spec.properties)


if __name__ == '__main__':
    ARGS = main()
    SOURCE = ARGS.deployment.read().decode('utf-8')
    TEMPLATE = string.Template(SOURCE)
    VARIABLES = {}
    VARIABLES.update(os.environ)
    DEPLOYMENT = TEMPLATE.safe_substitute(**VARIABLES)
    FILTERED_ARGS = [sys.argv[0]]
    if ARGS.debug or ARGS.verbose:
        FILTERED_ARGS.append('--verbose')
    else:
        FILTERED_ARGS.append('--quiet')
    unittest.main(argv=FILTERED_ARGS)
