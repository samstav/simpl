# pylint: disable=C0103,E1101,E1103,R0904,W0212,W0613

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

"""Tests for ChefMap."""

import hashlib
import logging
import os
import shutil
import unittest
import urlparse

import mox

from checkmate.common import git as common_git
from checkmate.providers.opscode import blueprint_cache
from checkmate.providers.opscode import chef_map
from checkmate import test
from checkmate import utils

LOG = logging.getLogger(__name__)


class TestChefMap(unittest.TestCase):
    def setUp(self):
        self.mox = mox.Mox()
        blueprint_cache.CONFIG = self.mox.CreateMockAnything()
        blueprint_cache.CONFIG.cache_dir = '/tmp/checkmate-chefmap'
        self.local_path = '/tmp/checkmate-chefmap'
        self.url = 'https://github.com/checkmate/app.git'
        self.cache_path = self.local_path + "/cache/blueprints/" + \
            hashlib.md5(self.url).hexdigest()
        self.fetch_head_path = os.path.join(self.cache_path, ".git",
                                            "FETCH_HEAD")
        self.chef_map_path = os.path.join(self.cache_path, "Chefmap")

        # Clean up from previous failed run
        if os.path.exists(self.local_path):
            shutil.rmtree(self.local_path)
            LOG.info("Removed '%s'", self.local_path)

    def tearDown(self):
        self.mox.UnsetStubs()
        if os.path.exists(self.local_path):
            shutil.rmtree('/tmp/checkmate-chefmap')

    def test_get_map_file_hit_cache(self):

        def fake_clone(repo_dir, location, branch_or_tag=None, verbose=False):
            """Helper method to fake a git clone."""
            git_path = os.path.join(repo_dir, ".git")
            os.makedirs(git_path)
            fetch_head_path = os.path.join(git_path, "FETCH_HEAD")
            chef_map_path = os.path.join(repo_dir, "Chefmap")

            with file(fetch_head_path, 'a'):
                os.utime(fetch_head_path, None)
            with open(chef_map_path, 'w') as the_file:
                the_file.write(TEMPLATE)

        # Make sure cache_expire_time is set to something that
        # shouldn't cause a cache miss
        chefmap = chef_map.ChefMap()
        os.environ["CHECKMATE_BLUEPRINT_CACHE_EXPIRE"] = "3600"

        chefmap.url = self.url

        def update_map(repo_dir=None, head=None, branch_or_tag='master',
                       verbose=False):
            """Helper method to mock update_map."""
            chef_map_path = os.path.join(repo_dir, "Chefmap")
            with open(chef_map_path, 'a') as the_file:
                the_file.write("new information")

        self.mox.StubOutWithMock(common_git, 'git_clone')
        common_git.git_clone(
            mox.IgnoreArg(), mox.IgnoreArg(), branch_or_tag='master',
            verbose=False).WithSideEffects(fake_clone)
        self.mox.StubOutWithMock(common_git, 'git_list_tags')
        common_git.git_list_tags(
            mox.IgnoreArg(), with_messages=False).AndReturn(['master'])
        self.mox.StubOutWithMock(common_git, 'git_checkout')
        common_git.git_checkout(
            mox.IgnoreArg(), mox.IgnoreArg()).WithSideEffects(update_map)

        self.mox.ReplayAll()
        map_file = chefmap.get_map_file()
        self.assertEqual(map_file, TEMPLATE + 'new information')

    def test_get_map_file_miss_cache(self):

        def fake_clone(repo_dir, location, branch_or_tag=None, verbose=False):
            """Helper method to fake a git clone."""
            git_path = os.path.join(repo_dir, ".git")
            os.makedirs(git_path)
            fetch_head_path = os.path.join(git_path, "FETCH_HEAD")
            chef_map_path = os.path.join(repo_dir, "Chefmap")

            with file(fetch_head_path, 'a'):
                os.utime(fetch_head_path, None)
            with open(chef_map_path, 'w') as the_file:
                the_file.write(TEMPLATE)

        # Make sure the expire time is set to something that WILL
        # cause a cache miss
        blueprint_cache.CONFIG.blueprint_cache_expiration = 0

        def update_map(repo_dir=None, head=None, branch_or_tag=None,
                       verbose=False):
            """Helper method to fake an update."""
            chef_map_path = os.path.join(repo_dir, "Chefmap")
            with open(chef_map_path, 'a') as the_file:
                the_file.write("new information")

        self.mox.StubOutWithMock(common_git, 'git_clone')
        common_git.git_clone(
            mox.IgnoreArg(), mox.IgnoreArg(), branch_or_tag='master',
            verbose=False).WithSideEffects(fake_clone)
        self.mox.StubOutWithMock(common_git, 'git_list_tags')
        common_git.git_list_tags(
            mox.IgnoreArg(), with_messages=False).AndReturn(['master'])
        self.mox.StubOutWithMock(common_git, 'git_fetch')
        self.mox.StubOutWithMock(common_git, 'git_checkout')
        common_git.git_checkout(
            mox.IgnoreArg(), mox.IgnoreArg()).WithSideEffects(update_map)

        self.mox.ReplayAll()
        chefmap = chef_map.ChefMap()
        chefmap.url = self.url
        map_file = chefmap.get_map_file()

        self.assertNotEqual(map_file, TEMPLATE)
        self.mox.VerifyAll()
        self.mox.UnsetStubs()

    def test_get_map_file_no_cache(self):
        chefmap = chef_map.ChefMap()

        def fake_clone(repo_dir, location, branch_or_tag=None, verbose=False):
            """Helper method to fake a git clone."""
            git_path = os.path.join(repo_dir, ".git")
            os.makedirs(git_path)
            fetch_head_path = os.path.join(git_path, "FETCH_HEAD")
            chef_map_path = os.path.join(repo_dir, "Chefmap")

            with file(fetch_head_path, 'a'):
                os.utime(fetch_head_path, None)
            with open(chef_map_path, 'w') as the_file:
                the_file.write(TEMPLATE)

        self.mox.StubOutWithMock(common_git, 'git_clone')
        common_git.git_clone(
            mox.IgnoreArg(), mox.IgnoreArg(), branch_or_tag=mox.IgnoreArg(),
            verbose=False).WithSideEffects(fake_clone)
        self.mox.StubOutWithMock(common_git, 'git_list_tags')
        common_git.git_list_tags(
            mox.IgnoreArg(), with_messages=False).AndReturn(['master'])
        self.mox.StubOutWithMock(common_git, 'git_checkout')
        common_git.git_checkout(mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.ReplayAll()

        chefmap.url = self.url
        map_file = chefmap.get_map_file()

        self.assertEqual(map_file, TEMPLATE)
        self.mox.VerifyAll()

    def test_get_map_file_local(self):
        blueprint = os.path.join(self.local_path, "blueprint")
        os.makedirs(blueprint)

        # Create a dummy Chefmap
        with file(os.path.join(blueprint, "Chefmap"), 'a') as the_file:
            the_file.write(TEMPLATE)

        url = "file://" + blueprint
        chefmap = chef_map.ChefMap(url=url)
        map_file = chefmap.get_map_file()

        self.assertEqual(map_file, TEMPLATE)

    def test_map_uri_parser(self):
        fxn = chef_map.ChefMap.parse_map_uri
        cases = [
            {
                'name': 'requirement from short form',
                'scheme': 'requirements',
                'netloc': 'database:mysql',
                'path': 'username',
            },
            {
                'name': 'requirement from long form',
                'scheme': 'requirements',
                'netloc': 'my_name',
                'path': 'root/child',
            },
            {
                'name': 'databag',
                'scheme': 'databags',
                'netloc': 'my_dbag',
                'path': 'item/key',
            },
            {
                'name': 'encrypted databag',
                'scheme': 'encrypted-databags',
                'netloc': 'secrets',
                'path': 'item/key/with/long/path',
            },
            {
                'name': 'attributes',
                'scheme': 'attributes',
                'netloc': '',
                'path': 'item/key/with/long/path',
            },
            {
                'name': 'clients',
                'scheme': 'clients',
                'netloc': 'provides_key',
                'path': 'item/key/with/long/path',
            },
            {
                'name': 'roles',
                'scheme': 'roles',
                'netloc': 'role-name',
                'path': 'item/key/with/long/path',
            },
            {
                'name': 'output',
                'scheme': 'outputs',
                'netloc': '',
                'path': 'item/key/with/long/path',
            },
            {
                'name': 'path check for output',
                'scheme': 'outputs',
                'netloc': '',
                'path': 'only/path',
            },
            {
                'name': 'only path check for attributes',
                'scheme': 'attributes',
                'netloc': '',
                'path': 'only/path',
            }
        ]

        for case in cases:
            uri = urlparse.urlunparse((
                case['scheme'],
                case['netloc'],
                case['path'],
                None,
                None,
                None
            ))
            result = fxn(uri)
            for key, value in result.iteritems():
                self.assertEqual(value, case.get(key, ''), msg="'%s' got '%s' "
                                 "wrong in %s" % (case['name'], key, uri))

    def test_map_uri_parser_netloc(self):
        result = chef_map.ChefMap.parse_map_uri("attributes://only/path")
        self.assertEqual(result['path'], 'only/path')

        result = chef_map.ChefMap.parse_map_uri("attributes://only")
        self.assertEqual(result['path'], 'only')

        result = chef_map.ChefMap.parse_map_uri("outputs://only/path")
        self.assertEqual(result['path'], 'only/path')

        result = chef_map.ChefMap.parse_map_uri("outputs://only")
        self.assertEqual(result['path'], 'only')

    def test_has_mapping_positive(self):
        new_map = chef_map.ChefMap(raw='''
                id: test
                maps:
                - source: 1
            ''')
        self.assertTrue(new_map.has_mappings('test'))

    def test_has_mapping_negative(self):
        new_map = chef_map.ChefMap(raw='''
                id: test
                maps: {}
            ''')
        self.assertFalse(new_map.has_mappings('test'))

    def test_has_requirement_map_positive(self):
        new_map = chef_map.ChefMap(raw='''
                id: test
                maps:
                - source: requirements://name/path
                - source: requirements://database:mysql/username
            ''')
        self.assertTrue(new_map.has_requirement_mapping('test', 'name'))
        self.assertTrue(new_map.has_requirement_mapping(
            'test', 'database:mysql'))
        self.assertFalse(new_map.has_requirement_mapping('test', 'other'))

    def test_has_requirement_mapping_negative(self):
        new_map = chef_map.ChefMap(raw='''
                id: test
                maps: {}
            ''')
        self.assertFalse(new_map.has_requirement_mapping('test', 'name'))

    def test_has_client_map_positive(self):
        new_map = chef_map.ChefMap(raw='''
                id: test
                maps:
                - source: clients://name/path
                - source: clients://database:mysql/ip
            ''')
        self.assertTrue(new_map.has_client_mapping('test', 'name'))
        self.assertTrue(new_map.has_client_mapping('test', 'database:mysql'))
        self.assertFalse(new_map.has_client_mapping('test', 'other'))

    def test_has_client_mapping_negative(self):
        new_map = chef_map.ChefMap(raw='''
                id: test
                maps: {}
            ''')
        self.assertFalse(new_map.has_client_mapping('test', 'name'))

    def test_get_attributes(self):
        new_map = chef_map.ChefMap(raw='''
                id: foo
                maps:
                - value: 1
                  targets:
                  - attributes://here
                \n--- # component bar
                id: bar
                maps:
                - value: 1
                  targets:
                  - databags://mybag/there
            ''')
        self.assertDictEqual(new_map.get_attributes('foo', None), {'here': 1})
        self.assertDictEqual(new_map.get_attributes('bar', None), {})
        self.assertIsNone(new_map.get_attributes('not there', None))

    def test_has_runtime_options(self):
        new_map = chef_map.ChefMap(raw='''
                id: foo
                maps:
                - source: requirements://database:mysql/
                \n---
                id: bar
                maps: {}
                ''')
        self.assertTrue(new_map.has_runtime_options('foo'))
        self.assertFalse(new_map.has_runtime_options('bar'))
        self.assertFalse(new_map.has_runtime_options('not there'))

    def test_filter_maps_by_schemes(self):
        maps = utils.yaml_to_dict('''
                - value: 1
                  targets:
                  - databags://bag/item
                - value: 2
                  targets:
                  - databags://bag/item
                  - roles://bag/item
                - value: 3
                  targets:
                  - attributes://id
                ''')
        expect = "Should detect all maps with databags target"
        schemes = ['databags']
        result = chef_map.ChefMap.filter_maps_by_schemes(
            maps, target_schemes=schemes)
        self.assertItemsEqual(result, maps[0:2], msg=expect)

        expect = "Should detect only map with roles target"
        schemes = ['roles']
        result = chef_map.ChefMap.filter_maps_by_schemes(
            maps, target_schemes=schemes)
        self.assertItemsEqual(result, [maps[1]], msg=expect)

        expect = "Should detect all maps once"
        schemes = ['databags', 'attributes', 'roles']
        result = chef_map.ChefMap.filter_maps_by_schemes(
            maps, target_schemes=schemes)
        self.assertItemsEqual(result, maps, msg=expect)

        expect = "Should return all maps"
        result = chef_map.ChefMap.filter_maps_by_schemes(maps)
        self.assertItemsEqual(result, maps, msg=expect)

        expect = "Should return all maps"
        result = chef_map.ChefMap.filter_maps_by_schemes(maps,
                                                         target_schemes=[])
        self.assertItemsEqual(result, maps, msg=expect)


TEMPLATE = \
    """# vim: set filetype=yaml syntax=yaml:
# Global function
{% set app_id = deployment.id + '_app' %}

--- # first component
id: webapp
provides:
- application: http
requires:
- host: linux
- database: mysql
options:
  "site_name":
    type: string
    sample: "Bob's tire shop"
    required: false
run-list:
  recipes:
  - first
maps:
- value: {{ setting('site_name') }}
  targets:
  - attributes://webapp/site/name
- source: requirements://database:mysql/database_name
  targets:
  - attributes://webapp/db/name
- source: requirements://database:mysql/username
  targets:
  - attributes://webapp/db/user
- source: requirements://database:mysql/host
  targets:
  - attributes://webapp/db/host
- source: requirements://database:mysql/password
  targets:
  - attributes://webapp/db/password
- source: requirements://database:mysql/root_password
  targets:
  - attributes://mysql/server_root_password

--- # second component map
id: mysql
is: database
provides:
- database: mysql
requires:
- host: linux
options:
  "database_name":
    type: string
    default: db1
    required: true
  "database_user":
    type: string
    default: db_user
    required: true
  "database_password":
    type: password
    default: =generate_password()
    required: true
chef-roles:
  mysql-master:
    create: true
    recipes:
    - apt
    - mysql::server
    - holland
    - holland::common
    - holland::mysqldump
maps:
- value: {{ setting('server_root_password') }}
  targets:
  - encrypted-databag://{{app_id}}/mysql/server_root_password
  - output://{{resource.index}}/instance/interfaces/mysql/root_password
- source: requirements://database/hostname  # database is defined in component
  targets:
  - encrypted-databag://{{deployment.id}}//{{app_id}}/mysql/host
- source: requirements://host/instance/ip
  targets:
  - output://{{resource.index}}/instance/interfaces/mysql/host
- source: requirements://database:mysql/database_user
  targets:
  - encrypted-databag://{{app_id}}/mysql/username
  - output://{{resource.index}}/instance/interfaces/mysql/username
- value: {{ setting('database_password') }}
  targets:
  - encrypted-databag://{{app_id}}/mysql/password
  - output://{{resource.index}}/instance/interfaces/mysql/password
- value: {{ deployment.id }} # Deployment ID needs to go to Node Attribute
  targets:
  - attributes://deployment/id
output:
  '{{resource.index}}':
    name: {{ setting('database_name') }}
    instance:
      interfaces:
        mysql:
          database_name: {{ setting('database_name') }}
"""


if __name__ == '__main__':
    test.run_with_params()
