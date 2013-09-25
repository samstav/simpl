# pylint: disable=W0212
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
import logging
import time

from celery import task as celtask
from SpiffWorkflow.storage import DictionarySerializer
from SpiffWorkflow import Task
from SpiffWorkflow import Workflow as SpiffWorkflow

from checkmate import celeryglobal as celery
from checkmate.common import statsd
from checkmate import db
from checkmate import deployment as cmdep
from checkmate import exceptions as cmexc
from checkmate import task as cmtsk
from checkmate import utils

LOG = logging.getLogger(__name__)
LOCK_DB = db.get_lock_db_driver()


@celtask.task(base=celery.SingleTask, default_retry_delay=2, max_retries=20,
              lock_db=LOCK_DB, lock_key="async_dep_writer:{args[0]}",
              lock_timeout=2)
@statsd.collect
def create(dep_id, workflow_id, op_type, tenant_id=None):
    """Decouples statsd and celery from the underlying implementation."""
    _create(dep_id, workflow_id, op_type, tenant_id)


def _create(dep_id, workflow_id, op_type, tenant_id):
    """Create a new operation of type 'op_type'."""
    driver = db.get_driver(api_id=dep_id)
    deployment = driver.get_deployment(dep_id, with_secrets=False)
    curr_wf = driver.get_workflow(workflow_id, with_secrets=False)
    serializer = DictionarySerializer()
    spiff_wf = SpiffWorkflow.deserialize(serializer, curr_wf)
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
                     deployment_status=None, check_only=False,
                     **kwargs):
    """Update the the operation in the deployment

    Note: exposed in common.tasks as a celery task

    :param deployment_id: the string ID of the deployment
    :param driver: the backend driver to use to get the deployments
    :param kwargs: the key/value pairs to write into the operation

    """
    if not kwargs and not deployment_status:
        return  # Nothing to do!

    delta = {}
    if deployment_status:
        delta['status'] = deployment_status
    driver = driver or db.get_driver(api_id=deployment_id)
    deployment_info = driver.get_deployment(deployment_id, with_secrets=True)
    deployment = cmdep.Deployment(deployment_info)

    try:
        op_type, op_index, op_details = get_operation(deployment, workflow_id)
        op_status = op_details.get('status')
        if op_status == "COMPLETE":
            LOG.warn("Ignoring the update operation call as the "
                     "operation is already COMPLETE")
        else:
            if op_index == -1:  # Current operation from 'operation'
                operation = dict(kwargs)
            else:  # Pad a list so we can put it back in the right spot
                operation = [{}] * op_index + [dict(kwargs)]

            delta[op_type] = operation
            try:
                if 'status' in kwargs:
                    if kwargs['status'] != op_status:
                        delta['display-outputs'] = \
                            deployment.calculate_outputs()
            except KeyError:
                LOG.warn("Cannot update deployment outputs: %s", deployment_id)
    except cmexc.CheckmateInvalidParameterError:
        LOG.debug("Could not find the operation with id %s", workflow_id)

    if delta:
        if not check_only:
            driver.save_deployment(deployment_id, delta, partial=True)

    return delta


def current_workflow_id(deployment):
    """Return the current Workflow's ID."""
    operation = deployment.get('operation')
    if operation:
        return operation.get('workflow-id', deployment.get('id'))


def get_operation(deployment, workflow_id):
    """Gets an operation by Workflow ID.

    Looks at the current deployment's OPERATION and OPERATIONS-HISTORY
    blocks for an operation that has a workflow-id that matches the passed
    in workflow_id. If found, returns a tuple containing three values:
      - where the operation was found: 'operation' or 'operations-history'
      - the index of the operation (mainly for 'operations-history')
      - the operation details as a dict

    If the workflow_id is not found, raises a KeyError

    :param workflow_id: the workflow ID on which to search
    :return: a Tuple containing op_type, op_index, and op_details
    """
    op_type, op_index, op_details = None, -1, {}
    if workflow_id is not None and \
            current_workflow_id(deployment) == workflow_id:
        op_type = 'operation'
        op_index = -1
        op_details = deployment.get('operation')
    else:
        for index, oper in enumerate(deployment.get('operations-history', [])):
            if oper.get('workflow-id', deployment.get('id')) == workflow_id:
                op_type = 'operations-history'
                op_index = index
                op_details = oper
                break

    if not op_type:
        LOG.warn("Cannot find operation with workflow id %s in "
                 "deployment %s", workflow_id, deployment.get('id'))
        raise cmexc.CheckmateInvalidParameterError('Invalid workflow ID.')

    return (op_type, op_index, op_details)


def init_operation(spiffwf, tenant_id=None):
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

    _update_operation_stats(operation, spiffwf)

    # Operation link
    workflow_id = (spiffwf.attributes.get('id') or
                   spiffwf.attributes.get('deploymentId'))
    operation['link'] = "/%s/workflows/%s" % (tenant_id, workflow_id)
    operation['workflow-id'] = workflow_id

    return operation


def _update_operation_stats(operation, spiffwf):
    """Update an operation dictionary for a given workflow.

    :param operation: a deployment operation dict
    :param spiffwf: SpiffWorkflow
    """
    tasks = spiffwf.task_tree.children
    duration = 0
    complete = 0
    failure = 0
    total = 0
    last_change = 0
    while tasks:
        current = tasks.pop(0)
        tasks.extend(current.children)
        if current._state == Task.COMPLETED:
            complete += 1
        elif cmtsk.is_failed(current):
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
