'''
Common code, utilities, and classes for managing the 'operation' object
'''
import itertools
import logging
import os

from checkmate import db
from checkmate.deployment import Deployment
from checkmate import utils

LOG = logging.getLogger(__name__)
DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))


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


def update_operation(deployment_id, driver=None, deployment_status=None,
                     **kwargs):
    '''Update the the operation in the deployment

    :param deployment_id: the string ID of the deployment
    :param driver: the backend driver to use to get the deployments
    :param kwargs: the key/value pairs to write into the operation

    Note: exposed in common.tasks as a celery task
    '''
    if kwargs:
        if utils.is_simulation(deployment_id):
            driver = SIMULATOR_DB
        if not driver:
            driver = DB
        deployment = driver.get_deployment(deployment_id, with_secrets=True)
        operation_status = deployment['operation']['status']

        #Do not update anything if the operation is already complete. The
        #operation gets marked as complete for both build and delete operation.
        if operation_status == "COMPLETE":
            LOG.warn("Ignoring the update operation call as the operation is "
                     "already COMPLETE")
            return

        delta = {'operation': dict(kwargs)}
        if deployment_status:
            delta.update({'status': deployment_status})
        try:
            if 'status' in kwargs:
                if kwargs['status'] != operation_status:
                    deployment = Deployment(deployment)
                    delta['display-outputs'] = deployment.calculate_outputs()
        except KeyError:
            LOG.warn("Cannot update deployment outputs: %s", deployment_id)
        driver.save_deployment(deployment_id, delta, partial=True)


def get_status_info(errors, tenant_id, workflow_id):
    '''
    Gets the status message and the retry and resume links for an operation
    :param errors: The workflow errors
    :param tenant_id: tenant_id
    :param workflow_id: workflow_id
    :return: dictionary with the status message and retry and resume link
    '''
    status_message = ""
    errors_with_action_required = filter(
        lambda x: x.get("action-required", False), errors)
    distinct_errors = _get_distinct_errors(errors_with_action_required)
    for error in distinct_errors:
        status_message += ("%s. %s\n" % (distinct_errors.index(error) + 1,
                           error["error-message"]))
    status_info = {'status-message': status_message}

    if any(error.get("retriable", False) for error in distinct_errors):
        retry_link = "/%s/workflows/%s/+retry-failed-tasks" % (tenant_id,
                                                               workflow_id)
        status_info.update({'retry-link': retry_link, 'retriable': True})
    if any(error.get("resumable", False) for error in distinct_errors):
        resume_link = "/%s/workflows/%s/+resume-failed-tasks" % (tenant_id,
                                                                 workflow_id)
        status_info.update({'resume-link': resume_link, 'resumable': True})

    return status_info


def _get_distinct_errors(errors):
    distinct_errors = []
    for k, g in itertools.groupby(errors, lambda x: x["error-type"]):
        distinct_errors.append(list(g)[0])
    return distinct_errors
