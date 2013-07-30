'''
Common code, utilities, and classes for managing the 'operation' object
'''
import itertools
import logging
import os
import time

from celery.task import task
from SpiffWorkflow import Workflow as SpiffWorkflow
from SpiffWorkflow.storage import DictionarySerializer

from checkmate import celeryglobal as celery
from checkmate import db
from checkmate.deployment import Deployment
from checkmate.utils import (
    get_time_string,
    is_simulation,
)


LOG = logging.getLogger(__name__)
DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))
LOCK_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_LOCK_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING')))


@task(base=celery.SingleTask, default_retry_delay=2, max_retries=20,
      lock_db=LOCK_DB, lock_key="async_dep_writer:{args[0]}", lock_timeout=2)
def create(dep_id, workflow_id, type, tenant_id=None):
    if is_simulation(dep_id):
        driver = SIMULATOR_DB
    else:
        driver = DB
    deployment = driver.get_deployment(dep_id, with_secrets=False)
    workflow = driver.get_workflow(workflow_id, with_secrets=False)
    serializer = DictionarySerializer()
    spiff_wf = SpiffWorkflow.deserialize(serializer, workflow)
    add(deployment, spiff_wf, type, tenant_id=tenant_id)
    driver.save_deployment(dep_id, deployment, secrets=None, tenant_id=tenant_id,
                       partial=False)


def add(deployment, spiff_wf, type, tenant_id=None):
    wf_data = init_operation(spiff_wf, tenant_id=tenant_id)
    return add_operation(deployment, type, **wf_data)


def add_operation(deployment, type_name, **kwargs):
    '''Adds an operation to a deployment

    Moves any existing operation to history

    :param deployment: dict or Deployment
    :param type_name: the operation name (BUILD, DELETE, etc...)
    :param kwargs: additional kwargs to add to operation
    :returns: operation
    '''
    if 'operation' in deployment:
        if 'operations-history' not in deployment:
            deployment['operations-history'] = []
        history = deployment.get('operations-history')
        history.insert(0, deployment.pop('operation'))
    operation = {'type': type_name}
    operation.update(**kwargs)
    deployment['operation'] = operation
    return operation


def update_operation(deployment_id, workflow_id, driver=None,
                     deployment_status=None,
                     **kwargs):
    '''Update the the operation in the deployment

    :param deployment_id: the string ID of the deployment
    :param driver: the backend driver to use to get the deployments
    :param kwargs: the key/value pairs to write into the operation

    Note: exposed in common.tasks as a celery task
    '''
    if kwargs:
        if is_simulation(deployment_id):
            driver = SIMULATOR_DB
        if not driver:
            driver = DB
        deployment = driver.get_deployment(deployment_id, with_secrets=True)
        deployment = Deployment(deployment)
        operation = deployment.get_operation(workflow_id)
        operation_value = operation.values()[0]
        if isinstance(operation_value, list):
            operation_status = operation_value[-1]['status']
        elif operation_value:
            operation_status = operation_value['status']
        else:
            operation_status = None

        #Do not update anything if the operation is already complete. The
        #operation gets marked as complete for both build and delete operation.
        if operation_status == "COMPLETE":
            LOG.warn("Ignoring the update operation call as the operation is "
                     "already COMPLETE")
            return
        if "history" in operation.keys():
            padded_list = []
            padded_list.extend(itertools.repeat({}, len(operation_value) - 1))
            padded_list.append(dict(kwargs))
            delta = {'operations-history': padded_list}
        else:
            delta = {'operation': dict(kwargs)}
        if deployment_status:
            delta.update({'status': deployment_status})
        try:
            if 'status' in kwargs:
                if kwargs['status'] != operation_status:
                    delta['display-outputs'] = deployment.calculate_outputs()
        except KeyError:
            LOG.warn("Cannot update deployment outputs: %s", deployment_id)
        driver.save_deployment(deployment_id, delta, partial=True)


def get_status_info(errors, tenant_id, workflow_id):
    status_info = {}
    friendly_messages = []
    distinct_errors = _get_distinct_errors(errors)
    print distinct_errors
    for error in distinct_errors:
        if 'friendly-message' in error:
            friendly_messages.append("%s. %s\n" %
                                    (len(friendly_messages) + 1,
                                     error['friendly-message']))

    status_message = ''.join(friendly_messages) \
        if len(distinct_errors) == len(friendly_messages) \
        else 'Multiple errors have occurred. Please contact support'
    status_info.update({'status-message': status_message})

    if any(error.get("retriable", False) for error in distinct_errors):
        retry_link = "/%s/workflows/%s/+retry-failed-tasks" % (tenant_id,
                                                               workflow_id)
        status_info.update({'retry-link': retry_link, 'retriable': True})

    if any(error.get("resumable", False) for error in distinct_errors):
        resume_link = "/%s/workflows/%s/+resume-failed-tasks" % (tenant_id,
                                                                 workflow_id)
        status_info.update({'resume-link': resume_link, 'resumable': True})
    return status_info


def init_operation(workflow, tenant_id=None):
    '''Create a new operation dictionary for a given workflow.

    Example:

    'operation': {
        'type': 'deploy',
        'status': 'IN PROGRESS',
        'estimated-duration': 2400,
        'tasks': 175,
        'complete': 100,
        'link': '/v1/{tenant_id}/workflows/982h3f28937h4f23847'
    }
    '''
    operation = {}

    _update_operation(operation, workflow)

    # Operation link
    workflow_id = (workflow.attributes.get('id') or
                   workflow.attributes.get('deploymentId'))
    operation['link'] = "/%s/workflows/%s" % (tenant_id, workflow_id)
    operation['workflow-id'] = workflow_id

    return operation


def _update_operation(operation, workflow):
    '''Update an operation dictionary for a given workflow.

    Example:

    'operation': {
        'type': 'deploy',
        'status': 'IN PROGRESS',
        'estimated-duration': 2400,
        'tasks': 175,
        'complete': 100,
        'link': '/v1/{tenant_id}/workflows/982h3f28937h4f23847'
    }

    :param operation: a deployment operation dict
    :param workflow: SpiffWorkflow
    '''

    tasks = workflow.task_tree.children

    # Loop through tasks and calculate statistics
    spiff_status = {
        1: "FUTURE",
        2: "LIKELY",
        4: "MAYBE",
        8: "WAITING",
        16: "READY",
        32: "CANCELLED",
        64: "COMPLETED",
        128: "TRIGGERED"
    }
    duration = 0
    complete = 0
    failure = 0
    total = 0
    last_change = 0
    while tasks:
        current = tasks.pop(0)
        tasks.extend(current.children)
        status = spiff_status[current._state]
        if status == "COMPLETED":
            complete += 1
        elif status == "FAILURE":
            failure += 1
        duration += current._get_internal_attribute('estimated_completed_in')
        if current.last_state_change > last_change:
            last_change = current.last_state_change
        total += 1
    operation['tasks'] = total
    operation['complete'] = complete
    operation['estimated-duration'] = duration
    operation['last-change'] = get_time_string(time_gmt=time.gmtime(
        last_change))
    if failure > 0:
        operation['status'] = "ERROR"
    elif total > complete:
        operation['status'] = "IN PROGRESS"
    elif total == complete:
        operation['status'] = "COMPLETE"
    else:
        operation['status'] = "UNKNOWN"


def _get_distinct_errors(errors):
    distinct_errors = []
    sorted_errors = sorted(errors, key=lambda k: k.get('error-type'))
    for k, g in itertools.groupby(sorted_errors, lambda x: x.get("error-type")):
        a = list(g)[0]
        distinct_errors.append(a)
    return distinct_errors
