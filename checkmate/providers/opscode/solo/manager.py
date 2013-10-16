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
"""Rackspace solo provider manager."""
import logging
import os
import re
import shutil
import subprocess

from checkmate.common import config
from checkmate import exceptions
from checkmate.providers.opscode.solo.chef_environment import ChefEnvironment
from checkmate import ssh

CONFIG = config.current()
LOG = logging.getLogger(__name__)


class Manager(object):
    """Contains loadbalancer provider model and logic for interaction."""

    @staticmethod
    def delete_cookbooks(name, service_name, path=None):
        """Remove cookbooks directory and contents from the file system."""
        environment = ChefEnvironment(name, root_path=path,
                                      kitchen_name=service_name)
        environment.delete_cookbooks()

    @staticmethod
    def delete_environment(name, path=None):
        """Remove the chef environment from the file system."""
        environment = ChefEnvironment(name, root_path=path)
        environment.delete()

    @staticmethod
    def create_environment(name, service_name, path=None, private_key=None,
                           public_key_ssh=None, secret_key=None,
                           source_repo=None, simulation=False):
        """Create a knife-solo environment

        The environment is a directory structure that is self-contained and
        separate from other environments. It is used by this provider to run
        knife solo commands.

        :param name: the name of the environment. This will be the directory
         name.
        :param path: an override to the root path where to create this
        environment
        :param private_key: PEM-formatted private key
        :param public_key_ssh: SSH-formatted public key
        :param secret_key: used for data bag encryption
        :param source_repo: provides cookbook repository in valid git syntax
        """
        if simulation:
            return {
                'environment': '/var/tmp/%s/' % name,
                'kitchen': '/var/tmp/%s/kitchen' % name,
                'private_key_path': '/var/tmp/%s/private.pem' % name,
                'public_key_path': '/var/tmp/%s/checkmate.pub' % name,
            }

        environment = ChefEnvironment(name, root_path=path,
                                      kitchen_name=service_name)
        environment.create_env_dir()

        key_data = environment.create_environment_keys(
            private_key=private_key, public_key_ssh=public_key_ssh)

        kitchen_data = environment.create_kitchen(secret_key=secret_key,
                                                  source_repo=source_repo)
        kitchen_key_path = os.path.join(environment.kitchen_path,
                                        'certificates',
                                        'checkmate-environment.pub')
        shutil.copy(environment.public_key_path, kitchen_key_path)
        LOG.debug("Wrote environment public key to kitchen: %s",
                  kitchen_key_path)

        if source_repo:
            environment.fetch_cookbooks()
        else:
            error_message = "Source repo not supplied and is required"
            raise exceptions.CheckmateException(
                error_message, friendly_message=exceptions.BLUEPRINT_ERROR)

        results = {"environment": environment.path}
        results.update(kitchen_data)
        results.update(key_data)
        LOG.debug("create_environment returning: %s", results)
        return results

    @staticmethod
    def register_node(context, host, environment, callback, path=None,
                      password=None, omnibus_version=None, attributes=None,
                      identity_file=None, kitchen_name='kitchen',
                      simulate=False):
        """Register a node in Chef.

        Using 'knife prepare' we will:
        - update apt caches on Ubuntu by default (which bootstrap does not do)
        - install chef on the client
        - register the node by creating as .json file for it in /nodes/

        Note: Maintaining same 'register_node' name as chefserver.py

        :param host: the public IP of the host (that's how knife solo tracks
        the nodes)
        :param environment: the ID of the environment/deployment
        :param path: an optional override for path to the environment root
        :param password: the node's password
        :param omnibus_version: override for knife bootstrap (default=latest)
        :param attributes: attributes to set on node (dict)
        :param identity_file: private key file to use to connect to the node
        """
        instance_key = 'instance:%s' % context['resource_key']
        results = {'status': "BUILD"}
        if simulate:
            # Update status of current resource to BUILD
            if attributes:
                node = {'run_list': []}  # default
                node.update(attributes)
                results.update({'node-attributes': node})
            results = {instance_key: results}
            return results

        res = {}

        results = {instance_key: results}
        res.update(results)

        callback(res)

        env = ChefEnvironment(environment, root_path=path,
                              kitchen_name=kitchen_name)

        # Rsync problem with creating path (missing -p so adding it ourselves)
        # and doing this before the complex prepare work
        ssh.remote_execute(host, "mkdir -p %s" % env.kitchen_path, 'root',
                           password=password, identity_file=identity_file)

        try:
            env.register_node(host, password=password,
                              omnibus_version=omnibus_version,
                              identity_file=identity_file)
        except (subprocess.CalledProcessError,
                exceptions.CheckmateCalledProcessError) as exc:
            msg = "Knife prepare failed for %s. Retrying." % host
            LOG.warn(msg)
            raise exceptions.CheckmateException(message=str(exc),
                                                options=exceptions.CAN_RESUME)
        except StandardError as exc:
            LOG.error("Knife prepare failed with an unhandled error '%s' for "
                      "%s.", exc, host)
            raise exc

        try:
            results = ssh.remote_execute(host, "knife -v", 'root',
                                         password=password,
                                         identity_file=identity_file)
            LOG.debug("Chef install check results on %s: %s", host,
                      results['stdout'])
            if (re.match('^Chef: [0-9]+.[0-9]+.[0-9]+', results['stdout'])
                    is None):
                exc = exceptions.CheckmateException(
                    "Check for chef install failed with unexpected response "
                    "'%s'" % results, options=exceptions.CAN_RESUME)
                raise exc
        except StandardError as exc:
            LOG.error("Chef install failed on %s: %s", host, exc)
            raise exceptions.CheckmateException(str(exc),
                                                options=exceptions.CAN_RESUME)

        node_data = env.write_node_attributes(host, attributes)
        if node_data:
            results = {
                instance_key: {
                    'node-attributes': node_data
                }
            }
            return results
