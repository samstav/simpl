"""
  Celery tasks to orchestrate a sophisticated deployment
"""
import logging
import time

import checkmate.workflow as cm_workflow

from celery.task import task
from celery.exceptions import MaxRetriesExceededError
from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.storage import DictionarySerializer

from checkmate.common.tasks import update_operation
from checkmate.db.common import ObjectLockedError
from checkmate.deployment import Deployment
from checkmate.middleware import RequestContext
from checkmate.operations import get_status_info
from checkmate.utils import extract_sensitive_data, match_celery_logging


LOG = logging.getLogger(__name__)


@task
def count_seconds(seconds):
    """ just for debugging and testing long-running tasks and updates """
    match_celery_logging(LOG)
    elapsed = 0
    while elapsed < seconds:
        time.sleep(1)
        elapsed += 1
        count_seconds.update_state(state="PROGRESS",
                                   meta={'complete': elapsed,
                                         'total': seconds})
    return seconds


@task(default_retry_delay=10, max_retries=300)
def run_workflow(w_id, timeout=900, wait=1, counter=1, driver=None):
    """Loop through trying to complete the workflow and periodically log
    status updates. Each time we cycle through, if nothing happens we
    extend the wait time between cycles so we don't load the system.

    This function should not consume time, so the timeout is only counting
    the number of seconds we wait between runs

    :param id: the workflow id
    :param timeout: the timeout in seconds. Unless we complete before then
    :param wait: how long to wait between runs. Grows without activity
    :param key: the key to unlock a locked workflow. Only should be passed in
        if the workfow has already been locked.
    :returns: True if workflow is complete
    """

    def _on_failure_handler(exc, task_id, args, kwargs, einfo):
        w_id = args[0]
        workflow = driver.get_workflow(w_id)
        dep_id = workflow["attributes"]["deploymentId"] or w_id
        kwargs = {'status': 'ERROR'}

        if isinstance(exc, MaxRetriesExceededError):
            kwargs.update({"errors": [{
                "error-message": "The maximum amount of permissible retries "
                                 "for workflow %s has elapsed. Please "
                                 "re-execute the workflow" % w_id,
                "error-help": "",
                "retriable": True,
                "retry-link": "%s/workflows/%s/+execute" % (tenant_id, w_id)
            }]})
            LOG.warn("Workflow %s has reached the maximum number of "
                     "permissible retries!", w_id)
            LOG.error("Workflow %s has reached the maximum number of "
                      "permissible retries!", w_id)
        else:
            kwargs.update({"errors": [{'error-message': exc.args[0]}]})

        update_operation.delay(dep_id, w_id, driver=driver, **kwargs)

    match_celery_logging(LOG)
    assert driver, "No driver supplied to orchestrator"

    # Lock the workflow
    try:
        workflow, key = driver.lock_workflow(w_id, with_secrets=True)
    except ObjectLockedError:
        run_workflow.retry()

    run_workflow.on_failure = _on_failure_handler

    dep_id = workflow["attributes"].get("deploymentId") or w_id
    deployment = driver.get_deployment(dep_id)
    operation_result = Deployment(deployment).get_operation(w_id)
    if not operation_result:
        driver.unlock_workflow(w_id, key)
        LOG.debug("RunWorkflow for workflow %s cannot proceed, as operation "
                  "could not be found. Deployment Id: %s", w_id, dep_id)
        run_workflow.retry()

    if "history" in operation_result:
        operation = operation_result.values()[0][-1]
    else:
        operation = operation_result.values()[0]

    operation_type = operation.get("type")
    action = operation.get("action")

    if action and action == "PAUSE" and operation_type == "BUILD":
        driver.unlock_workflow(w_id, key)
        return False

    # Get the workflow
    serializer = DictionarySerializer()
    d_wf = Workflow.deserialize(serializer, workflow)
    LOG.debug("Deserialized workflow %s" % w_id,
              extra=dict(data=d_wf.get_dump()))

    # Prepare to run it
    tenant_id = workflow.get("tenantId")
    if d_wf.is_completed():
        if d_wf.get_attribute('status') != "COMPLETE":
            cm_workflow.update_workflow(d_wf, tenant_id,
                                        driver=driver, workflow_id=w_id)
            update_operation.delay(dep_id, w_id, driver=driver,
                                   deployment_status="UP",
                                   status=d_wf.get_attribute('status'),
                                   tasks=d_wf.get_attribute('total'),
                                   complete=d_wf.get_attribute('completed'))
            LOG.debug("Workflow '%s' is already complete. Marked it so.", w_id)
        else:
            LOG.debug("Workflow '%s' is already complete. Nothing to do.",
                      w_id)

        driver.unlock_workflow(w_id, key)
        return True

    before = d_wf.get_dump()

    # Run!
    try:
        d_wf.complete_all()
    except Exception as exc:
        LOG.exception(exc)
    finally:
        # Save any changes, even if we errored out
        deployment_status = None
        errors = cm_workflow.get_errors(d_wf, tenant_id)
        after = d_wf.get_dump()

        if before != after or errors:
            #save if there are failed tasks or the workflow has progressed
            cm_workflow.update_workflow(d_wf, workflow.get("tenantId"),
                                        driver=driver, workflow_id=w_id)

        if before != after:
            # We made some progress, so prioritize next run
            wait = 1

            # Report progress
            completed = d_wf.get_attribute('completed')
            total = d_wf.get_attribute('total')
            workflow_status = operation_status = d_wf.get_attribute('status')
            status_info = {}

            if errors:
                operation_status = "ERROR"
                status_info = get_status_info(errors, tenant_id, w_id)

            if total == completed:
                deployment_status = ("DELETED" if operation_type == "DELETE"
                                     else "UP")

            operation_kwargs = {'status': operation_status,
                                'tasks': total,
                                'complete': completed,
                                'errors': errors}
            operation_kwargs.update(status_info)

            update_operation.delay(dep_id, w_id, driver=driver,
                                   deployment_status=deployment_status,
                                   **operation_kwargs)

            LOG.debug("Workflow status: %s/%s (state=%s)" % (completed,
                                                             total,
                                                             workflow_status))
            run_workflow.update_state(state="PROGRESS",
                                      meta={'complete': completed,
                                            'total': total})

        else:
            # No progress made. So drop priority (to max of 20s wait)
            if wait < 20:
                wait += 1
            LOG.debug("Workflow '%s' did not make any progress. "
                      "Deprioritizing it and waiting %s seconds to retry."
                      % (w_id, wait))

    # Assess impact of run
    if d_wf.is_completed():
        driver.unlock_workflow(w_id, key)
        return True

    timeout = timeout - wait if timeout > wait else 0
    if timeout:
        LOG.debug("Finished run of workflow '%s'. %i seconds to go. Waiting "
                  "%i seconds to next run. Retries done: %s", w_id, timeout,
                  wait, counter)
        # If we have to retry the run, pass in the key so that
        # we will not try to re-lock the workflow.
        retry_kwargs = {
            'timeout': timeout,
            'wait': wait,
            'counter': counter + 1,
            'driver': driver,
        }
        driver.unlock_workflow(w_id, key)
        return run_workflow.retry([w_id], kwargs=retry_kwargs, countdown=wait,
                                  Throw=False)
    else:
        LOG.debug("Workflow '%s' did not complete (no timeout set).", w_id)
        driver.unlock_workflow(w_id, key)
        return False


@task
def run_one_task(context, workflow_id, task_id, timeout=60, driver=None):
    """Attempt to complete one task.
    returns True/False indicating if task completed"""
    match_celery_logging(LOG)
    assert driver, "No driver supplied to orchestrator"

    workflow = None
    key = None
    try:
        # Lock the workflow
        try:
            workflow, key = driver.lock_workflow(workflow_id,
                                                 with_secrets=True)
        except ObjectLockedError:
            run_one_task.retry()
        if not workflow:
            raise IndexError("Workflow %s not found" % workflow_id)

        LOG.debug("Deserializing workflow '%s'" % workflow_id)
        serializer = DictionarySerializer()
        d_wf = Workflow.deserialize(serializer, workflow)
        task = d_wf.get_task(task_id)
        original = serializer._serialize_task(task, skip_children=True)
        if not task:
            raise IndexError("Task '%s' not found in Workflow '%s'" % (task_id,
                             workflow_id))
        if task._is_finished():
            raise ValueError("Task '%s' is in state '%s' which cannot be "
                             "executed" % (task.get_name(),
                                           task.get_state_name()))

        if task._is_predicted() or task._has_state(Task.WAITING):
            LOG.debug("Progressing task '%s' (%s)" % (task_id,
                                                      task.get_state_name()))
            if isinstance(context, dict):
                context = RequestContext(**context)
            # Refresh token if it exists in args[0]['auth_token]
            if hasattr(task, 'args') and task.task_spec.args and \
                    len(task.task_spec.args) > 0 and \
                    isinstance(task.task_spec.args[0], dict) and \
                    task.task_spec.args[0].get('auth_token') != \
                    context.auth_token:
                task.task_spec.args[0]['auth_token'] = context.auth_token
                LOG.debug("Updating task auth token with new caller token")
            result = task.task_spec._update_state(task)
        elif task._has_state(Task.READY):
            LOG.debug("Completing task '%s' (%s)" % (task_id,
                      task.get_state_name()))
            result = d_wf.complete_task_from_id(task_id)
        else:
            LOG.warn("Task '%s' in Workflow '%s' is in state %s and cannot be "
                     "progressed", task_id, workflow_id, task.get_state_name())
            return False
        cm_workflow.update_workflow_status(d_wf, workflow_id=workflow_id)
        updated = d_wf.serialize(serializer)
        if original != updated:
            LOG.debug("Task '%s' in Workflow '%s' completion result: %s" % (
                      task_id, workflow_id, result))
            msg = "Saving: %s" % d_wf.get_dump()
            LOG.debug(msg)
            #TODO: make DRY
            body, secrets = extract_sensitive_data(updated)
            body['tenantId'] = workflow.get('tenantId')
            body['id'] = workflow_id
            #TODO remove these from this whole class to the db layer
            driver.save_workflow(workflow_id, body, secrets)
        return result
    finally:
        if key:
            driver.unlock_workflow(workflow_id, key)
