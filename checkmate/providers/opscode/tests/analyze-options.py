#!/usr/bin/env python
import argparse
import json
import logging
import os
from string import Template
import sys
import unittest2 as unittest

from prettytable import PrettyTable
from SpiffWorkflow import Workflow
from SpiffWorkflow.specs import Transform, TransMerge

import checkmate.common.tracer  # @UnusedImport # module runs on import
# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate.deployments import Deployment, plan, get_deployments_count, \
        get_deployments_by_bp_count, _deploy, generate_keys
from checkmate.exceptions import CheckmateException
from checkmate.providers.base import PROVIDER_CLASSES
from checkmate.middleware import RequestContext, TokenAuthMiddleware
from checkmate.providers.opscode import local
from checkmate.providers.opscode.local import Transforms
from checkmate.test import StubbedWorkflowBase, ENV_VARS, TestProvider
from checkmate.utils import yaml_to_dict, dict_to_yaml
from checkmate.workflows import create_workflow_deploy, \
        create_workflow_spec_deploy

DEPLOYMENT = None

ARGS = None

def main():
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


class AnalyzeOptionsLogic(StubbedWorkflowBase):
    """Tests the parsing and processing of Chef options

    Requires correctly configured chef-stockton repo"""
    def setUp(self):
        StubbedWorkflowBase.setUp(self)
        # Set up context (with auth if parameters provided)
        self.context = RequestContext()
        if ARGS.username or ARGS.token:
            if ARGS.tenant:
                self.context.tenant = ARGS.tenant
            middleware = TokenAuthMiddleware(None, ARGS.endpoint)
            content = middleware._auth_keystone(self.context, token=ARGS.token,
                                      username=ARGS.username,
                                      apikey=ARGS.apikey)
            self.context.set_context(content)
        # Load deployment
        self.deployment = Deployment(yaml_to_dict(DEPLOYMENT))
        if 'id' not in self.deployment:
            self.deployment['id'] = ARGS.deployment.name[0:32]
        # Load providers (register all if authenticated, else use test stubs)
        if self.context.authenticated is True:
            from checkmate.providers import rackspace, opscode
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
                    PROVIDER_CLASSES['%s.%s' % (vendor, key)] = local.Provider
                else:
                    PROVIDER_CLASSES['%s.%s' % (vendor, key)] = TestProvider

    def skip_test_options_parsing(self):
        try:
            parsed = plan(self.deployment, self.context)
        except Exception as exc:
            print "Deployment error: %s" % exc
            return
        self.assertEqual(parsed['status'], "PLANNED")
        workflow_spec = create_workflow_spec_deploy(parsed, self.context)
        for spec in workflow_spec.task_specs.values():
            if ((isinstance(spec, TransMerge) or
                    isinstance(spec, Transform)) and
                    'collect_options' in spec.get_property('task_tags', [])):
                self.print_options(spec)

    @staticmethod
    def print_options(collect):
        """Prints out options for a task spec"""
        print ("\n*** RUN-TIME OPTIONS ***\n"
               "These values will be evaluated while the workflow runs for "
               "resource %s from provider %s" % (
                collect.get_property('resource'),
                collect.get_property('provider')))
        columns = ["Component", "Name to find", "Where to put in data bag?"]
        table = PrettyTable(columns)
        for column in columns:
            table.align[column] = "l"
        for component, values in collect.properties['options']\
                           ['run_time_options'].iteritems():
            for name, target in values:
                table.add_row([component, name, target])
        print table

        print ("\n*** PLANNING TIME OPTIONS ***\n"
               "These values have already been found and evaluated during "
               "planning.")
        columns = ["Component", "Setting Name", "Value"]
        table = PrettyTable(columns)
        for column in columns:
            table.align[column] = "l"
        for component, values in collect.properties['options']\
                           ['planning_time_options'].iteritems():
            for name, target in values.iteritems():
                table.add_row([component, name, target])
        print table

        print ("\n*** REQUIRED OPTIONS ***\n"
               "The workflow will wait for these options to exist before "
               "proceeding any further.")
        columns = ["Component", "Setting Name"]
        table = PrettyTable(columns)
        for column in columns:
            table.align[column] = "l"
        for component, values in collect.properties['options']\
                           ['planning_time_options'].iteritems():
            if values:
                for value in values:
                    table.add_row([component, value])
        print table

        if '--verbose' in sys.argv or '--debug' in sys.argv:
            print dict_to_yaml(collect.properties['options'])


    def skip_test_options_processing(self):
        try:
            parsed = plan(Deployment(self.deployment), RequestContext())
        except Exception as exc:
            print "Deployment error: %s" % exc
            return
        self.assertEqual(parsed['status'], "PLANNED")
        workflow = self._get_stubbed_out_workflow()
        workflow.complete_next()
        workflow.complete_next()
        for task in workflow.get_tasks():
            print task.id, task.get_state_name(), task.get_name()
        print workflow.get_task(6).attributes
        print workflow.get_task(6).task_spec.properties
        # workflow = create_workflow_deploy(parsed, RequestContext())
        #chef_task = [task for task in workflow.get_tasks()
        #   if task.get_name() == 'Collect Chef Data for 1']
        #print chef_task
        #print json.dumps(parsed._data, indent=2)


if __name__ == '__main__':
    ARGS = main()
    source = ARGS.deployment.read().decode('utf-8')
    t = Template(source)
    variables = {}
    variables.update(os.environ)
    DEPLOYMENT = t.safe_substitute(**variables)
    filtered_args = [sys.argv[0]]
    if ARGS.debug or ARGS.verbose:
        filtered_args.append('--verbose')
    else:
        filtered_args.append('--quiet')
    unittest.main(argv=filtered_args)
