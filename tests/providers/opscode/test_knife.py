"""Tests for Knife commands"""
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

import git
import mox
from mox import In, IsA, And, IgnoreArg, ContainsKeyValue, Not

from checkmate.exceptions import CheckmateException
from checkmate.providers.opscode import knife
from checkmate.test import StubbedWorkflowBase


class TestKnife(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

        local_path = '/tmp/checkmate/test'
        os.environ['CHECKMATE_CHEF_LOCAL_PATH'] = local_path
        if not os.path.exists(local_path):
            shutil.os.makedirs(local_path)
            LOG.info("Created '%s'" % local_path)
        test_path = os.path.join(local_path, 'test_env', 'kitchen', 'roles')
        if not os.path.exists(test_path):
            knife.create_environment('test_env', 'kitchen')

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_cook_missing_role(self):
        """Test that missing role error is correctly detected and reported"""
        results = """Checking cookbook syntax...
[Mon, 21 May 2012 17:25:54 +0000] INFO: *** Chef 0.10.10 ***
[Mon, 21 May 2012 17:25:55 +0000] INFO: Setting the run_list to ["role[build]", "role[wordpress-web]"] from JSON
[Mon, 21 May 2012 17:25:55 +0000] ERROR: Role build is in the runlist but does not exist. Skipping expand.
[Mon, 21 May 2012 17:25:55 +0000] ERROR: Role wordpress-web is in the runlist but does not exist. Skipping expand.
[Mon, 21 May 2012 17:25:55 +0000] FATAL: Stacktrace dumped to /tmp/checkmate/environments/myEnv/chef-stacktrace.out
[Mon, 21 May 2012 17:25:55 +0000] FATAL: Chef::Exceptions::MissingRole: Chef::Exceptions::MissingRole
"""
        params = ['knife', 'cook', 'root@a.b.c.d',
                  '-c', "/tmp/checkmate/test/myEnv/kitchen/solo.rb",
                  '-p', '22']

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

          #Stub out call to resource_postback
        self.mox.StubOutWithMock(knife.resource_postback, 'delay')
        host_results={'instance:1': {'status': 'BUILD'}, 'instance:rackspace': {'status': 'CONFIGURE'}}
        knife.resource_postback.delay('myEnv', host_results).AndReturn(True)

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
        self.mox.StubOutWithMock(knife, 'check_all_output')
        knife.check_all_output("myEnv", params).AndReturn(results)

        #Stub out call to resource_postback
        #self.mox.StubOutWithMock(knife.resource_postback, 'delay')
        host_results={'instance:rackspace': {'status': 'ACTIVE'}}
        knife.resource_postback.delay('myEnv', host_results).AndReturn(True)
        
        #Stub out call to update_dep_error
        self.mox.StubOutWithMock(knife, 'update_dep_error')
        knife.update_dep_error(IsA(str), IsA(str)).AndReturn(True)

        self.mox.ReplayAll()
        try:
            resource = {
                'index':1, 
                'hosted_on': 'rackspace'
            }
            knife.cook('a.b.c.d', 'myEnv', resource, recipes=None,
                       roles=['build', 'not-a-role'])
        except Exception as exc:
            if 'MissingRole' in exc.__str__():
                # If got the right error, check that it is correctly formatted
                self.assertIn("Chef/Knife error encountered: MissingRole",
                        exc.__str__())
            else:
                LOG.error("This should be a trace here", exc_info=True)
                self.assertIn("OutOfKitchenError",
                        exc.__str__())

        #TODO: check this self.mox.VerifyAll()

    def test_databag_create(self):
        """Test databag item creation (with checkmate filling in ID)"""
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
        resource = {
            'index':1, 
            'hosted_on': 'rackspace'
        }
        bag = uuid.uuid4().hex
        knife.write_databag('test_env', bag, 'test', original, resource)
        stored = knife._run_kitchen_command(
                "dep_id",
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
        resource  = {'index': 1234,
                     'hosted_on':"rackspace"
                     }
        knife.write_databag('test_env', bag, 'test', original, resource)
        knife.write_databag('test_env', bag, 'test', merge, resource, merge=True)
        stored = knife._run_kitchen_command(
                'test',
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
        resource = {'index':1234}
        bag = uuid.uuid4().hex
        self.assertRaises(CheckmateException, knife.write_databag,
                'test_env', bag, 'test', original, resource)

    def test_create_environment(self):
        """Test create_environment"""
        path = '/fake_path'
        fullpath = os.path.join(path, "test")
        service = "test_service"
        #Stub out checks for paths
        self.mox.StubOutWithMock(os, 'mkdir')
        os.mkdir(fullpath, 0770).AndReturn(True)
        self.mox.StubOutWithMock(knife, '_get_root_environments_path')
        knife._get_root_environments_path("test", path).AndReturn(path)
        self.mox.StubOutWithMock(knife, '_create_environment_keys')
        knife._create_environment_keys("test", fullpath, private_key="PPP",
                                       public_key_ssh="SSH").AndReturn(
                                       dict(keys="keys"))
        self.mox.StubOutWithMock(knife, '_create_kitchen')
        knife._create_kitchen("test", service, fullpath, secret_key="SSS")\
                .AndReturn(dict(kitchen="kitchen_path"))
        kitchen_path = os.path.join(fullpath, service)
        public_key_path = os.path.join(fullpath, 'checkmate.pub')
        kitchen_key_path = os.path.join(kitchen_path, 'certificates',
                                        'checkmate-environment.pub')
        self.mox.StubOutWithMock(shutil, 'copy')
        shutil.copy(public_key_path, kitchen_key_path).AndReturn(True)
        self.mox.StubOutWithMock(knife, '_init_repo')
        knife._init_repo("test", os.path.join(kitchen_path, 'cookbooks'))\
                .AndReturn(True)
        self.mox.StubOutWithMock(knife, 'download_cookbooks')
        knife.download_cookbooks("test", service, path=path).AndReturn(True)
        knife.download_cookbooks("test", service, path=path, use_site=True)\
                .AndReturn(True)
        self.mox.StubOutWithMock(knife, 'download_roles')
        knife.download_roles("test", service, path=path).AndReturn(True)

        self.mox.ReplayAll()
        expected = {'environment': '/fake_path/test',
                    'keys': 'keys',
                    'kitchen': 'kitchen_path'}
        self.assertDictEqual(knife.create_environment("test",
                                                      service, path=path,
                                                      private_key="PPP",
                                                      public_key_ssh="SSH",
                                                      secret_key="SSS"),
                             expected)
        self.mox.VerifyAll()

    def test_create_environment_repo_cheffile(self):
        """Test create_environment with a source repository containing
           a Cheffile"""
        path = '/fake_path'
        fullpath = os.path.join(path, "test")
        service = "test_service"
        #Stub out checks for paths
        self.mox.StubOutWithMock(os, 'mkdir')
        os.mkdir(fullpath, 0770).AndReturn(True)
        self.mox.StubOutWithMock(knife, '_get_root_environments_path')
        knife._get_root_environments_path("test", path).AndReturn(path)
        self.mox.StubOutWithMock(knife, '_create_environment_keys')
        knife._create_environment_keys("test", fullpath, private_key="PPP",
                                       public_key_ssh="SSH").AndReturn(
                                       dict(keys="keys"))
        self.mox.StubOutWithMock(knife, '_create_kitchen')
        knife._create_kitchen("test", service, fullpath, secret_key="SSS")\
                .AndReturn(dict(kitchen="kitchen_path"))
        kitchen_path = os.path.join(fullpath, service)
        public_key_path = os.path.join(fullpath, 'checkmate.pub')
        kitchen_key_path = os.path.join(kitchen_path, 'certificates',
                                        'checkmate-environment.pub')
        self.mox.StubOutWithMock(shutil, 'copy')
        shutil.copy(public_key_path, kitchen_key_path).AndReturn(True)

        self.mox.StubOutWithMock(os.path, 'exists')
        os.path.exists(kitchen_path).AndReturn(True)
        repo = self.mox.CreateMockAnything()
        remote = self.mox.CreateMockAnything()
        self.mox.StubOutWithMock(git.Repo, 'init')
        git.Repo.init(kitchen_path).AndReturn(repo)
        repo.remotes = []
        repo.create_remote('origin', "git://ggg").AndReturn(remote)
        remote.fetch(refspec='master').AndReturn(True)

        self.mox.StubOutWithMock(git, 'Git')
        gb_mock = self.mox.CreateMockAnything()
        git.Git(kitchen_path).AndReturn(gb_mock)
        gb_mock.checkout('FETCH_HEAD').AndReturn(True)

        os.path.exists(os.path.join(kitchen_path, 'Berksfile')).AndReturn(False)
        os.path.exists(os.path.join(kitchen_path, 'Cheffile')).AndReturn(True)
        self.mox.StubOutWithMock(os, 'chdir')
        os.chdir(kitchen_path).AndReturn(True)
        self.mox.StubOutWithMock(knife, 'check_all_output')
        knife.check_all_output("test", ['librarian-chef', 'install']).AndReturn('OK')

        self.mox.ReplayAll()
        expected = {'environment': '/fake_path/test',
                    'keys': 'keys',
                    'kitchen': 'kitchen_path'}
        self.assertDictEqual(knife.create_environment("test",
                                                      service, path=path,
                                                      private_key="PPP",
                                                      public_key_ssh="SSH",
                                                      secret_key="SSS",
                                                      source_repo="git://ggg"),
                             expected)
        self.mox.VerifyAll()




    def test_create_environment_repo_berksfile(self):
        """Test create_environment with a source repository containing
           a Berksfile"""
        path = '/fake_path'
        fullpath = os.path.join(path, "test")
        service = "test_service"
        #Stub out checks for paths
        self.mox.StubOutWithMock(os, 'mkdir')
        os.mkdir(fullpath, 0770).AndReturn(True)
        self.mox.StubOutWithMock(knife, '_get_root_environments_path')
        knife._get_root_environments_path('test', path).AndReturn(path)
        self.mox.StubOutWithMock(knife, '_create_environment_keys')
        knife._create_environment_keys('test', fullpath, private_key="PPP",
                                       public_key_ssh="SSH").AndReturn(
                                       dict(keys="keys"))
        self.mox.StubOutWithMock(knife, '_create_kitchen')
        knife._create_kitchen('test', service, fullpath, secret_key="SSS")\
                .AndReturn(dict(kitchen="kitchen_path"))
        kitchen_path = os.path.join(fullpath, service)
        public_key_path = os.path.join(fullpath, 'checkmate.pub')
        kitchen_key_path = os.path.join(kitchen_path, 'certificates',
                                        'checkmate-environment.pub')
        self.mox.StubOutWithMock(shutil, 'copy')
        shutil.copy(public_key_path, kitchen_key_path).AndReturn(True)

        self.mox.StubOutWithMock(os.path, 'exists')
        os.path.exists(kitchen_path).AndReturn(True)
        repo = self.mox.CreateMockAnything()
        remote = self.mox.CreateMockAnything()
        self.mox.StubOutWithMock(git.Repo, 'init')
        git.Repo.init(kitchen_path).AndReturn(repo)
        repo.remotes = []
        repo.create_remote('origin', "git://ggg").AndReturn(remote)
        remote.fetch(refspec='master').AndReturn(True)

        self.mox.StubOutWithMock(git, 'Git')
        gb_mock = self.mox.CreateMockAnything()
        git.Git(kitchen_path).AndReturn(gb_mock)
        gb_mock.checkout('FETCH_HEAD').AndReturn(True)

        os.path.exists(os.path.join(kitchen_path, 'Berksfile')).AndReturn(True)
        #os.path.exists(os.path.join(kitchen_path, 'Cheffile')).AndReturn(False)
        self.mox.StubOutWithMock(os, 'chdir')
        os.chdir(kitchen_path).AndReturn(True)
        self.mox.StubOutWithMock(knife, 'check_all_output')
        knife.check_all_output('test', ['berks', 'install', '--path',
                os.path.join(kitchen_path, 'cookbooks')]).AndReturn('OK')

        self.mox.ReplayAll()
        expected = {'environment': '/fake_path/test',
                    'keys': 'keys',
                    'kitchen': 'kitchen_path'}
        self.assertDictEqual(knife.create_environment("test",
                                                      service, path=path,
                                                      private_key="PPP",
                                                      public_key_ssh="SSH",
                                                      secret_key="SSS",
                                                      source_repo="git://ggg"), expected)
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
