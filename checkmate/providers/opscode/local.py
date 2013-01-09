"""Chef Local/Solo configuration management provider

How do settings flow through:
- values that are only available at run time (ex. ip of a server) can be picked
  up directly using the Attrib() object (Attrib('ip') gets resolved into the
  'ip' key's value before the call)
- settings available at compile time get set in the context object. The context
  object is made available during the run and any task can pick up a value from
  it using the Attrib() object (Attrib('ip') gets resolved into the 'ip' key's
  before the call)
- setting that are generated?

Component IDs:
- they come from cookbooks
- roles get a '-role' appended to them
- recipes get added with ::

"""
import logging
import os
import json

from SpiffWorkflow.operators import Attrib, PathAttrib
from SpiffWorkflow.specs import Celery, Transform, Merge
from SpiffWorkflow.specs.Simple import Simple
from checkmate.common import schema
from checkmate.components import Component
from checkmate.exceptions import CheckmateException, CheckmateIndexError
from checkmate.keys import hash_SHA512
from checkmate.providers import ProviderBase
from checkmate.utils import get_source_body, merge_dictionary
from checkmate.workflows import wait_for
from checkmate.providers.opscode.databag import _get_repo_path
from celery.task import task  # @UnresolvedImport

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    """Implements a Chef Local/Solo configuration management provider"""
    name = 'chef-local'
    vendor = 'opscode'

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
        self.prep_task = {}
        self.collect_data_tasks = {}

    def _get_deployment_local_services(self, deployment, context):
        servicenames = set()
        for resource in deployment.get('resources', {}).values():
            if resource.get('provider') == self.name:
                servicenames.add(resource.get('service'))
        return list(servicenames)

    def prep_environment(self, wfspec, deployment, context):
        if self.prep_task:
            return  # already prepped
        self._hash_all_user_resource_passwords(deployment)

        simple = Simple(wfspec, 'Create Chef Environments')
        for service_name in self._get_deployment_local_services(deployment,
                                                                context):
            create_environment_task = Celery(wfspec,
                    'Create Chef Environment for %s' % service_name,
                    'checkmate.providers.opscode.databag.create_environment',
                    call_args=[deployment['id'], service_name],
                    public_key_ssh=deployment.settings().get('keys', {}).get(
                            'deployment', {}).get('public_key_ssh'),
                    private_key=deployment.settings().get('keys', {}).get(
                            'deployment', {}).get('private_key'),
                    secret_key=deployment.get_setting('secret_key'),
                    source_repo=deployment.get_setting('source',
                                                  provider_key=self.key,
                                                  service_name=service_name),
                    defines=dict(provider=self.key,
                                task_tags=['root']),
                    properties={'estimated_duration': 10})
            create_environment_task.follow(simple)

            # Create a global task to write options. This will be fed into and
            # connected to by other tasks as needed. The 'write_options' tag
            # identifies it.
            # relations will determine if resources write to or read from this
            # task's attributes
            # apps will read/write to this structure:
            # {'chef_options': {
            #       'app_name': {'option1': value, 'option2': value},
            #       'other_app_name': {'option1': value, 'option2': value}
            #   }}
            if str(os.environ.get('CHECKMATE_CHEF_USE_DATA_BAGS', True)
                        ).lower() in ['true', '1', 'yes']:
                # Call write_databag(environment, bagname, itemname, contents)
                write_options = Celery(wfspec,
                        "Write Data Bag for %s" % service_name,
                       'checkmate.providers.opscode.databag.write_databag',
                        call_args=[deployment['id'], deployment['id'],
                                Attrib('app_id'), Attrib('chef_options')],
                        kitchen_name=service_name,
                        secret_file='certificates/chef.pem',
                        merge=True,
                        defines=dict(provider=self.key),
                        properties={'estimated_duration': 5})
            else:
                write_options = Celery(wfspec,
                        "Write Overrides for %s" % service_name,
                        'checkmate.providers.opscode.databag.manage_role',
                        call_args=[deployment['id'], deployment['id']],
                        kitchen_name=service_name,
                        override_attributes=Attrib('chef_options'),
                        description="Take the JSON prepared earlier and write "
                            "it into the application role. It will be used "
                            "by the Chef recipe to access global data",
                        defines=dict(provider=self.key),
                        properties={'estimated_duration': 5})

            collect = Merge(wfspec,
                    "Collect Chef Data for %s" % service_name,
                    defines=dict(provider=self.key, extend_lists=True),
                    )
            # Make sure the environment exists before writing options.
            collect.follow(create_environment_task)
            write_options.follow(collect)
            # Any tasks that need to be collected will wire themselves into
            # this task
            self.collect_data_tasks[service_name] = dict(root=collect,
                                                         final=write_options)
            self.prep_task[service_name] = create_environment_task

        return dict(root=simple,
                    final=simple)

    def _hash_all_user_resource_passwords(self, deployment):
        """Wordpress and/or Chef need passwords to be a hash"""
        if 'resources' in deployment:
            for resource in deployment['resources'].values():
                if resource.get('type') == 'user':
                    instance = resource.get('instance', {})
                    if 'password' in instance:
                        instance['hash'] = hash_SHA512(instance['password'])

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        """Create and write data_bag, generate run_list, and call cook

        Steps:
        1 - wait on all host tasks
        2 - add tasks for each component/dependency
        3 - wait on those tasks
        1 - configure the resource
        """
        wait_on, service_name, component = self._add_resource_tasks_helper(
                resource, key, wfspec, deployment, context, wait_on)

        # 2 - Make a call for each component (some have custom code)
        def recursive_load_dependencies(stack, current, provider, context):
            """Get and add dependencies to components list recursively"""
            # Skip ones we have already processed
            if current not in stack:
                if type(current) is dict:  # not Component
                    found = self.find_components(context, **current)
                    if found and len(found) == 1:
                        current = found[0]
                    elif not found:
                        raise CheckmateException("Component '%s' not found" %
                                                 current.get('id'))
                    else:
                        raise CheckmateException("Component '%s' matches %s "
                                                 "components" % current)
                stack.append(current)
                for dependency in current.get('dependencies', []):
                    if isinstance(dependency, basestring):
                        dependency = provider.get_component(context,
                                                            dependency)
                        if dependency:
                            dependency = [dependency]
                    if isinstance(dependency, dict):
                        dependency = provider.find_components(context,
                                **dependency) or []
                    for item in dependency:
                        if item in stack:
                            LOG.debug("Component '%s' encountered more than "
                                      "once" % item['id'])
                            continue
                        recursive_load_dependencies(stack, item, provider,
                                                    context)

        LOG.debug("Analyzing dependencies for '%s'" % component['id'])
        components = []  # this component comes first
        recursive_load_dependencies(components, component, self, context)
        LOG.debug("Recursion for dependencies for '%s' found: %s" % (
                  component['id'],
                  ', '.join([c['id'] for c in components[1:]])))

        # just parse options
        default_task_handler = self._process_options

        assert component in components
        for item in components:
            if item is component or item == component:
                # Set app ID
                # TODO: find a more better way to do this
                prefix = deployment.get_setting('prefix')
                app_id = "webapp_%s_%s" % (component['id'].split('-')[0],
                                           prefix)
                deployment.settings()['app_id'] = app_id
                # This is our main recipe which we should cook with
                self._add_component_tasks(wfspec, item, deployment, key,
                                          context, service_name)
                continue
            if isinstance(item, basestring):
                item = self.get_component(context, item)
            else:
                LOG.debug("Calling default task handler for %s" % item['id'])
                default_task_handler(wfspec, item, deployment, key, context,
                                     service_name)

        return {}  # TODO: do we need dict(root=root, final=final)?

    def _process_options(self, wfspec, component, deployment, key, context,
                service_name, write_separately=False):
        """Parse options and place them in the workflow. If any options need to
        be picked up at run time, then generate tasks for that.

        By default, this will use the global collect_data_tasks tasks created
        in prepare_environment to write option values out to chef. But if this
        component needs to write its own options, then the write_separately
        parameter creates a separate write task for this component.

        :param write_separately: create tasks to write out options separately
        instead of using the global collect_data_tasks tasks.
        :returns: task that completes the option writing (ready to cook)

        """
        assert component, "Empty component passed to _add_component_tasks"
        resource = deployment['resources'][key]

        # Get list of options
        option_maps = []  # keep option names, source field name, and default
        for name, option in component.get('options', {}).iteritems():
            if 'source' in option and option['source'] != component['id']:
                # comes form somewhere else. Let the 'somewhere else' handle it
                continue
            option_maps.append((name, option.get('source_field_name', name),
                    option.get('default')))
            LOG.debug("Processing option %s from component %s" %
                      (option_maps[-1], component.get("id", "UNKNOWN")))

        # Set the options if they are available now (at planning time) and mark
        # ones we need to get at run-time
        planning_time_options = {}
        run_time_options = []  # (name, source_field_name) tuples
        for name, mapped_name, default in option_maps:
            value = deployment.get_setting(name, provider_key=self.key,
                    resource_type=resource['type'], service_name=service_name)
            if not value and default and isinstance(default, basestring):
                if default.startswith('=generate'):
                    value = self.evaluate(default[1:])
                else:
                    # Let chef handle it
                    continue
            if value:
                planning_time_options[mapped_name] = value
            else:
                run_time_options.append((name, mapped_name))

        if not (planning_time_options or run_time_options):
            LOG.debug("Component '%s' does not have options to set" %
                    component['id'])
            return  # nothing to do for this component

        planning_time_options = {component['id']: planning_time_options}

        # Create the task that collects the data to write. The task will take
        # the planning time options from the task properties and merge in any
        # run-time options

        # Collect runtime and planning-time options
        def build_data_code(my_task):  # Holds code for the task
            LOG.debug("Attributes: %s" % my_task.attributes)
            data = my_task.task_spec.properties['planning_time_options']
            if not data:
                data = {}
            component_id = my_task.task_spec.get_property('component_id')
            if component_id not in data:
                data[component_id] = {}
            values = data[component_id]

            run_time_options = my_task.task_spec.get_property(
                    'run_time_options')
            if run_time_options:
                for name, mapped_name in run_time_options:
                    value = my_task.attributes.get(name)
                    if value:
                        values[mapped_name] = value
                    else:
                        LOG.debug("Option '%s' not found in attributes" %
                                name)

            # Explode paths into dicts
            if isinstance(values, dict):
                results = {}
                for key, value in values.iteritems():
                    if '/' in key:
                        next_one = results
                        for part in key.split('/'):
                            current = next_one
                            if part not in current:
                                current[part] = {}
                            next_one = current[part]
                        current[part] = value
                    else:
                        results[key] = value
                # Flatten duplicate component_id
                if component_id in results:
                    results.update(results.pop(component_id))
                if results:
                    data[component_id] = results

            # And write chef options under this component's key
            if 'chef_options' not in my_task.attributes:
                my_task.attributes['chef_options'] = {}
            if data and data.get(component_id):
                my_task.attributes['chef_options'].update(data)

        LOG.debug("Creating task to collect run-time options %s for %s [%s]" %
            (', '.join([m for n, m in run_time_options]),  # @UnusedVariable
            service_name, component['id']))
        LOG.debug("Options collected at planning time for %s [%s] were: %s" % (
                service_name, component['id'], planning_time_options))
        collect_data = Transform(wfspec, "Collect %s Chef Data for %s: %s" % (
                component['id'], service_name, key),
                transforms=[get_source_body(build_data_code)],
                description="Get %s data needed for our cookbooks and "
                        "place it in a structure ready for storage in a "
                        "databag or role" % component['id'],
                defines=dict(provider=self.key,
                        resource=key,
                        run_time_options=run_time_options,
                        component_id=component['id'],
                        planning_time_options=planning_time_options))

        # Set the write_option task (find the global one or create our own)
        if run_time_options:
            contents_param = Attrib('chef_options')  # eval at run-time
        else:
            contents_param = planning_time_options  # no run-time eval needed
            collect_data.follow(self.prep_task[service_name])  # no wait needed
        if write_separately:
            if str(os.environ.get('CHECKMATE_CHEF_USE_DATA_BAGS', True)
                        ).lower() in ['true', '1', 'yes']:
                # Call write_databag(environment, bagname, itemname, contents)
                write_options = Celery(wfspec,
                        "Write Data Bag for %s/%s" % (component['id'], key),
                       'checkmate.providers.opscode.databag.write_databag',
                        call_args=[deployment['id'], deployment['id'],
                                Attrib('app_id'), contents_param],
                        secret_file='certificates/chef.pem',
                        kitchen_name=service_name,
                        merge=True,
                        defines=dict(provider=self.key, resource=key),
                        properties={'estimated_duration': 5},
                        )
            else:
                write_options = Celery(wfspec,
                        "Write Overrides for %s/%s for %s" %
                        (component['id'], key, service_name),
                        'checkmate.providers.opscode.databag.manage_role',
                        call_args=[deployment['id'], deployment['id']],
                        kitchen_name=service_name,
                        override_attributes=contents_param,
                        merge=True,
                        description="Take the JSON prepared earlier and write "
                                "it into the application role. It will be "
                                "used by the Chef recipe to access global "
                                "data",
                        defines=dict(provider=self.key, resource=key),
                        properties={'estimated_duration': 5},
                        )
        else:
            write_options = self.collect_data_tasks[service_name]['root']

        # Write must wait on collect
        wait_for(wfspec, write_options, [collect_data],
                name="Feed data to Write task for %s (%s)" %
                    (key, service_name))

        tasks = self.get_relation_final_tasks(wfspec, resource)
        LOG.debug("Attaching %s to %s (%s)" % (write_options.name, ', '.join(
                        [t.name for t in tasks]), service_name))
        if not tasks:
            tasks = [self.prep_task[service_name]]
        wait_for(wfspec, collect_data, tasks,
                name="Get %s data: %s (%s)" %
                (component['id'], key, service_name),
                description="Before applying chef recipes, we need to "
                "know that the server has chef on it and that the "
                "overrides (database settings) have been applied")

        return write_options

    def _add_component_tasks(self, wfspec, component, deployment, key,
            context, service_name):
        # Make sure we've processed and written options
        options_ready = self._process_options(wfspec, component,
                deployment, key, context, service_name)

        # Get component/role or recipe name
        kwargs = {}
        LOG.debug("Determining component from dict: %s" % component.get('id'),
                extra=component)
        if 'role' in component:
            name = '%s::%s' % (component['id'], component['role'])
        else:
            name = component['id']
            if name == 'mysql':
                name += "::server"  # install server by default, not client

        if component['id'].endswith('-role'):
            kwargs['roles'] = [name[0:-5]]  # trim the '-role'
        else:
            kwargs['recipes'] = [name]
        LOG.debug("Component determined to be %s" % kwargs)

        # Create the cook task
        resource = deployment['resources'][key]
        configure_task = Celery(wfspec,
                'Configure %s: %s (%s)' % (component['id'],
                key, service_name),
               'checkmate.providers.opscode.databag.cook',
                call_args=[
                        PathAttrib('instance:%s/ip' %
                                resource.get('hosted_on', key)),
                        deployment['id']],
                password=PathAttrib('instance:%s/password' %
                        resource.get('hosted_on', key)),
                kitchen_name=service_name,
                identity_file=Attrib('private_key_path'),
                description="Push and apply Chef recipes on the server",
                defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['final']),
                properties={'estimated_duration': 100},
                **kwargs)

        # Collect dependencies
        dependencies = [self.prep_task[service_name],
                        self.collect_data_tasks[service_name]['final']]
        if options_ready:
            dependencies.append(options_ready)

        # Wait for relations tasks to complete
        for relation_key in resource.get('relations', {}).keys():
            tasks = self.find_tasks(wfspec,
                    resource=key,
                    relation=relation_key,
                    tag='final')
            if tasks:
                dependencies.extend(tasks)

        # Wait for all data from all data to be collected to account for
        # inter-resource dependencies
        dependencies.extend(self.find_tasks(wfspec, tag='write_options'))
        server_id = deployment['resources'][key].get('hosted_on', key)
        wait_for(wfspec, configure_task, dependencies,
                name="After server %s (%s) is registered and options are ready"
                        % (server_id, service_name),
                description="Before applying chef recipes, we need to know "
                "that the server has chef on it and that the overrides "
                "(ex. database settings) have been applied")

        # if we have a host task marked 'complete', make that wait on configure
        host_complete = self.get_host_complete_task(wfspec, resource)
        if host_complete:
            wait_for(wfspec, host_complete, [configure_task],
                     name='Wait for %s to be configured before completing '
                     'host %s' %
                     (service_name, resource.get('hosted_on', key)))

    def add_connection_tasks(self, resource, key, relation, relation_key,
            wfspec, deployment, context):
        """Write out or Transform data. Provide final task for relation sources
        to hook into"""
        LOG.debug("Adding connection task  resource: %s, key: %s, relation: %s"
                  " relation_key: %s"
                  % (resource, key, relation, relation_key))

        if relation_key != 'host':
            target = deployment['resources'][relation['target']]
            relation_name = relation['name']
            interface = relation['interface']
            # Get the definition of the interface
            interface_schema = schema.INTERFACE_SCHEMA\
                                .get(interface, {})  # @UndefinedVariable
            # Get the fields this interface defines
            fields = interface_schema.get('fields', {}).keys()
            if 'attribute' in relation:
                if relation['attribute'] not in fields:
                    raise CheckmateException(
                             'Relation attribute %s is not in interface %s'
                             % (relation['attribute'], interface))
                fields = [relation['attribute']]
            if not fields:
                LOG.debug("No fields defined for interface '%s', so nothing "
                    "to do for connection '%s'" % (interface, relation_key))
                return  # nothing to do
            comp = self.get_component(context,
                                      resource.get('component', '!_!NONE!_!'))

            # see if we need to write lists for merging later
            aggregate = False
            if comp:
                comp_opts = comp.get("options", {})
                setting = comp_opts.get(relation_name)
                if setting:
                    if 'type' in setting and ('array' == setting.get('type')):
                        aggregate = True
                # check to see if we're just grabbing the entire interface
                else:
                    short_keys = [a_name[:len(relation_name)] for a_name
                                  in comp_opts.keys()]
                    LOG.info("Looking for interface relationship"
                             " {} in short keys {}"
                             .format(relation_name, short_keys))
                    if relation_name not in short_keys:
                        LOG.warn("Component {} does not have a setting {}"
                                 .format(comp.get('id', 'UNKNOWN'),
                                         relation_name))
            else:
                LOG.warn("Could not find component {}"
                         .format(resource.get('component', '!_!NONE!_!')))
            # Build full path to 'instance:id/interfaces/:interface/:fieldname'
            fields_with_path = []

            for field in fields:
                if interface != 'host':
                    fields_with_path.append('instance:%s/interfaces/%s/%s' % (
                        relation['target'], interface, field))
                else:
                    fields_with_path.append('instance:%s/%s' % (
                        relation['target'], field))

            # Get the final task for the target
            target_final = self.find_tasks(wfspec, provider=target['provider'],
                    resource=relation['target'], tag='final')
            if not target_final:
                raise CheckmateException("'Final' task not found for relation "
                                         "'%s' connecting %s to %s" %
                                         (relation_key, key,
                                          relation['target']))
            if len(target_final) > 1:
                raise CheckmateException("Multiple relation final tasks "
                        "found: %s" % [t.name for t in target_final])
            target_final = target_final[0]
            # Write the task to get the values

            def get_attribute_code(my_task):
                if 'chef_options' not in my_task.attributes:
                    my_task.attributes['chef_options'] = {}
                key = my_task.get_property('relation')
                name = my_task.get_property('relation_name', key)
                fields = my_task.get_property('fields', [])
                aggregate = my_task.get_property('aggregate_field', False)
                part = None
                if fields:
                    field = fields[0]
                    parts = field.split("/")
                    val = my_task.attributes
                    for part in parts:
                        if part not in val:
                            LOG.warn("Could not locate {} in task attributes"
                                     .format(field))
                            val = None
                            break
                        val = val[part]
                if val:
                    if aggregate:
                        val = [val]
                    cur = my_task.attributes['chef_options']
                    if "/" in name:
                        last = cur
                        keys = name.split("/")
                        for k in keys:
                            last = cur
                            if not cur.get(k):
                                cur[k] = {}
                            cur = cur[k]
                        if cur and aggregate:
                            if hasattr(cur, "extend"):
                                val.extend(cur)
                            else:
                                val.append(cur)
                        LOG.info("Setting {} to {}".format(name, val))
                        last[k] = val
                    else:
                        if cur.get(name) and aggregate:
                            if hasattr(cur[name], "extend"):
                                val.extend(cur[name])
                            else:
                                val.append(cur[name])
                        LOG.info("Setting {} to {}".format(name, val))
                        cur[name] = val
                else:
                    LOG.warn("Could not determine a value to set for {}"
                             .format(key))

            def get_fields_code(my_task):  # Holds code for the task
                if 'chef_options' not in my_task.attributes:
                    my_task.attributes['chef_options'] = {}
                key = my_task.get_property('relation')
                name = my_task.get_property('relation_name', key)
                fields = my_task.get_property('fields', [])
                aggregate = my_task.get_property('aggregate_field', [])
                data = {}
                for field in fields:
                    parts = field.split('/')
                    current = my_task.attributes
                    for part in parts:
                        if part not in current:
                            LOG.warn("Could not locate {} in task attributes"
                                     .format(field))
                            current = None
                            break
                        current = current[part]
                    if current:
                        data[part] = current
                if data:
                    if aggregate:
                        data = [data]
                    cur = my_task.attributes['chef_options']
                    if "/" in name:
                        keys = name.split("/")
                        for k in keys:
                            if not cur.get(k):
                                cur[k] = {}
                            cur = cur[k]
                        if cur and aggregate:
                            if hasattr(cur, "extend"):
                                data.extend(cur)
                            else:
                                data.append(cur)
                            LOG.info("Setting {} to {}".format(name, data))
                        else:
                            LOG.info("Setting {} to {}".format(name, data))
                            cur.update(data)
                    else:
                        if cur.get(name) and aggregate:
                            if hasattr(cur[k], "extend"):
                                data.extend(cur[k])
                            else:
                                data.append(cur[k])
                        LOG.info("Setting {} to {}".format(name, data))
                        cur[name] = data
                else:
                    LOG.warn("Could not find values to set for {}".format(key))

            compile_override = Transform(wfspec, "Get %s values for %s (%s)" %
                    (relation_key, key, resource['service']),
                    transforms=[get_source_body(
                        get_attribute_code if 'attribute' in relation
                        else get_fields_code)],
                    description="Get all the variables "
                            "we need (like database name and password) and "
                            "compile them into JSON that we can set on the "
                            "role or environment",
                    defines=dict(relation=relation_key,
                                provider=self.key,
                                resource=key,
                                fields=fields_with_path,
                                relation_name=relation_name,
                                aggregate_field=aggregate,
                                task_tags=['final'])
                    )
            # When target is ready, compile data
            wait_for(wfspec, compile_override, [target_final])
            # Feed data into collection task
            tasks = [self.collect_data_tasks[resource['service']]['root']]
            #tasks = self.find_tasks(wfspec, provider=resource['provider'],
            #        resource=key, tag='final')
            if tasks:
                for task in tasks:
                    wait_for(wfspec, task, [compile_override])

        if relation_key == 'host':
            # Wait on host to be ready
            wait_on = self.get_host_ready_tasks(resource, wfspec,
                    deployment)
            if not wait_on:
                raise CheckmateException("No host resource found for relation "
                                         "'%s'" % relation_key)

            # Create chef setup tasks
            register_node_task = Celery(wfspec,
                    'Register Server %s (%s)' % (relation['target'],
                                                 resource['service']),
                    'checkmate.providers.opscode.databag.register_node',
                    call_args=[
                            PathAttrib('instance:%s/ip' % relation['target']),
                            deployment['id']],
                    password=PathAttrib('instance:%s/password' %
                            relation['target']),
                    kitchen_name=resource['service'],
                    omnibus_version="10.12.0-1",
                    identity_file=Attrib('private_key_path'),
                    attributes={'deployment': {'id': deployment['id']}},
                    defines=dict(resource=key,
                                relation=relation_key,
                                provider=self.key),
                    description="Install Chef client on the target machine "
                            "and register it in the environment",
                    properties=dict(estimated_duration=120))

            bootstrap_task = Celery(wfspec,
                    'Pre-Configure Server %s (%s)' % (relation['target'],
                                                      resource['service']),
                    'checkmate.providers.opscode.databag.cook',
                    call_args=[
                            PathAttrib('instance:%s/ip' % relation['target']),
                            deployment['id']],
                    password=PathAttrib('instance:%s/password' %
                            relation['target']),
                    kitchen_name=resource['service'],
                    identity_file=Attrib('private_key_path'),
                    description="Install basic pre-requisites on %s"
                                % relation['target'],
                    defines=dict(resource=key,
                                 relation=relation_key,
                                 provider=self.key),
                    properties=dict(estimated_duration=100,
                                    task_tags=['final']))
            bootstrap_task.follow(register_node_task)

            # Register only when server is up and environment is ready
            wait_on.append(self.prep_task[resource['service']])
            root = wait_for(wfspec, register_node_task, wait_on,
                    name="After Environment is Ready and Server %s (%s) is Up"
                            % (relation['target'], resource['service']),
                    resource=key, relation=relation_key, provider=self.key)
            if 'task_tags' in root.properties:
                root.properties['task_tags'].append('root')
            else:
                root.properties['task_tags'] = ['root']
            return dict(root=root, final=bootstrap_task)

    def get_catalog(self, context, type_filter=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one"""

        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #        this for every provider
        results = ProviderBase.get_catalog(self, context,
            type_filter=type_filter)
        if results:
            # We have a prexisting or injected catalog stored. Use it.
            return results

        # build a live catalog - this would be the on_get_catalog called if no
        # stored/override existed
        # Get cookbooks
        cookbooks = self._get_cookbooks(context, site_cookbooks=False)
        site_cookbooks = self._get_cookbooks(context, site_cookbooks=True)
        roles = self._get_roles(context)

        cookbooks.update(roles)
        cookbooks.update(site_cookbooks)

        results = {}
        for key, cookbook in cookbooks.iteritems():
            provides = cookbook.get('provides', ['application'])
            for entry in provides:
                if isinstance(entry, dict):
                    entry = entry.keys()[0]
                    if type_filter is None or type_filter == entry:
                        if entry not in results:
                            results[entry] = {}
                        results[entry][key] = cookbook
        return results

    def get_component(self, context, id):
        # Get cookbook
        assert id, 'Blank component ID requested from get_component'

        # Parse recipe out of name (we call that 'role' in checkmate. Not to be
        # confused with a role in Chef, which is identified by a '-role' at the
        # end of the name)
        role = None
        if '::' in id:
            id, role = id.split('::')[0:2]

        #Try superclass call first if we have an injected or stored catalog
        if self._dict and 'catalog' in self._dict:
            result = ProviderBase.get_component(self, context, id)
            if result:
                if role:
                    result['role'] = role
                return Component(**result)

        try:
            cookbook = self._get_cookbook(context, id, site_cookbook=True)
            if cookbook:
                if role:
                    cookbook['role'] = role
                return Component(**cookbook)
        except CheckmateIndexError:
            pass
        try:
            cookbook = self._get_cookbook(context, id, site_cookbook=False)
            if cookbook:
                if role:
                    cookbook['role'] = role
                return Component(**cookbook)
        except CheckmateIndexError:
            pass

        chef_role = self._get_role(id, context)
        if chef_role:
            if role:
                chef_role['role'] = role
            return Component(**chef_role)

        LOG.debug("Component '%s' not found" % id)

    def _get_cookbooks(self, context, site_cookbooks=False):
        """Get all cookbooks as Checkmate components"""
        results = {}
        # Get cookbook names (with source if translated)
        cookbooks = self._get_cookbook_names(site_cookbooks=site_cookbooks)
        # Load individual cookbooks
        for name in cookbooks.keys():
            data = self._get_cookbook(context,
                                      cookbooks.get('source_name', name),
                                      site_cookbook=site_cookbooks)
            if data:
                results[data['id']] = data
        return results

    def _get_cookbook_names(self, site_cookbooks=False):
        """Get all cookbooks names (as dict with source_name if canonicalized)
        """
        results = {}
        repo_path = _get_repo_path()
        if site_cookbooks:
            path = os.path.join(repo_path, 'site-cookbooks')
        else:
            path = os.path.join(repo_path, 'cookbooks')

        names = []
        for top, dirs, files in os.walk(path):  # @UnusedVariable
            names = [name for name in dirs if name[0] != '.']
            break

        for name in names:
            # hack for now, this prevents un-altered cookbooks from being used
            canonical_name = schema.translate(name)
            results[canonical_name] = dict(id=canonical_name)
            if canonical_name != name:
                results[canonical_name]['source_name'] = name
        return results

    def _get_cookbook(self, context, id, site_cookbook=False):
        """Get a cookbook as a Checkmate component"""
        assert id, 'Blank cookbook ID requested from _get_cookbook'
        # Get cookbook names (with source if translated)
        cookbooks = self._get_cookbook_names(site_cookbooks=site_cookbook)
        if id not in cookbooks:
            raise CheckmateIndexError("Cookbook '%s' not found" % id)
        cookbook = cookbooks[id]
        repo_path = _get_repo_path()
        if site_cookbook:
            meta_path = os.path.join(repo_path, 'site-cookbooks',
                    cookbook.get('source_name', id), 'metadata.json')
        else:
            meta_path = os.path.join(repo_path, 'cookbooks',
                    cookbook.get('source_name', id), 'metadata.json')
        cookbook = self._parse_cookbook_metadata(context, meta_path)
        if 'id' not in cookbook:
            cookbook['id'] = id
        return cookbook

    def _parse_cookbook_metadata(self, context, metadata_json_path):
        """Get a cookbook's data and format it as a checkmate component

        :param metadata_json_path: path to metadata.json file
        """
        component = {'is': 'application'}
        if os.path.exists(metadata_json_path):
            with file(metadata_json_path, 'r') as f:
                data = json.load(f)
            canonical_name = schema.translate(data['name'])
            component['id'] = canonical_name
            if data['name'] != canonical_name:
                component['source_name'] = data['name']
            component['summary'] = data.get('description')
            component['version'] = data.get('version')
            LOG.debug("Parsing attributes from %s" % metadata_json_path)
            if 'attributes' in data:
                component['options'] = self.translate_options(
                        data['attributes'], component['id'])
            if 'dependencies' in data:
                dependencies = []
                for key, value in data['dependencies'].iteritems():
                    dependencies.append(dict(id=schema.translate(key),
                            version=value))
                component['dependencies'] = dependencies
            if 'platforms' in data:
                #TODO: support multiple options
                if 'ubuntu' in data['platforms'] or 'centos' in \
                        data['platforms']:
                    requires = [dict(host='linux')]
                    component['requires'] = requires
        # Look for optional checkmate.json file
        checkmate_json_file = os.path.join(os.path.dirname(metadata_json_path),
                'checkmate.json')
        if os.path.exists(checkmate_json_file):
            with file(checkmate_json_file, 'r') as f:
                checkmate_data = json.load(f)

            # If fields are mapped, then apply the mappings
            remove = []
            if 'options' in checkmate_data:
                checkmate_fields = checkmate_data.get('options', {})
                for name, option in checkmate_fields.iteritems():
                    if 'source_field_name' in option:
                        translated = schema.translate(option[
                                                      'source_field_name'])
                        if translated == name:
                            continue
                        mapped = component.get('options', {}).get(translated)
                        if mapped:
                            LOG.debug("Removing mapped field '%s'" %
                                      translated)
                            updated = merge_dictionary(mapped, option)
                            option.update(updated)
                            remove.append(translated)
            for key in remove:
                del component['options'][key]
            merge_dictionary(component, checkmate_data, extend_lists=True)

        # Add hosting relationship (we're assuming we always need it for chef)
        LOG.debug("Parsing requires from %s" % metadata_json_path)
        if 'requires' in component:
            found = False
            for entry in component['requires']:
                key, value = entry.items()[0]
                if key == 'host':
                    found = True
                    break
                if isinstance(value, dict):
                    if value.get('relation') == 'host':
                        found = True
                        break
            if not found:
                component['requires'].append(dict(host='linux'))
        else:
            component['requires'] = [dict(host='linux')]
        LOG.debug("Processing dependencies for cookbook %s" %
                  os.path.dirname(metadata_json_path).split(os.path.sep)[-1])
        self._process_component_deps(context, component, add_requires=False,
                                     add_provides=False)
        return component

    def _get_roles(self, context):
        """Get all roles as Checkmate components"""
        results = {}
        repo_path = _get_repo_path()
        path = os.path.join(repo_path, 'roles')

        names = []
        for top, dirs, files in os.walk(path):  # @UnusedVariable
            names = [name for name in files if name.endswith('.json')]
            break

        for name in names:
            data = self._get_role(name[:-5], context)
            if data:
                results[data['id']] = data
        return results

    def _get_role(self, id, context):
        """Get a role as a Checkmate component"""
        assert id, 'Blank role ID requested from _get_role'
        role = {}
        repo_path = _get_repo_path()
        if id.endswith("-role"):
            id = id[:-5]
        role_path = os.path.join(repo_path, 'roles', "%s.json" % id)
        if os.path.exists(role_path):
            role = self._parse_role_metadata(role_path, context)
        return role

    def _parse_role_metadata(self, role_json_path, context):
        """Get a roles's data and format it as a checkmate component

        :param role_json_path: path to role json file

        Note: role names get '-role' appended to their ID to identify them as
              roles.
        """
        component = {'is': 'application'}
        provides = []
        requires = []
        options = {}
        with file(role_json_path, 'r') as f:
            data = json.load(f)
        component['id'] = "%s-role" % data['name']
        if data.get('description'):
            component['summary'] = data['description']
        if 'is' in data:
            component['is'] = data['is']
        if 'run_list' in data:
            dependencies = []
            for value in data['run_list']:
                if value.startswith('recipe'):
                    name = value[value.index('[') + 1:-1]
                    dependencies.append(name)
                elif value.startswith('role'):
                    name = value[value.index('[') + 1:-1]
                    dependencies.append("%s-role" % name)
                else:
                    continue
            if dependencies:
                component['dependencies'] = dependencies
            if provides:
                component['provides'] = provides
            if requires:
                component['requires'] = requires
            if options:
                component['options'] = options  # already translated
        self._process_component_deps(context, component)
        return component

    def _process_component_deps(self, context, component, add_provides=True,
                                add_requires=True):
        if component:
            for dep in component.get('dependencies', []):
                try:
                    dep_id = dep.get('id', 'UNKNOWN')
                except (AttributeError, TypeError):
                    dep_id = dep
                dependency = self.get_component(context, dep_id)
                if dependency:
                    if add_provides and 'provides' in dependency:
                        if 'provides' not in component:
                            component['provides'] = []
                        for entry in dependency['provides']:
                            if entry not in component['provides']:
                                component['provides'].append(entry)
                    if add_requires and 'requires' in dependency:
                        if 'requires' not in component:
                            component['requires'] = []
                        for entry in dependency['requires']:
                            if entry not in component['requires']:
                                component['requires'].append(entry)
                    if 'options' in dependency:
                        if 'options' not in component:
                            component['options'] = {}
                        # Mark options as coming from another component
                        for key, option in dependency['options'].iteritems():
                            if 'source' not in option:
                                option['source'] = dependency['id']
                            if key not in component['options']:
                                component['options'][key] = option

    def translate_options(self, native_options, component_id):
        """Translate native provider options to canonical, checkmate options

        :param native_options: dict coming from metadata.json
        :component_id: the cookbook id which should be removed from the
        translated name
        """
        options = {}
        for key, option in native_options.iteritems():
            canonical = schema.translate(key)
            translated = {}
            if 'display_name' in option:
                translated['label'] = option['display_name']
            if 'description' in option:
                translated['description'] = option['description']
            if 'default' in option:
                translated['default'] = option['default']
            if 'required' in option:
                translated['required'] = option['required']
            if 'type' in option:
                translated['type'] = option['type']
                if translated['type'] not in schema.OPTION_TYPES:  # log only
                    LOG.info("Invalid option type '%s' in '%s'" % (
                            option['type'], key))
            if 'source' in option:
                translated['source'] = option['source']
            if 'source_field_name' in option:
                translated['source_field_name'] = \
                        option['source_field_name']
#             TODO: do we really need to be so strict regarding option names?
            if canonical != key:
                translated['source_field_name'] = key
            violations = schema.validate(translated, schema.OPTION_SCHEMA)
            if violations:  # log only now
                LOG.info("Schema violations in '%s': %s" % (violations, key))
            options[canonical] = translated
        return options

    def find_components(self, context, **kwargs):
        """Special parsing for roles, then defer to superclass"""
        cid = kwargs.get('id', None)
        name = kwargs.get('name', None)
        role = kwargs.pop('role', None)
        if (not cid) and name:
            if role:
                cid = "%s::%s" % (name, role)
            else:
                cid = name
        LOG.debug("Finding components that match: id=%s, name=%s, role=%s, %s"
                  % (cid, name, role, kwargs))
        if cid:
            result = self.get_component(context, cid)
            if result:
                LOG.debug("'%s' matches in provider '%s' and provides %s" %
                            (cid, self.key, result.get('provides', [])))
                return [self.get_component(context, cid)]
            else:
                LOG.warn("Component id '%s' provided but not "
                        "found in provider '%s'" % (cid, self.key))
                return []
        return ProviderBase.find_components(self, context, **kwargs)

    def status(self):
        # Files to be changed:
        #   git diff --stat --color remotes/origin/master..master
        # Full diff: remove --stat
        pass
