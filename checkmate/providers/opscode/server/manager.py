# pylint: disable=R0913,R0914
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

"""OpsCode Chef Server provider manager."""

import json
import logging
import os
import shutil
import tempfile

from checkmate.common import config
from checkmate import exceptions
from checkmate.providers.opscode.kitchen import ChefKitchen
from checkmate import utils

CONFIG = config.current()
LOG = logging.getLogger(__name__)


class Manager(object):

    """Contains Chef Server provider model and logic for interaction."""

    @staticmethod
    def create_kitchen(name, service_name, path=None, private_key=None,
                       public_key_ssh=None, secret_key=None,
                       source_repo=None, server_credentials=None,
                       simulation=False):
        """Create a workspace and knife kitchen.

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
        :param server_credentials: keys and info to connect to chef server
        """
        if simulation:
            return {
                'environment': '/var/tmp/%s/' % name,
                'kitchen': '/var/tmp/%s/kitchen' % name,
                'private_key_path': '/var/tmp/%s/private.pem' % name,
                'public_key_path': '/var/tmp/%s/checkmate.pub' % name,
            }

        environment = ChefKitchen(name, root_path=path,
                                  kitchen_name=service_name)
        environment.create_env_dir()

        key_data = environment.create_kitchen_keys(
            private_key=private_key, public_key_ssh=public_key_ssh)

        environment.ensure_kitchen_path_exists()

        kitchen_data = environment.create_kitchen(secret_key=secret_key,
                                                  source_repo=source_repo)
        kitchen_key_path = os.path.join(environment.kitchen_path,
                                        'certificates',
                                        'checkmate-environment.pub')
        shutil.copy(environment.public_key_path, kitchen_key_path)
        LOG.debug("Wrote environment public key to kitchen: %s",
                  kitchen_key_path)
        # Write credentials
        if server_credentials:
            knife_rb = {}
            for key, value in server_credentials.items():
                if key == 'server_url':
                    knife_rb['chef_server_url'] = '"%s"' % value
                elif key == 'server_username':
                    knife_rb['node_name'] = '"%s"' % value
                elif key == 'server_user_key':
                    knife_rb['client_key'] = '"%s"' % os.path.join(
                        environment.kitchen_path, ".chef", "client.key")
                    environment.write_kitchen_file(".chef/client.key", value)
                elif key == 'validator_pem':
                    knife_rb['validation_key'] = '"%s"' % os.path.join(
                        environment.kitchen_path, ".chef", "validator.key")
                    environment.write_kitchen_file(".chef/validator.key",
                                                   value)
                elif key == 'validator_username':
                    knife_rb['validation_client_name'] = '"%s"' % value
            if knife_rb:
                environment._knife.update_config(**knife_rb)
        if source_repo:
            environment.fetch_cookbooks()
        else:
            error_message = "Source repo not supplied and is required"
            raise exceptions.CheckmateException(
                error_message, friendly_message=exceptions.BLUEPRINT_ERROR)

        results = {"environment": environment.path}
        results.update(kitchen_data)
        results.update(key_data)
        LOG.debug("create_kitchen returning: %s", results)
        return results

    @staticmethod
    def update_environment(name, deployment_id, desc=None, run_list=None,
                           default_attributes=None, override_attributes=None,
                           env_run_lists=None):
        """Write/Update environment."""
        kitchen = ChefKitchen(deployment_id)
        knife = kitchen._knife
        preexisting = False
        envs = knife.run_command(['knife', 'environment', 'list']).split()
        if name in envs:
            preexisting = True
            data = json.loads(knife.run_command(
                ['knife', 'environment', 'show', name, '-F', 'json']))
        else:
            data = {}

        if run_list is not None:
            data['run_list'] = run_list
        if default_attributes is not None:
            data['default_attributes'] = default_attributes
        if override_attributes is not None:
            data['override_attributes'] = override_attributes
        if env_run_lists is not None:
            data['env_run_lists'] = env_run_lists
        if desc:
            data['description'] = desc

        LOG.debug("Writing environment '%s'", name)
        with tempfile.NamedTemporaryFile() as handle:
            json.dump(data, handle)
            if preexisting:
                command = 'edit'
            else:
                command = 'create'
            knife.run_command(['knife', 'environment', command, name,
                               'from', 'file', handle.name,
                               '--disable-editing'])

        return data

    @staticmethod
    def update_role(name, deployment_id, desc=None, run_list=None,
                    default_attributes=None, override_attributes=None,
                    run_lists=None):
        """Write/Update role."""
        kitchen = ChefKitchen(deployment_id)
        knife = kitchen._knife
        preexisting = False
        envs = knife.run_command(['knife', 'role', 'list']).split()
        if name in envs:
            preexisting = True
            data = json.loads(knife.run_command(
                ['knife', 'role', 'show', name, '-F', 'json']))
        else:
            data = {}

        if run_list is not None:
            data['run_list'] = run_list
        if default_attributes is not None:
            data['default_attributes'] = default_attributes
        if override_attributes is not None:
            data['override_attributes'] = override_attributes
        if run_lists is not None:
            data['run_lists'] = run_lists
        if desc:
            data['description'] = desc

        LOG.debug("Writing role '%s'", name)
        with tempfile.NamedTemporaryFile() as handle:
            json.dump(data, handle)
            if preexisting:
                command = 'edit'
            else:
                command = 'create'
            knife.run_command(['knife', 'role', command, name,
                               'from', 'file', handle.name,
                               '--disable-editing'])

        return data

    @staticmethod
    def update_databag(deployment_id, bag_name, item_name, contents,
                       kitchen_name='kitchen'):
        """Write/Update data bag."""
        kitchen = ChefKitchen(deployment_id)
        knife = kitchen._knife
        data = {}
        bags = knife.run_command(['knife', 'data', 'bag', 'list']).split()
        if bag_name in bags:
            items = knife.run_command(
                ['knife', 'data', 'bag', 'show', bag_name]).split()
            if item_name in items:
                data = json.loads(knife.run_command(
                    ['knife', 'data', 'bag', 'show', bag_name, item_name,
                     '-F', 'json']))
        else:
            knife.run_command(['knife', 'data', 'bag', 'create', bag_name])
            LOG.info("Created data bag %s", bag_name)
        utils.merge_dictionary(data, contents)
        LOG.debug("Writing data bag '%s'", bag_name)
        if 'id' not in data:
            data['id'] = item_name
        elif data['id'] != item_name:
            raise exceptions.CheckmateValidationException(
                "Data bag item id mismatch")
        path = os.path.join('databags', bag_name, '%s.json' % item_name)
        kitchen.write_kitchen_file(path, json.dumps(data))
        try:
            knife.run_command(['knife', 'data', 'bag', 'from', 'file',
                               bag_name, path, '--disable-editing'])
        finally:
            os.unlink(path)
        LOG.info("Updated data bag %s item %s", bag_name, item_name)
        return data

    @staticmethod
    def upload(context, deployment_id, simulation=False):
        """Berks upload cookbooks."""
        kitchen = ChefKitchen(deployment_id)
        knife = kitchen._knife

        if simulation:
            LOG.info("Would run berks")
            return True

        params = ['berks', 'install']
        knife.run_command(params)

        params = ['berks', 'update']
        knife.run_command(params)

        params = ['berks', 'upload']
        knife.run_command(params)

        params = ['berks', 'apply', deployment_id]
        knife.run_command(params)

        return True

    @staticmethod
    def bootstrap(context, deployment_id, name, ip, username='root',
                  password=None, port=22, identity_file=None,
                  run_list=None, distro='chef-full', environment=None,
                  simulation=False, callback=None):
        """Bootstrap a node with knife."""
        kitchen = ChefKitchen(deployment_id)
        knife = kitchen._knife

        if CONFIG.knife_bastion_suffix:
            address = '%s%s' % (ip, CONFIG.knife_bastion_suffix)
        else:
            address = ip

        params = ['knife', 'bootstrap', address, '-x', username, '-N', name]
        if identity_file:
            params.extend(['-i', identity_file])
        if distro:
            params.extend(['-d', distro])
        if run_list:
            params.extend(['-r', run_list])
        if password:
            params.extend(['-P', password])
        if port:
            params.extend(['-p', str(port)])
        if environment:
            params.extend(['-E', environment])

        if simulation:
            results = {'status': 'ACTIVE'}
            LOG.info("Would run: %s", params)
            return results

        results = {'status': 'BUILD'}
        if callable(callback):
            callback(results)
        knife.run_command(params)
        results = {'status': "ACTIVE"}
        return results
