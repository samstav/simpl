'''
Workflow Class and Helper Functions
'''
import copy
import logging
import uuid

from celery.exceptions import MaxRetriesExceededError
from SpiffWorkflow import Workflow as SpiffWorkflow, Task
from SpiffWorkflow.specs import Celery
from SpiffWorkflow.storage import DictionarySerializer

from checkmate.common import schema
from checkmate.classes import ExtensibleDict
from checkmate.db import get_driver
from checkmate.exceptions import CheckmateException
from checkmate.exceptions import CheckmateResetTaskTreeException
from checkmate.exceptions import CheckmateResumableException
from checkmate.exceptions import CheckmateRetriableException
from checkmate.exceptions import CheckmateUserException
from checkmate.exceptions import UNEXPECTED_ERROR
from checkmate import utils

DB = get_driver()
LOG = logging.getLogger(__name__)


def create_workflow(spec, deployment, context, driver=DB, workflow_id=None,
                    wf_type="BUILD"):
    '''Creates a workflow for the passes in spec and deployment

    :param spec: WorkflowSpec to use for creating the workflow
    :param deployment: deployment to create the workflow for
    :param context: request context
    :param driver: database driver
    :param workflow_id: id of the workflow to be created
    :param wf_type: type of the workflow to be created
    :return:
    '''
    if not workflow_id:
        workflow_id = utils.get_id(context.simulation)
    spiff_wf = init_spiff_workflow(spec, deployment, context, workflow_id,
                                   wf_type)
    serializer = DictionarySerializer()
    workflow = spiff_wf.serialize(serializer)
    workflow['id'] = workflow_id
    body, secrets = utils.extract_sensitive_data(workflow)
    driver.save_workflow(workflow_id, body, secrets, tenant_id=deployment[
        'tenantId'])
    return spiff_wf


def get_number_of_errors(d_wf):
    '''Gets the number of tasks in error for a workflow
    :param d_wf: spiff workflow to get the errors from
    :return: number of tasks in error
    '''
    tasks = d_wf.get_tasks()
    count = 0
    while tasks:
        task = tasks.pop(0)
        if is_failed_task(task):
            count += 1
    return count


def update_workflow_status(workflow):
    '''Update the status, total, completed and errored tasks in a workflow

    :param workflow: workflow to be updated
    :return:
    '''
    workflow_state = {
        'total': len(workflow.get_tasks(state=Task.ANY_MASK)),
        'completed': len(workflow.get_tasks(state=Task.COMPLETED)),
        'errored': get_number_of_errors(workflow)
    }
    if workflow_state['total'] is not None and workflow_state['total'] > 0:
        workflow_state['progress'] = int(100 * workflow_state['completed'] /
                                         workflow_state['total'])
    else:
        workflow_state['progress'] = 100
    workflow.attributes['progress'] = workflow_state['progress']
    workflow.attributes['total'] = workflow_state['total']
    workflow.attributes['completed'] = workflow_state['completed']
    workflow.attributes['errored'] = workflow_state['errored']

    if workflow.is_completed():
        workflow.attributes['status'] = "COMPLETE"
    elif workflow_state['completed'] == 0:
        workflow.attributes['status'] = "NEW"
    elif workflow_state['errored'] > 0:
        workflow.attributes['status'] = "ERROR"
    else:
        workflow.attributes['status'] = "IN PROGRESS"
    return workflow_state


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
            task._state = Task.FUTURE
            task.task_spec._update_state(task)
            break
        task = parent_task


def update_workflow(d_wf, tenant_id, status=None, driver=DB, workflow_id=None):
    '''Updates the workflow status, and saves the workflow. Worflow status
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

    update_workflow_status(d_wf)
    if status:
        d_wf.attributes['status'] = status

    serializer = DictionarySerializer()
    updated = d_wf.serialize(serializer)
    body, secrets = utils.extract_sensitive_data(updated)
    body['tenantId'] = tenant_id
    body['id'] = workflow_id
    driver.save_workflow(workflow_id, body, secrets=secrets)


def reset_failed_tasks(d_wf):
    '''Traverses through all the workflow tasks and searches for reset task
    tree exception. If found the task tree is reset

    :param d_wf: Workflow to traverse
    :return:
    '''
    tasks = d_wf.get_tasks()
    while tasks:
        task = tasks.pop(0)
        if is_failed_task(task):
            task_state = task._get_internal_attribute("task_state")
            info = task_state.get("info")
            try:
                exception = eval(info)
                if (type(exception) is
                        CheckmateResetTaskTreeException):
                    reset_task_tree(task)
            except Exception:
                LOG.error("There was a exception while resetting the task "
                          "tree for task %s in deployment %s", task.id,
                          d_wf.attributes["deploymentId"])


def convert_exc_to_dict(exception, task, tenant_id, workflow_id, traceback):
    '''Converts a exception to a dictionary
    :param exception: exception to convert
    :param task: task that raised the exception
    :param tenant_id: tenant_id
    :param workflow_id: workflow id
    :param traceback: traceback of the exception
    :return: the dictionary of the exception
    '''
    exc_dict = {}
    if type(exception) is CheckmateRetriableException:
        exc_dict = {
            "error-type": exception.error_type,
            "error-message": exception.error_message,
            "error-help": exception.error_help,
            "retriable": True,
            "task-id": task.id,
            "retry-link":
                "/%s/workflows/%s/tasks/%s/+reset-task-tree" % (
                    tenant_id, workflow_id, task.id),
            "error-traceback": traceback,
            "friendly-message": str(exception.friendly_message)
        }
    elif type(exception) is CheckmateResumableException:
        exc_dict = {
            "error-type": exception.error_type,
            "error-message": exception.error_message,
            "error-help": exception.error_help,
            "resumable": True,
            "task-id": task.id,
            "resume-link": "/%s/workflows/%s/tasks/%s/+execute" % (
                tenant_id,
                workflow_id,
                task.id),
            "error-traceback": traceback,
            "friendly-message": exception.friendly_message
        }
    elif type(exception) is CheckmateUserException:
        exc_dict = {
            "error-type": exception.error_type,
            "error-message": exception.error_message,
            "error-help": exception.error_help,
            "task-id": task.id,
            "error-traceback": traceback,
            "friendly-message": exception.friendly_message
        }
    elif type(exception) is MaxRetriesExceededError:
        exc_dict = {
            "error-message": "The maximum amount of permissible "
                             "retries for workflow %s has elapsed."
                             " Please re-execute the workflow" %
                             workflow_id,
            "error-help": "",
            "error-type": "MaxRetriesExceededError",
            "retriable": True,
            "retry-link": "%s/workflows/%s/+execute" % (
                tenant_id, workflow_id),
            "friendly-message": "There was a timeout while "
                                "executing the workflow"
        }
    elif isinstance(exception, Exception):
        exc_dict = {
            "error-type": utils.get_class_name(exception),
            "error-message": str(exception),
            "error-traceback": traceback
        }
    return exc_dict


def get_errors(wf_dict, tenant_id):
    '''Traverses through the workflow-tasks, and collects errors information
    from all the failed tasks
    :param wf_dict: The workflow to get the tasks from
    :return: List of error information
    '''
    results = []
    tasks = wf_dict.get_tasks()
    workflow_id = wf_dict.get_attribute('id')

    while tasks:
        task = tasks.pop(0)
        if is_failed_task(task):
            task_state = task._get_internal_attribute("task_state")
            info = task_state.get("info")
            traceback = task_state.get("traceback")
            try:
                exception = eval(info)
                results.append(convert_exc_to_dict(exception,
                                                   task,
                                                   tenant_id,
                                                   workflow_id,
                                                   traceback))
            except Exception:
                results.append({
                    "error-message": info,
                    "error-traceback": traceback
                })
    return results


def is_failed_task(task):
    '''Checks whether a task has failed by checking the task_state dict in
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


def get_spiff_workflow_status(workflow):
    """Returns the subtree as a string for debugging.

    :param workflow: a SpiffWorkflow Workflow
    @rtype:  dict
    @return: The debug information.
    """
    def get_task_status(task, output):
        """Recursively fills task data into dict"""
        my_dict = {
            'id': task.id,
            'threadId': task.thread_id,
            'state': task.get_state_name()
        }
        output[task.get_name()] = my_dict
        for child in task.children:
            get_task_status(child, my_dict)

    result = {}
    task = workflow.task_tree
    get_task_status(task, result)
    return result


def init_spiff_workflow(spiff_wf_spec, deployment, context, workflow_id,
                        wf_type):
    '''Creates a SpiffWorkflow for initial deployment of a Checkmate deployment

    :returns: SpiffWorkflow.Workflow
    '''
    LOG.info("Creating workflow for deployment '%s'", deployment['id'])
    results = spiff_wf_spec.validate()
    if results:
        serializer = DictionarySerializer()
        serialized_spec = spiff_wf_spec.serialize(serializer)
        error_message = '. '.join(results)
        LOG.debug("Errors in Workflow: %s", error_message,
                  extra=dict(data=serialized_spec))
        raise CheckmateUserException(
            error_message,
            utils.get_class_name(CheckmateException),
            UNEXPECTED_ERROR, '')

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
    workflow.attributes['id'] = workflow_id
    workflow.attributes['tenant_id'] = deployment['tenantId']
    workflow.attributes['type'] = wf_type
    update_workflow_status(workflow)

    return workflow


def format(resources):
    formatted_resources = {}
    for resource_key, resource_value in resources.iteritems():
        formatted_resources.update({("instance:%s" % resource_key):
                                    resource_value.get("instance", {})})
    return formatted_resources


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
