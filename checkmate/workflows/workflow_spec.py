import logging

from SpiffWorkflow import specs

from checkmate import exceptions
from checkmate import utils

LOG = logging.getLogger(__name__)


class WorkflowSpec(specs.WorkflowSpec):
    @staticmethod
    def create_delete_deployment_workflow_spec(deployment, context):
        '''Creates a SpiffWorkflow spec for deleting a deployment
        :param deployment:
        :param context:
        :return: SpiffWorkflow.WorkflowSpec
        '''
        LOG.info("Building workflow spec for deleting deployment '%s'"
                 % deployment['id'])
        blueprint = deployment['blueprint']
        environment = deployment.environment()
        dep_id = deployment["id"]
        operation = deployment['operation']
        existing_workflow_id = operation.get('workflow-id', dep_id)

        # Build a workflow spec (the spec is the design of the workflow)
        wf_spec = WorkflowSpec(name="Delete deployment %s(%s)" %
                                    (dep_id, blueprint['name']))

        if operation['status'] in ('COMPLETE', 'PAUSED'):
            root_task = wf_spec.start
        else:
            root_task = specs.Celery(
                wf_spec, 'Pause %s Workflow %s' % (operation['type'],
                                                   existing_workflow_id),
                'checkmate.workflows.tasks.pause_workflow',
                call_args=[dep_id],
                properties={'estimated_duration': 10})
            wf_spec.start.connect(root_task)

        for key, resource \
                in deployment.get_non_deleted_resources().iteritems():
            if key not in ['connections', 'keys'] and 'provider' in resource:
                provider = environment.get_provider(resource.get('provider'))
                if not provider:
                    LOG.warn("Deployment %s resource %s has an unknown "
                             "provider: %s", dep_id, key,
                             resource.get("provider"))
                    continue
                del_tasks = provider.delete_resource_tasks(wf_spec, context,
                                                           dep_id, resource,
                                                           key)
                if del_tasks:
                    tasks = del_tasks.get('root')
                    if isinstance(tasks, list):
                        for task in tasks:
                            root_task.connect(task)
                    else:
                        root_task.connect(tasks)

        # Check that we have a at least one task. Workflow fails otherwise.
        if not wf_spec.start.outputs:
            noop = specs.Simple(wf_spec, "end")
            wf_spec.start.connect(noop)
        return wf_spec

    @staticmethod
    def create_workflow_spec_deploy(deployment, context):
        """Creates a SpiffWorkflow spec for initial deployment of a Checkmate
        deployment

        :return: SpiffWorkflow.WorkflowSpec
        """
        LOG.info("Building workflow spec for deployment %s" % deployment['id'])
        blueprint = deployment['blueprint']
        environment = deployment.environment()
        new_and_planned_resources = deployment.get_new_and_planned_resources()

        # Build a workflow spec (the spec is the design of the workflow)
        wf_spec = WorkflowSpec(name="Deploy '%s' Workflow" % blueprint['name'])

        #
        # Create the tasks that make the async calls
        #

        # Get list of providers
        providers = {}  # Unique providers used in this deployment

        provider_keys = set()
        non_deleted_resources = deployment.get_non_deleted_resources()
        for key, resource in non_deleted_resources.iteritems():
            if (key not in ['connections', 'keys'] and 'provider' in
                    resource and resource['provider'] not in provider_keys):
                provider_keys.add(resource['provider'])
        LOG.debug("Obtained providers from resources: %s" %
                  ', '.join(provider_keys))

        for key in provider_keys:
            provider = environment.get_provider(key)
            providers[provider.key] = provider
            prep_result = provider.prep_environment(wf_spec, deployment,
                                                    context)
            # Wire up tasks if not wired in somewhere
            if prep_result and not prep_result['root'].inputs:
                wf_spec.start.connect(prep_result['root'])

        sorted_resources = []

        def recursive_add_host(sorted_list, resource_key, resources, stack):
            if resource_key in new_and_planned_resources.keys():
                resource = resources[resource_key]
                for key, relation in resource.get('relations', {}).iteritems():
                    if 'target' in relation:
                        if relation['target'] not in sorted_list:
                            if relation['target'] in stack:
                                error_message = ("Circular dependency in "
                                                 "resources between %s and "
                                                 "%s" % (resource_key,
                                                 relation['target']))
                                raise exceptions.CheckmateUserException(
                                    error_message, utils.get_class_name(
                                        exceptions.CheckmateException),
                                    exceptions.BLUEPRINT_ERROR, '')
                            stack.append(resource_key)
                            recursive_add_host(sorted_resources,
                                               relation['target'], resources,
                                               stack)
                if resource_key not in sorted_list:
                        sorted_list.append(resource_key)
        for key, resource in new_and_planned_resources.iteritems():
            if key not in ['connections', 'keys'] and 'provider' in resource:
                recursive_add_host(sorted_resources, key,
                                   deployment.get('resources'),
                                   [])
        LOG.debug("Ordered resources: %s" % '->'.join(sorted_resources))

        # Do resources
        for key in sorted_resources:
            resource = deployment['resources'][key]
            provider = providers[resource['provider']]
            provider_result = provider.add_resource_tasks(resource, key,
                                                          wf_spec,
                                                          deployment, context)

            if (provider_result and provider_result.get('root') and not
                    provider_result['root'].inputs):
                # Attach unattached tasks
                wf_spec.start.connect(provider_result['root'])
            # Process hosting relationship before the hosted resource
            if 'hosts' in resource:
                for index in resource['hosts']:
                    hr = deployment['resources'][index]
                    relations = [r for r in hr['relations'].values()
                                 if (r.get('relation') == 'host'
                                     and r['target'] == key)]
                    if len(relations) > 1:
                        error_message = ("Multiple 'host' relations for "
                                         "resource '%s'" % key)
                        raise exceptions.CheckmateUserException(
                            error_message, utils.get_class_name(
                                exceptions.CheckmateException),
                            exceptions.UNEXPECTED_ERROR, '')
                    relation = relations[0]
                    provider = providers[hr['provider']]
                    provider_result = provider.add_connection_tasks(hr, index,
                                                                    relation,
                                                                    'host',
                                                                    wf_spec,
                                                                    deployment,
                                                                    context)
                    if (provider_result and provider_result.get('root') and
                            not provider_result['root'].inputs):
                        # Attach unattached tasks
                        LOG.debug("Attaching '%s' to 'Start'",
                                  provider_result['root'].name)
                        wf_spec.start.connect(provider_result['root'])

        # Do relations
        for key, resource in non_deleted_resources.iteritems():
            if 'relations' in resource:
                for name, relation in resource['relations'].iteritems():
                    # Process where this is a source (host relations done
                    # above)
                    if ('target' in relation
                        and name != 'host'
                        and relation['target'] in non_deleted_resources
                        and (relation['target'] in
                        new_and_planned_resources.keys()
                             or key in new_and_planned_resources.keys())):
                        provider = providers[resource['provider']]
                        provider_result = provider.add_connection_tasks(
                            resource, key, relation, name, wf_spec,
                            deployment, context)
                        if (provider_result and provider_result.get('root')
                                and not provider_result['root'].inputs):
                            # Attach unattached tasks
                            LOG.debug("Attaching '%s' to 'Start'",
                                      provider_result['root'].name)
                            wf_spec.start.connect(provider_result['root'])

        # Check that we have a at least one task. Workflow fails otherwise.
        if not wf_spec.start.outputs:
            noop = specs.Simple(wf_spec, "end")
            wf_spec.start.connect(noop)
        return wf_spec

    def find_task_specs(self, **kwargs):
        '''Find tasks in the workflow with matching properties.

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        :param kwargs: properties to match (all must match)

        Note: 'tag' is a special case where the tag only needs to exist in
              the task_tags property. To match all tags, match against the
              'task_tags' property

        Example kwargs:
            relation: the ID of the relation we are looking for
            resource: the ID of the resource we are looking for
            provider: the key of the provider we are looking for
            tag: the tag for the task (root, final, create, etc..)
        '''
        tasks = []
        for task in self.task_specs.values():
            match = True
            if kwargs:
                for key, value in kwargs.iteritems():
                    if key == 'tag':
                        if value is not None and value not in\
                                (task.get_property('task_tags', []) or []):
                            match = False
                            break
                    elif value is not None and task.get_property(key) != value:
                        match = False
                        break

                    # Don't match if the task is tied to a relation and no
                    # relation key was provided
                    if 'relation' not in kwargs and \
                            task.get_property('relation'):
                        match = False
                        break
            if match:
                tasks.append(task)
        if not tasks:
            LOG.debug("No tasks found in find_tasks for %s", ', '.join(
                      ['%s=%s' % (k, v) for k, v in kwargs.iteritems() or {}]))
        return tasks

    def wait_for(self, task, wait_list, name=None, **kwargs):
        """Wires up tasks so that 'task' will wait for all tasks in 'wait_list'
        to complete before proceeding.

        If wait_list has more than one task, we'll use a Merge task. If
        wait_list only contains one task, we'll just wire them up directly.
        If task input is already a subclass of join, we'll tap into that.

        :param wf_spec: the workflow spec being worked on
        :param task: the task that will be waiting
        :param wait_list: a list of tasks to wait on
        :param name: the name of the merge task (autogenerated if not supplied)
        :param kwargs: all additional kwargs are passed to Merge.__init__
        :returns: the final task or the task itself if no waiting needs to
        happen
        """
        if wait_list:
            wait_set = list(set(wait_list))  # remove duplicates
            join_task = None
            if issubclass(task.__class__, specs.Join):
                # It's a join. Just add the inputs
                for tsk in wait_set:
                    if tsk not in task.ancestors():
                        tsk.connect(task)
                return task

            if task.inputs:
                # Move inputs to join
                for input_spec in task.inputs:
                    # If input_spec is a Join, keep it as an input and use it
                    if isinstance(input_spec, specs.Join):
                        if join_task:
                            LOG.warning("Task %s seems to have multiple Join "
                                        "inputs", task.name)
                        else:
                            LOG.debug("Using existing Join task %s",
                                      input_spec.name)
                            join_task = input_spec
                            continue
                    if input_spec not in wait_set:
                        wait_set.append(input_spec)
                    # remove it from the other tasks outputs
                    input_spec.outputs.remove(task)
                if join_task:
                    task.inputs = [join_task]
                else:
                    task.inputs = []

            if len(wait_set) > 1:
                if not join_task:
                    # Create a new Merge task since it doesn't exist
                    if not name:
                        ids = [str(t.id) for t in wait_set]
                        ids.sort()
                        name = "After %s run %s" % (",".join(ids), task.id)
                    join_task = specs.Merge(self, name, **kwargs)
                if task not in join_task.outputs:
                    task.follow(join_task)
                for tsk in wait_set:
                    if tsk not in join_task.ancestors():
                        tsk.connect(join_task)
                return join_task
            elif join_task:
                wait_set[0].connect(join_task)
                return join_task
            else:
                task.follow(wait_set[0])
                return wait_set[0]
        else:
            return task

    @staticmethod
    def create_delete_node_spec(deployment, resources_to_delete, context):
        LOG.debug("Creating workflow spec for deleting resources %s",
                  resources_to_delete)
        blueprint = deployment['blueprint']
        dep_id = deployment["id"]
        wf_spec = WorkflowSpec(name="Delete resources %s for deployment %s)" %
                                    (dep_id, blueprint['name']))
        resources = deployment.get('resources')
        LOG.debug("[Delete Nodes] Attempting to delete %s",
                  resources_to_delete)
        LOG.debug("[Delete Nodes] Deployment resources %s",
                  resources)

        for resource_key in resources_to_delete:
            wait_tasks = []
            LOG.debug("[Delete Nodes] Resource Key %s", resource_key)
            resource = resources.get(resource_key)
            LOG.debug("[Delete Nodes] Resource from Deployment %s", resource)
            #Process host-relations for resource
            if 'hosts' in resource:
                for host in resource['hosts']:
                    WorkflowSpec._add_delete_tasks_for_resource_relation(
                        wf_spec, deployment, host, context)
                    wait_tasks.extend(wf_spec.find_task_specs(
                        resource=host, tag="delete_connection"))

            #Process relations for resource
            WorkflowSpec._add_delete_tasks_for_resource_relation(wf_spec,
                                                                 deployment,
                                                                 resource_key,
                                                                 context)
            wait_tasks.extend(wf_spec.find_task_specs(resource=resource_key,
                                                      tag="delete_connection"))

            #Process resource to be deleted
            provider_key = resource.get("provider")
            environment = deployment.environment()
            provider = environment.get_provider(provider_key)
            del_tasks = provider.delete_resource_tasks(wf_spec, context,
                                                       dep_id,
                                                       resource,
                                                       resource_key)
            if del_tasks:
                tasks = del_tasks.get('root')
                if wait_tasks:
                    if isinstance(tasks, list) and tasks:
                        merge_task = wf_spec.wait_for(
                            tasks[0], wait_tasks,
                            name="Wait before deleting resource %s" %
                                 resource_key)
                        for task in tasks[1:]:
                            merge_task.connect(task)
                    else:
                        wf_spec.wait_for(
                            tasks, wait_tasks,
                            name="Wait before deleting resource %s" %
                                 resource_key)
                else:
                    if isinstance(tasks, list) and tasks:
                        for task in tasks:
                            wf_spec.start.connect(task)
                    else:
                        wf_spec.start.connect(tasks)
        return wf_spec

    @staticmethod
    def _add_delete_tasks_for_resource_relation(wf_spec, deployment,
                                                resource_key, context):
        resources = deployment['resources']
        resource = resources[resource_key]
        if resource["status"] == "DELETED":
            return
        if 'relations' in resource:
            environment = deployment.environment()
            for relation_key, relation in resource['relations'].iteritems():
                if relation_key != 'host' and 'source' in relation:
                    source_resource = resources.get(relation["source"])
                    if source_resource["status"] == "DELETED":
                        continue
                    source_provider_key = source_resource["provider"]
                    source_provider = environment.get_provider(
                        source_provider_key)
                    source_provider.add_delete_connection_tasks(
                        wf_spec, context, deployment, source_resource,
                        resource)
