"""Chef Solo configuration management provider"""
import logging

from SpiffWorkflow.operators import Attrib, PathAttrib
from SpiffWorkflow.specs import Celery, Transform, Merge

from checkmate import utils
from checkmate.keys import hash_SHA512
from checkmate.providers import ProviderBase
from checkmate.workflows import wait_for

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    """Implements a Chef Solo configuration management provider"""
    name = 'chef-solo'
    vendor = 'opscode'

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
        self.prep_task = None
        self.collect_data_task = None

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
        defines = {'provider': self.key, 'task_tags': ['root']}
        properties = {'estimated_duration': 10}
        task_name = 'checkmate.providers.opscode.local.create_environment'
        create_environment_task = Celery(wfspec,
                                         'Create Chef Environment',
                                         task_name,
                                         call_args=[deployment['id'],
                                                    'kitchen'],
                                         public_key_ssh=public_key_ssh,
                                         private_key=private_key,
                                         secret_key=secret_key,
                                         source_repo=source_repo,
                                         defines=defines,
                                         properties=properties)

        #FIXME: use a map file
        # Call manage_databag(environment, bagname, itemname, contents)
        """
        write_options = Celery(wfspec,
                "Write Data Bag",
               'checkmate.providers.opscode.local.manage_databag',
                call_args=[deployment['id'], deployment['id'],
                        Attrib('app_id'), Attrib('chef_options')],
                kitchen_name="kitchen",
                secret_file='certificates/chef.pem',
                merge=True,
                defines=dict(provider=self.key),
                properties={'estimated_duration': 5})

        collect = Merge(wfspec,
                        "Collect Chef Data",
                        defines={'provider': self.key,
                                 'extend_lists': True,
                                 'task_tags': ['write_options']})
        # Make sure the environment exists before writing options.
        collect.follow(create_environment_task)
        write_options.follow(collect)
        # Any tasks that need to be collected will wire themselves into
        # this task
        self.collect_data_task = dict(root=collect, final=write_options)
        self.prep_task = create_environment_task
        return {'root': create_environment_task, 'final': write_options}
        """
        self.collect_data_task = dict(root=create_environment_task,
                                      final=create_environment_task)
        self.prep_task = create_environment_task
        return {'root': create_environment_task,
                'final': create_environment_task}

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        """Create and write settings, generate run_list, and call cook"""
        wait_on, service_name, component = self._add_resource_tasks_helper(
                resource, key, wfspec, deployment, context, wait_on)
        self._add_component_tasks(wfspec, component, deployment, key,
                                  context, service_name)

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
        dependencies = [self.prep_task, self.collect_data_task['final']]
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
        write_tasks = self.find_tasks(wfspec, tag='write_options')
        if write_tasks:
            dependencies.extend(write_tasks)
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
                transforms=[utils.get_source_body(build_data_code)],
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

    def _hash_all_user_resource_passwords(self, deployment):
        """Chef needs all passwords to be a hash"""
        if 'resources' in deployment:
            for resource in deployment['resources'].values():
                if resource.get('type') == 'user':
                    instance = resource.get('instance', {})
                    if 'password' in instance:
                        instance['hash'] = hash_SHA512(instance['password'])


