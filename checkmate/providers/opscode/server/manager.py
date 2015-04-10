# pylint: disable=R0913,R0914
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
                       github_token=None, berksfile=None,
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
                                  kitchen_name=service_name,
                                  github_token=github_token)
        environment.create_env_dir()

        key_data = environment.create_kitchen_keys(
            private_key=private_key, public_key_ssh=public_key_ssh)

        environment.ensure_kitchen_path_exists()

        kitchen_data = environment.create_kitchen(secret_key=secret_key,
                                                  source_repo=source_repo,
                                                  berksfile=berksfile)
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
        if source_repo or berksfile:
            environment.fetch_cookbooks()
        else:
            error_message = ("Neither source repo nor Berksfile supplied. At "
                             "least one of them is required")
            raise exceptions.CheckmateException(
                error_message, friendly_message=exceptions.BLUEPRINT_ERROR)

        results = {"environment": environment.path}
        results.update(kitchen_data)
        results.update(key_data)
        LOG.debug("create_kitchen returning: %s", results)
        return results

    @staticmethod
    def register_node(context, deployment_id, name, desc=None, run_list=None,
                      default_attributes=None, normal_attributes=None,
                      override_attributes=None, environment=None):
        """Create Node on CHhef Server."""
        data = {
            'chef_type': 'node',
            'json_class': 'Chef::Node',
            'name': name,
        }
        if environment:
            data['chef_environment'] = environment
        if desc:
            data['description'] = desc
        if run_list is not None:
            data['run_list'] = run_list.split(', ')
        if default_attributes is not None:
            data['default'] = default_attributes
        if normal_attributes is not None:
            data['normal'] = normal_attributes
        if override_attributes is not None:
            data['override'] = override_attributes

        LOG.debug("Writing node '%s'", name)
        # TODO(zns): bypassing node creation - causes 403 in bootstrap
        return
        kitchen = ChefKitchen(deployment_id)
        knife = kitchen._knife
        with tempfile.NamedTemporaryFile(suffix='.js') as handle:
            json.dump(data, handle)
            handle.flush()
            knife.run_command(['knife', 'node', 'from', 'file',
                               handle.name, '--disable-editing'])
        return data

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
        with tempfile.NamedTemporaryFile(suffix='.js') as handle:
            json.dump(data, handle)
            handle.flush()
            if preexisting:
                command = 'edit'
            else:
                command = 'create'
            knife.run_command(['knife', 'environment', command, name,
                               'from', 'file', handle.name,
                               '--disable-editing'])

        return data

    @staticmethod
    def delete_environment(name, deployment_id):
        """Delete environment."""
        kitchen = ChefKitchen(deployment_id)
        knife = kitchen._knife
        knife.run_command(['knife', 'environment', 'delete', name, '-y'])

    @staticmethod
    def delete_client(name, deployment_id):
        """Delete client."""
        kitchen = ChefKitchen(deployment_id)
        knife = kitchen._knife
        knife.run_command(['knife', 'client', 'delete', name, '-y'])

    @staticmethod
    def delete_node(name, deployment_id):
        """Delete node."""
        kitchen = ChefKitchen(deployment_id)
        knife = kitchen._knife
        knife.run_command(['knife', 'node', 'delete', name, '-y'])

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
        with tempfile.NamedTemporaryFile(suffix='.js') as handle:
            json.dump(data, handle)
            handle.flush()
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
                       kitchen_name='kitchen', secret_file=None):
        """Write/Update data bag."""
        if contents is None:
            return
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
        bags_dir_rel_path = os.path.join(kitchen_name, 'data_bags')
        kitchen.ensure_path_exists(bags_dir_rel_path)
        bag_rel_path = os.path.join('data_bags', bag_name,
                                    '%s.json' % item_name)
        bag_full_path = os.path.join(kitchen._kitchen_path, bag_rel_path)
        kitchen.write_kitchen_file(bag_full_path, json.dumps(data))
        try:
            knife_command = ['knife', 'data', 'bag', 'from', 'file',
                             bag_name, bag_full_path, '--disable-editing']
            if secret_file:
                secret_file_path = os.path.join(kitchen._kitchen_path,
                                                secret_file)
                knife_command = knife_command + ['--secret-file',
                                                 secret_file_path]
            knife.run_command(knife_command)
        finally:
            os.unlink(bag_full_path)
        LOG.info("Updated data bag %s item %s", bag_name, item_name)
        return data

    @staticmethod
    def upload(context, deployment_id, environment, simulation=False):
        """Berks upload cookbooks."""
        kitchen = ChefKitchen(deployment_id)

        if simulation:
            LOG.info("Would run berks")
            return True

        env = os.environ.copy()
        env['BERKSHELF_CHEF_CONFIG'] = os.path.join(kitchen.kitchen_path,
                                                    '.chef', 'knife.rb')
        # Downloads cookbooks based on Berksfile.lock locked versions
        params = ['berks', 'install']
        stdout, stderr, _ = utils.check_all_output(
            params, cwd=kitchen.kitchen_path, env=env)
        LOG.debug("'berks install' results: %s, %s", stdout, stderr)

        # Upload them to the server
        params = ['berks', 'upload']
        stdout, stderr, _ = utils.check_all_output(
            params, cwd=kitchen.kitchen_path, env=env)
        LOG.debug("'berks upload' results: %s, %s", stdout, stderr)

        # Pins cookbook versions in the environment
        params = ['berks', 'apply', environment]
        stdout, stderr, _ = utils.check_all_output(
            params, cwd=kitchen.kitchen_path, env=env)
        LOG.debug("'berks apply' results: %s, %s", stdout, stderr)

        return True

    @staticmethod
    def bootstrap(context, deployment_id, name, ip, username='root',
                  password=None, port=22, identity_file=None,
                  run_list=None, distro='chef-full', bootstrap_version=None,
                  environment=None, attributes=None,
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
        if bootstrap_version:
            params.extend(['--bootstrap-version', bootstrap_version])
        if kitchen.secret_key_path:
            params.extend(['--secret-file', kitchen.secret_key_path])

        if simulation:
            results = {'status': 'ACTIVE'}
            LOG.info("Would run: %s", params)
            return results

        results = {'status': 'BUILD'}
        if callable(callback):
            callback(results)
        if attributes:
            params.extend(['-j', json.dumps(attributes)])
        knife.run_command(params)
        results = {'status': "ACTIVE"}
        return results
