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

from checkmate import exceptions
from checkmate.providers.opscode import base
from checkmate.providers import ProviderBase
from checkmate.providers.opscode.chef_map import ChefMap


LOG = logging.getLogger(__name__)
OMNIBUS_DEFAULT = os.environ.get('CHECKMATE_CHEF_OMNIBUS_DEFAULT', "11.16.4-1")


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
            deployment['id'],
        ]
        properties = {'estimated_duration': 1, 'task_tags': ['cleanup']}
        cleanup_task = specs.Celery(wfspec, 'Delete Chef Environment', call,
                                    call_args=call_args,
                                    defines=defines, properties=properties)

        return {'root': cleanup_task, 'final': cleanup_task}

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        """Create and write settings, generate run_list, and call cook."""
        wait_on, service_name, component = self._add_resource_tasks_helper(
            resource, key, wfspec, deployment, context, wait_on)

        # Get component/role or recipe name
        component_id = component['id']
        LOG.debug("Determining component from dict: %s", component_id,
                  extra=component)

        bootstrap_version = deployment.get_setting(
            'bootstrap-version', provider_key=self.key,
            service_name=service_name)
        if not bootstrap_version:
            omnibus_version = deployment.get_setting(
                'omnibus-version', provider_key=self.key,
                service_name=service_name)
            if omnibus_version:
                bootstrap_version = omnibus_version
                LOG.warning("'omnibus-version' is deprecated. Please "
                            "update the blueprint to use "
                            "'bootstrap-version'")
            else:
                bootstrap_version = deployment.get_setting(
                    'bootstrap-version', provider_key=self.key,
                    service_name=service_name, default=OMNIBUS_DEFAULT)

        kwargs = self.map_file.get_component_run_list(component)
        resource = deployment['resources'][key]
        host_idx = resource.get('hosted_on', key)
        instance_ip = operators.PathAttrib("instance:%s/ip" % host_idx)
        anchor_task = configure_task = specs.Celery(
            wfspec,
            'Configure %s: %s (%s)' % (component_id, key, service_name),
            'checkmate.providers.opscode.server.tasks.bootstrap',
            call_args=[
                context.get_queued_task_dict(
                    deployment_id=deployment['id'],
                    resource_key=key),
                deployment['id'],
                instance_ip,
                instance_ip,  # name
            ],
            environment=deployment['id'],
            password=operators.PathAttrib(
                'instance:%s/password' % resource.get('hosted_on', key)
            ),
            bootstrap_version=bootstrap_version,
            merge_results=True,
            identity_file=operators.Attrib('private_key_path'),
            description="Bootstrap server as a Chef client",
            defines=dict(resource=key, provider=self.key, task_tags=['final']),
            properties={'estimated_duration': 100},
            **kwargs
        )

        if self.map_file.has_mappings(component_id):
            collect_data_tasks = self.get_prep_tasks(
                wfspec, deployment, key, component, context,
                provider='checkmate.providers.opscode.server')
            configure_task.follow(collect_data_tasks['final'])
            anchor_task = collect_data_tasks['root']

        # Collect dependencies
        dependencies = [self.prep_task] if self.prep_task else []

        # Wait for relations tasks to complete
        for relation_key in resource.get('relations', {}).keys():
            tasks = wfspec.find_task_specs(resource=key,
                                           relation=relation_key, tag='final')
            if tasks:
                dependencies.extend(tasks)

        server_id = resource.get('hosted_on', key)

        if anchor_task:
            wfspec.wait_for(
                anchor_task, dependencies,
                name="After server %s (%s) is registered and options are ready"
                     % (server_id, service_name),
                description="Before applying chef recipes, we need to know "
                            "that the server has chef on it and that the "
                            "overrides (ex. database settings) have been "
                            "applied"
            )

        # if we have a host task marked 'complete', make that wait on configure
        host_complete = self.get_host_complete_task(wfspec, resource)
        if host_complete:
            wfspec.wait_for(
                host_complete,
                [configure_task],
                name='Wait for %s to be configured before completing host %s' %
                     (service_name, resource.get('hosted_on', key)))

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        """Write out or Transform data. Provide final task for relation sources
        to hook into.
        """
        LOG.debug("Adding connection task for resource '%s' for relation '%s'",
                  key, relation_key, extra={'data': {'resource': resource,
                                                     'relation': relation}})

        environment = deployment.environment()
        provider = environment.get_provider(resource['provider'])
        component = provider.get_component(context, resource['component'])
        map_with_context = self.map_file.get_map_with_context(
            deployment=deployment, resource=resource, component=component)

        # Is this relation in one of our maps? If so, let's handle that
        tasks = []
        if map_with_context.has_requirement_mapping(resource['component'],
                                                    relation['requires-key']):
            LOG.debug("Relation '%s' for resource '%s' has a mapping",
                      relation_key, key)
            # Set up a wait for the relation target to be ready
            tasks = wfspec.find_task_specs(resource=relation['target'],
                                           tag='final')

        if tasks:
            # The collect task will have received a copy of the map and
            # will pick up the values that it needs when these precursor
            # tasks signal they are complete.
            collect_tasks = self.get_prep_tasks(
                wfspec, deployment, key, component, context,
                provider='checkmate.providers.opscode.server')
            wfspec.wait_for(collect_tasks['root'], tasks)

        if relation.get('relation') == 'host':
            # Wait on host to be ready
            wait_on = self.get_host_ready_tasks(resource, wfspec, deployment)
            if not wait_on:
                raise exceptions.CheckmateException(
                    "No host resource found for relation '%s'" % relation_key)
            attributes = map_with_context.get_attributes(resource['component'],
                                                         deployment)
            service_name = resource['service']
            kwargs = map_with_context.get_component_run_list(component)

            # Create chef setup tasks
            register_node_task = specs.Celery(
                wfspec,
                'Register Server %s (%s)' % (
                    relation['target'], resource['service']),
                'checkmate.providers.opscode.server.tasks.register_node',
                call_args=[
                    context.get_queued_task_dict(
                        deployment_id=deployment['id'],
                        resource_key=key),
                    deployment['id'],
                    operators.PathAttrib(
                        'instance:%s/ip' % relation['target'])  # name
                ],
                environment=deployment['id'],
                attributes=attributes,
                defines=dict(
                    resource=key, relation=relation_key, provider=self.key,
                    task_tags=['final']
                ),
                description=("Register the node on the Chef server"),
                properties=dict(estimated_duration=120),
                **kwargs
            )
            # Register only when server is up and environment is ready
            if self.prep_task:
                wait_on.append(self.prep_task)
            root = wfspec.wait_for(
                register_node_task, wait_on,
                name="After Environment is Ready and Server %s (%s) is Up" %
                     (relation['target'], service_name),
                resource=key, relation=relation_key, provider=self.key
            )
            if 'task_tags' in root.properties:
                root.properties['task_tags'].append('root')
            else:
                root.properties['task_tags'] = ['root']
            return dict(root=root, final=register_node_task)

        # Inform server when a client is ready if it has client mappings
        # TODO(zns): put this in an add_client_ready_tasks for all providers or
        # make it available as a separate workflow or set of tasks

        resources = deployment['resources']
        target = resources[relation['target']]
        if target['provider'] == self.key:
            if map_with_context.has_client_mapping(target['component'],
                                                   relation['requires-key']):
                server = target  # our view is from the source of the relation
                client = resource  # this is the client that is just finishing
                environment = deployment.environment()
                provider = environment.get_provider(server['provider'])
                server_component = provider.get_component(context,
                                                          server['component'])
                recon_tasks = self.get_reconfigure_tasks(wfspec, deployment,
                                                         client,
                                                         server,
                                                         server_component,
                                                         context)
                recollect_task = recon_tasks.get('root')

                final_tasks = wfspec.find_task_specs(resource=key,
                                                     provider=self.key,
                                                     tag='final')
                host_complete = self.get_host_complete_task(wfspec, server)
                final_tasks.extend(wfspec.find_task_specs(
                    resource=server.get('index'),
                    provider=self.key, tag='final')
                )
                if not final_tasks:
                    # If server already configured, anchor to root
                    LOG.warn("Did not find final task for resource %s", key)
                    final_tasks = [self.prep_task]
                LOG.debug("Reconfig waiting on %s", final_tasks)
                if recollect_task:
                    wfspec.wait_for(recollect_task, final_tasks)

                if host_complete:
                    LOG.debug("Re-ordering the Mark Server Online task to "
                              "follow Reconfigure tasks")
                    wfspec.wait_for(host_complete, [recon_tasks['final']])

    def get_reconfigure_tasks(self, wfspec, deployment, client, server,
                              server_component, context):
        """Gets (creates if does not exist) a task to reconfigure a server when
        a client is ready.

        This generates only one task per workflow which all clients tie in to.
        If it is desired for each client to trigger a separate call to
        reconfigure the server, then the client creation should be launched in
        a separate workflow.

        :param wfspec: the workflow specific
        :param deployment: the deployment
        :param client: the client resource dict
        :param server: the server resource dict
        :param server_component: the component for the server
        """
        result = {}
        LOG.debug("Inform server %s (%s) that client %s (%s) is ready to "
                  "connect it", server['index'], server['component'],
                  client['index'], client['component'])
        existing = wfspec.find_task_specs(resource=server['index'],
                                          provider=self.key,
                                          tag='client-ready')
        collect_tag = "reconfig"
        ready_tag = "reconfig-options-ready"

        if existing:
            reconfigure_task = existing[0]
            collect = wfspec.find_task_specs(resource=server['index'],
                                             provider=self.key,
                                             tag=collect_tag)
            if collect:
                root_task = collect[0]
            else:
                root_task = reconfigure_task
            result = {'root': root_task, 'final': reconfigure_task}
        return result

    @staticmethod
    def connect(context):
        # TODO (zns): support config from kitchen file?
        #api = chef.from_config_file(... path to knife.rb...)
        #return api
        return
