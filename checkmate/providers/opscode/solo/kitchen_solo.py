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

"""Knife Solo Kitchen domain object."""

import json
import logging
import os
import subprocess

from eventlet.green import threading

from checkmate import exceptions, utils
from checkmate.providers.opscode import kitchen
from checkmate.providers.opscode.solo.knife_solo import KnifeSolo

LOG = logging.getLogger(__name__)


class KitchenSolo(kitchen.ChefKitchen):

    """Knife Solo Kitchen domain object."""

    def __init__(self, env_name, root_path=None, kitchen_name="kitchen"):
        super(KitchenSolo, self).__init__(env_name, root_path=root_path,
                                          kitchen_name=kitchen_name)
        self._knife = KnifeSolo(self._kitchen_path)

    def register_node(self, host, password=None, bootstrap_version=None,
                      identity_file=None):
        """Registers a node in the kitchen."""
        self._knife.prepare(host, password=password,
                            bootstrap_version=bootstrap_version,
                            identity_file=identity_file)

    def create_kitchen(self, secret_key=None, source_repo=None):
        results = super(KitchenSolo, self).create_kitchen(
            secret_key=secret_key, source_repo=source_repo)

        nodes_path = os.path.join(self._kitchen_path, 'nodes')
        if os.path.exists(nodes_path):
            if any((f.endswith('.json') for f in os.listdir(nodes_path))):
                msg = ("Kitchen already exists and seems to have nodes "
                       "defined in it: %s" % nodes_path)
                LOG.debug(msg)
                return {"kitchen": self._kitchen_path}

        # we don't pass the config file here because we're creating the
        # kitchen for the first time and knife will overwrite our config
        # file
        self._knife.init()

        return results

    def write_node_attributes(self, host, attributes, run_list=None):
        """Merge node attributes into existing ones in node file."""
        node_path = self._knife.get_node_path(host)
        if not os.path.exists(node_path):
            raise exceptions.CheckmateException(
                "Node '%s' is not registered in %s" % (host,
                                                       self._kitchen_path))
        if attributes or run_list:
            lock = threading.Lock()
            lock.acquire()
            try:
                with file(node_path, 'r') as node_file_r:
                    node = json.load(node_file_r)
                if 'run_list' not in node:
                    node['run_list'] = []
                if run_list:
                    for entry in run_list:
                        if entry not in node['run_list']:
                            node['run_list'].append(entry)
                if attributes:
                    utils.merge_dictionary(node, attributes)

                with file(node_path, 'w') as node_file_w:
                    json.dump(node, node_file_w)
                LOG.info("Node %s written in %s", node,
                         node_path, extra=dict(data=node))
                return node
            except StandardError:
                raise
            finally:
                lock.release()

    def ruby_role_exists(self, name):
        """Checks if a ruby role file exists."""
        ruby_role_path = os.path.join(self.kitchen_path, 'roles',
                                      '%s.rb' % name)
        return os.path.exists(ruby_role_path)

    def write_role(self, name, desc=None, run_list=None,
                   default_attributes=None, override_attributes=None,
                   env_run_lists=None):
        """Write/Update role."""
        role_path = os.path.join(self.kitchen_path, 'roles', '%s.json' % name)

        if os.path.exists(role_path):
            with file(role_path, 'r') as role_file_r:
                role = json.load(role_file_r)
            if run_list is not None:
                role['run_list'] = run_list
            if default_attributes is not None:
                role['default_attributes'] = default_attributes
            if override_attributes is not None:
                role['override_attributes'] = override_attributes
            if env_run_lists is not None:
                role['env_run_lists'] = env_run_lists
        else:
            role = {
                "name": name,
                "chef_type": "role",
                "json_class": "Chef::Role",
                "default_attributes": default_attributes or {},
                "description": desc,
                "run_list": run_list or [],
                "override_attributes": override_attributes or {},
                "env_run_lists": env_run_lists or {}
            }

        LOG.debug("Writing role '%s' to %s", name, role_path)
        with file(role_path, 'w') as role_file_w:
            json.dump(role, role_file_w)
        return role

    def write_data_bag(self, bag_name, item_name, contents, secret_file=None):
        """Writes data bag to the kitchen."""
        if not os.path.exists(self._knife.data_bags_path):
            msg = ("Data bags path does not exist: %s" %
                   self._knife.data_bags_path)
            raise exceptions.CheckmateException(msg)

        self._knife.create_data_bag(bag_name)

        lock = threading.Lock()
        lock.acquire()
        try:
            self._knife.create_data_bag_item(bag_name, item_name,
                                             contents,
                                             secret_file=secret_file)
        except subprocess.CalledProcessError as exc:
            raise exceptions.CheckmateCalledProcessError(exc.returncode,
                                                         exc.cmd,
                                                         output=str(exc))
        finally:
            lock.release()
