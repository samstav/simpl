'''
Workflow Class and Helper Functions
'''
import copy
import logging
import uuid

from SpiffWorkflow import Workflow as SpiffWorkflow, Task
from SpiffWorkflow.specs import WorkflowSpec, Simple, Join, Merge, Celery
from SpiffWorkflow.storage import DictionarySerializer

from checkmate import utils
from checkmate.common import schema
from checkmate.classes import ExtensibleDict
from checkmate.db import get_driver
from checkmate.deployment import get_status
from checkmate.exceptions import (
    BLUEPRINT_ERROR,
    CheckmateException,
    CheckmateRetriableException,
    CheckmateResumableException,
    CheckmateUserException,
    UNEXPECTED_ERROR,
)

DB = get_driver()
LOG = logging.getLogger(__name__)


def create_workflow(spec, deployment, context, driver=DB, workflow_id=None):
    if not workflow_id:
        workflow_id = utils.get_id(context.simulation)
    spiff_wf = init_spiff_workflow(spec, deployment, context)
    spiff_wf.attributes['id'] = workflow_id
    serializer = DictionarySerializer()
    workflow = spiff_wf.serialize(serializer)
    workflow['id'] = workflow_id
    body, secrets = utils.extract_sensitive_data(workflow)
    driver.save_workflow(workflow_id, body, secrets, tenant_id=deployment[
        'tenantId'])
    return spiff_wf


def update_workflow_status(workflow, tenant_id=None):
    total = len(workflow.get_tasks(state=Task.ANY_MASK))
    completed = len(workflow.get_tasks(state=Task.COMPLETED))
    if total is not None and total > 0:
        progress = int(100 * completed / total)
    else:
        progress = 100
    workflow.attributes['progress'] = progress
    workflow.attributes['total'] = total
    workflow.attributes['completed'] = completed
    errors = get_errors(workflow, tenant_id)

    if workflow.is_completed():
        workflow.attributes['status'] = "COMPLETE"
    elif workflow.attributes['completed'] == 0:
        workflow.attributes['status'] = "NEW"
    elif errors:
        workflow.attributes['status'] = "FAILED"
    else:
        workflow.attributes['status'] = "IN PROGRESS"


def reset_task_tree(task):
    '''
    For a given task, would traverse through the parents of the task, changing
    the state of each of the task(s) to FUTURE, until the 'root' task is found.
    For this 'root' task, the state is changed to WAITING.

    :param task: Task which would have to be reset.
    :return:
    '''
    while True:
        if isinstance(task.task_spec, Celery):
            task.task_spec._clear_celery_task_data(task)
        task._state = Task.FUTURE

        tags = task.get_property('task_tags', [])
        parent_task = task.parent

        if 'root' in tags or not parent_task:
            task._state = Task.WAITING
            break
        task = parent_task


def update_workflow(d_wf, tenant_id, status=None, driver=DB, workflow_id=None):
    '''
    Updates the workflow status, and saves the workflow. Worflow status
    can be overriden by providing a custom value for the 'status' parameter.

    :param d_wf: De-serialized workflow
    :param tenant_id: Tenant Id
    :param status: A custom value that can be passed, which would be set
        as the workflow status. If this value is not provided, the workflow
        status would be set with regard to the current statuses of the tasks
        associated with the workflow.
    :param driver: DB driver
    :return:
    '''

    update_workflow_status(d_wf, tenant_id=tenant_id)
    if status:
        d_wf.attributes['status'] = status

    serializer = DictionarySerializer()
    updated = d_wf.serialize(serializer)
    body, secrets = utils.extract_sensitive_data(updated)
    body['tenantId'] = tenant_id
    body['id'] = workflow_id
    driver.save_workflow(workflow_id, body, secrets=secrets)


def get_errors(wf_dict, tenant_id):
    '''
    Traverses through the workflow-tasks, and collects errors information from
    all the failed tasks
    :param wf_dict: The workflow to get the tasks from
    :return: List of error information
    '''
    results = []
    tasks = wf_dict.get_tasks()
    while tasks:
        task = tasks.pop(0)
        if is_failed_task(task):
            task_state = task._get_internal_attribute("task_state")
            info = task_state.get("info")
            traceback = task_state.get("traceback")
            try:
                exception = eval(info)
                if type(exception) is CheckmateRetriableException:
                    results.append({
                        "error-type": exception.error_type,
                        "error-message": exception.error_message,
                        "error-help": exception.error_help,
                        "retriable": True,
                        "task-id": task.id,
                        "retry-link":
                        "/%s/workflows/%s/tasks/%s/+reset-task-tree" % (
                        tenant_id, wf_dict.attributes["id"], task.id),
                        "error-traceback": traceback,
                        "friendly-message": str(exception.friendly_message)
                    })
                elif type(exception) is CheckmateResumableException:
                    results.append({
                        "error-type": exception.error_type,
                        "error-message": exception.error_message,
                        "error-help": exception.error_help,
                        "resumable": True,
                        "task-id": task.id,
                        "resume-link": "/%s/workflows/%s/tasks/%s/+execute" % (
                            tenant_id,
                            wf_dict.attributes["id"],
                            task.id),
                        "error-traceback": traceback,
                        "friendly-message": exception.friendly_message
                    })
                elif type(exception) is CheckmateUserException:
                    results.append({
                        "error-type": exception.error_type,
                        "error-message": exception.error_message,
                        "error-help": exception.error_help,
                        "task-id": task.id,
                        "error-traceback": traceback,
                        "friendly-message": exception.friendly_message
                    })
                elif isinstance(exception, Exception):
                    results.append({
                        "error-type": utils.get_class_name(exception),
                        "error-message": str(exception),
                        "error-traceback": traceback
                    })
            except Exception as exp:
                results.append({
                    "error-message": info,
                    "error-traceback": traceback
                })
    return results


def is_failed_task(task):
    '''
    Checks whether a task has failed by checking the task_state dict in
    internal attribs. The format of task_state is
    task_state: {
        'state': 'FAILURE',
        'traceback': 'Has the stacktrace of the exception',
        'info': 'info about the exception',
    }
    :param task:
    :return:
    '''
    task_state = task._get_internal_attribute("task_state")
    return task_state and task_state.get("state") == "FAILURE"


def get_SpiffWorkflow_status(workflow):
    """
    Returns the subtree as a string for debugging.

    :param workflow: a SpiffWorkflow Workflow
    @rtype:  dict
    @return: The debug information.
    """
    def get_task_status(task, output):
        """Recursively fills task data into dict"""
        my_dict = {}
        my_dict['id'] = task.id
        my_dict['threadId'] = task.thread_id
        my_dict['state'] = task.get_state_name()
        output[task.get_name()] = my_dict
        for child in task.children:
            get_task_status(child, my_dict)

    result = {}
    task = workflow.task_tree
    get_task_status(task, result)
    return result


def create_delete_deployment_workflow_spec(deployment, context):
    """Creates a SpiffWorkflow spec for deleting a deployment

    :returns: SpiffWorkflow.WorkflowSpec"""
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
        root_task = Celery(wf_spec, 'Pause %s Workflow %s' %
                                    (operation['type'], existing_workflow_id),
                           'checkmate.workflows.tasks.pause_workflow',
                           call_args=[dep_id],
                           properties={'estimated_duration': 10})
        wf_spec.start.connect(root_task)

    for key, resource in deployment.get('resources', {}).iteritems():
        if key not in ['connections', 'keys'] and 'provider' in resource:
            provider = environment.get_provider(resource.get('provider'))
            if not provider:
                LOG.warn("Deployment %s resource %s has an unknown provider:"
                         " %s", dep_id, key, resource.get("provider"))
                continue
            del_tasks = provider.delete_resource_tasks(wf_spec, context,
                                                       dep_id, resource, key)
            if del_tasks:
                tasks = del_tasks.get('root')
                if isinstance(tasks, list):
                    for task in tasks:
                        root_task.connect(task)
                else:
                    root_task.connect(tasks)

    # Check that we have a at least one task. Workflow fails otherwise.
    if not wf_spec.start.outputs:
        noop = Simple(wf_spec, "end")
        wf_spec.start.connect(noop)
    return wf_spec


def init_spiff_workflow(spiff_wf_spec, deployment, context):
    """Creates a SpiffWorkflow for initial deployment of a Checkmate deployment

    :returns: SpiffWorkflow.Workflow"""
    LOG.info("Creating workflow for deployment '%s'", deployment['id'])
    results = spiff_wf_spec.validate()
    if results:
        serializer = DictionarySerializer()
        serialized_spec = spiff_wf_spec.serialize(serializer)
        error_message = '. '.join(results)
        LOG.debug("Errors in Workflow: %s", error_message,
                  extra=dict(data=serialized_spec))
        raise CheckmateUserException(error_message, utils.get_class_name(
            CheckmateException), UNEXPECTED_ERROR, '')

    workflow = SpiffWorkflow(spiff_wf_spec)
    #Pass in the initial deployemnt dict (task 2 is the Start task)
    runtime_context = copy.copy(deployment.settings())
    runtime_context['token'] = context.auth_token
    runtime_context.update(format(deployment.get_indexed_resources()))
    workflow.get_task(2).set_attribute(**runtime_context)

    # Calculate estimated_duration
    root = workflow.task_tree
    root._set_internal_attribute(estimated_completed_in=0)
    tasks = root.children[:]
    overall = 0
    while tasks:
        task = tasks.pop(0)
        tasks.extend(task.children)
        expect_to_take = (task.parent._get_internal_attribute(
                          'estimated_completed_in') +
                          task.task_spec.get_property('estimated_duration',
                                                      0))
        if expect_to_take > overall:
            overall = expect_to_take
        task._set_internal_attribute(estimated_completed_in=expect_to_take)
    LOG.debug("Workflow %s estimated duration: %s", deployment['id'],
              overall)
    workflow.attributes['estimated_duration'] = overall
    workflow.attributes['deploymentId'] = deployment['id']
    update_workflow_status(workflow, tenant_id=deployment.get('tenantId'))

    return workflow


def format(resources):
    formatted_resources = {}
    for resource_key, resource_value in resources.iteritems():
        formatted_resources.update({("instance:%s" % resource_key):
                                    resource_value.get("instance", {})})
    return formatted_resources


def create_workflow_spec_deploy(deployment, context):
    """Creates a SpiffWorkflow spec for initial deployment of a Checkmate
    deployment

    :returns: SpiffWorkflow.WorkflowSpec"""
    LOG.info("Building workflow spec for deployment '%s'" % deployment['id'])
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
    for key, resource in deployment.get('resources', {}).iteritems():
        if key not in ['connections', 'keys'] and 'provider' in resource and\
                resource['provider'] not in provider_keys:
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
                            error_message = "Circular dependency in resources between %s " \
                                      "and %s" % (
                                      resource_key, relation['target'])
                            raise CheckmateUserException(
                                error_message,utils.get_class_name(
                                    CheckmateException), BLUEPRINT_ERROR, '')
                        stack.append(resource_key)
                        recursive_add_host(sorted_resources,
                                           relation['target'], resources, stack)
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
        provider_result = provider.add_resource_tasks(resource, key, wf_spec,
                                                      deployment, context)

        if provider_result and provider_result.get('root') and \
                not provider_result['root'].inputs:
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
                    error_message = ("Multiple 'host' relations for resource "
                                     "'%s'" % key)
                    raise CheckmateUserException(error_message,
                                                 utils.get_class_name(
                                                     CheckmateException),
                                                 UNEXPECTED_ERROR, '')
                relation = relations[0]
                provider = providers[hr['provider']]
                provider_result = provider.add_connection_tasks(hr, index,
                                                                relation,
                                                                'host',
                                                                wf_spec,
                                                                deployment,
                                                                context)
                if provider_result and provider_result.get('root') and \
                        not provider_result['root'].inputs:
                    # Attach unattached tasks
                    LOG.debug("Attaching '%s' to 'Start'",
                              provider_result['root'].name)
                    wf_spec.start.connect(provider_result['root'])

    # Do relations
    for key, resource in deployment.get('resources', {}).iteritems():
        if 'relations' in resource:
            for name, relation in resource['relations'].iteritems():
                # Process where this is a source (host relations done above)
                if 'target' in relation and name != 'host' and (relation[
                        'target'] in new_and_planned_resources.keys() or key
                        in new_and_planned_resources.keys()):
                    provider = providers[resource['provider']]
                    provider_result = provider.add_connection_tasks(resource,
                                                                    key,
                                                                    relation,
                                                                    name,
                                                                    wf_spec,
                                                                    deployment,
                                                                    context)
                    if provider_result and provider_result.get('root') and \
                            not provider_result['root'].inputs:
                        # Attach unattached tasks
                        LOG.debug("Attaching '%s' to 'Start'",
                                  provider_result['root'].name)
                        wf_spec.start.connect(provider_result['root'])

    # Check that we have a at least one task. Workflow fails otherwise.
    if not wf_spec.start.outputs:
        noop = Simple(wf_spec, "end")
        wf_spec.start.connect(noop)
    return wf_spec


def wait_for(wf_spec, task, wait_list, name=None, **kwargs):
    """Wires up tasks so that 'task' will wait for all tasks in 'wait_list' to
    complete before proceeding.

    If wait_list has more than one task, we'll use a Merge task. If wait_list
    only contains one task, we'll just wire them up directly. If task input is
    already a subclass of join, we'll tap into that.

    :param wf_spec: the workflow spec being worked on
    :param task: the task that will be waiting
    :param wait_list: a list of tasks to wait on
    :param name: the name of the merge task (autogenerated if not supplied)
    :param kwargs: all additional kwargs are passed to Merge.__init__
    :returns: the final task or the task itself if no waiting needs to happen
    """
    if wait_list:
        wait_set = list(set(wait_list))  # remove duplicates
        join_task = None
        if issubclass(task.__class__, Join):
            # It's a join. Just add the inputs
            for tsk in wait_set:
                if tsk not in task.ancestors():
                    tsk.connect(task)
            return task

        if task.inputs:
            # Move inputs to join
            for input_spec in task.inputs:
                # If input_spec is a Join, keep it as an input and use it
                if isinstance(input_spec, Join):
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
                join_task = Merge(wf_spec, name, **kwargs)
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


def find_tasks(wf, state=Task.ANY_MASK, **kwargs):
    tasks = []
    filtered_tasks = wf.get_tasks(state=state)
    for task in filtered_tasks:
        match = True
        if kwargs:
            for key, value in kwargs.iteritems():
                if key == 'tag':
                    if value is not None and value not in task.get_property(
                            "task_tags", []):
                        match = False
                        break
        if match:
            tasks.append(task)
    return tasks


class Workflow(ExtensibleDict):
    """A workflow.

    Acts like a dict. Includes validation, setting logic and other useful
    methods.
    Handles persistence, serialization, and managing additional attributes like
    id, tenantId, etc... which are not part of the normal SpiffWorkflow
    workflow
    """
    def __init__(self, *args, **kwargs):
        ExtensibleDict.__init__(self, *args, **kwargs)
        self.id = self.get('id', uuid.uuid4().hex)
        # Note: workflowId = deploymentId until deploymentId started getting
        # set in workflow.attributes['deloymentId']

    @classmethod
    def inspect(cls, obj):
        errors = schema.validate(obj, schema.WORKFLOW_SCHEMA)
        errors.extend(schema.validate_inputs(obj))
        return errors
