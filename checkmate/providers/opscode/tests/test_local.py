#!/usr/bin/env python
import __builtin__
import json
import logging
import os
import shutil
import unittest2 as unittest
import uuid

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

import mox
from mox import IsA, In, And, Or, IgnoreArg, ContainsKeyValue, Func, \
        StrContains

from checkmate.deployments import Deployment
from checkmate.exceptions import CheckmateException
from checkmate.providers.base import PROVIDER_CLASSES
from checkmate.providers.opscode import local
from checkmate.test import StubbedWorkflowBase, ENV_VARS
from checkmate.utils import yaml_to_dict


class TestChefLocal(unittest.TestCase):
    """ Test ChefLocal Module """

    @classmethod
    def setUpClass(cls):
        os.environ['CHECKMATE_CHEF_LOCAL_PATH'] = '/tmp/checkmate/test'
        if not os.path.exists(os.environ['CHECKMATE_CHEF_LOCAL_PATH']):
            shutil.os.makedirs(os.environ['CHECKMATE_CHEF_LOCAL_PATH'])
            local.create_environment('test_env')

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_cook_missing_role(self):
        results = """Checking cookbook syntax...
[Mon, 21 May 2012 17:25:54 +0000] INFO: *** Chef 0.10.10 ***
[Mon, 21 May 2012 17:25:55 +0000] INFO: Setting the run_list to ["role[build]", "role[wordpress-web]"] from JSON
[Mon, 21 May 2012 17:25:55 +0000] ERROR: Role build is in the runlist but does not exist. Skipping expand.
[Mon, 21 May 2012 17:25:55 +0000] ERROR: Role wordpress-web is in the runlist but does not exist. Skipping expand.
[Mon, 21 May 2012 17:25:55 +0000] FATAL: Stacktrace dumped to /tmp/checkmate/environments/myEnv/chef-stacktrace.out
[Mon, 21 May 2012 17:25:55 +0000] FATAL: Chef::Exceptions::MissingRole: Chef::Exceptions::MissingRole
"""
        params = ['knife', 'cook', 'root@a.b.c.d', '-p', '22']

        #Stub out checks for paths
        self.mox.StubOutWithMock(os.path, 'exists')
        os.path.exists('/tmp/checkmate/test').AndReturn(True)
        os.path.exists('/tmp/checkmate/test/myEnv/kitchen').AndReturn(True)
        os.path.exists('/tmp/checkmate/test/myEnv/kitchen/nodes/a.b.c.d.json')\
                .AndReturn(True)

        #Stub out file access
        mock_file = self.mox.CreateMockAnything()
        mock_file.__enter__().AndReturn(mock_file)
        mock_file.__exit__(None, None, None).AndReturn(None)

        #Stub out file reads
        node = json.loads('{ "run_list": [] }')
        self.mox.StubOutWithMock(json, 'load')
        json.load(mock_file).AndReturn(node)

        #Stub out file write
        mock_file.__enter__().AndReturn(mock_file)
        self.mox.StubOutWithMock(json, 'dump')
        json.dump(node, mock_file).AndReturn(None)
        mock_file.__exit__(None, None, None).AndReturn(None)

        #Stub out file opens
        self.mox.StubOutWithMock(__builtin__, 'file')
        __builtin__.file("/tmp/checkmate/test/myEnv/kitchen/nodes/a.b.c.d."
                "json", 'r').AndReturn(mock_file)
        __builtin__.file("/tmp/checkmate/test/myEnv/kitchen/nodes/a.b.c.d."
                "json", 'w').AndReturn(mock_file)

        #Stub out directory change
        self.mox.StubOutWithMock(os, 'chdir')
        os.chdir('/tmp/checkmate/test/myEnv/kitchen').AndReturn(None)

        #Stub out process call to knife
        self.mox.StubOutWithMock(local, 'check_output')
        local.check_output(params).AndReturn(results)

        self.mox.ReplayAll()
        try:
            local.cook('a.b.c.d',  'myEnv', recipes=None,
                roles=['build', 'wordpress-web'])
        except Exception as exc:
            if 'MissingRole' in exc.__str__():
                # If got the right error, check that it is correctly formatted
                self.assertIn("Chef/Knife error encountered: MissingRole",
                        exc.__str__())
            else:
                self.assertIn("OutOfKitchenError",
                        exc.__str__())

        #TODO: check this self.mox.VerifyAll()

    def test_databag_create(self):
        """Test databag item creation (with chekcmate filling in ID)"""
        original = {
                'a': 1,
                'b': '2',
                'boolean': False,
                'blank': None,
                'multi-level': {
                        'ml_stays': "I'm here!",
                        'ml_goes': 'Bye!',
                    },
            }
        bag = uuid.uuid4().hex
        local.manage_databag('test_env', bag, 'test', original)
        stored = local._run_kitchen_command(
                "/tmp/checkmate/test/test_env/kitchen/",
                ['knife', 'solo', 'data', 'bag', 'show', bag, 'test', '-F',
                'json'])
        self.assertDictEqual(json.loads(stored), original)

    def test_databag_merge(self):
        """Test databag item merging"""
        original = {
                'a': 1,
                'b': '2',
                'boolean': False,
                'blank': None,
                'multi-level': {
                        'ml_stays': "I'm here!",
                        'ml_goes': 'Bye!',
                    },
            }
        merge = {
                'b': 3,
                'multi-level': {
                        'ml_goes': 'fishing',
                    },
        }
        expected = {
                'id': 'test',
                'a': 1,
                'b': 3,
                'boolean': False,
                'blank': None,
                'multi-level': {
                        'ml_stays': "I'm here!",
                        'ml_goes': 'fishing',
                    },
            }
        bag = uuid.uuid4().hex
        local.manage_databag('test_env', bag, 'test', original)
        local.manage_databag('test_env', bag, 'test', merge, merge=True)
        stored = local._run_kitchen_command(
                "/tmp/checkmate/test/test_env/kitchen/",
                ['knife', 'solo', 'data', 'bag', 'show', bag, 'test', '-F',
                'json'])
        self.assertDictEqual(json.loads(stored),
                             json.loads(json.dumps(expected)))

    def test_databag_create_bad_id(self):
        """Test databag item creation (with supplied ID not matching)"""
        original = {
                'id': 'Not-the-tem-name',
            }
        bag = uuid.uuid4().hex
        self.assertRaises(CheckmateException, local.manage_databag,
                'test_env', bag, 'test', original)


class TestWorkflowLogic(StubbedWorkflowBase):
    """ Test Basic Workflow code """

    def test_provider_catalog_override(self):
        """Test that an injected catalog gets applied"""
        data = yaml_to_dict("""
                  provides:
                  - widget: foo
                  - widget: bar
                  vendor: test
                  catalog:
                    widget:
                      small_widget:
                        is: widget
                        provides:
                        - widget: foo
                      big_widget:
                        is: widget
                        provides:
                        - widget: bar
            """)
        base = local.Provider(data, key='base')
        self.assertDictEqual(base.get_catalog(None), data['catalog'])

    def test_workflow_option_flow(self):
        """Test that options get routed to data bag/overrides

        - tests global, blueprint, service, and provider options
        - tests that options get mapped to provider field name
        - tests that options named like paths get expanded to dicts
        """
        self.deployment = Deployment(yaml_to_dict("""
                id: test
                blueprint:
                  name: test bp
                  services:
                    one:
                      component:
                        type: widget
                        interface: foo
                environment:
                  name: environment
                  providers:
                    base:
                      provides:
                      - widget: foo
                      vendor: test
                      catalog:
                        widget:
                          small_widget:
                            is: widget
                            provides:
                            - widget: foo
                            options: &options
                              global_input:
                                type: string
                              blueprint_input:
                                type: string
                              service_input:
                                type: string
                              provider_input:
                                type: string
                              widget/configuration_file:
                                type: string
                                source_field_name: widget/conf_file
                inputs:
                  prefix: T
                  global_input: g
                  blueprint:
                    blueprint_input: b
                  services:
                    one:
                      widget:
                        service_input: s1
                  providers:
                    base:
                      widget:
                        provider_input: p1
            """))
        PROVIDER_CLASSES['test.base'] = local.Provider

        expected_calls = [{
                # Create Chef Environment
                'call': 'checkmate.providers.opscode.local.create_environment',
                'args': [self.deployment['id']],
                'kwargs': And(ContainsKeyValue('private_key', IgnoreArg()),
                        ContainsKeyValue('secret_key', IgnoreArg()),
                        ContainsKeyValue('public_key_ssh', IgnoreArg())),
                'result': {
                        'environment': '/var/tmp/%s/' %
                                self.deployment['id'],
                        'kitchen': '/var/tmp/%s/kitchen',
                        'private_key_path': '/var/tmp/%s/private.pem' %
                                self.deployment['id'],
                        'public_key_path': '/var/tmp/%s/checkmate.pub' %
                                self.deployment['id'],
                        'public_key': ENV_VARS['CHECKMATE_CLIENT_PUBLIC_KEY']}
            }, {
                'call': 'checkmate.providers.opscode.local.manage_databag',
                'args': [self.deployment['id'], self.deployment['id'],
                        IgnoreArg(),
                        {'small_widget':
                                {
                                'global_input': 'g',
                                'provider_input': 'p1',
                                'service_input': 's1',
                                'blueprint_input': 'b',
                                'widget': {
                                        'conf_file': 'F'
                                    },
                            }
                        }
                        ],
                'kwargs': And(ContainsKeyValue('secret_file',
                        'certificates/chef.pem'), ContainsKeyValue('merge',
                        True)),
                'result': None
            }, {
                'call': 'checkmate.providers.opscode.local.cook',
                'args': [None, self.deployment['id']],
                'kwargs': And(In('password'), ContainsKeyValue('recipes',
                        ['small_widget']),
                        ContainsKeyValue('identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id'])),
                'result': None
            }, {
                'call': 'checkmate.providers.opscode.local.cook',
                'args': [None, self.deployment['id']],
                'kwargs': And(In('password'), ContainsKeyValue('recipes',
                        ['big_widget']),
                        ContainsKeyValue('identity_file',
                                '/var/tmp/%s/private.pem' %
                                self.deployment['id'])),
                'result': None
            }]

        workflow = self._get_stubbed_out_workflow(
                expected_calls=expected_calls)
        workflow.get_task(2).set_attribute(
                **{'widget/configuration_file': 'F'})
        self.mox.ReplayAll()
        workflow.complete_all()
        self.assertTrue(workflow.is_completed())
        self.assertEqual(len(workflow.get_tasks()), 9)
        self.assertDictEqual(self.outcome,
                {
                  'data_bags': {
                    'test': {
                      'webapp_small_widget_T': {
                        'small_widget': {
                          'global_input': 'g',
                          'provider_input': 'p1',
                          'widget': {
                            'conf_file': 'F'
                          },
                          'service_input': 's1',
                          'blueprint_input': 'b'
                        }
                      }
                    }
                  }
                }

            )

if __name__ == '__main__':
    # Run tests. Handle our paramsters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
