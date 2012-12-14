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
import errno
import logging
import os
import urlparse

from Crypto.PublicKey import RSA  # pip install pycrypto
from Crypto.Random import atfork
from SpiffWorkflow.operators import Attrib, PathAttrib
from SpiffWorkflow.specs import Celery, Transform, Merge

from checkmate.common import schema
from checkmate.components import Component
from checkmate.exceptions import CheckmateException, CheckmateIndexError,\
        CheckmateCalledProcessError
from checkmate.keys import hash_SHA512
from checkmate.providers import ProviderBase
from checkmate.utils import get_source_body, merge_dictionary, \
        match_celery_logging
from checkmate.workflows import wait_for
from SpiffWorkflow.specs.Simple import Simple

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
                    'checkmate.providers.opscode.local.create_environment',
                    call_args=[deployment['id'], service_name],
                    public_key_ssh=deployment.settings().get('keys', {}).get(
                            'deployment', {}).get('public_key_ssh'),
                    private_key=deployment.settings().get('keys', {}).get(
                            'deployment', {}).get('private_key'),
                    secret_key=deployment.get_setting('secret_key'),
                    source_repo=deployment.get_setting('source',
                                                      provider_key=\
                                                            self.key,
                                                      service_name=\
                                                            service_name),
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
                # Call manage_databag(environment, bagname, itemname, contents)
                write_options = Celery(wfspec,
                        "Write Data Bag for %s" % service_name,
                       'checkmate.providers.opscode.local.manage_databag',
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
                        'checkmate.providers.opscode.local.manage_role',
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
                # Call manage_databag(environment, bagname, itemname, contents)

                write_options = Celery(wfspec,
                        "Write Data Bag for %s/%s" % (component['id'], key),
                       'checkmate.providers.opscode.local.manage_databag',
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
                        'checkmate.providers.opscode.local.manage_role',
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
               'checkmate.providers.opscode.local.cook',
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
                    'checkmate.providers.opscode.local.register_node',
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
                    'checkmate.providers.opscode.local.cook',
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
                raise CheckmateException("Component id '%s' provided but not "
                        "found in provider '%s'" % (cid, self.key))
        return ProviderBase.find_components(self, context, **kwargs)

    def status(self):
        # Files to be changed:
        #   git diff --stat --color remotes/origin/master..master
        # Full diff: remove --stat
        pass

#
# Celery Tasks (moved from python-stockton)
#
from collections import deque
import git
import json
import shutil
from subprocess import check_output, CalledProcessError, Popen, PIPE
import sys
import threading

from celery.task import task  # @UnresolvedImport

from checkmate.ssh import execute as ssh_execute


@task
def create_environment(name, service_name, path=None, private_key=None,
                       public_key_ssh=None, secret_key=None, source_repo=None):
    """Create a knife-solo environment

    The environment is a directory structure that is self-contained and
    seperate from other environments. It is used by this provider to run knife
    solo commands.

    :param name: the name of the environment. This will be the directory name.
    :param path: an override to the root path where to create this environment
    :param private_key: PEM-formatted private key
    :param public_key_ssh: SSH-formatted public key
    :param secret_key: used for data bag encryption
    :param source_repo: provides cookbook repository in valid git syntax
    """
    match_celery_logging(LOG)
    # Get path
    root = _get_root_environments_path(path)
    fullpath = os.path.join(root, name)

    # Create environment
    try:
        os.mkdir(fullpath, 0770)
        LOG.debug("Created environment directory: %s" % fullpath)
    except OSError as ose:
        if ose.errno == errno.EEXIST:
            LOG.warn("Environment directory %s already exists", fullpath,
                      exc_info=True)
        else:
            raise CheckmateException(
                "Could not create environment %s" % fullpath, ose)

    results = {"environment": fullpath}

    key_data = _create_environment_keys(fullpath, private_key=private_key,
            public_key_ssh=public_key_ssh)

    # Kitchen is created in a /kitchen subfolder since it gets completely
    # rsynced to hosts. We don't want the whole environment rsynced
    kitchen_data = _create_kitchen(service_name, fullpath,
            secret_key=secret_key)
    kitchen_path = os.path.join(fullpath, service_name)

    # Copy environment public key to kitchen certs folder
    public_key_path = os.path.join(fullpath, 'checkmate.pub')
    kitchen_key_path = os.path.join(kitchen_path, 'certificates',
            'checkmate-environment.pub')
    shutil.copy(public_key_path, kitchen_key_path)
    LOG.debug("Wrote environment public key to kitchen: %s" % kitchen_key_path)

    if source_repo:
        _init_repo(kitchen_path, source_repo=source_repo)
        # If Cheffile exists, all librarian-chef to pull in cookbooks
        if os.path.exists(os.path.join(kitchen_path, 'Cheffile')):
            _run_ruby_command(kitchen_path, 'librarian-chef', ['install'],
                              lock=True)
            LOG.debug("Ran 'librarian-chef install' in: %s" % kitchen_path)
    else:
        _init_repo(os.path.join(kitchen_path, 'cookbooks'))
        # Keep for backwards compatibility, but source_repo should be provided
        # Temporary Hack: load all cookbooks and roles from chef-stockton
        # TODO: Undo this and use more git
        download_cookbooks(name, service_name, path=root)
        download_cookbooks(name, service_name, path=root, use_site=True)
        download_roles(name, service_name, path=root)

    results.update(kitchen_data)
    results.update(key_data)
    LOG.debug("create_environment returning: %s" % results)
    return results


def _get_root_environments_path(path=None):
    """Build the path using provided inputs and using any environment variables
    or configuration settings"""
    root = path or os.environ.get("CHECKMATE_CHEF_LOCAL_PATH",
            "/var/local/checkmate/deployments")
    if not os.path.exists(root):
        raise CheckmateException("Invalid root path: %s" % root)
    return root


def _create_kitchen(name, path, secret_key=None):
    """Creates a new knife-solo kitchen in path

    :param name: the name of the kitchen
    :param path: where to create the kitchen
    :param secret_key: PEM-formatted private key for data bag encryption
    """
    if not os.path.exists(path):
        raise CheckmateException("Invalid path: %s" % path)

    kitchen_path = os.path.join(path, name)
    if not os.path.exists(kitchen_path):
        os.mkdir(kitchen_path, 0770)
        LOG.debug("Created kitchen directory: %s" % kitchen_path)
    else:
        LOG.debug("Kitchen directory exists: %s" % kitchen_path)

    nodes_path = os.path.join(kitchen_path, 'nodes')
    if os.path.exists(nodes_path):
        if any((f.endswith('.json') for f in os.listdir(nodes_path))):
            raise CheckmateException("Kitchen already exists and seems to "
                    "have nodes defined in it: %s" % nodes_path)
    else:
        # we don't pass the config file here becasuse we're creating the
        # kitchen for the first time and knife will overwrite our config file
        params = ['knife', 'kitchen', '.']
        _run_kitchen_command(kitchen_path, params)

    solo_file, secret_key_path = _write_knife_config_file(kitchen_path)

    # Copy bootstrap.json to the kitchen
    repo_path = _get_repo_path()
    bootstrap_path = os.path.join(repo_path, 'bootstrap.json')
    if not os.path.exists(bootstrap_path):
        raise CheckmateException("Invalid master repo. {} not found"
                                 .format(bootstrap_path))
    shutil.copy(bootstrap_path, os.path.join(kitchen_path, 'bootstrap.json'))

    # Create certificates folder
    certs_path = os.path.join(kitchen_path, 'certificates')
    if os.path.exists(certs_path):
        LOG.debug("Certs directory exists: %s" % certs_path)
    else:
        os.mkdir(certs_path, 0770)
        LOG.debug("Created certs directory: %s" % certs_path)

    # Store (generate if necessary) the secrets file
    if os.path.exists(secret_key_path):
        if secret_key:
            with file(secret_key_path, 'r') as f:
                data = f.read(secret_key)
            if data != secret_key:
                raise CheckmateException("Kitchen secrets key file '%s' "
                        "already exists and does not match the provided value"
                        % secret_key_path)
        LOG.debug("Stored secrets file exists: %s" % secret_key_path)
    else:
        if not secret_key:
            # celery runs os.fork(). We need to reset the random number
            # generator before generating a key. See atfork.__doc__
            atfork()
            key = RSA.generate(2048)
            secret_key = key.exportKey('PEM')
            LOG.debug("Generated secrets private key")
        with file(secret_key_path, 'w') as f:
            f.write(secret_key)
        LOG.debug("Stored secrets file: %s" % secret_key_path)

    # Knife defaults to knife.rb, but knife-solo looks for solo.rb, so we link
    # both files so that knife and knife-solo commands will work and anyone
    # editing one will also change the other
    knife_file = os.path.join(path, name, 'knife.rb')
    if os.path.exists(knife_file):
        LOG.debug("Knife.rb already exists: %s" % knife_file)
    else:
        os.link(solo_file, knife_file)
        LOG.debug("Linked knife.rb: %s" % knife_file)

    LOG.debug("Finished creating kitchen: %s" % kitchen_path)
    return {"kitchen": kitchen_path}


def _write_knife_config_file(kitchen_path):
    """Writes a solo.rb config file and links a knife.rb file too"""
    secret_key_path = os.path.join(kitchen_path, 'certificates', 'chef.pem')
    config = """# knife -c knife.rb
file_cache_path  "%s"
cookbook_path    ["%s", "%s"]
role_path  "%s"
data_bag_path  "%s"
log_level        :info
log_location     STDOUT
ssl_verify_mode  :verify_none
encrypted_data_bag_secret "%s"
""" % (kitchen_path,
            os.path.join(kitchen_path, 'cookbooks'),
            os.path.join(kitchen_path, 'site-cookbooks'),
            os.path.join(kitchen_path, 'roles'),
            os.path.join(kitchen_path, 'data_bags'),
            secret_key_path)
    # knife kitchen creates a default solo.rb, so the file already exists
    solo_file = os.path.join(kitchen_path, 'solo.rb')
    with file(solo_file, 'w') as handle:
        handle.write(config)
    LOG.debug("Created solo file: %s" % solo_file)
    return (solo_file, secret_key_path)


def _create_environment_keys(environment_path, private_key=None,
        public_key_ssh=None):
    """Put keys in an existing environment

    If none are provided, a new set of public/private keys are created
    """
    # Create private key
    private_key_path = os.path.join(environment_path, 'private.pem')
    if os.path.exists(private_key_path):
        # Already exists.
        if private_key:
            with file(private_key_path, 'r') as f:
                data = f.read()
            if data != private_key:
                raise CheckmateException("A private key already exists in "
                        "environment %s and does not match the value provided "
                        % environment_path)
    else:
        if private_key:
            with file(private_key_path, 'w') as f:
                f.write(private_key)
            LOG.debug("Wrote environment private key: %s" % private_key_path)
        else:
            params = ['openssl', 'genrsa', '-out', private_key_path, '2048']
            result = check_output(params)
            LOG.debug(result)
            LOG.debug("Generated environment private key: %s" %
                      private_key_path)

    # Secure private key
    os.chmod(private_key_path, 0600)
    LOG.debug("Private cert permissions set: chmod 0600 %s" %
            private_key_path)

    # Get or Generate public key
    public_key_path = os.path.join(environment_path, 'checkmate.pub')
    if os.path.exists(public_key_path):
        LOG.debug("Public key exists. Retrieving it from %s" % public_key_path)
        with file(public_key_path, 'r') as f:
            public_key_ssh = f.read()
    else:
        if not public_key_ssh:
            params = ['ssh-keygen', '-y', '-f', private_key_path]
            public_key_ssh = check_output(params)
            LOG.debug("Generated environment public key: %s" % public_key_path)
        # Write it to environment
        with file(public_key_path, 'w') as f:
            f.write(public_key_ssh)
        LOG.debug("Wrote environment public key: %s" % public_key_path)
    return dict(public_key_ssh=public_key_ssh, public_key_path=public_key_path,
            private_key_path=private_key_path)


def register_scheme(scheme):
    '''
    Use this to register a new scheme with urlparse and have it be parsed
    in the same way as http is parsed
    '''
    for method in filter(lambda s: s.startswith('uses_'), dir(urlparse)):
        getattr(urlparse, method).append(scheme)


register_scheme('git')  # without this, urlparse won't handle git:// correctly


def _init_repo(path, source_repo=None):
    """Initialize a git repo. Pull it if remote is supplied."""
    if not os.path.exists(path):
        raise CheckmateException("Invalid repo path: %s" % path)

    # Init git repo
    repo = git.Repo.init(path)

    if source_repo:  # Pull remote if supplied
        source_repo, ref = urlparse.urldefrag(source_repo)
        remotes = [r for r in repo.remotes
                     if r.config_reader.get('url') == source_repo]
        if remotes:
            remote = remotes[0]
        else:
            #FIXME: there's a gap here. We don't check if origin exists.
            remote = repo.create_remote('origin', source_repo)
        remote.pull(refspec=ref or 'master')
        LOG.debug("Pulled '%s' ref '%s' into repo: %s" % (source_repo,
                                                          ref or 'master',
                                                          path))
    else:
        # Make path a git repo
        file_path = os.path.join(path, '.gitignore')
        with file(file_path, 'w') as f:
            f.write("#Checkmate Created Repo")
        index = repo.index
        index.add(['.gitignore'])
        index.commit("Initial commit")
        LOG.debug("Initialized blank repo: %s" % path)


@task
def download_cookbooks(environment, service_name, path=None, cookbooks=None,
        source=None, use_site=False):
    """Download cookbooks from a remote repo
    :param environment: the name of the kitchen/environment environment.
        It should have cookbooks and site-cookbooks subfolders
    :param path: points to the root of environments.
        It should have cookbooks and site-cookbooks subfolders
    :param cookbooks: the names of the cookbooks to download (blank=all)
    :param source: the source repos (a github URL)
    :param use_site: use site-cookbooks instead of cookbooks
    :returns: count of cookbooks copied"""
    match_celery_logging(LOG)
    # Until we figure out a better solution, I'm assuming the chef-stockton
    # repo is cloned as a subfolder under the provider (and cloning it if
    # not) and we copy the cookbooks from there

    # Get path
    root = _get_root_environments_path(path)
    fullpath = os.path.join(root, environment)
    if not os.path.exists(fullpath):
        raise CheckmateException("Environment does not exist: %s" % fullpath)
    kitchen_path = os.path.join(fullpath, service_name)
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Kitchen does not exist: %s" % kitchen_path)

    # Find/get cookbook source
    repo_path = _get_repo_path()

    if use_site:
        cookbook_subdir = 'site-cookbooks'
    else:
        cookbook_subdir = 'cookbooks'

    # Check that cookbooks requested exist
    if cookbooks:
        for cookbook in cookbooks:
            if not os.path.exists(os.path.join(repo_path, cookbook_subdir,
                    cookbook)):
                raise CheckmateException("Cookbook '%s' not available in repo:"
                        " %s" % (cookbook, repo_path))
    else:
        # If none specificed, assume all
        cookbooks = [p for p in os.listdir(os.path.join(repo_path,
                cookbook_subdir)) if os.path.isdir(os.path.join(repo_path,
                cookbook_subdir, p))]

    # Copy the cookbooks over
    count = 0
    for cookbook in cookbooks:
        target = os.path.join(kitchen_path, cookbook_subdir, cookbook)
        if not os.path.exists(target):
            LOG.debug("Copying cookbook '%s' to %s" % (cookbook, repo_path))
            shutil.copytree(os.path.join(repo_path, cookbook_subdir, cookbook),
                    target)
            count += 1
    return count


@task
def download_roles(environment, service_name, path=None, roles=None,
                   source=None):
    """Download roles from a remote repo
    :param environment: the name of the kitchen/environment environment.
        It should have a roles subfolder.
    :param path: points to the root of environments.
        It should have a roles subfolders
    :param roles: the names of the roles to download (blank=all)
    :param source: the source repos (a github URL)
    :returns: count of roles copied"""
    match_celery_logging(LOG)
    # Until we figure out a better solution, I'm assuming the chef-stockton
    # repo is cloned as a subfolder under python-stockton (and cloning it if
    # not) and we copy the roles from there

    # Get path
    root = _get_root_environments_path(path)
    fullpath = os.path.join(root, environment)
    if not os.path.exists(fullpath):
        raise CheckmateException("Environment does not exist: %s" % fullpath)
    kitchen_path = os.path.join(fullpath, service_name)
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Kitchen does not exist: %s" % kitchen_path)

    # Find/get cookbook source
    repo_path = _get_repo_path()

    if not os.path.exists(repo_path):
        rax_repo = 'git://github.rackspace.com/ManagedCloud/chef-stockton.git'
        git.Repo.clone_from(rax_repo, repo_path)
        LOG.info("Cloned chef-stockton from %s to %s" % (rax_repo, repo_path))
    else:
        LOG.debug("Getting roles from %s" % repo_path)

    # Check that roles requested exist
    if roles:
        for role in roles:
            if not os.path.exists(os.path.join(repo_path, 'roles',
                    role)):
                raise CheckmateException("Role '%s' not available in repo: "
                        "%s" % (role, repo_path))
    else:
        # If none specificed, assume all
        roles = [p for p in os.listdir(os.path.join(repo_path, 'roles'))]

    # Copy the roles over
    count = 0
    for role in roles:
        target = os.path.join(kitchen_path, 'roles', role)
        if not os.path.exists(target):
            LOG.debug("Copying role '%s' to %s" % (role, repo_path))
            shutil.copy(os.path.join(repo_path, 'roles', role), target)
            count += 1
    return count


@task
def register_node(host, environment, path=None, password=None,
        omnibus_version=None, attributes=None, identity_file=None,
        kitchen_name='kitchen'):
    """Register a node in Chef.

    Using 'knife prepare' we will:
    - update apt caches on Ubuntu by default (which bootstrap does not do)
    - install chef on the client
    - register the node by creating as .json file for it in /nodes/

    Note: Maintaining same 'register_node' name as chefserver.py

    :param host: the public IP of the host (that's how knife solo tracks the
        nodes)
    :param environment: the ID of the environment
    :param path: an optional override for path to the environment root
    :param password: the node's password
    :param omnibus_version: override for knife bootstrap (default=latest)
    :param attributes: attributes to set on node (dict)
    :param identity_file: private key file to use to connect to the node
    """
    match_celery_logging(LOG)
    # Get path
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, kitchen_name)
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Environment kitchen does not exist: %s" %
                kitchen_path)

    # Rsync problem with creating path (missing -p so adding it ourselves) and
    # doing this before the complex prepare work
    ssh_execute(host, "mkdir -p %s" % kitchen_path, 'root', password=password,
            identity_file=identity_file)

    # Calculate node path and check for prexistance
    node_path = os.path.join(kitchen_path, 'nodes', '%s.json' % host)
    if os.path.exists(node_path):
        raise CheckmateException("Node seems to already be registered: %s" %
                node_path)

    # Build and execute command 'knife prepare' command
    params = ['knife', 'prepare', 'root@%s' % host,
              '-c', os.path.join(kitchen_path, 'solo.rb')]
    if password:
        params.extend(['-P', password])
    if omnibus_version:
        params.extend(['--omnibus-version', omnibus_version])
    if identity_file:
        params.extend(['-i', identity_file])
    _run_kitchen_command(kitchen_path, params)
    LOG.info("Knife prepare succeeded for %s" % host)

    if attributes:
        lock = threading.Lock()
        lock.acquire()
        try:
            node = {'run_list': []}  # default
            with file(node_path, 'r') as f:
                node = json.load(f)
            node.update(attributes)
            with file(node_path, 'w') as f:
                json.dump(node, f)
            LOG.info("Node attributes written in %s" % node_path, extra=dict(
                    data=node))
        except StandardError, exc:
            raise exc
        finally:
            lock.release()


def _run_kitchen_command(kitchen_path, params, lock=True):
    """Runs the 'knife xxx' command.

    This also needs to handle knife command errors, which are returned to
    stderr.

    That needs to be run in a kitchen, so we move curdir and need to make sure
    we stay there, so I added some synchronization code while that takes place
    However, if code calls in that already has a lock, the optional lock param
    can be set to false so thise code does not lock
    """
    LOG.debug("Running: '%s' in path '%s'" % (' '.join(params), kitchen_path))
    if '-c' not in params:
        LOG.warning("Knife command called without a '-c' flag. The '-c' flag "
                  "is a strong safeguard in case knife runs in the wrong "
                  "directory. Consider adding it and pointing to solo.rb")
        config_file = os.path.join(kitchen_path, 'solo.rb')
        if os.path.exists(config_file):
            LOG.debug("Defaulting to config file '%s'" % config_file)
            params.extend(['-c', config_file])
    result = _run_ruby_command(kitchen_path, params[0], params[1:], lock=lock)

    # Knife succeeds even if there is an error. This code tries to parse the
    # output to return a useful error. Note that FATAL erros will be picked up
    # by _run_ruby_command
    last_error = ''
    for line in result.split('\n'):
        if 'ERROR:' in line:
            LOG.error(line)
            last_error = line
    if last_error:
        if 'KnifeSolo::::' in last_error:
            # Get the string after a Knife-Solo error::
            error = last_error.split('Error:')[-1]
            if error:
                raise CheckmateCalledProcessError(1, ' '.join(params),
                        output="Knife error encountered: %s" % error)
            # Don't raise on all errors. They don't all mean failure!
    return result


def _run_ruby_command(path, command, params, lock=True):
    """Runs a knife-like command (ex. librarian-chef).

    Since knife-ike command errors are returned to stderr, we need to capture
    stderr and check for errors.

    That needs to be run in a kitchen, so we move curdir and need to make sure
    we stay there, so I added some synchronization code while that takes place
    However, if code calls in that already has a lock, the optional lock param
    can be set to false so thise code does not lock.
    :param version_param: the parameter used to get the command's version. This
            is used to check if the program is installed.
    """
    params.insert(0, command)
    LOG.debug("Running: '%s' in path '%s'" % (' '.join(params), path))
    if lock:
        path_lock = threading.Lock()
        path_lock.acquire()
        try:
            if path:
                os.chdir(path)
            result = check_all_output(params)  # check_output(params)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                # Check if command is installed
                output = check_output(['which', command])
                if not output:
                    raise CheckmateException("'%s' is not installed or not "
                                             "accessible on the server" %
                                             command)
            raise exc
        except CalledProcessError, exc:
            #retry and pass ex
            # CalledProcessError cannot be serialized using Pickle, so raising
            # it would fail in celery; we wrap the exception in something
            # Pickle-able.
            raise CheckmateCalledProcessError(exc.returncode, exc.cmd,
                                              output=exc.output)
        finally:
            path_lock.release()
    else:
        if path:
            os.chdir(path)
        result = check_all_output(params)
    LOG.debug(result)
    # Knife-like commands succeed even if there is an error. This code tries to
    # parse the output to return a useful error
    fatal = []
    last_fatal = ''
    for line in result.split('\n'):
        if 'FATAL:' in line:
            fatal.append(line)
            last_fatal = line
    if fatal:
        command = ' '.join(params)
        if 'Chef::Exceptions::' in last_fatal:
            # Get the string after Chef::Exceptions::
            error = last_fatal.split('::')[-1]
            if error:
                raise CheckmateCalledProcessError(1, command,
                        output="Chef/Knife error encountered: %s" % error)
        output = '\n'.join(fatal)
        raise CheckmateCalledProcessError(1, command, output=output)

    return result


@task(countdown=20, max_retries=3)
def cook(host, environment, recipes=None, roles=None, path=None,
         username='root', password=None, identity_file=None, port=22,
         kitchen_name='kitchen'):
    """Apply recipes/roles to a server"""
    match_celery_logging(LOG)
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, kitchen_name)
    if not os.path.exists(kitchen_path):
        raise CheckmateException("Environment kitchen does not exist: %s" %
                kitchen_path)
    node_path = os.path.join(kitchen_path, 'nodes', '%s.json' % host)
    if not os.path.exists(node_path):
        cook.retry(exc=CheckmateException("Node '%s' is not registered in %s"
                                          % (host, kitchen_path)))

    # Add any missing recipes to node settings
    run_list = []
    if roles:
        run_list.extend(["role[%s]" % role for role in roles])
    if recipes:
        run_list.extend(["recipe[%s]" % recipe for recipe in recipes])
    if run_list:
        add_list = []
        # Open file, read/parse/calculate changes, then write
        lock = threading.Lock()
        lock.acquire()
        try:
            with file(node_path, 'r') as f:
                node = json.load(f)
            for entry in run_list:
                if entry not in node['run_list']:
                    node['run_list'].append(entry)
                    add_list.append(entry)
            if add_list:
                with file(node_path, 'w') as f:
                    json.dump(node, f)
        finally:
            lock.release()
        if add_list:
            LOG.debug("Added to %s: %s" % (node_path, add_list))
        else:
            LOG.debug("All run_list already exists in %s: %s" % (node_path,
                    run_list))
    else:
        LOG.debug("No recipes or roles to add. Will just run 'knife cook' for "
                "%s using bootstrap.json" % node_path)

    # Build and run command
    if not username:
        username = 'root'
    params = ['knife', 'cook', '%s@%s' % (username, host),
              '-c', os.path.join(kitchen_path, 'solo.rb')]
    if not run_list:
        params.extend(['bootstrap.json'])
    if identity_file:
        params.extend(['-i', identity_file])
    if password:
        params.extend(['-P', password])
    if port:
        params.extend(['-p', str(port)])
    _run_kitchen_command(kitchen_path, params)


@task(countdown=20, max_retries=3)
def manage_role(name, environment, path=None, desc=None,
        run_list=None, default_attributes=None, override_attributes=None,
        env_run_lists=None, kitchen_name='kitchen'):
    """Write/Update role"""
    match_celery_logging(LOG)
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, kitchen_name)
    if not os.path.exists(kitchen_path):
        manage_role.retry(exc=CheckmateException(
                             "Environment does not exist: %s" %
                             kitchen_path))
    the_ruby = os.path.join(kitchen_path, 'roles', '%s.rb' % name)
    if os.path.exists(the_ruby):
        raise CheckmateException("Encountered a chef role in Ruby. Only JSON "
                "roles can be manipulated by Checkmate: %s" % the_ruby)

    role_path = os.path.join(kitchen_path, 'roles', '%s.json' % name)

    if os.path.exists(role_path):
        with file(role_path, 'r') as f:
            role = json.load(f)
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

    LOG.debug("Writing role '%s' to %s" % (name, role_path))
    with file(role_path, 'w') as f:
        json.dump(role, f)


@task
def manage_databag(environment, bagname, itemname, contents,
        path=None, secret_file=None, merge=True, kitchen_name='kitchen'):
    """Updates a data_bag or encrypted_data_bag

    :param environment: the ID of the environment
    :param bagname: the name of the databag (in solo, this end up being a
            directory)
    :param item: the name of the item (in solo this ends up being a .json file)
    :param contents: this is a dict of attributes to write in to the databag
    :param path: optional override to the default path where environments live
    :param secret_file: the path to a certificate used to encrypt a data_bag
    :param merge: if True, the data will be merged in. If not, it will be
            completely overwritten
    """
    match_celery_logging(LOG)
    root = _get_root_environments_path(path)
    kitchen_path = os.path.join(root, environment, kitchen_name)
    databags_root = os.path.join(kitchen_path, 'data_bags')
    if not os.path.exists(databags_root):
        raise CheckmateException("Data bags path does not exist: %s" %
                databags_root)

    # Check if the bag already exists (create it if not)
    params = ['knife', 'solo', 'data', 'bag', 'list', '-F', 'json',
              '-c', os.path.join(kitchen_path, 'solo.rb')]
    data_bags = _run_kitchen_command(kitchen_path, params)
    if data_bags:
        data_bags = json.loads(data_bags)
    if bagname not in data_bags:
        merge = False  # Nothing to merge if it is new!
        _run_kitchen_command(kitchen_path, ['knife', 'solo', 'data', 'bag',
                'create', bagname,
                '-c', os.path.join(kitchen_path, 'solo.rb')])
        LOG.debug("Created data bag '%s' in '%s'" % (bagname, databags_root))

    # Check if the item already exists (create it if not)
    params = ['knife', 'solo', 'data', 'bag', 'show', bagname, '-F', 'json',
              '-c', os.path.join(kitchen_path, 'solo.rb')]
    existing_contents = _run_kitchen_command(kitchen_path, params)
    if existing_contents:
        existing_contents = json.loads(existing_contents)
    if itemname not in existing_contents:
        merge = False  # Nothing to merge if it is new!

    # Write contents
    if merge:
        params = ['knife', 'solo', 'data', 'bag', 'show', bagname, itemname,
            '-F', 'json', '-c', os.path.join(kitchen_path, 'solo.rb')]
        if secret_file:
            params.extend(['--secret-file', secret_file])

        lock = threading.Lock()
        lock.acquire()
        try:
            data = _run_kitchen_command(kitchen_path, params)
            existing = json.loads(data)
            contents = merge_dictionary(existing, contents)
            if isinstance(contents, dict):
                contents = json.dumps(contents)
            params = ['knife', 'solo', 'data', 'bag', 'create', bagname,
                      itemname, '-c', os.path.join(kitchen_path, 'solo.rb'),
                      '-d', '--json', contents]
            if secret_file:
                params.extend(['--secret-file', secret_file])
            result = _run_kitchen_command(kitchen_path, params, lock=False)
        except CalledProcessError, exc:
            # Reraise pickleable exception
            raise CheckmateCalledProcessError(exc.returncode, exc.cmd,
                    output=exc.output)
        finally:
            lock.release()
        LOG.debug(result)
    else:
        if contents:
            if 'id' not in contents:
                contents['id'] = itemname
            elif contents['id'] != itemname:
                raise CheckmateException("The value of the 'id' field in a databag"
                        " item is reserved by Chef and must be set to the name of "
                        "the databag item. Checkmate will set this for you if it "
                        "is missing, but the data you supplied included an ID "
                        "that did not match the databag item name. The ID was "
                        "'%s' and the databg item name was '%s'" % (contents['id'],
                        itemname))
            if isinstance(contents, dict):
                contents = json.dumps(contents)
            params = ['knife', 'solo', 'data', 'bag', 'create', bagname, itemname,
                      '-d', '-c', os.path.join(kitchen_path, 'solo.rb'),
                      '--json', contents]
            if secret_file:
                params.extend(['--secret-file', secret_file])
            result = _run_kitchen_command(kitchen_path, params)
            LOG.debug(result)
        else:
            LOG.warning("Managed databag was called with no contents")


def check_all_output(params):
    """Similar to subprocess check_output, but returns all output in error if
    an error is raised.

    We use this for processing Knife output where the details of the error are
    piped to stdout and the actual error does not have everything we need"""
    ON_POSIX = 'posix' in sys.builtin_module_names

    def start_thread(func, *args):
        t = threading.Thread(target=func, args=args)
        t.daemon = True
        t.start()
        return t

    def consume(infile, output, errors):
        for line in iter(infile.readline, ''):
            output(line)
            if 'FATAL' in line:
                errors(line)
        infile.close()

    p = Popen(params, stdout=PIPE, stderr=PIPE, bufsize=1, close_fds=ON_POSIX)

    # preserve last N lines of stdout and stderr
    N = 100
    queue = deque(maxlen=N)  # will capture output
    errors = deque(maxlen=N)  # will capture Knife errors (contain 'FATAL')
    threads = [start_thread(consume, *args)
                for args in (p.stdout, queue.append, errors.append),
                (p.stderr, queue.append, errors.append)]
    for t in threads:
        t.join()  # wait for IO completion

    retcode = p.wait()

    if retcode == 0:
        return '%s%s' % (''.join(errors), ''.join(queue))
    else:
        # Raise CalledProcessError, but include the Knife-specifc errors
        raise CheckmateCalledProcessError(retcode, ' '.join(params),
                output='\n'.join(queue), error_info='\n'.join(errors))

CHECKMATE_CHEF_REPO = None
def _get_repo_path():
    """Find the master repo path for chef cookbooks"""
    global CHECKMATE_CHEF_REPO
    if not CHECKMATE_CHEF_REPO:
        CHECKMATE_CHEF_REPO = os.environ.get('CHECKMATE_CHEF_REPO')
        if not CHECKMATE_CHEF_REPO:
            CHECKMATE_CHEF_REPO = "/var/local/checkmate/chef-stockton"
            LOG.warning("CHECKMATE_CHEF_REPO variable not set. Defaulting to "
                        "%s" % CHECKMATE_CHEF_REPO)
            if not os.path.exists(CHECKMATE_CHEF_REPO):
                git.Repo.clone_from('git://github.rackspace.com/checkmate/'
                        'chef-stockton.git', CHECKMATE_CHEF_REPO)
                LOG.info("Cloned chef-stockton to %s" % CHECKMATE_CHEF_REPO)
    return CHECKMATE_CHEF_REPO
