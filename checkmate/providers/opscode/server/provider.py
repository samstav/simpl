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

"""Implements a Chef Server configuration management provider."""

import logging
import os

import chef
from SpiffWorkflow import operators
from SpiffWorkflow import specs

from checkmate.providers.opscode import base
from checkmate.providers import ProviderBase
from checkmate.providers.opscode.chef_map import ChefMap


LOG = logging.getLogger(__name__)


class Provider(base.BaseOpscodeProvider):

    """Implements a Chef Server configuration management provider."""

    name = 'chef-server'
    vendor = 'opscode'

    __status_mapping__ = {
        'ACTIVE': 'ACTIVE',
        'BUILD': 'BUILD',
        'DELETED': 'DELETED',
        'ERROR': 'ERROR',
        'CONFIGURE': 'CONFIGURE',
    }

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)

        # Map File
        self.source = self.get_setting('source')
        if self.source:
            self.map_file = ChefMap(url=self.source)
        else:
            # Create noop map file
            self.map_file = ChefMap(raw="")
        self.server_credentials = {}

    def prep_environment(self, wfspec, deployment, context):
        ProviderBase.prep_environment(self, wfspec, deployment, context)
        if self.prep_task:
            return  # already prepped

        self.server_credentials = {
            'server_url': deployment.get_setting('server-url',
                                                 provider_key=self.key),
            'server_username': deployment.get_setting('server-username',
                                                      provider_key=self.key),
            'server_user_key': deployment.get_setting('server-user-key',
                                                      provider_key=self.key),
            'validator_pem': deployment.get_setting('validator-pem',
                                                    provider_key=self.key),
            'validator_username': deployment.get_setting('validator-username',
                                                         provider_key=self.key)
        }
        source_repo = deployment.get_setting('source', provider_key=self.key)
        create_workspace = specs.Celery(
            wfspec,
            'Create Workspace',
            'checkmate.providers.opscode.server.tasks.create_kitchen',
            call_args=[
                context.get_queued_task_dict(deployment_id=deployment['id']),
                deployment['id'],
                'kitchen'
            ],
            source_repo=source_repo,
            server_credentials=self.server_credentials,
            defines={'resource': 'workspace', 'provider': self.key},
            properties={'estimated_duration': 10, 'task_tags': ['root']}
        )
        create_environment = specs.Celery(
            wfspec,
            'Create Chef Server Environment',
            'checkmate.providers.opscode.server.tasks.manage_environment',
            call_args=[
                context.get_queued_task_dict(deployment_id=deployment['id']),
                deployment['id'],
                deployment['id']  # environment name
            ],
            desc='Checkmate Environment',
            defines={'resource': 'workspace', 'provider': self.key},
            properties={'estimated_duration': 10}
        )
        create_environment.follow(create_workspace)

        upload_environment = specs.Celery(
            wfspec,
            'Upload Cookbooks',
            'checkmate.providers.opscode.server.tasks.upload_cookbooks',
            call_args=[
                context.get_queued_task_dict(deployment_id=deployment['id']),
                deployment['id'],
                deployment['id']  # environment name
            ],
            defines={'resource': 'workspace', 'provider': self.key},
            properties={'estimated_duration': 60}
        )
        upload_environment.follow(create_environment)
        self.prep_task = upload_environment
        return {'root': create_workspace, 'final': self.prep_task}

    def cleanup_environment(self, wfspec, deployment, context):
        call = 'checkmate.providers.opscode.server.tasks.delete_environment'
        defines = {'provider': self.key, 'resource': 'workspace'}
        call_args = [
            context.get_queued_task_dict(deployment_id=deployment['id']),
            deployment['id'],
        ]
        properties = {'estimated_duration': 1, 'task_tags': ['cleanup']}
        cleanup_task = specs.Celery(wfspec, 'Delete Chef Environment', call,
                                    call_args=call_args,
                                    defines=defines, properties=properties)

        return {'root': cleanup_task, 'final': cleanup_task}

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        wait_on, service_name, component = self._add_resource_tasks_helper(
            resource, key, wfspec, deployment, context, wait_on)
        context_arg = context.get_queued_task_dict(
            deployment_id=deployment['id'], resource_key=key)

        # Get component/role or recipe name
        component_id = component['id']
        LOG.debug("Determining component from dict: %s", component_id,
                  extra=component)

        run_list = self.map_file.get_component_run_list(component)

        register_node_task = specs.Celery(
            wfspec,
            'Register Server:%s (%s)' % (key, resource['service']),
            'checkmate.providers.opscode.server.tasks.register_node',
            call_args=[
                context_arg,
                deployment['id'],
                resource.get('dns-name')
            ],
            environment=deployment['id'],
            defines={'resource': key, 'provider': self.key},
            description=("Register the node in the Chef Server. "
                         "Nothing is done the node itself"),
            properties={'estimated_duration': 20},
            **run_list
        )
        self.prep_task.connect(register_node_task)

        resource = deployment['resources'][key]
        host_idx = resource.get('hosted_on', key)
        instance_ip = operators.PathAttrib("instance:%s/ip" % host_idx)

        proxy_kwargs = self.get_bastion_kwargs()
        ssh_apt_get_task = specs.Celery(
            wfspec,
            'Apt-get Fix:%s (%s)' % (key, resource['service']),
            'checkmate.ssh.execute_2',
            call_args=[
                context_arg,
                instance_ip,
                "sudo apt-get update",
                'root'
            ],
            password=operators.PathAttrib(
                'instance:%s/password' % resource.get('hosted_on', key)
            ),
            identity_file=operators.Attrib('private_key_path'),
            defines={'resource': key, 'provider': self.key},
            properties={'estimated_duration': 100},
            **proxy_kwargs
        )
        # TODO: stop assuming only one wait_on=create_server_task
        wait_on[0].connect(ssh_apt_get_task)

        bootstrap_task = anchor_task = specs.Celery(
            wfspec,
            'Bootstrap Server:%s (%s)' % (key, resource['service']),
            'checkmate.providers.opscode.server.tasks.bootstrap',
            call_args=[
                context_arg,
                deployment['id'],
                resource.get('dns-name'),
                instance_ip
            ],
            password=operators.PathAttrib(
                'instance:%s/password' % resource.get('hosted_on', key)
            ),
            identity_file=operators.Attrib('private_key_path'),
            environment=deployment['id'],
            defines={'resource': key, 'provider': self.key},
            properties={'estimated_duration': 90},
            **run_list
        )

        # Copied from solo
        if self.map_file.has_mappings(component_id):
            collect_data_tasks = self.get_prep_tasks(
                wfspec, deployment, key, component, context,
                provider='checkmate.providers.opscode.server')
            bootstrap_task.follow(collect_data_tasks['final'])
            anchor_task = collect_data_tasks['root']

        # Collect dependencies
        dependencies = [self.prep_task] if self.prep_task else []
        dependencies.extend([ssh_apt_get_task, register_node_task])

        # Wait for relations tasks to complete
        for relation_key in resource.get('relations', {}).keys():
            tasks = wfspec.find_task_specs(resource=key,
                                           relation=relation_key, tag='final')
            if tasks:
                dependencies.extend(tasks)

        server_id = resource.get('hosted_on', key)

        wfspec.wait_for(
            anchor_task, dependencies,
            name="After server %s (%s) is registered and options are ready"
                 % (server_id, service_name),
            description="Before applying chef recipes, we need to know that "
                        "the server has chef on it and that the overrides "
                        "(ex. database settings) have been applied"
        )

        # if we have a host task marked 'complete', make that wait on configure
        host_complete = self.get_host_complete_task(wfspec, resource)
        if host_complete:
            wfspec.wait_for(
                host_complete,
                [bootstrap_task],
                name='Wait for %s to be configured before completing host %s' %
                     (service_name, resource.get('hosted_on', key)))

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        target = deployment['resources'][relation['target']]
        interface = relation['interface']

        if interface == 'mysql':
            #Take output from Create DB task and write it into
            # the 'override' dict to be available to future tasks
            context_arg = context.get_queued_task_dict(
                deployment_id=deployment['id'], resource_key=key)

            tasks = wfspec.find_task_specs(relation=relation['target'],
                                           provider=target['provider'],
                                           tag='final')

            compile_override = specs.Transform(
                wfspec,
                "Prepare Overrides:%s" % key,
                transforms=[
                    "my_task.attributes['overrides']={'wordpress': {'db': "
                    "{'host': my_task.attributes['hostname'], "
                    "'database': my_task.attributes['context']['db_name'], "
                    "'user': my_task.attributes['context']['db_username'], "
                    "'password': my_task.attributes['context']"
                    "['db_password']}}}"
                ],
                description="Get all the variables we need (like database "
                            "name and password) and compile them into JSON "
                            "that we can set on the role or environment",
                defines=dict(
                    relation=relation_key, provider=self.key, task_tags=None
                )
            )
            wfspec.wait_for(compile_override, tasks)

            set_overrides = specs.Celery(
                wfspec,
                "Write Database Settings:%s" % key,
                'checkmate.providers.opscode.server.tasks.manage_env',
                call_args=[
                    context_arg,
                    deployment['id']
                ],
                desc='Checkmate Environment',
                override_attributes=operators.Attrib('overrides'),
                description="Take the JSON prepared earlier and write it into"
                            "the environment overrides. It will be used by "
                            "the Chef recipe to connect to the database",
                defines=dict(
                    relation=relation_key, resource=key,
                    provider=self.key, task_tags=None
                ),
                properties={'estimated_duration': 15}
            )

            wait_on = [compile_override, self.prep_task]
            wfspec.wait_for(
                set_overrides, wait_on,
                name="Wait on Environment and Settings:%s" % key
            )

            config_final = wfspec.find_task_specs(relation=key,
                                                  provider=self.key,
                                                  tag='final')
            # Assuming input is join
            if config_final:
                assert isinstance(config_final.inputs[0], specs.Merge)
                set_overrides.connect(config_final.inputs[0])

        else:
            LOG.warning(
                "Provider '%s' does not recognized connection interface '%s'",
                self.key, interface
            )

    @staticmethod
    def connect(context):
        api = chef.autoconfigure(
            base_path=os.environ.get('CHECKMATE_CHEF_PATH')
        )
        return api
