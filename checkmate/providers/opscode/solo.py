'''Chef Solo configuration management provider.'''
import copy
import json
import logging
import os
import urlparse

from jinja2 import BytecodeCache
from jinja2 import DictLoader
from jinja2.sandbox import ImmutableSandboxedEnvironment
from jinja2 import TemplateError
from SpiffWorkflow.operators import Attrib, PathAttrib
from SpiffWorkflow.specs import Celery, SafeTransMerge
import yaml
from yaml.composer import ComposerError
from yaml.parser import ParserError
from yaml.scanner import ScannerError

from checkmate import utils
from checkmate.common import schema
from checkmate.exceptions import (
    CheckmateException,
    CheckmateValidationException,
    CheckmateUserException,
    UNEXPECTED_ERROR,
)
from checkmate.inputs import Input
from checkmate.keys import hash_SHA512
from checkmate.providers import ProviderBase
from checkmate.providers.opscode import knife

LOG = logging.getLogger(__name__)
OMNIBUS_DEFAULT = os.environ.get('CHECKMATE_CHEF_OMNIBUS_DEFAULT',
                                 "10.24.0")
CODE_CACHE = {}


class CompilerCache(BytecodeCache):
    '''Cache for compiled template code.'''

    def load_bytecode(self, bucket):
        if bucket.key in CODE_CACHE:
            bucket.bytecode_from_string(CODE_CACHE[bucket.key])

    def dump_bytecode(self, bucket):
        CODE_CACHE[bucket.key] = bucket.bytecode_to_string()


def register_scheme(scheme):
    '''
    Use this to register a new scheme with urlparse and have it be
    parsed in the same way as http is parsed
    '''
    for method in filter(lambda s: s.startswith('uses_'), dir(urlparse)):
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly


class SoloProviderNotReady(CheckmateException):
    '''Expected data are not yet available.'''
    pass


class Provider(ProviderBase):
    '''Implements a Chef Solo configuration management provider.'''
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
        if self.prep_task:
            return  # already prepped
        self._hash_all_user_resource_passwords(deployment)

        # Create Celery Task
        settings = deployment.settings()
        keys = settings.get('keys', {})
        deployment_keys = keys.get('deployment', {})
        public_key_ssh = deployment_keys.get('public_key_ssh')
        private_key = deployment_keys.get('private_key')
        secret_key = deployment.get_setting('secret_key')
        source_repo = deployment.get_setting('source', provider_key=self.key)
        defines = {'provider': self.key}
        properties = {'estimated_duration': 10, 'task_tags': ['root']}
        task_name = 'checkmate.providers.opscode.knife.create_environment'
        self.prep_task = Celery(wfspec,
                                'Create Chef Environment',
                                task_name,
                                call_args=[deployment['id'], 'kitchen'],
                                public_key_ssh=public_key_ssh,
                                private_key=private_key,
                                secret_key=secret_key,
                                source_repo=source_repo,
                                provider=Provider.name,
                                defines=defines,
                                properties=properties)

        return {'root': self.prep_task, 'final': self.prep_task}

    def cleanup_environment(self, wfspec, deployment):
        call = 'checkmate.providers.opscode.knife.delete_environment'
        defines = {'provider': self.key}
        properties = {'estimated_duration': 1, 'task_tags': ['cleanup']}
        cleanup_task = Celery(wfspec,
                              'Delete Chef Environment',
                              call,
                              call_args=[deployment['id']],
                              defines=defines,
                              properties=properties)

        return {'root': cleanup_task, 'final': cleanup_task}

    def cleanup_temp_files(self, wfspec, deployment):

        '''Cleans up temporary files created during a deployment
        :param wfspec: workflow spec
        :param deployment: deployment being worked on
        :return: root and final tasks for cleaning up the environment
        '''
        client_ready_tasks = wfspec.find_task_specs(provider=self.key,
                                                    tag='client-ready')
        final_tasks = wfspec.find_task_specs(provider=self.key, tag='final')
        client_ready_tasks.extend(final_tasks)
        call = 'checkmate.providers.opscode.knife.delete_cookbooks'
        cleanup_task = Celery(wfspec,
                              'Delete Cookbooks',
                              call,
                              call_args=[deployment['id'], 'kitchen'],
                              defines={'provider': self.key},
                              properties={'estimated_duration': 1})
        root = wfspec.wait_for(cleanup_task, client_ready_tasks,
                               name="Wait before deleting cookbooks",
                               provider=self.key)

        return {'root': root, 'final': cleanup_task}

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        '''Create and write settings, generate run_list, and call cook.'''
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
        anchor_task = configure_task = Celery(
            wfspec,
            'Configure %s: %s (%s)' % (component_id, key, service_name),
            'checkmate.providers.opscode.knife.cook',
            call_args=[
                PathAttrib('instance:%s/ip' % resource.get('hosted_on', key)),
                deployment['id'], resource
            ],
            password=PathAttrib(
                'instance:%s/password' % resource.get('hosted_on', key)
            ),
            attributes=PathAttrib('chef_options/attributes:%s' % key),
            identity_file=Attrib('private_key_path'),
            description="Push and apply Chef recipes on the server",
            defines=dict(resource=key, provider=self.key, task_tags=['final']),
            properties={'estimated_duration': 100},
            **kwargs
        )

        if self.map_file.has_mappings(component_id):
            collect_data_tasks = self.get_prep_tasks(wfspec, deployment, key,
                                                     component)
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
                       collect_tag='collect', ready_tag='options-ready'):
        '''Create (or get if they exist) tasks that collect and write map
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
        '''
        # Do tasks already exist?
        collect_tasks = wfspec.find_task_specs(provider=self.key,
                                               resource=resource_key,
                                               tag=collect_tag)
        if collect_tasks:
            ready_tasks = wfspec.find_task_specs(provider=self.key,
                                                 resource=resource_key,
                                                 tag=ready_tag)
            if not ready_tasks:
                raise CheckmateException("'collect' task exists, but "
                                         "'options-ready' is missing")
            return {'root': collect_tasks[0], 'final': ready_tasks[0]}

        collect_data = None
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
        func = "checkmate.providers.opscode.solo.Transforms.collect_options"
        collect_data = SafeTransMerge(
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
                uri = ChefMap.parse_map_URI(target)
                scheme = uri['scheme']
                if scheme not in ['databags', 'encrypted-databags']:
                    continue
                encrypted = scheme == 'encrypted-databags'
                bag_name = uri['netloc']
                path_parts = uri['path'].strip('/').split('/')
                if len(path_parts) < 1:
                    msg = ("Mapping target '%s' is invalid. It needs "
                           "a databag name and a databag item name")
                    raise CheckmateValidationException(msg)
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
                                          "has multiple items: %s" % (bag_name,
                                          items))
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
            write_databag = Celery(
                wfspec, name,
                'checkmate.providers.opscode.knife.write_databag',
                call_args=[
                    deployment['id'], bag_name, item_name,
                    PathAttrib(path), resource
                ],
                secret_file=secret_file,
                merge=True,
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
                        uri = map_with_context.parse_map_URI(target)
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
            write_role = Celery(
                wfspec, name,
                'checkmate.providers.opscode.knife.manage_role',
                call_args=[role_name, deployment['id'], resource],
                kitchen_name='kitchen',
                override_attributes=PathAttrib(path),
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
        '''Returns a map file that was parsed with real data in the context.'''
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
        parsed = self.map_file.parse(self.map_file.raw, **kwargs)
        return ChefMap(parsed=parsed)

    def get_resource_prepared_maps(self, resource, deployment, map_file=None):
        '''Parse maps for a resource and identify paths for finding the map
        data.

        By looking at a requirement's key and finding the relations that
        satisfy that key (using the requires-key attribute) and that have a
        'target' attribute, we can identify the resource we need to get the
        data from and provide the path to that resource as a hint to the
        TransMerge task
        '''
        if map_file is None:
            map_file = self.map_file

        maps = map_file.get_component_maps(resource['component'])
        result = []
        for mapping in maps or []:

            # find paths for sources

            if 'source' in mapping:
                url = ChefMap.parse_map_URI(mapping['source'])
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
        '''Chef needs all passwords to be a hash.'''
        if 'resources' in deployment:
            for resource in deployment['resources'].values():
                if resource.get('type') == 'user':
                    instance = resource.get('instance', {})
                    if 'password' in instance:
                        instance['hash'] = hash_SHA512(instance['password'])

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        '''Write out or Transform data. Provide final task for relation sources
        to hook into.
        '''
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
                                                component)
            wfspec.wait_for(collect_tasks['root'], tasks)

        if relation.get('relation') == 'host':
            # Wait on host to be ready
            wait_on = self.get_host_ready_tasks(resource, wfspec, deployment)
            if not wait_on:
                raise CheckmateException("No host resource found for relation "
                                         "'%s'" % relation_key)
            attributes = map_with_context.get_attributes(resource['component'],
                                                         deployment)
            service_name = resource['service']
            omnibus_version = deployment.get_setting('omnibus-version',
                                                     provider_key=self.key,
                                                     service_name=service_name,
                                                     default=OMNIBUS_DEFAULT)
            # Create chef setup tasks
            register_node_task = Celery(
                wfspec,
                'Register Server %s (%s)' % (
                    relation['target'], resource['service']
                ),
                'checkmate.providers.opscode.knife.register_node',
                call_args=[
                    PathAttrib('instance:%s/ip' % relation['target']),
                    deployment['id'], resource
                ],
                password=PathAttrib(
                    'instance:%s/password' % relation['target']
                ),
                kitchen_name='kitchen',
                attributes=attributes,
                omnibus_version=omnibus_version,
                identity_file=Attrib('private_key_path'),
                defines=dict(
                    resource=key, relation=relation_key, provider=self.key
                ),
                description=("Install Chef client on the target machine "
                             "and register it in the environment"),
                properties=dict(estimated_duration=120)
            )

            bootstrap_task = Celery(
                wfspec,
                'Pre-Configure Server %s (%s)' % (
                    relation['target'], service_name
                ),
                'checkmate.providers.opscode.knife.cook',
                call_args=[
                    PathAttrib('instance:%s/ip' % relation['target']),
                    deployment['id'], resource
                ],
                password=PathAttrib(
                    'instance:%s/password' % relation['target']
                ),
                identity_file=Attrib('private_key_path'),
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
                                                         server_component)
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
                              server_component):
        '''Gets (creates if does not exist) a task to reconfigure a server when
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
        '''
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
            reconfigure_task = Celery(
                wfspec,
                name,
                'checkmate.providers.opscode.knife.cook',
                call_args=[
                    PathAttrib('instance:%s/public_ip' % host_idx),
                    deployment['id'], client
                ],
                password=PathAttrib('instance:%s/password' % host_idx),
                attributes=PathAttrib(
                    'chef_options/attributes:%s' % server['index']
                ),
                identity_file=Attrib('private_key_path'),
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
                    collect_tag=collect_tag, ready_tag=ready_tag
                )
                reconfigure_task.follow(collect_tasks['final'])
                result = {'root': collect_tasks['root'],
                          'final': reconfigure_task}
            else:
                result = {'root': reconfigure_task, 'final': reconfigure_task}
        return result

    def get_catalog(self, context, type_filter=None):
        '''Return stored/override catalog if it exists, else connect, build,
        and return one.
        '''

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
        '''Gets the remote catalog from a repo by obtaining a Chefmap file, if
        it exists, and parsing it.
        '''
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
            raise CheckmateException(msg)
        except (ParserError, ScannerError) as exc:
            raise CheckmateValidationException("Invalid YAML syntax in "
                                               "Chefmap. Check:\n%s" % exc)
        except ComposerError as exc:
            raise CheckmateValidationException("Invalid YAML structure in "
                                               "Chefmap. Check:\n%s" % exc)
        return catalog


class Transforms(object):
    '''Class to hold transform functions.

    We put them in a separate class to:
    - access them from tests
    - possible, in the future, use them as a library instead of passing the
      actual code in to Spiff for better security
    TODO(zns): Should separate them out into their own module (not class)
    '''
    @staticmethod  # self will actually be a SpiffWorkflow.TaskSpec
    def collect_options(self, my_task):  # pylint: disable=W0211
        '''Collect and write run-time options.'''
        try:
            import copy  # pylint: disable=W0404,W0621
            # pylint: disable=W0621
            from checkmate.providers.opscode.solo import (ChefMap,
                                                          SoloProviderNotReady)
            # pylint: disable=W0621
            from checkmate.deployments import resource_postback as postback
            maps = self.get_property('chef_maps', [])
            data = my_task.attributes

            # Evaluate all maps and exit if any of them are not ready

            queue = []
            for mapping in maps:
                try:
                    result = ChefMap.evaluate_mapping_source(mapping, data)
                    if ChefMap.is_writable_val(result):
                        queue.append((mapping, result))
                except SoloProviderNotReady:
                    return False  # false means not done/not ready

            # All maps are resolved, so combine them with the ones resolved at
            # planning-time

            results = self.get_property('chef_options', {})
            for mapping, result in queue:
                ChefMap.apply_mapping(mapping, result, results)

            # Write to the task attributes and postback the desired output

            output_template = self.get_property('chef_output')
            if output_template:
                output_template = copy.copy(output_template)
            else:
                output_template = {}
            if results:

                # outputs do not go into chef_options
                outputs = results.pop('outputs', {})
                # Use output_template as a template for outputs
                if output_template:
                    outputs = utils.merge_dictionary(
                        copy.copy(output_template), outputs)

                # Write chef_options for databag and role tasks
                if results:
                    if 'chef_options' not in my_task.attributes:
                        my_task.attributes['chef_options'] = {}
                    utils.merge_dictionary(my_task.attributes['chef_options'],
                                           results, True)

                # write outputs (into attributes and output_template)
                if outputs:
                    # Write results into attributes
                    utils.merge_dictionary(my_task.attributes, outputs)
                    # Be compatible and write without 'instance'
                    compat = {}
                    for key, value in outputs.iteritems():
                        if isinstance(value, dict) and 'instance' in value:
                            compat[key] = value['instance']
                    if compat:
                        utils.merge_dictionary(my_task.attributes, compat)

                    # Write outputs into output template
                    utils.merge_dictionary(output_template, outputs)
            else:
                if output_template:
                    utils.merge_dictionary(my_task.attributes, output_template)

            # postback output into deployment resource

            if output_template:
                dep = self.get_property('deployment')
                if dep:
                    LOG.debug("Writing task outputs: %s", output_template)
                    postback.delay(dep, output_template)
                else:
                    LOG.warn("Deployment id not in task properties, "
                             "cannot update deployment from chef-solo")

            return True
        except StandardError as exc:
            import sys
            import traceback
            LOG.error("Error in transform: %s", exc)
            tb = sys.exc_info()[2]
            tb_info = traceback.extract_tb(tb)
            mod, line = tb_info[-1][-2:]
            raise Exception("%s %s in %s executing: %s" % (type(exc).__name__,
                                                           exc, mod, line))


class ChefMap(object):
    '''Retrieves and parses Chefmap files.'''

    def __init__(self, url=None, raw=None, parsed=None):
        '''Create a new Chefmap instance.

        :param url: is the path to the root git repo. Supported protocols
                       are http, https, and git. The .git extension is
                       optional. Appending a branch name as a #fragment works::

                map_file = ChefMap("http://github.com/user/repo")
                map_file = ChefMap("https://github.com/org/repo.git")
                map_file = ChefMap("git://github.com/user/repo#master")
        :param raw: provide the raw content of the map file
        :param parsed: provide parsed content of the map file

        :return: solo.ChefMap

        '''
        self.url = url
        self._raw = raw
        self._parsed = parsed

    @property
    def raw(self):
        '''Returns the raw file contents.'''
        if self._raw is None:
            self._raw = self.get_map_file()
        return self._raw

    @property
    def parsed(self):
        '''Returns the parsed file contents.'''
        if self._parsed is None:
            self._parsed = self.parse(self.raw)
        return self._parsed

    def get_map_file(self):
        '''Return the Chefmap file as a string.'''
        if self.url.startswith("file://"):
            chefmap_dir = self.url[7:]  # strip off "file://"
            chefmap_path = os.path.join(chefmap_dir, "Chefmap")
            with open(chefmap_path) as chefmap:
                return chefmap.read()
        else:
            knife._cache_blueprint(self.url)
            repo_cache = knife._get_blueprints_cache_path(self.url)
            if os.path.exists(os.path.join(repo_cache, "Chefmap")):
                with open(os.path.join(repo_cache, "Chefmap")) as chefmap:
                    return chefmap.read()
            else:
                error_message = "No Chefmap in repository %s" % repo_cache
                raise CheckmateUserException(error_message,
                                             utils.get_class_name(
                                                 CheckmateException),
                                             UNEXPECTED_ERROR, '')

    @property
    def components(self):
        '''The components in the map file.'''
        try:
            result = [
                c for c in yaml.safe_load_all(self.parsed) if 'id' in c
            ]
        except (ParserError, ScannerError) as exc:
            raise CheckmateValidationException("Invalid YAML syntax in "
                                               "Chefmap. Check:\n%s" % exc)
        except ComposerError as exc:
            raise CheckmateValidationException("Invalid YAML structure in "
                                               "Chefmap. Check:\n%s" % exc)
        return result

    def has_mappings(self, component_id):
        '''Does the map file have any mappings for this component.'''
        for component in self.components:
            if component_id == component['id']:
                if component.get('maps') or component.get('output'):
                    return True
        return False

    def has_requirement_mapping(self, component_id, requirement_key):
        '''Does the map file have any 'requirements' mappings for this
        component's requirement_key requirement.
        '''
        for component in self.components:
            if component_id == component['id']:
                for _map in component.get('maps', []):
                    url = self.parse_map_URI(_map.get('source'))
                    if url['scheme'] == 'requirements':
                        if url['netloc'] == requirement_key:
                            return True
        return False

    def has_client_mapping(self, component_id, provides_key):
        '''Does the map file have any 'clients' mappings for this
        component's provides_key connection point.
        '''
        for component in self.components:
            if component_id == component['id']:
                for _map in component.get('maps', []):
                    url = self.parse_map_URI(_map.get('source'))
                    if url['scheme'] == 'clients':
                        if url['netloc'] == provides_key:
                            return True
        return False

    @staticmethod
    def is_writable_val(val):
        '''Determine if we should write the value.'''
        return val is not None and len(str(val)) > 0

    def get_attributes(self, component_id, deployment):
        '''Parse maps and get attributes for a specific component that are
        ready.
        '''
        for component in self.components:
            if component_id == component['id']:
                maps = (m for m in component.get('maps', [])
                        if any(target for target in m.get('targets', [])
                               if (self.parse_map_URI(target)['scheme'] ==
                                   'attributes')))
                if maps:
                    result = {}
                    for _map in maps:
                        value = None
                        try:
                            value = self.evaluate_mapping_source(_map,
                                                                 deployment)
                        except SoloProviderNotReady:
                            LOG.debug("Map not ready yet: %s", _map)
                            continue
                        if ChefMap.is_writable_val(value):
                            for target in _map.get('targets', []):
                                url = self.parse_map_URI(target)
                                if url['scheme'] == 'attributes':
                                    utils.write_path(result, url['path'],
                                                     value)
                    return result

    def get_component_maps(self, component_id):
        '''Get maps for a specific component.'''
        for component in self.components:
            if component_id == component['id']:
                return component.get('maps')

    def get_component_output_template(self, component_id):
        '''Get output template for a specific component.'''
        for component in self.components:
            if component_id == component['id']:
                return component.get('output')

    def get_component_run_list(self, component_id):
        '''Get run_list for a specific component.'''
        for component in self.components:
            if component_id == component['id']:
                return component.get('run_list')

    def has_runtime_options(self, component_id):
        '''Check if a component has maps that can only be resolved at run-time.

        Those would be items like:
        - requirement sources where the required resource does not exist yet

        :returns: boolean
        '''
        for component in self.components:
            if component_id == component['id']:
                maps = (m for m in component.get('maps', [])
                        if (self.parse_map_URI(
                            m.get('source'))['scheme'] in ['requirements']))
                if any(maps):
                    return True
        return False

    @staticmethod
    def filter_maps_by_schemes(maps, target_schemes=None):
        '''Returns the maps that have specific target schemes.'''
        if not maps or not target_schemes:
            return maps
        result = []
        for mapping in maps:
            for target in mapping.get('targets', []):
                url = ChefMap.parse_map_URI(target)
                if url['scheme'] in target_schemes:
                    result.append(mapping)
                    break
        return result

    @staticmethod
    def resolve_map(mapping, data, output):
        '''Resolve mapping and write output.'''
        ChefMap.apply_mapping(
            mapping,
            ChefMap.evaluate_mapping_source(mapping, data),
            output
        )

    @staticmethod
    def apply_mapping(mapping, value, output):
        '''Applies the mapping value to all the targets.

        :param mapping: dict of the mapping
        :param value: the value of the mapping. This is evaluated elsewhere.
        :param output: a dict to apply the mapping to
        '''
        # FIXME: hack to get v0.5 out. Until we implement search() or Craig's
        # ValueFilter. For now, just write arrays for all 'clients' mappings
        if not ChefMap.is_writable_val(value):
            return
        write_array = False
        if 'source' in mapping:
            url = ChefMap.parse_map_URI(mapping['source'])
            if url['scheme'] == 'clients':
                write_array = True

        for target in mapping.get('targets', []):
            url = ChefMap.parse_map_URI(target)
            if url['scheme'] == 'attributes':
                if 'resource' not in mapping:
                    message = 'Resource hint required in ' \
                                        'attribute mapping'
                    raise CheckmateUserException(message,
                                                 utils.get_class_name(
                                                     CheckmateException),
                                                 UNEXPECTED_ERROR, '')

                path = '%s:%s' % (url['scheme'], mapping['resource'])
                if path not in output:
                    output[path] = {}
                if write_array:
                    existing = utils.read_path(output[path],
                                               url['path'].strip('/'))
                    if not existing:
                        existing = []
                    if value not in existing:
                        existing.append(value)
                    value = existing
                utils.write_path(output[path], url['path'].strip('/'), value)
                LOG.debug("Wrote to target '%s': %s", target, value)
            elif url['scheme'] == 'outputs':
                if url['scheme'] not in output:
                    output[url['scheme']] = {}
                if write_array:
                    existing = utils.read_path(output[url['scheme']],
                                               url['path'].strip('/'))
                    if not existing:
                        existing = []
                    if value not in existing:
                        existing.append(value)
                    value = existing
                utils.write_path(
                    output[url['scheme']], url['path'].strip('/'), value
                )
                LOG.debug("Wrote to target '%s': %s", target, value)
            elif url['scheme'] in ['databags', 'encrypted-databags', 'roles']:
                if url['scheme'] not in output:
                    output[url['scheme']] = {}
                path = os.path.join(url['netloc'], url['path'].strip('/'))
                if write_array:
                    existing = utils.read_path(output[url['scheme']], path)
                    if not existing:
                        existing = []
                    if value not in existing:
                        existing.append(value)
                    value = existing
                utils.write_path(output[url['scheme']], path, value)
                LOG.debug("Wrote to target '%s': %s", target, value)
            else:
                raise NotImplementedError("Unsupported url scheme '%s' in url "
                                          "'%s'" % (url['scheme'], target))

    @staticmethod
    def evaluate_mapping_source(mapping, data):
        '''Returns the mapping source value.

        Raises a SoloProviderNotReady exception if the source is not yet
        available

        :param mapping: the mapping to resolved
        :param data: the data to read from
        :returns: the value
        '''
        value = None
        if 'source' in mapping:
            url = ChefMap.parse_map_URI(mapping['source'])
            if url['scheme'] in ['requirements', 'clients']:
                path = mapping.get('path', url['netloc'])
                try:
                    value = utils.read_path(data, os.path.join(path,
                                            url['path']))
                except (KeyError, TypeError) as exc:
                    LOG.debug("'%s' not yet available at '%s': %s",
                              mapping['source'], path, exc,
                              extra={'data': data})
                    raise SoloProviderNotReady("Not ready")
                LOG.debug("Resolved mapping '%s' to '%s'", mapping['source'],
                          value)
            else:
                raise NotImplementedError("Unsupported url scheme '%s' in url "
                                          "'%s'" % (url['scheme'],
                                          mapping['source']))
        elif 'value' in mapping:
            value = mapping['value']
        else:
            message = "Mapping has neither 'source' nor 'value'"
            raise CheckmateUserException(message, utils.get_class_name(
                CheckmateException), UNEXPECTED_ERROR, '')
        return value

    @staticmethod
    def resolve_ready_maps(maps, data, output):
        '''Parse and apply maps that are ready.

        :param maps: a list of maps to attempt to resolve
        :param data: the source of the data (a deployment)
        :param output: a dict to write the output to
        :returns: unresolved maps
        '''
        unresolved = []
        for mapping in maps:
            value = None
            try:
                value = ChefMap.evaluate_mapping_source(mapping, data)
            except SoloProviderNotReady:
                unresolved.append(mapping)
                continue
            if value is not None:
                ChefMap.apply_mapping(mapping, value, output)
            else:
                unresolved.append(mapping)
        return unresolved

    @staticmethod
    def parse_map_URI(uri):
        '''Parses the URI format of a map.

        :param uri: string uri based on map file supported sources and targets
        :returns: dict
        '''
        try:
            parts = urlparse.urlparse(uri)
        except AttributeError:
            # probably a scalar
            parts = urlparse.urlparse('')

        result = {
            'scheme': parts.scheme,
            'netloc': parts.netloc,
            'path': parts.path.strip('/'),
            'query': parts.query,
            'fragment': parts.fragment,
        }
        if parts.scheme in ['attributes', 'outputs']:
            result['path'] = os.path.join(parts.netloc.strip('/'),
                                          parts.path.strip('/')).strip('/')
        return result

    @staticmethod
    def parse(template, **kwargs):
        '''Parse template.

        :param template: the template contents as a string
        :param kwargs: extra arguments are passed to the renderer
        '''
        template_map = {'template': template}
        env = ImmutableSandboxedEnvironment(loader=DictLoader(template_map),
                                            bytecode_cache=CompilerCache())

        def do_prepend(value, param='/'):
            '''Prepend a string if the passed in string exists.

            Example:
            The template '{{ root|prepend('/')}}/path';
            Called with root undefined renders:
                /path
            Called with root defined as 'root' renders:
                /root/path
            '''
            if value:
                return '%s%s' % (param, value)
            else:
                return ''
        env.filters['prepend'] = do_prepend

        env.json = json

        def evaluate(value):
            '''Handle defaults with functions.'''
            if isinstance(value, basestring):
                if value.startswith('=generate'):
                    # TODO(zns): Optimize. Maybe have Deployment class handle
                    # it
                    value = ProviderBase({}).evaluate(value[1:])
            return value

        def parse_url(value):
            '''Parse a url into its components.

            :returns: Input parsed as url to support full option parsing

            returns a blank URL if none provided to make this a safe function
            to call from within a Jinja template which will generally not cause
            exceptions and will always return a url object
            '''
            result = Input(value or '')
            result.parse_url()
            for attribute in ['certificate', 'private_key',
                              'intermediate_key']:
                if getattr(result, attribute) is None:
                    setattr(result, attribute, '')
            return result
        env.globals['parse_url'] = parse_url
        deployment = kwargs.get('deployment')
        resource = kwargs.get('resource')
        defaults = kwargs.get('defaults', {})
        if deployment:
            if resource:
                fxn = lambda setting_name: evaluate(
                    utils.escape_yaml_simple_string(
                        deployment.get_setting(
                            setting_name,
                            resource_type=resource['type'],
                            provider_key=resource['provider'],
                            service_name=resource['service'],
                            default=defaults.get(setting_name, '')
                        )
                    )
                )
            else:
                fxn = lambda setting_name: evaluate(
                    utils.escape_yaml_simple_string(
                        deployment.get_setting(
                            setting_name, default=defaults.get(setting_name,
                                                               '')
                        )
                    )
                )
        else:
            # noop
            fxn = lambda setting_name: evaluate(
                utils.escape_yaml_simple_string(
                    defaults.get(setting_name, '')))
        env.globals['setting'] = fxn
        env.globals['hash'] = hash_SHA512

        template = env.get_template('template')
        minimum_kwargs = {
            'deployment': {'id': ''},
            'resource': {},
            'component': {},
            'clients': [],
        }
        minimum_kwargs.update(kwargs)

        try:
            result = template.render(**minimum_kwargs)
            #TODO(zns): exceptions in Jinja template sometimes missing
            #traceback
        except StandardError as exc:
            LOG.error(exc, exc_info=True)
            error_message = "Chef template rendering failed: %s" % exc
            raise CheckmateUserException(error_message,utils.get_class_name(
                CheckmateException), UNEXPECTED_ERROR, '' )
        except TemplateError as exc:
            LOG.error(exc, exc_info=True)
            error_message = "Chef template had an error: %s" % exc
            raise CheckmateUserException(error_message, utils.get_class_name(
                CheckmateException), UNEXPECTED_ERROR, '')
        return result
