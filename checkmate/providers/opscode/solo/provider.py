# pylint: disable=R0912,R0913,R0914,R0915
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

"""Chef Solo configuration management provider."""
import copy
import logging
import os

from SpiffWorkflow import operators
from SpiffWorkflow import specs
import yaml
from yaml.composer import ComposerError
from yaml.parser import ParserError
from yaml.scanner import ScannerError

from checkmate import common
from checkmate.common import schema
from checkmate import exceptions
from checkmate import keys
from checkmate.providers.opscode.solo.chef_map import ChefMap
from checkmate.providers import ProviderBase

LOG = logging.getLogger(__name__)
OMNIBUS_DEFAULT = os.environ.get('CHECKMATE_CHEF_OMNIBUS_DEFAULT',
                                 "10.24.0")


class Provider(ProviderBase):
    """Implements a Chef Solo configuration management provider."""
    name = 'chef-solo'
    vendor = 'opscode'

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)

        # Map File
        self.source = self.get_setting('source')
        if self.source:
            self.map_file = ChefMap(url=self.source)
        else:
            # Create noop map file
            self.map_file = ChefMap(raw="")

    def prep_environment(self, wfspec, deployment, context):
        ProviderBase.prep_environment(self, wfspec, deployment, context)
        if self.prep_task:
            return  # already prepped
        self._hash_all_user_resource_passwords(deployment)

        # Create Celery Task
        settings = deployment.settings()
        all_keys = settings.get('keys', {})
        deployment_keys = all_keys.get('deployment', {})
        public_key_ssh = deployment_keys.get('public_key_ssh')
        private_key = deployment_keys.get('private_key')
        secret_key = deployment.get_setting('secret_key')
        source_repo = deployment.get_setting('source', provider_key=self.key)
        defines = {'provider': self.key}
        properties = {'estimated_duration': 30, 'task_tags': ['root'],
                      'resource': 'workspace'}
        task_name = 'checkmate.providers.opscode.solo.tasks.create_environment'
        self.prep_task = specs.Celery(wfspec,
                                      'Create Chef Environment', task_name,
                                      call_args=[
                                          context.get_queued_task_dict(
                                              deployment_id=deployment['id']),
                                          deployment['id'], 'kitchen'],
                                      public_key_ssh=public_key_ssh,
                                      private_key=private_key,
                                      secret_key=secret_key,
                                      source_repo=source_repo,
                                      provider=Provider.name,
                                      defines=defines,
                                      properties=properties)

        return {'root': self.prep_task, 'final': self.prep_task}

    def cleanup_environment(self, wfspec, deployment):
        call = 'checkmate.providers.opscode.solo.tasks.delete_environment'
        defines = {'provider': self.key, 'resource': 'workspace'}
        properties = {'estimated_duration': 1, 'task_tags': ['cleanup']}
        cleanup_task = specs.Celery(wfspec, 'Delete Chef Environment', call,
                                    call_args=[deployment['id']],
                                    defines=defines, properties=properties)

        return {'root': cleanup_task, 'final': cleanup_task}

    def cleanup_temp_files(self, wfspec, deployment):
        """Cleans up temporary files created during a deployment
        :param wfspec: workflow spec
        :param deployment: deployment being worked on
        :return: root and final tasks for cleaning up the environment
        """
        client_ready_tasks = wfspec.find_task_specs(provider=self.key,
                                                    tag='client-ready')
        final_tasks = wfspec.find_task_specs(provider=self.key, tag='final')
        client_ready_tasks.extend(final_tasks)
        call = 'checkmate.providers.opscode.solo.tasks.delete_cookbooks'
        defines = {'resource': 'workspace', 'provider': self.key}
        cleanup_task = specs.Celery(wfspec, 'Delete Cookbooks', call,
                                    call_args=[deployment['id'], 'kitchen'],
                                    defines=defines,
                                    properties={'estimated_duration': 1})
        root = wfspec.wait_for(cleanup_task, client_ready_tasks,
                               name="Wait before deleting cookbooks",
                               defines=defines)

        return {'root': root, 'final': cleanup_task}

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        """Create and write settings, generate run_list, and call cook."""
        wait_on, service_name, component = self._add_resource_tasks_helper(
            resource, key, wfspec, deployment, context, wait_on)
        #chef_map = self.get_map(component)
        self._add_component_tasks(wfspec, component, deployment, key,
                                  context, service_name)

    def _get_component_run_list(self, component):
        run_list = {}
        component_id = component['id']
        for mcomponent in self.map_file.components:
            if mcomponent['id'] == component_id:
                run_list = mcomponent.get('run-list', {})
                assert isinstance(run_list, dict), ("component '%s' run-list "
                                                    "is not a map" %
                                                    component_id)
        if not run_list:
            if 'role' in component:
                name = '%s::%s' % (component_id, component['role'])
            else:
                name = component_id
                if name == 'mysql':
                    # FIXME: hack (install server by default, not client)
                    name += "::server"
            if component_id.endswith('-role'):
                run_list['roles'] = [name[0:-5]]  # trim the '-role'
            else:
                run_list['recipes'] = [name]
        LOG.debug("Component run_list determined to be %s", run_list)
        return run_list

    def _add_component_tasks(self, wfspec, component, deployment, key,
                             context, service_name):
        # Get component/role or recipe name
        component_id = component['id']
        LOG.debug("Determining component from dict: %s", component_id,
                  extra=component)

        kwargs = self._get_component_run_list(component)

        # Create the cook task

        resource = deployment['resources'][key]
        host_idx = resource.get('hosted_on', key)
        instance_ip = operators.PathAttrib("instance:%s/ip" % host_idx)
        anchor_task = configure_task = specs.Celery(
            wfspec,
            'Configure %s: %s (%s)' % (component_id, key, service_name),
            'checkmate.providers.opscode.solo.tasks.cook',
            call_args=[
                context.get_queued_task_dict(
                    deployment_id=deployment['id'],
                    resource_key=key),
                instance_ip,
                deployment['id']
            ],
            password=operators.PathAttrib(
                'instance:%s/password' % resource.get('hosted_on', key)
            ),
            attributes=operators.PathAttrib('chef_options/attributes:%s' %
                                            key),
            identity_file=operators.Attrib('private_key_path'),
            description="Push and apply Chef recipes on the server",
            defines=dict(resource=key, provider=self.key, task_tags=['final']),
            properties={'estimated_duration': 100},
            **kwargs
        )

        if self.map_file.has_mappings(component_id):
            collect_data_tasks = self.get_prep_tasks(wfspec, deployment, key,
                                                     component, context)
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
                [configure_task],
                name='Wait for %s to be configured before completing host %s' %
                     (service_name, resource.get('hosted_on', key)))

    def get_prep_tasks(self, wfspec, deployment, resource_key, component,
                       context, collect_tag='collect',
                       ready_tag='options-ready'):
        """Create (or get if they exist) tasks that collect and write map
        options.

        The collect task will run its code whenever an input task completes.
        The code to pick up the actual values based on the map comes from the
        Transforms class.

        :param wfspec: the current workflow
        :param deployment: the current deployment
        :param resource_key: the key of the resource we are configuring
        :param component: the component for that resource
        :param collect_tag: the tag to use for the collect task.
        :param ready_tag: the tag to tuse for the final, options-ready task
        :returns: a dict with 'root' and 'final' tasks. The tasks are linked
                  together but are not linked into the workflow

        One collect task is created for each resource and marked with a
        'collect' tag.

        If databag tasks are needed, they are marked with a 'write-databag'
        tag.

        If role tasks are needed, they are marked with a 'write-role' tag.

        If a new set of tasks are needed (for example, in order to reconfigure
        a resource when a client is ready) then supply a different set of tags
        for the collect_tag and ready_tag than the default.

        Note:
        Only one databag with one item is currently supported per component.
        Only one role per component is supported now.
        """
        # Do tasks already exist?
        collect_tasks = wfspec.find_task_specs(provider=self.key,
                                               resource=resource_key,
                                               tag=collect_tag)
        if collect_tasks:
            ready_tasks = wfspec.find_task_specs(provider=self.key,
                                                 resource=resource_key,
                                                 tag=ready_tag)
            if not ready_tasks:
                raise exceptions.CheckmateException(
                    "'collect' task exists, but 'options-ready' is missing")
            return {'root': collect_tasks[0], 'final': ready_tasks[0]}

        write_databag = None
        write_role = None

        # Create the task data collection/map parsing task

        component_id = component['id']
        resource = deployment['resources'][resource_key]

        # Get a map file parsed with all the right objhects available in the
        # Jinja context. These objects had not been available until now.

        map_with_context = self.get_map_with_context(deployment=deployment,
                                                     resource=resource,
                                                     component=component)
        all_maps = self.get_resource_prepared_maps(resource, deployment,
                                                   map_file=map_with_context)

        chef_options = {}

        # Parse all maps and resolve the ones where the data is ready.

        unresolved = ChefMap.resolve_ready_maps(all_maps, deployment,
                                                chef_options)
        attrib_key = 'attributes:%s' % resource_key
        if attrib_key in chef_options:
            # Remove ones already added in Register
            del chef_options[attrib_key]

        # Create the output template defined in the map file

        output = map_with_context.get_component_output_template(component_id)
        name = "%s Chef Data for %s" % (collect_tag.capitalize(),
                                        resource_key)
        func = "checkmate.providers.opscode.solo.transforms" \
               ".Transforms.collect_options"
        collect_data = specs.SafeTransMerge(
            wfspec,
            name,
            function_name=func,
            description="Get data needed for our cookbooks and place it in a "
                        "structure ready for storage in a databag or role",
            properties={
                'task_tags': [collect_tag],
                'chef_maps': unresolved,
                'chef_output': output,
                'chef_options': chef_options,
                'deployment': deployment['id'],
                'extend_lists': True,
            },
            defines={'provider': self.key, 'resource': resource_key}
        )
        LOG.debug("Created data collection task for '%s'", resource_key)

        # Create the databag writing task (if needed)

        schemes = ['encrypted-databags', 'databags']
        databag_maps = ChefMap.filter_maps_by_schemes(
            all_maps, target_schemes=schemes) or []
        databags = {}
        for mapping in databag_maps:
            for target in mapping.get('targets', []):
                uri = ChefMap.parse_map_uri(target)
                scheme = uri['scheme']
                if scheme not in ['databags', 'encrypted-databags']:
                    continue
                encrypted = scheme == 'encrypted-databags'
                bag_name = uri['netloc']
                path_parts = uri['path'].strip('/').split('/')
                if len(path_parts) < 1:
                    msg = ("Mapping target '%s' is invalid. It needs "
                           "a databag name and a databag item name")
                    raise exceptions.CheckmateValidationException(msg)
                item_name = path_parts[0]

                if bag_name not in databags:
                    databags[bag_name] = {'encrypted': encrypted, 'items': []}
                if encrypted:
                    databags[bag_name]['encrypted'] = True
                if item_name not in databags[bag_name]['items']:
                    databags[bag_name]['items'].append(item_name)

        if len(databags) == 1:
            bag_name = next(databags.iterkeys())
            items = databags[bag_name]['items']
            if len(items) > 1:
                raise NotImplementedError("Chef-solo provider does not "
                                          "currently support more than one "
                                          "databag item per component. '%s' "
                                          "has multiple items: %s" %
                                          (bag_name, items))
            item_name = items[0]
            if databags[bag_name]['encrypted'] is True:
                secret_file = 'certificates/chef.pem'
                path = 'chef_options/encrypted-databags/%s/%s' % (bag_name,
                                                                  item_name)
            else:
                secret_file = None
                path = 'chef_options/databags/%s/%s' % (bag_name, item_name)

            if collect_tag == 'collect':
                name = "Write Data Bag for %s" % resource['index']
            else:
                name = "Rewrite Data Bag for %s (%s)" % (
                    resource['index'], collect_tag.capitalize())
            write_databag = specs.Celery(
                wfspec, name,
                'checkmate.providers.opscode.solo.tasks.write_databag',
                call_args=[context.get_queued_task_dict(
                    deployment_id=deployment['id'],
                    resource_key=resource_key),
                    deployment['id'], bag_name, item_name,
                    operators.PathAttrib(path)
                ],
                secret_file=secret_file,
                defines={
                    'provider': self.key,
                    'resource': resource_key,
                },
                properties={
                    'estimated_duration': 5,
                    'task_tags': ['write-databag'],
                }
            )

        elif len(databags) > 1:
            raise NotImplementedError("Chef-solo provider does not currently "
                                      "support more than one databag per "
                                      "component. Databags requested: %s" %
                                      databags.keys())

        # Create the role writing task (if needed)

        roles = {}
        for mcomponent in map_with_context.components:
            if mcomponent['id'] == component_id:

                # Collect from chef-roles

                roles = mcomponent.get('chef-roles', {})

                # Also run through map targets

                for mapping in mcomponent.get('maps', []):
                    for target in mapping.get('targets', []):
                        uri = map_with_context.parse_map_uri(target)
                        scheme = uri['scheme']
                        if scheme != 'roles':
                            continue
                        role_name = uri['netloc']

                        if role_name not in roles:
                            roles[role_name] = {'create': False,
                                                'recipes': []}
        if len(roles) == 1:
            role_name = next(roles.iterkeys())
            role = roles[role_name]
            path = 'chef_options/roles/%s' % role_name
            run_list = None
            recipes = role.get('recipes', [])
            if recipes:
                run_list = ["recipe[%s]" % r for r in recipes]
            # FIXME: right now we create all
            # if role['create'] == True:
            if collect_tag == 'collect':
                name = "Write Role %s for %s" % (role_name, resource_key)
            else:
                name = "Rewrite Role %s for %s (%s)" % (
                    role_name, resource_key, collect_tag.capitalize())
            write_role = specs.Celery(
                wfspec, name,
                'checkmate.providers.opscode.solo.tasks.manage_role',
                call_args=[context.get_queued_task_dict(
                    deployment_id=deployment['id'],
                    resource_key=resource_key), role_name,
                    deployment['id']],
                kitchen_name='kitchen',
                override_attributes=operators.PathAttrib(path),
                run_list=run_list,
                description="Take the JSON prepared earlier and write "
                            "it into the application role. It will be "
                            "used by the Chef recipe to access global "
                            "data",
                defines={
                    'provider': self.key,
                    'resource': resource_key
                },
                properties={
                    'estimated_duration': 5,
                    'task_tags': ['write-role'],
                },
            )
        elif len(roles) > 1:
            raise NotImplementedError("Chef-solo provider does not currently "
                                      "support more than one role per "
                                      "component")

        # Chain the tasks: collect -> write databag -> write role
        # Note: databag and role don't depend on each other. They could run in
        # parallel, but chaining them is easier for now and less tasks

        result = {'root': collect_data}
        if write_role:
            write_role.set_property(task_tags=['options-ready'])
            result['final'] = write_role
            if write_databag:
                write_databag.follow(collect_data)
                write_role.follow(write_databag)
            else:
                write_role.follow(collect_data)
        else:
            if write_databag:
                write_databag.follow(collect_data)
                write_databag.set_property(task_tags=['options-ready'])
                result['final'] = write_databag
            else:
                result['final'] = collect_data
                collect_data.properties['task_tags'].append('options-ready')
        return result

    def get_map_with_context(self, **kwargs):
        """Returns a map file that was parsed with real data in the context."""
        # Add defaults if there is a component and no defaults specified
        if kwargs and 'defaults' not in kwargs and 'component' in kwargs:
            component = kwargs['component']
            # used by setting() in Jinja context to return defaults
            defaults = {}
            for key, option in component.get('options', {}).iteritems():
                if 'default' in option:
                    default = option['default']
                    try:
                        if default.startswith('=generate'):
                            default = self.evaluate(default[1:])
                    except AttributeError:
                        pass  # default probably not a string type
                    defaults[key] = default
            kwargs['defaults'] = defaults
        parsed = common.templating.parse(self.map_file.raw, **kwargs)
        return ChefMap(parsed=parsed)

    def get_resource_prepared_maps(self, resource, deployment, map_file=None):
        """Parse maps for a resource and identify paths for finding the map
        data.

        By looking at a requirement's key and finding the relations that
        satisfy that key (using the requires-key attribute) and that have a
        'target' attribute, we can identify the resource we need to get the
        data from and provide the path to that resource as a hint to the
        TransMerge task
        """
        if map_file is None:
            map_file = self.map_file

        maps = map_file.get_component_maps(resource['component'])
        result = []
        for mapping in maps or []:

            # find paths for sources

            if 'source' in mapping:
                url = ChefMap.parse_map_uri(mapping['source'])
                if url['scheme'] == 'requirements':
                    key = url['netloc']
                    relations = [
                        r for r in resource['relations'].values()
                        if (r.get('requires-key') == key and 'target' in r)
                    ]
                    if relations:
                        target = relations[0]['target']
                        #  account for host
                        #  FIXME: This representation needs to be consistent!
                        if relations[0].get('relation', '') != 'host':
                            mapping['path'] = ('instance:%s/interfaces/%s'
                                               % (target,
                                                  relations[0]['interface']))
                        else:
                            mapping['path'] = 'instance:%s' % target
                    result.append(mapping)
                elif url['scheme'] == 'clients':
                    key = url['netloc']
                    for client in deployment['resources'].values():
                        if 'relations' not in client:
                            continue
                        relations = [r for r in client['relations'].values()
                                     if (r.get('requires-key') == key and
                                         r.get('target') == resource['index'])
                                     ]
                        if relations:
                            mapping['path'] = 'instance:%s' % client['index']
                            result.append(copy.copy(mapping))
                else:
                    result.append(mapping)
            else:
                result.append(mapping)

        # Write attribute hints
        key = resource['index']
        for mapping in result:
            mapping['resource'] = key
        return result

    def _hash_all_user_resource_passwords(self, deployment):
        """Chef needs all passwords to be a hash."""
        if 'resources' in deployment:
            for resource in deployment['resources'].values():
                if resource.get('type') == 'user':
                    instance = resource.get('instance', {})
                    if 'password' in instance:
                        instance['hash'] = keys.hash_SHA512(
                            instance['password'])

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
        map_with_context = self.get_map_with_context(deployment=deployment,
                                                     resource=resource,
                                                     component=component)

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
            collect_tasks = self.get_prep_tasks(wfspec, deployment, key,
                                                component, context)
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
            omnibus_version = deployment.get_setting('omnibus-version',
                                                     provider_key=self.key,
                                                     service_name=service_name,
                                                     default=OMNIBUS_DEFAULT)
            # Create chef setup tasks
            register_node_task = specs.Celery(
                wfspec,
                'Register Server %s (%s)' % (
                    relation['target'], resource['service']
                ),
                'checkmate.providers.opscode.solo.tasks.register_node',
                call_args=[context.get_queued_task_dict(
                    deployment_id=deployment['id'],
                    resource_key=key),
                    operators.PathAttrib(
                        'instance:%s/ip' % relation['target']),
                    deployment['id']
                ],
                password=operators.PathAttrib(
                    'instance:%s/password' % relation['target']
                ),
                kitchen_name='kitchen',
                attributes=attributes,
                omnibus_version=omnibus_version,
                identity_file=operators.Attrib('private_key_path'),
                defines=dict(
                    resource=key, relation=relation_key, provider=self.key
                ),
                description=("Install Chef client on the target machine "
                             "and register it in the environment"),
                properties=dict(estimated_duration=120)
            )

            bootstrap_task = specs.Celery(
                wfspec,
                'Pre-Configure Server %s (%s)' % (
                    relation['target'], service_name
                ),
                'checkmate.providers.opscode.solo.tasks.cook',
                call_args=[context.get_queued_task_dict(
                    deployment_id=deployment['id'],
                    resource_key=key),
                    operators.PathAttrib(
                        'instance:%s/ip' % relation['target']),
                    deployment['id']
                ],
                password=operators.PathAttrib(
                    'instance:%s/password' % relation['target']
                ),
                identity_file=operators.Attrib('private_key_path'),
                description="Install basic pre-requisites on %s"
                            % relation['target'],
                defines=dict(
                    resource=key, relation=relation_key, provider=self.key
                ),
                properties=dict(estimated_duration=100, task_tags=['final'])
            )
            bootstrap_task.follow(register_node_task)

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
            return dict(root=root, final=bootstrap_task)

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
                recollect_task = recon_tasks['root']

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
        else:
            name = 'Reconfigure %s: client ready' % server['component']
            host_idx = server.get('hosted_on', server['index'])
            run_list = self._get_component_run_list(server_component)
            instance_ip = operators.PathAttrib("instance:%s/ip" % host_idx)

            reconfigure_task = specs.Celery(
                wfspec,
                name,
                'checkmate.providers.opscode.solo.tasks.cook',
                call_args=[context.get_queued_task_dict(
                    deployment_id=deployment['id'],
                    resource_key=server['index']),
                    instance_ip,
                    deployment['id']
                ],
                password=operators.PathAttrib(
                    'instance:%s/password' % host_idx),
                attributes=operators.PathAttrib(
                    'chef_options/attributes:%s' % server['index']
                ),
                identity_file=operators.Attrib('private_key_path'),
                description="Push and apply Chef recipes on the server",
                defines={
                    'resource': server['index'],
                    'provider': self.key,
                },
                properties={
                    'estimated_duration': 100,
                    'task_tags': ['client-ready'],
                },
                **run_list
            )
            if self.map_file.has_mappings(server['component']):
                collect_tasks = self.get_prep_tasks(
                    wfspec, deployment, server['index'], server_component,
                    context, collect_tag=collect_tag, ready_tag=ready_tag)
                reconfigure_task.follow(collect_tasks['final'])
                result = {'root': collect_tasks['root'],
                          'final': reconfigure_task}
            else:
                result = {'root': reconfigure_task, 'final': reconfigure_task}
        return result

    def get_catalog(self, context, type_filter=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one.
        """

        # TODO(zns): maybe implement this an on_get_catalog so we don't have to
        #        do this for every provider
        results = ProviderBase.get_catalog(self, context,
                                           type_filter=type_filter)
        if results:
            # We have a prexisting or injected catalog stored. Use it.
            return results

        if self.source:
            # Get remote catalog
            catalog = self.get_remote_catalog()

            # Validate and cache catalog
            self.validate_catalog(catalog)
            if type_filter is None:
                self._dict['catalog'] = catalog
            return catalog

    def get_remote_catalog(self, source=None):
        """Gets the remote catalog from a repo by obtaining a Chefmap file, if
        it exists, and parsing it.
        """
        if source:
            map_file = ChefMap(url=source)
        else:
            map_file = self.map_file
        catalog = {}
        try:
            for doc in yaml.safe_load_all(map_file.parsed):
                if 'id' in doc:
                    for key in doc.keys():
                        if key not in schema.COMPONENT_SCHEMA:
                            del doc[key]
                    resource_type = doc.get('is', 'application')
                    if resource_type not in catalog:
                        catalog[resource_type] = {}
                    catalog[resource_type][doc['id']] = doc
            LOG.debug('Obtained remote catalog from %s', map_file.url)
        except ValueError:
            msg = 'Catalog source did not return parsable content'
            raise exceptions.CheckmateException(msg)
        except (ParserError, ScannerError) as exc:
            raise exceptions.CheckmateValidationException(
                "Invalid YAML syntax in Chefmap. Check:\n%s" % exc)
        except ComposerError as exc:
            raise exceptions.CheckmateValidationException(
                "Invalid YAML structure in Chefmap. Check:\n%s" % exc)
        return catalog
