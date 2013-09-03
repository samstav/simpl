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

"""Common code, utilities, and classes for managing the 'operation' object."""
import itertools
import logging
import os
import time

from celery import task as celtask
from SpiffWorkflow.storage import DictionarySerializer
from SpiffWorkflow import Workflow as SpiffWorkflow

from checkmate import celeryglobal as celery
from checkmate.common import statsd
from checkmate import db
from checkmate import deployment as cmdep
from checkmate import utils

LOG = logging.getLogger(__name__)
DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))
LOCK_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_LOCK_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING')))


@celtask.task(base=celery.SingleTask, default_retry_delay=2, max_retries=20,
              lock_db=LOCK_DB, lock_key="async_dep_writer:{args[0]}",
              lock_timeout=2)
@statsd.collect
def create(dep_id, workflow_id, op_type, tenant_id=None):
    """Create a new operation of type 'op_type'."""
    if utils.is_simulation(dep_id):
        driver = SIMULATOR_DB
    else:
        driver = DB
    deployment = driver.get_deployment(dep_id, with_secrets=False)
    workflow = driver.get_workflow(workflow_id, with_secrets=False)
    serializer = DictionarySerializer()
    spiff_wf = SpiffWorkflow.deserialize(serializer, workflow)
    add(deployment, spiff_wf, op_type, tenant_id=tenant_id)
    driver.save_deployment(dep_id, deployment, secrets=None,
                           tenant_id=tenant_id, partial=False)


def add(deployment, spiff_wf, op_type, tenant_id=None):
    """Initialize new workflow in the operation and add to the deployment."""
    wf_data = init_operation(spiff_wf, tenant_id=tenant_id)
    return add_operation(deployment, op_type, **wf_data)


def add_operation(deployment, op_type, **kwargs):
    """Adds an operation to a deployment

    Moves any existing operation to history

    :param deployment: dict or Deployment
    :param op_type: the operation name (BUILD, DELETE, etc...)
    :param kwargs: additional kwargs to add to operation
    :returns: operation
    """
    if 'operation' in deployment:
        if 'operations-history' not in deployment:
            deployment['operations-history'] = []
        history = deployment.get('operations-history')
        history.insert(0, deployment.pop('operation'))
    operation = {'type': op_type}
    operation.update(**kwargs)
    deployment['operation'] = operation
    return operation


def update_operation(deployment_id, workflow_id, driver=None,
                     deployment_status=None,
                     **kwargs):
    """Update the the operation in the deployment

    Note: exposed in common.tasks as a celery task

    :param deployment_id: the string ID of the deployment
    :param driver: the backend driver to use to get the deployments
    :param kwargs: the key/value pairs to write into the operation

    """
    if kwargs:
        if utils.is_simulation(deployment_id):
            driver = SIMULATOR_DB
        if not driver:
            driver = DB
        dep = driver.get_deployment(deployment_id, with_secrets=True)
        dep = cmdep.Deployment(dep)

        try:
            op_type, op_index, op_details = dep.get_operation(workflow_id)
        except cmexc.CheckmateInvalidParameterError:
            return  # Nothing to do!

        op_status = op_details.get('status')
        if op_status == "COMPLETE":
            LOG.warn("Ignoring the update operation call as the "
                     "operation is already COMPLETE")
            return

        if op_type == 'operations-history':
            op_list = _pad_list(op_index, dict(kwargs))
        else:  # It's the current operation
            op_list = dict(kwargs)

        delta = {op_type: op_list}
        if deployment_status:
            delta['status'] = deployment_status
        try:
            if 'status' in kwargs:
                if kwargs['status'] != op_status:
                    delta['display-outputs'] = dep.calculate_outputs()
        except KeyError:
            LOG.warn("Cannot update deployment outputs: %s", deployment_id)
        driver.save_deployment(deployment_id, delta, partial=True)


def _pad_list(last_item_id, last_item):
    padded_list = []
    for index in range(last_item_id):
        padded_list.append({})
    padded_list.append(last_item)

    return padded_list


def get_status_info(errors, tenant_id, workflow_id):
    """Update and return status_info."""
    status_info = {}
    friendly_messages = []
    distinct_errors = _get_distinct_errors(errors)
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
    """Create a new operation dictionary for a given workflow.

    Example:

    'operation': {
        'type': 'deploy',
        'status': 'IN PROGRESS',
        'estimated-duration': 2400,
        'tasks': 175,
        'complete': 100,
        'link': '/v1/{tenant_id}/workflows/982h3f28937h4f23847'
    }
    """
    operation = {}

    _update_operation(operation, workflow)

    # Operation link
    workflow_id = (workflow.attributes.get('id') or
                   workflow.attributes.get('deploymentId'))
    operation['link'] = "/%s/workflows/%s" % (tenant_id, workflow_id)
    operation['workflow-id'] = workflow_id

    return operation


def _update_operation(operation, workflow):
    """Update an operation dictionary for a given workflow.

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
    """

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
    operation['last-change'] = utils.get_time_string(time_gmt=time.gmtime(
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
    """Eliminate duplicate errors."""
    distinct_errors = []
    sorted_errors = sorted(errors, key=lambda k: k.get('error-type'))
    for _, group in itertools.groupby(sorted_errors,
                                      lambda x: x.get("error-type")):
        new_error = list(group)[0]
        distinct_errors.append(new_error)
    return distinct_errors
