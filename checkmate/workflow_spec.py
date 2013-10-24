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
# pylint: disable=R0903

"""Creates spiff workflow spec for different actions
"""
import copy
import logging

from SpiffWorkflow import specs

from checkmate import exceptions

LOG = logging.getLogger(__name__)


class ProviderFactory:

    def __init__(self, deployment, environment):
        self.providers = {}

        non_deleted_resources = deployment.get_non_deleted_resources()
        for key, resource in non_deleted_resources.iteritems():
            if (key not in ['connections', 'keys'] and
                    'provider' in resource and
                    resource['provider'] not in self.providers.keys()):
                provider = environment.get_provider(resource['provider'])
                if not provider:
                    LOG.warn("Deployment %s resource %s has an unknown "
                             "provider: %s", deployment.get("id"), key,
                             resource.get("provider"))
                    continue
                self.providers[resource['provider']] = provider

    def get_provider(self, resource):
        assert "provider" in resource
        return self.providers[resource['provider']]

    def get_all_providers(self):
        return self.providers

class WorkflowSpec(specs.WorkflowSpec):
    """Workflow Spec related methods."""
    @staticmethod
    def create_take_offline_spec(context, deployment, **kwargs):
        """Creates the workflow spec for taking a resource offline
        :param deployment:
        :param resource_id:
        :param context:
        :return:
        """
        environment = deployment.environment()
        resources = deployment.get_non_deleted_resources()
        resource_id = kwargs.get('resource_id')
        resource = deployment['resources'].get(resource_id)
        wf_spec = WorkflowSpec(name="Take resource offline %s(%s)" % (
            deployment["id"], resource_id))
        for _, relation in resource.get('relations', {}).iteritems():
            if relation.get('source'):
                source_resource = resources[relation.get('source')]
                source_relation_key = "%s-%s" % (relation.get('name'),
                                                 resource_id)
                source_relation = source_resource['relations'].get(
                    source_relation_key)
                provider = environment.get_provider(
                    source_resource['provider'])
                tasks = provider.disable_connection_tasks(wf_spec,
                                                          deployment, context,
                                                          source_resource,
                                                          resource,
                                                          source_relation)
                if tasks:
                    wf_spec.start.connect(tasks.get('root'))

        if not wf_spec.start.outputs:
            noop = specs.Simple(wf_spec, "end")
            wf_spec.start.connect(noop)
        return wf_spec

    @staticmethod
    def create_bring_online_spec(context, deployment, **kwargs):
        """Creates the workflow spec for getting a resource online
        :param deployment:
        :param resource_id:
        :param context:
        :return:
        """
        resource_id = kwargs['resource_id']
        environment = deployment.environment()
        resources = deployment.get_non_deleted_resources()
        resource = deployment['resources'].get(resource_id)
        wf_spec = WorkflowSpec(name="Get resource %s in deployment %s online"
                                    % (resource_id, deployment["id"]))
        for _, relation in resource.get('relations', {}).iteritems():
            if relation.get('source'):
                source_resource = resources[relation.get('source')]
                source_relation_key = "%s-%s" % (relation.get('name'),
                                                 resource_id)
                source_relation = source_resource['relations'].get(
                    source_relation_key)
                provider = environment.get_provider(
                    source_resource['provider'])
                tasks = provider.enable_connection_tasks(wf_spec,
                                                         deployment,
                                                         context,
                                                         source_resource,
                                                         resource,
                                                         source_relation)
                if tasks:
                    wf_spec.start.connect(tasks.get('root'))

        if not wf_spec.start.outputs:
            noop = specs.Simple(wf_spec, "end")
            wf_spec.start.connect(noop)
        return wf_spec

    @staticmethod
    def create_delete_dep_wf_spec(deployment, context):
        """Creates a SpiffWorkflow spec for deleting a deployment
        :param deployment:
        :param context:
        :return: SpiffWorkflow.WorkflowSpec
        """
        LOG.info("Building workflow spec for deleting deployment '%s'",
                 deployment['id'])
        blueprint = deployment['blueprint']
        environment = deployment.environment()
        dep_id = deployment["id"]
        operation = deployment['operation']
        current_workflow_id = operation.get('workflow-id', dep_id)

        # Build a workflow spec (the spec is the design of the workflow)
        wf_spec = WorkflowSpec(name="Delete deployment %s(%s)" %
                                    (dep_id, blueprint['name']))

        if operation['status'] in ('COMPLETE', 'PAUSED'):
            root_task = wf_spec.start
        else:
            root_task = specs.Celery(
                wf_spec, 'Pause %s Workflow %s' % (operation['type'],
                                                   current_workflow_id),
                'checkmate.workflows.tasks.pause_workflow',
                call_args=[current_workflow_id],
                properties={'estimated_duration': 10})
            wf_spec.start.connect(root_task)

        factory = ProviderFactory(deployment, environment)
        all_providers = factory.get_all_providers()
        #LOG.warn("[Providers] %s", all_providers)
        #providers = {}
        #
        #non_deleted_resources = deployment.get_non_deleted_resources()
        #for key, resource in non_deleted_resources.iteritems():
        #    if (key not in ['connections', 'keys'] and 'provider' in
        #            resource and resource['provider'] not in provider_keys):
        #        provider = environment.get_provider(resource['provider'])
        #        if not provider:
        #            LOG.warn("Deployment %s resource %s has an unknown "
        #                     "provider: %s", dep_id, key,
        #                     resource.get("provider"))
        #            continue
        #        provider_keys.add(resource['provider'])
        #        providers[provider.key] = provider

        LOG.debug("Obtained providers from resources: %s",
                  ', '.join(factory.get_all_providers().keys()))

        for provider in all_providers.values():
            cleanup_result = provider.cleanup_environment(wf_spec,
                                                          deployment)
            # Wire up tasks if not wired in somewhere
            if cleanup_result and not cleanup_result['root'].inputs:
                wf_spec.start.connect(cleanup_result['root'])

        resources_to_del = deployment.get_non_deleted_resources().iteritems()
        for key, resource in resources_to_del:
            if (key not in ['connections', 'keys'] and
                    'provider' in resource and
                    'hosted_on' not in resource):
                provider = factory.get_provider(resource)

                host_del_tasks = []
                if resource.get("hosts"):
                    host_del_tasks = WorkflowSpec.get_host_delete_tasks(
                        resource, deployment, factory, wf_spec, context
                    )

                del_tasks = provider.delete_resource_tasks(wf_spec, context,
                                                           dep_id, resource,
                                                           key)
                if del_tasks:
                    tasks = del_tasks.get('root')
                    for host_del_task in host_del_tasks:
                        del_tasks['final'].connect(host_del_task)
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
    def get_host_delete_tasks(resource, deployment, factory, wf_spec,
                          context):
        hosts = resource.get("hosts", [])
        host_resources = [deployment.get_non_deleted_resources()[i] for i in
                          hosts]
        host_del_tasks = []
        for resource in host_resources:
            provider = factory.get_provider(resource)
            host_del_tasks.append(provider.delete_resource_tasks(
                                  wf_spec, context, deployment.get("id"),
                                  resource, resource["index"]))
        return host_del_tasks

    @staticmethod
    def create_reset_failed_resource_spec(context, deployment,
                                          task_to_reset, workflow_id):
        """Creates workflow spec for passed in failed resource and task
        :param context: request context
        :param deployment: deployment
        :param task_to_reset: failed task id
        :param workflow_id: workflow containing the task
        :return:
        """
        wf_spec = WorkflowSpec(name=('Reset failed resources in Deployment '
                                     '%s' % deployment['id']))
        environment = deployment.environment()
        context = copy.deepcopy(context)
        resource_key = task_to_reset.task_spec.get_property("resource")
        LOG.info("Building workflow spec for deleting resource %s "
                 "deployment %s", resource_key, deployment['id'])

        wait_for_errored_resource = specs.Celery(
            wf_spec,
            'Wait for resource %s to move to ERROR status' %
            resource_key,
            'checkmate.deployments.tasks.wait_for_resource_status',
            call_args=[
                deployment.get("id"),
                resource_key,
                "ERROR"
            ],
            defines=dict(
                resource=resource_key,
            ),
            properties={'estimated_duration': 10}
        )

        resource = deployment.get("resources").get(resource_key)
        provider = environment.get_provider(resource["provider"])
        delete_tasks = provider.delete_resource_tasks(wf_spec,
                                                      context,
                                                      deployment["id"],
                                                      resource,
                                                      resource_key)
        wait_for_deleted_resource = specs.Celery(
            wf_spec,
            'Wait for resource %s to move to DELETED status' %
            resource_key,
            'checkmate.deployments.tasks.wait_for_resource_status',
            call_args=[
                deployment.get("id"),
                resource_key,
                "DELETED"
            ],
            defines=dict(
                resource=resource_key,
            ),
            properties={'estimated_duration': 10}
        )

        reset_errored_resource_task = specs.Celery(
            wf_spec,
            'Copy errored resource %s to a new resource' % resource_key,
            'checkmate.deployments.tasks.reset_failed_resource_task',
            call_args=[
                deployment.get("id"),
                resource_key
            ],
            defines=dict(
                resource=resource_key,
            ),
            properties={'estimated_duration': 5}
        )

        reset_task_tree = specs.Celery(
            wf_spec,
            'Reset task %s in workflow %s' % (task_to_reset.id, workflow_id),
            'checkmate.workflows.tasks.reset_task_tree',
            call_args=[
                workflow_id,
                task_to_reset.id
            ],
            properties={'estimated_duration': 5}
        )

        wf_spec.start.connect(wait_for_errored_resource)
        if delete_tasks:
            tasks = delete_tasks.get('root')
            if isinstance(tasks, list):
                for task in tasks:
                    wait_for_errored_resource.connect(task)
            else:
                wait_for_errored_resource.connect(tasks)
        delete_tasks.get('final').connect(wait_for_deleted_resource)
        wait_for_deleted_resource.connect(reset_errored_resource_task)
        reset_errored_resource_task.connect(reset_task_tree)

        if not wf_spec.start.outputs:
            noop = specs.Simple(wf_spec, "end")
            wf_spec.start.connect(noop)

        return wf_spec

    @staticmethod
    def create_scale_up_spec(context, deployment):
        return WorkflowSpec.create_build_spec(context, deployment)

    @staticmethod
    def create_build_spec(context, deployment):
        """Creates a SpiffWorkflow spec for initial deployment of a Checkmate
        deployment

        :return: SpiffWorkflow.WorkflowSpec
        """
        LOG.info("Building workflow spec for deployment %s", deployment['id'])
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
        LOG.debug("Obtained providers from resources: %s",
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
                for _, relation in resource.get('relations', {}).iteritems():
                    if 'target' in relation:
                        if relation['target'] not in sorted_list:
                            if relation['target'] in stack:
                                error_message = ("Circular dependency in "
                                                 "resources between %s and "
                                                 "%s" % (resource_key,
                                                 relation['target']))
                                raise exceptions.CheckmateException(
                                    error_message,
                                    friendly_message=exceptions.BLUEPRINT_ERROR
                                )
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
        LOG.debug("Ordered resources: %s", '->'.join(sorted_resources))

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
                    hosted_resource = deployment['resources'][index]
                    relations = [r for r in
                                 hosted_resource['relations'].values()
                                 if (r.get('relation') == 'host'
                                     and r['target'] == key)]
                    if len(relations) > 1:
                        error_message = ("Multiple 'host' relations for "
                                         "resource '%s'" % key)
                        raise exceptions.CheckmateException(error_message)
                    relation = relations[0]
                    provider = providers[hosted_resource['provider']]
                    provider_result = provider.add_connection_tasks(
                        hosted_resource, index, relation, 'host', wf_spec,
                        deployment, context)
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

        for key, provider in providers.iteritems():
            cleanup_result = provider.cleanup_temp_files(wf_spec, deployment)
            # Wire up tasks if not wired in somewhere
            if cleanup_result and not cleanup_result['root'].inputs:
                wf_spec.start.connect(cleanup_result['root'])

        # Check that we have a at least one task. Workflow fails otherwise.
        if not wf_spec.start.outputs:
            noop = specs.Simple(wf_spec, "end")
            wf_spec.start.connect(noop)
        return wf_spec

    def find_task_specs(self, **kwargs):
        """Find tasks in the workflow with matching properties.

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
        """
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
    def create_scale_down_spec(context, deployment, **kwargs):
        """Create the workflow spec for deleting a node in a deployment
        :param deployment: The deployment to delete the node from
        :param resources_to_delete: Comma separated list of resource ids
        which need to be deleted
        :param context: RequestContext
        :return: Workflow spec for delete of passed in resources
        """
        resources_to_delete = kwargs['victim_list']
        LOG.debug("Creating workflow spec for deleting resources %s",
                  resources_to_delete)
        dep_id = deployment["id"]
        wf_spec = WorkflowSpec(name="Delete nodes %s for deployment %s)" %
                                    (",".join(resources_to_delete), dep_id))
        resources = deployment.get('resources')
        LOG.debug("Attempting to delete %s", resources_to_delete)

        for resource_key in resources_to_delete:
            wait_tasks = []
            resource = resources.get(resource_key)
            resource_ids_to_delete = [resource_key]

            #Process relations for resource
            WorkflowSpec._add_del_tasks_for_res_relatns(wf_spec,
                                                        deployment,
                                                        resource_key,
                                                        context)
            wait_tasks.extend(wf_spec.find_task_specs(resource=resource_key,
                                                      tag="delete_connection"))

            #Process host-relations for resource
            if 'hosted_on' in resource:
                resource_ids_to_delete.append(resource['hosted_on'])

            #Process resource to be deleted
            for resource_id_to_delete in resource_ids_to_delete:
                resource_to_delete = resources.get(resource_id_to_delete)
                provider_key = resource_to_delete.get("provider")
                environment = deployment.environment()
                provider = environment.get_provider(provider_key)
                del_tasks = provider.delete_resource_tasks(
                    wf_spec, context, dep_id, resource_to_delete,
                    resource_id_to_delete)
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
    def _add_del_tasks_for_res_relatns(wf_spec, deployment,
                                       resource_key, context):
        """Adds the delete task for a resource relation
        :param wf_spec: Workflow Spec to add the tasks to
        :param deployment: The deployment from which the resourced need to
        be deleted
        :param resource_key: The resource key of the resource to be deleted
        :param context: RequestContext
        :return:
        """
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
