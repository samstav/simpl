'''
Workflows Asynchronous tasks
'''
import logging
import os
from celery.exceptions import MaxRetriesExceededError

from celery.task import task
from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.storage import DictionarySerializer
from SpiffWorkflow.specs import Celery

from checkmate import db
from checkmate import workflow as cm_workflow
from checkmate import utils
from checkmate.common import (
    statsd,
    tasks as common_tasks,
)
from checkmate.deployment import Deployment
from checkmate.middleware import RequestContext
from checkmate.operations import get_status_info
from checkmate.workflows import Manager

LOG = logging.getLogger(__name__)
DRIVERS = {}
DB = DRIVERS['default'] = db.get_driver()
SIMULATOR_DB = DRIVERS['simulation'] = db.get_driver(
    connection_string=os.environ.get(
        'CHECKMATE_SIMULATOR_CONNECTION_STRING',
        os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')
    )
)

MANAGERS = {'workflows': Manager(DRIVERS)}


@task(default_retry_delay=10, max_retries=300)
@statsd.collect
def run_workflow(w_id, timeout=900, wait=1, counter=1, driver=DB):
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

        common_tasks.update_operation.delay(dep_id, w_id, driver=driver,
                                            **kwargs)

    utils.match_celery_logging(LOG)
    assert driver, "No driver supplied to orchestrator"

    # Lock the workflow
    try:
        workflow, key = driver.lock_workflow(w_id, with_secrets=True)
    except db.ObjectLockedError:
        run_workflow.retry()

    run_workflow.on_failure = _on_failure_handler

    dep_id = workflow["attributes"].get("deploymentId") or w_id
    deployment = driver.get_deployment(dep_id)
    operation = Deployment(deployment).get_current_operation(w_id)
    if not operation:
        driver.unlock_workflow(w_id, key)
        LOG.debug("RunWorkflow for workflow %s cannot proceed, as operation "
                  "could not be found. Deployment Id: %s", w_id, dep_id)
        run_workflow.retry()

    operation_type = operation.get("type")
    action = operation.get("action")

    if action and action == "PAUSE":
        driver.unlock_workflow(w_id, key)
        return False

    # Get the workflow
    serializer = DictionarySerializer()
    d_wf = Workflow.deserialize(serializer, workflow)
    LOG.debug("Deserialized workflow %s", w_id,
              extra=dict(data=d_wf.get_dump()))

    # Prepare to run it
    tenant_id = workflow.get("tenantId")
    if d_wf.is_completed():
        if d_wf.get_attribute('status') != "COMPLETE":
            cm_workflow.update_workflow(d_wf, tenant_id,
                                        driver=driver, workflow_id=w_id)
            common_tasks.update_operation.delay(
                dep_id, w_id, driver=driver, deployment_status="UP",
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
        errors = cm_workflow.get_errors(d_wf, tenant_id)
        after = d_wf.get_dump()

        if before != after or errors:
            #save if there are failed tasks or the workflow has progressed
            cm_workflow.update_workflow(d_wf, workflow.get("tenantId"),
                                        driver=driver, workflow_id=w_id)
            completed = d_wf.get_attribute('completed')
            total = d_wf.get_attribute('total')
            workflow_status = operation_status = d_wf.get_attribute('status')
            status_info = {}

            if errors:
                operation_status = "ERROR"
                status_info = get_status_info(errors, tenant_id, w_id)

            operation_kwargs = {'status': operation_status,
                                'tasks': total,
                                'complete': completed,
                                'errors': errors}
            operation_kwargs.update(status_info)

            common_tasks.update_operation.delay(dep_id, w_id, driver=driver,
                                                **operation_kwargs)

        if before != after:
            # We made some progress, so prioritize next run
            wait = 1

            if total == completed:
                deployment_status = ("DELETED" if operation_type == "DELETE"
                                     else "UP")
                common_tasks.update_deployment_status.delay(dep_id,
                                                            deployment_status,
                                                            driver=driver)

            LOG.debug("Workflow status: %s/%s (state=%s)", completed, total,
                      workflow_status)
            run_workflow.update_state(state="PROGRESS",
                                      meta={'complete': completed,
                                            'total': total})
        else:
            # No progress made. So drop priority (to max of 20s wait)
            if wait < 20:
                wait += 1
            LOG.debug("Workflow '%s' did not make any progress. Deprioritizing"
                      " it and waiting %s seconds to retry.", w_id, wait)

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
@statsd.collect
def run_one_task(context, workflow_id, task_id, timeout=60, driver=DB):
    """Attempt to complete one task.
    returns True/False indicating if task completed"""
    utils.match_celery_logging(LOG)
    workflow = None
    key = None
    try:
        # Lock the workflow
        try:
            workflow, key = driver.lock_workflow(workflow_id,
                                                 with_secrets=True)
        except db.ObjectLockedError:
            run_one_task.retry()
        if not workflow:
            raise IndexError("Workflow %s not found" % workflow_id)

        LOG.debug("Deserializing workflow '%s'", workflow_id)
        serializer = DictionarySerializer()
        d_wf = Workflow.deserialize(serializer, workflow)
        wf_task = d_wf.get_task(task_id)
        original = serializer._serialize_task(wf_task, skip_children=True)
        if not wf_task:
            raise IndexError("Task '%s' not found in Workflow '%s'" % (task_id,
                             workflow_id))
        if wf_task._is_finished():
            raise ValueError("Task '%s' is in state '%s' which cannot be "
                             "executed" % (wf_task.get_name(),
                                           wf_task.get_state_name()))

        if wf_task._is_predicted() or wf_task._has_state(Task.WAITING):
            LOG.debug("Progressing task '%s' (%s)" % (task_id,
                                                      wf_task.get_state_name()))
            if isinstance(context, dict):
                context = RequestContext(**context)
            # Refresh token if it exists in args[0]['auth_token]
            if hasattr(wf_task, 'args') and wf_task.task_spec.args and \
                    len(wf_task.task_spec.args) > 0 and \
                    isinstance(wf_task.task_spec.args[0], dict) and \
                    wf_task.task_spec.args[0].get('auth_token') != \
                    context.auth_token:
                wf_task.task_spec.args[0]['auth_token'] = context.auth_token
                LOG.debug("Updating task auth token with new caller token")
            result = wf_task.task_spec._update_state(wf_task)
        elif wf_task._has_state(Task.READY):
            LOG.debug("Completing task '%s' (%s)" % (task_id,
                      wf_task.get_state_name()))
            result = d_wf.complete_task_from_id(task_id)
        else:
            LOG.warn("Task '%s' in Workflow '%s' is in state %s and cannot be "
                     "progressed", task_id, workflow_id,
                     wf_task.get_state_name())
            return False
        cm_workflow.update_workflow_status(d_wf,
                                           tenant_id=workflow.get('tenantId'))
        updated = d_wf.serialize(serializer)
        if original != updated:
            LOG.debug("Task '%s' in Workflow '%s' completion result: %s" % (
                      task_id, workflow_id, result))
            msg = "Saving: %s" % d_wf.get_dump()
            LOG.debug(msg)
            #TODO: make DRY
            body, secrets = utils.extract_sensitive_data(updated)
            body['tenantId'] = workflow.get('tenantId')
            body['id'] = workflow_id
            #TODO remove these from this whole class to the db layer
            driver.save_workflow(workflow_id, body, secrets)
        return result
    finally:
        if key:
            driver.unlock_workflow(workflow_id, key)


@task(default_retry_delay=10, max_retries=300)
@statsd.collect
def pause_workflow(w_id, driver=DB, retry_counter=0):
    '''
    Waits for all the waiting celery tasks to move to ready and then marks the
    operation as paused
    :param w_id: Workflow id
    :param driver: DB driver
    :return:
    '''
    number_of_waiting_celery_tasks = 0
    try:
        workflow, key = driver.lock_workflow(w_id, with_secrets=True)
    except db.common.ObjectLockedError:
        pause_workflow.retry()

    deployment_id = workflow["attributes"].get("deploymentId") or w_id
    deployment = driver.get_deployment(deployment_id)
    operation = Deployment(deployment).get_current_operation(w_id)

    action = operation.get("action")

    if action and action == "PAUSE":
        if operation.get("action-response") != "ACK":
            kwargs = {"action-response": "ACK"}
            common_tasks.update_operation.delay(deployment_id, w_id,
                                                driver=driver, **kwargs)
    elif operation["status"] == "COMPLETE":
        LOG.warn("Received a pause workflow request for a completed "
                 "operation for deployment %s. Ignoring the request",
                 deployment_id)
        driver.unlock_workflow(w_id, key)
        return True
    elif retry_counter >= 10:
        LOG.debug("Skipping waitiing for Operation Action to turn to PAUSE - "
                  "pause_workflow for workflow %s has already been retried %s "
                  "times", w_id, retry_counter)
        pass
    else:
        LOG.warn("Pause request for workflow %s received but operation's "
                 "action is not PAUSE. Retry-Count waiting for action to "
                 "turn to PAUSE: %s  ", w_id, retry_counter)
        driver.unlock_workflow(w_id, key)
        retry_counter += 1
        pause_workflow.retry([w_id], kwargs={
            'retry_counter': retry_counter,
            'driver': driver
        })

    serializer = DictionarySerializer()
    d_wf = Workflow.deserialize(serializer, workflow)
    final_tasks = cm_workflow.find_tasks(d_wf, state=Task.WAITING, tag='final')

    for final_task in final_tasks:
        if (isinstance(final_task.task_spec, Celery) and
                not cm_workflow.is_failed_task(final_task)):
            final_task.task_spec._update_state(final_task)
            if final_task._has_state(Task.WAITING):
                number_of_waiting_celery_tasks += 1

    LOG.debug("Workflow %s has %s waiting celery tasks", w_id,
              number_of_waiting_celery_tasks)
    kwargs = {"action-completes-after": number_of_waiting_celery_tasks}

    if number_of_waiting_celery_tasks == 0:
        LOG.debug("No waiting celery tasks for workflow %s", w_id)
        kwargs.update({'status': 'PAUSED', 'action-response': None,
                       'action': None})

        common_tasks.update_operation.delay(deployment_id, w_id, driver=driver,
                                            **kwargs)
        cm_workflow.update_workflow(d_wf, workflow.get("tenantId"),
                                    status="PAUSED", workflow_id=w_id)
        driver.unlock_workflow(w_id, key)
        return True
    else:
        common_tasks.update_operation.delay(deployment_id, w_id, driver=driver,
                                            **kwargs)
        cm_workflow.update_workflow(d_wf, workflow.get("tenantId"),
                                    workflow_id=w_id)
        driver.unlock_workflow(w_id, key)
        pause_workflow.retry([w_id], kwargs={
            'retry_counter': retry_counter,
            'driver': driver
        })
