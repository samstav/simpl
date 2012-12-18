#!/usr/bin/env python
"""Tests for chef-solo provider"""
import logging
import unittest2 as unittest

from mox import In, IsA, And, IgnoreArg, ContainsKeyValue, Not

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

from checkmate import test, utils
from checkmate.deployments import Deployment
from checkmate.providers import base, register_providers
from checkmate.providers.opscode import solo


class TestChefSolo(test.ProviderTester):
    klass = solo.Provider


class TestDBWorkflow(test.StubbedWorkflowBase):
    """ Test MySQL Resource Creation Workflow """

    def setUp(self):
        test.StubbedWorkflowBase.setUp(self)
        base.PROVIDER_CLASSES = {}
        register_providers([solo.Provider, test.TestProvider])
        self.deployment = Deployment(utils.yaml_to_dict("""
                id: 'DEP-ID-1000'
                blueprint:
                  name: test db
                  services:
                    db:
                      component:
                        id: mysql
                        is: database
                        type: database
                environment:
                  name: test
                  providers:
                    chef-solo:
                      vendor: opscode
                      provides:
                      - database: mysql
                      catalog:
                        database:
                          mysql:
                            id: mysql
                            provides:
                            - database: mysql
                            requires:
                            - host: 'linux'
                    base:
                      vendor: test
                      provides:
                      - compute: linux
                      catalog:
                        compute:
                          linux_instance:
                            id: linux_instance
                            is: compute
                            provides:
                            - compute: linux
                inputs:
                  blueprint:
                    region: DFW
            """))
        expected = []
        # Create Chef Environment
        expected.append({
                # Use chef-solo tasks for now
                'call': 'checkmate.providers.opscode.local.create_environment',
                # Use only one kitchen. Call it "kitchen" like we used to
                'args': [self.deployment['id'], 'kitchen'],
                'kwargs': And(ContainsKeyValue('private_key', IgnoreArg()),
                        ContainsKeyValue('secret_key', IgnoreArg()),
                        ContainsKeyValue('public_key_ssh', IgnoreArg()),
                        ContainsKeyValue('source_repo', IgnoreArg())),
                'result': {
                    'environment': '/var/tmp/%s/' % self.deployment['id'],
                    'kitchen': '/var/tmp/%s/kitchen' % self.deployment['id'],
                    'private_key_path': '/var/tmp/%s/private.pem' %
                            self.deployment['id'],
                    'public_key_path': '/var/tmp/%s/checkmate.pub' %
                            self.deployment['id'],
                    'public_key': test.ENV_VARS['CHECKMATE_CLIENT_PUBLIC_KEY']}
            })
        expected.append({
                    'call': 'checkmate.providers.test.create_resource',
                    'args': [IsA(dict),
                            {'index': '0', 'component': 'linux_instance',
                            'dns-name': 'CM-DEP-ID--db1.checkmate.local',
                            'instance': {}, 'hosts': ['1'], 'provider': 'base',
                            'type': 'compute', 'service': 'db'}],
                    'kwargs': None,
                    'result': {
                            'instance:0': {
                                'status': "ACTIVE",
                                'ip': '4.4.4.1',
                                'private_ip': '10.1.2.1',
                                'addresses': {
                                  'public': [
                                    {
                                      "version": 4,
                                      "addr": "4.4.4.1",
                                    },
                                    {
                                      "version": 6,
                                      "addr": "2001:babe::ff04:36c1",
                                    }
                                  ],
                                  'private': [
                                    {
                                      "version": 4,
                                      "addr": "10.1.2.1",
                                    }
                                  ]
                                }
                            }
                        },
                    'post_back_result': True,
                })
        expected.append({
                'call': 'checkmate.providers.opscode.local.register_node',
                'args': ["4.4.4.1", self.deployment['id']],
                'kwargs': In('password'),
                'result': None,
                'resource': '1',
            })
        # build-essential (now just cook with bootstrap.json)
        expected.append({
                'call': 'checkmate.providers.opscode.local.cook',
                'args': ["4.4.4.1", self.deployment['id']],
                'kwargs': And(In('password'),
                              Not(In('recipes')),
                              Not(In('roles')),
                              ContainsKeyValue('identity_file',
                                        '/var/tmp/%s/private.pem' %
                                        self.deployment['id'])),
                'result': None,
                'resource': '1',
            })
        # Cook with role
        expected.append(
            {
                'call': 'checkmate.providers.opscode.local.cook',
                'args': ["4.4.4.1", self.deployment['id']],
                'kwargs': And(In('password'), ContainsKeyValue('recipes',
                        ["mysql::server"]),
                        ContainsKeyValue('identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id'])),
                'result': None,
                'resource': '1',
            })
        expected.append({
                'call': 'checkmate.providers.opscode.local.manage_databag',
                'args': [self.deployment['id'],
                        self.deployment['id'],
                        None,
                        None],
                'kwargs': And(ContainsKeyValue('secret_file',
                        'certificates/chef.pem'), ContainsKeyValue('merge',
                        True)),
                'result': None
            })
        self.workflow = self._get_stubbed_out_workflow(expected_calls=expected)

    def test_workflow_completion(self):
        """Verify workflow sequence and data flow"""

        self.mox.ReplayAll()

        self.workflow.complete_all()
        self.assertTrue(self.workflow.is_completed(), "Workflow did not "
                        "complete")


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
