'''
Workflows Asynchronous tasks
'''
import logging
import os

import celery

from celery.exceptions import MaxRetriesExceededError
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
from checkmate.deployment import (
    Deployment,
    OPERATION_DEPLOYMENT_STATUS_MAP,
)
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


class WorkflowEventHandlerTask(celery.Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        w_id = args[0]

        if isinstance(exc, MaxRetriesExceededError):
            error = exc.__repr__()
            LOG.error("Workflow %s has reached the maximum number of "
                      "permissible retries!", w_id)
        else:
            error = exc.__repr__()
        update_deployment.delay(args[0], error=error)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        self.on_success(None, task_id, args, kwargs)

    def on_success(self, retval, task_id, args, kwargs):
        update_deployment.delay(args[0])


@celery.task(default_retry_delay=10, max_retries=10, ignore_result=True)
def update_deployment(w_id, error=None):
    '''Update the deployment progress and status depending on the status of
    the workflow
    :param w_id: Workflow to update the deployment from
    :param errors: Additional errors that need to be updated
    '''
    driver = MANAGERS['workflows'].select_driver(w_id)
    workflow = MANAGERS['workflows'].get_workflow(w_id)
    serializer = DictionarySerializer()
    d_wf = Workflow.deserialize(serializer, workflow)

    dep_id = d_wf.get_attribute("deploymentId") or w_id
    tenant_id = d_wf.get_attribute("tenant_id")
    status = d_wf.get_attribute('status'),
    total = d_wf.get_attribute('total'),
    completed = d_wf.get_attribute('completed')
    type = d_wf.get_attribute('type')

    if d_wf.is_completed():
        dep_status = OPERATION_DEPLOYMENT_STATUS_MAP.get(type, None)
        common_tasks.update_operation.delay(
            dep_id, w_id, driver=driver, deployment_status=dep_status,
            status=status,
            tasks=total,
            complete=completed)
    else:
        status_info = {}
        wf_errors = cm_workflow.get_errors(d_wf, tenant_id)
        if error:
            wf_errors.append(cm_workflow.convert_exc_to_dict(error, None,
                                                             tenant_id, w_id,
                                                             None))
        if wf_errors:
            status_info = get_status_info(wf_errors, tenant_id, w_id)

        operation_kwargs = {'status': status,
                            'tasks': total,
                            'complete': completed,
                            'errors': wf_errors}
        operation_kwargs.update(status_info)
        common_tasks.update_operation.delay(dep_id, w_id, driver=driver,
                                            **operation_kwargs)


@celery.task(base=WorkflowEventHandlerTask, default_retry_delay=10,
             max_retries=300, time_limit=3600, ignore_result=True)
def cycle_workflow(w_id, wait=1):
    '''Loop through trying to complete the workflow and periodically log
    status updates. Each time we cycle through, if nothing happens we
    extend the wait time between cycles so we don't load the system.

    :param w_id: the workflow id
    :param wait: how long to wait between runs. Grows without activity
    '''
    utils.match_celery_logging(LOG)
    try:
        workflow, key = MANAGERS['workflows'].lock_workflow(w_id,
                                                            with_secrets=True)

        serializer = DictionarySerializer()
        d_wf = Workflow.deserialize(serializer, workflow)

        initial_wf_state = cm_workflow.update_workflow_status(d_wf)
        d_wf.complete_all()
        final_workflow_state = cm_workflow.update_workflow_status(d_wf)

        if initial_wf_state != final_workflow_state:
            MANAGERS['workflows'].save_spiff_workflow(
                d_wf, celery_task_id=cycle_workflow.request.id)
            wait = 1
            completed_tasks = final_workflow_state['completed']
            total_tasks = final_workflow_state['total']
            LOG.debug("Workflow status: %s/%s (state=%s)", completed_tasks,
                      total_tasks, d_wf.get_attribute('status'))
            if d_wf.is_completed():
                LOG.debug("Workflow '%s' is complete", w_id)
                return
            else:
                cycle_workflow.update_state(state="PROGRESS", meta={
                    'complete': completed_tasks,
                    'total': total_tasks
                })
        else:
            if wait < 20:
                wait += 1
            LOG.debug("Workflow '%s' did not make any progress. "
                      "Deprioritizing it and waiting %s seconds to retry"
                      ".", w_id, wait)
    except db.ObjectLockedError:
        cycle_workflow.retry()
    except Exception as exc:
        LOG.exception(exc)
    finally:
        MANAGERS['workflows'].unlock_workflow(w_id, key)

    LOG.debug("Finished run of workflow '%s'. Waiting %i seconds to "
              "next run. Retries done: %s", w_id, wait,
              cycle_workflow.request.retries)
    cycle_workflow.retry([w_id], kwargs={'wait': wait}, countdown=wait)


@celery.task(default_retry_delay=10, max_retries=300)
@statsd.collect
def run_workflow(w_id, timeout=900, wait=1, counter=1, driver=DB):
    '''
    DEPRECATED: Please use cycle_workflow in checkmate.workflows.tasks
    '''
    LOG.warn('DEPRECATED method run_workflow called for workflow %s', w_id)
    cycle_workflow.delay(w_id, wait=wait)


@celery.task
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
        cm_workflow.update_workflow_status(d_wf)
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


@celery.task(default_retry_delay=10, max_retries=300)
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
            revoke_task.delay(workflow['celery_task_id'])
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


@celery.task
def revoke_task(task_id):
    if task_id:
        celery.current_app.control.revoke(task_id)
        LOG.debug("Revoked task %s", task_id)
    else:
        LOG.debug("No task id passed to revoke_task")
