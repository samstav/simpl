# pylint: disable=C0103,E1101,E1103,W0212

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

"""Tests for knife (Chef)."""
import json
import logging
import os
import shutil
import subprocess
import unittest
import uuid

import mox

from checkmate import deployments as cmdeps
from checkmate import exceptions as cmexc
from checkmate.providers.opscode import knife

LOG = logging.getLogger(__name__)
TEST_PATH = '/tmp/checkmate/test'


class TestKnife(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()
        self.orignal_dir = os.getcwd()  # our knife calls will change it
        self.deploymentId = uuid.uuid4().hex
        knife.CONFIG = self.mox.CreateMockAnything()
        knife.CONFIG.deployments_path = TEST_PATH
        if not os.path.exists(TEST_PATH):
            shutil.os.makedirs(TEST_PATH)
            LOG.info("Created '%s'", TEST_PATH)

        # Fake a call to create_environment
        url = 'https://example.com/checkmate/app.git'
        cache_path = knife._get_blueprints_cache_path(url)
        self.environment_path = os.path.join(TEST_PATH, self.deploymentId)
        self.kitchen_path = os.path.join(self.environment_path, 'kitchen')

        if not os.path.exists(self.kitchen_path):
            os.makedirs(self.kitchen_path)
            knife._create_kitchen(self.deploymentId, 'kitchen',
                                  self.environment_path)
            LOG.info("Created kitchen '%s'", self.kitchen_path)

        databag_path = os.path.join(self.kitchen_path, "data_bags")
        if not os.path.exists(databag_path):
            os.makedirs(databag_path)
        with open(
                os.path.join(self.kitchen_path, "Cheffile"), 'w') as the_file:
            the_file.write(CHEFFILE)
        with open(
                os.path.join(self.kitchen_path, "Berksfile"), 'w') as the_file:
            the_file.write(BERKSFILE)
        if not os.path.exists(cache_path):
            os.makedirs(os.path.join(cache_path, ".git"))

    def tearDown(self):
        self.mox.UnsetStubs()
        os.chdir(self.orignal_dir)  # restore what knife may have changed
        shutil.rmtree(self.environment_path)

    def test_delete_environment(self):
        self.mox.StubOutWithMock(shutil, "rmtree")
        shutil.rmtree(self.environment_path)
        self.mox.ReplayAll()
        knife.delete_environment(self.deploymentId)

    def test_delete_environment_exception_handling(self):
        self.mox.StubOutWithMock(shutil, "rmtree")
        shutil.rmtree("/tmp/foo/%s" % self.deploymentId).AndRaise(
            cmexc.CheckmateUserException("", "", "", ""))
        self.mox.ReplayAll()
        self.assertRaises(cmexc.CheckmateUserException,
                          knife.delete_environment,
                          self.deploymentId, path="/tmp/foo")

    def test_delete_cookbooks(self):
        self.mox.StubOutWithMock(shutil, "rmtree")
        shutil.rmtree(os.path.join(self.kitchen_path, "cookbooks"))
        shutil.rmtree(os.path.join(self.kitchen_path, "site-cookbooks"))
        self.mox.ReplayAll()
        knife.delete_cookbooks(self.deploymentId, 'kitchen')

    def test_databag_create(self):
        """Test databag item creation (with checkmate filling in ID)."""
        original = {
            'a': 1,
            'b': '2',
            'boolean': False,
            'blank': '',
            'multi-level': {
                'ml_stays': "I'm here!",
                'ml_goes': 'Bye!',
            },
        }
        resource = {
            'index': 1,
            'hosted_on': 'rackspace'
        }
        bag = uuid.uuid4().hex
        self.mox.StubOutWithMock(cmdeps.resource_postback, 'delay')
        knife.write_databag(self.deploymentId, bag, 'test', original, resource)
        params = ['knife', 'solo', 'data', 'bag', 'show', bag, 'test', '-F',
                  'json']
        stored = knife._run_kitchen_command("dep_id", "/tmp/checkmate/test/"
                                            "%s/kitchen/" % self.deploymentId,
                                            params)
        self.assertDictEqual(json.loads(stored), original)

    def test_databag_merge(self):
        """Test databag item merging."""
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
        resource = {
            'index': 1234,
            'hosted_on': "rackspace"
        }
        self.mox.StubOutWithMock(cmdeps.resource_postback, 'delay')
        knife.write_databag(self.deploymentId, bag, 'test', original, resource)
        knife.write_databag(self.deploymentId, bag, 'test', merge, resource,
                            merge=True)
        params = ['knife', 'solo', 'data', 'bag', 'show', bag, 'test', '-F',
                  'json']
        stored = knife._run_kitchen_command('test', "/tmp/checkmate/test/"
                                            "%s/kitchen/" % self.deploymentId,
                                            params)
        self.assertDictEqual(json.loads(stored),
                             json.loads(json.dumps(expected)))

    def test_databag_create_bad_id(self):
        """Test databag item creation (with supplied ID not matching)."""
        original = {
            'id': 'Not-the-tem-name',
        }
        resource = {'index': 1234}
        bag = uuid.uuid4().hex
        self.assertRaises(cmexc.CheckmateException, knife.write_databag,
                          self.deploymentId, bag, 'test', original, resource)

    def test_create_environment(self):
        """Test create_environment."""
        path = '/fake_path'
        fullpath = os.path.join(path, "test")
        service = "test_service"
        #Stub out checks for paths
        self.mox.StubOutWithMock(os, 'mkdir')
        os.mkdir(fullpath, 0o770).AndReturn(True)
        self.mox.StubOutWithMock(knife, '_get_root_environments_path')
        knife._get_root_environments_path("test", path).AndReturn(path)
        self.mox.StubOutWithMock(knife, '_create_environment_keys')
        knife._create_environment_keys("test", fullpath, private_key="PPP",
                                       public_key_ssh="SSH")\
             .AndReturn(dict(keys="keys"))
        self.mox.StubOutWithMock(knife, '_create_kitchen')
        knife._create_kitchen("test", service, fullpath, secret_key="SSS",
                              source_repo="git://ggg")\
             .AndReturn(dict(kitchen="kitchen_path"))
        kitchen_path = os.path.join(fullpath, service)
        public_key_path = os.path.join(fullpath, 'checkmate.pub')
        kitchen_key_path = os.path.join(kitchen_path, 'certificates',
                                        'checkmate-environment.pub')
        self.mox.StubOutWithMock(shutil, 'copy')
        shutil.copy(public_key_path, kitchen_key_path).AndReturn(True)

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

    def test_create_environment_repo_cheffile(self):
        """Test create_environment with source repo containing a Cheffile."""
        path = '/fake_path'
        fullpath = os.path.join(path, "test")
        service = "test_service"
        #Stub out checks for paths
        self.mox.StubOutWithMock(os, 'mkdir')
        os.mkdir(fullpath, 0o770).AndReturn(True)
        self.mox.StubOutWithMock(knife, '_get_root_environments_path')
        knife._get_root_environments_path("test", path).AndReturn(path)
        self.mox.StubOutWithMock(knife, '_create_environment_keys')
        knife._create_environment_keys("test", fullpath, private_key="PPP",
                                       public_key_ssh="SSH")\
             .AndReturn(dict(keys="keys"))
        self.mox.StubOutWithMock(knife, '_create_kitchen')
        knife._create_kitchen("test", service, fullpath, secret_key="SSS",
                              source_repo="git://ggg")\
             .AndReturn(dict(kitchen="kitchen_path"))
        kitchen_path = os.path.join(fullpath, service)
        public_key_path = os.path.join(fullpath, 'checkmate.pub')
        kitchen_key_path = os.path.join(kitchen_path, 'certificates',
                                        'checkmate-environment.pub')
        self.mox.StubOutWithMock(shutil, 'copy')
        shutil.copy(public_key_path, kitchen_key_path).AndReturn(True)
        self.mox.StubOutWithMock(os.path, 'exists')

        os.path.exists(os.path.join(kitchen_path, 'Berksfile'))\
               .AndReturn(False)
        os.path.exists(os.path.join(kitchen_path, 'Cheffile')).AndReturn(True)
        self.mox.StubOutWithMock(os, 'chdir')
        os.chdir(kitchen_path).AndReturn(True)
        self.mox.StubOutWithMock(subprocess, 'check_output')
        subprocess.check_output(['librarian-chef', 'install']).AndReturn('OK')

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

    # Note: The logic in knife._cache_blueprint() is being tested in
    # the following methods in test_solo.py:
    # - TestChefMap.test_get_map_file_hit_cache()
    # - TestChefMap.test_get_map_file_miss_cache()
    # - TestChefMap.test_get_map_file_no_cache()

    def test_create_environment_repo_berksfile(self):
        """Test create_environment with source repo containing a Berksfile."""
        path = '/fake_path'
        fullpath = os.path.join(path, "test")
        service = "test_service"
        #Stub out checks for paths
        self.mox.StubOutWithMock(knife, "_ensure_berkshelf_environment")
        knife._ensure_berkshelf_environment().AndReturn(True)
        self.mox.StubOutWithMock(os, 'mkdir')
        os.mkdir(fullpath, 0o770).AndReturn(True)
        self.mox.StubOutWithMock(knife, '_get_root_environments_path')
        knife._get_root_environments_path('test', path).AndReturn(path)
        self.mox.StubOutWithMock(knife, '_create_environment_keys')
        knife._create_environment_keys("test", fullpath, private_key="PPP",
                                       public_key_ssh="SSH")\
             .AndReturn(dict(keys="keys"))
        self.mox.StubOutWithMock(knife, '_create_kitchen')
        knife._create_kitchen("test", service, fullpath, secret_key="SSS",
                              source_repo="git://ggg")\
             .AndReturn(dict(kitchen="kitchen_path"))
        kitchen_path = os.path.join(fullpath, service)
        public_key_path = os.path.join(fullpath, 'checkmate.pub')
        kitchen_key_path = os.path.join(kitchen_path, 'certificates',
                                        'checkmate-environment.pub')
        self.mox.StubOutWithMock(shutil, 'copy')
        shutil.copy(public_key_path, kitchen_key_path).AndReturn(True)

        self.mox.StubOutWithMock(os.path, 'exists')
        os.path.exists(os.path.join(kitchen_path, 'Berksfile')).AndReturn(True)
        self.mox.StubOutWithMock(os, 'chdir')
        os.chdir(kitchen_path).AndReturn(True)

        self.mox.StubOutWithMock(subprocess, 'check_output')
        subprocess.check_output([
            'berks', 'install', '--path',
            os.path.join(kitchen_path, 'cookbooks')
        ]).AndReturn('OK')

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


class TestKnifeTasks(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()

    def test_register_node(self):
        ignore = mox.IgnoreArg()
        path = '/fake_path'
        workspace_path = os.path.join(path, "test")
        service = "test_service"
        kitchen_path = os.path.join(workspace_path, service)
        node_path = os.path.join(kitchen_path, 'nodes', 'localhost.json')

        # Stub frst call to postback
        self.mox.StubOutWithMock(knife.cmdeps.resource_postback, 'delay')
        postback_mock = knife.cmdeps.resource_postback.delay
        postback_mock(ignore, ignore).AndReturn(None)

        # Stub out path checks
        self.mox.StubOutWithMock(knife, '_get_root_environments_path')
        knife._get_root_environments_path("test", None).AndReturn(path)

        self.mox.StubOutWithMock(os.path, 'exists')
        os.path.exists(kitchen_path).AndReturn(True)

        # Stubout mkdir ssh call
        self.mox.StubOutWithMock(knife.ssh, 'remote_execute')
        knife.ssh.remote_execute('localhost', ignore, ignore,
                                 identity_file=None, password=None)\
            .AndReturn(True)

        # Stubout check for already registered
        os.path.exists(node_path).AndReturn(False)

        # Stubout chef run
        self.mox.StubOutWithMock(knife, '_run_kitchen_command')
        knife._run_kitchen_command("test", kitchen_path, ignore)\
            .AndReturn(None)

        # Stubout check for installed chef
        res = {'stderr': '', 'stdout': 'Chef: 10.12.0\n'}
        knife.ssh.remote_execute('localhost', "chef-solo -v", 'root',
                                 identity_file=None, password=None)\
            .AndReturn(res)

        # Stub out call to write node attributes
        self.mox.StubOutWithMock(knife, '_write_node_attributes')
        knife._write_node_attributes(node_path, ignore).AndReturn({})

        resource = {'hosted_on': '1', 'index': '0'}
        self.mox.ReplayAll()
        knife.register_node('localhost', 'test', resource,
                            kitchen_name=service)
        self.mox.VerifyAll()

    def test_register_node_retry_chef(self):
        ignore = mox.IgnoreArg()
        path = '/fake_path'
        workspace_path = os.path.join(path, "test")
        service = "test_service"
        kitchen_path = os.path.join(workspace_path, service)
        node_path = os.path.join(kitchen_path, 'nodes', 'localhost.json')

        # Stub frst call to postback
        self.mox.StubOutWithMock(knife.cmdeps.resource_postback, 'delay')
        postback_mock = knife.cmdeps.resource_postback.delay
        postback_mock(ignore, ignore).AndReturn(None)

        # Stub out path checks
        self.mox.StubOutWithMock(knife, '_get_root_environments_path')
        knife._get_root_environments_path("test", None).AndReturn(path)

        self.mox.StubOutWithMock(os.path, 'exists')
        os.path.exists(kitchen_path).AndReturn(True)

        # Stubout mkdir ssh call
        self.mox.StubOutWithMock(knife.ssh, 'remote_execute')
        knife.ssh.remote_execute('localhost', ignore, ignore,
                                 identity_file=None, password=None)\
            .AndReturn(True)

        # Stubout check for already registered
        os.path.exists(node_path).AndReturn(False)

        # Stubout chef run
        self.mox.StubOutWithMock(knife, '_run_kitchen_command')
        knife._run_kitchen_command("test", kitchen_path, ignore)\
            .AndReturn(None)

        # Stubout check for installed chef
        res = {'stderr': 'bash: chef-solo: command not found\n', 'stdout': ''}
        knife.ssh.remote_execute('localhost', "chef-solo -v", 'root',
                                 identity_file=None, password=None)\
            .AndReturn(res)

        resource = {'hosted_on': '1', 'index': '0'}
        self.mox.ReplayAll()
        with self.assertRaises(cmexc.CheckmateException):
            knife.register_node('localhost', 'test', resource,
                                kitchen_name=service)
        self.mox.VerifyAll()


CHEFFILE = """#!/usr/bin/env ruby
#^syntax detection

site 'http://community.opscode.com/api/v1'

cookbook 'chef-client'
cookbook 'memcached'
cookbook 'build-essential'

cookbook 'apache2',
  :git => 'https://github.rackspace.com/Cookbooks/apache2.git',
  :ref => 'origin/checkmate-solo-apache2'
cookbook 'mysql',
  :git => 'https://github.rackspace.com/Cookbooks/checkmate-solo-mysql.git'
cookbook 'php5',
  :git => 'https://github.rackspace.com/Cookbooks/php5.git',
  :ref => 'origin/checkmate-solo'
cookbook 'apt',
  :git => 'https://github.rackspace.com/Cookbooks/apt.git'
cookbook 'holland',
  :git => 'https://github.rackspace.com/Cookbooks/holland.git'
cookbook 'lsyncd',
  :git => 'https://github.rackspace.com/Cookbooks/checkmate-solo-lsyncd.git'
cookbook 'varnish',
  :git => 'https://github.rackspace.com/Cookbooks/checkmate-solo-varnish.git'
cookbook 'monit',
  :git => 'https://github.rackspace.com/Cookbooks/monit.git'
cookbook 'vsftpd',
  :git => 'https://github.rackspace.com/Cookbooks/checkmate-solo-vsftpd.git'
cookbook 'wordpress',
  :git => 'https://github.rackspace.com/Cookbooks/checkmate-solo-wordpress.git'
cookbook 'firewall',
  :git => 'https://github.rackspace.com/Cookbooks/firewall.git'
cookbook 'suhosin',
  :git => 'https://github.rackspace.com/Cookbooks/suhosin.git'
"""

BERKSFILE = """#!/usr/bin/env ruby
#^syntax detection

site :opscode

cookbook 'chef-client'
cookbook 'memcached'
cookbook 'build-essential'

cookbook 'apache2',
  :git => 'https://github.rackspace.com/Cookbooks/apache2.git',
  :ref => 'origin/checkmate-solo-apache2'
cookbook 'mysql',
  :git => 'https://github.rackspace.com/Cookbooks/checkmate-solo-mysql.git'
cookbook 'php5',
  :git => 'https://github.rackspace.com/Cookbooks/php5.git',
  :ref => 'origin/checkmate-solo'
cookbook 'apt',
  :git => 'https://github.rackspace.com/Cookbooks/apt.git'
cookbook 'holland',
  :git => 'https://github.rackspace.com/Cookbooks/holland.git'
cookbook 'lsyncd',
  :git => 'https://github.rackspace.com/Cookbooks/checkmate-solo-lsyncd.git'
cookbook 'varnish',
  :git => 'https://github.rackspace.com/Cookbooks/checkmate-solo-varnish.git'
cookbook 'monit',
  :git => 'https://github.rackspace.com/Cookbooks/monit.git'
cookbook 'vsftpd',
  :git => 'https://github.rackspace.com/Cookbooks/checkmate-solo-vsftpd.git'
cookbook 'wordpress',
  :git => 'https://github.rackspace.com/Cookbooks/checkmate-solo-wordpress.git'
cookbook 'firewall',
  :git => 'https://github.rackspace.com/Cookbooks/firewall.git'
cookbook 'suhosin',
  :git => 'https://github.rackspace.com/Cookbooks/suhosin.git'
"""

if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
