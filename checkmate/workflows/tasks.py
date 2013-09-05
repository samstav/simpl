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


"""Workflows Asynchronous tasks."""
import logging

import celery
from celery import exceptions as celexc
from celery import task as celtask
from SpiffWorkflow.specs import Celery
from SpiffWorkflow.storage import DictionarySerializer
from SpiffWorkflow import Task
from SpiffWorkflow import Workflow

from checkmate.common import statsd
from checkmate.common import tasks as cmtasks
from checkmate import db
from checkmate import deployment as cmdep
from checkmate import middleware as cmmid
from checkmate import operations as cmops
from checkmate import utils
from checkmate import workflow as cmwf
from checkmate.workflows import exception_handlers as cmexch
from manager import Manager


LOG = logging.getLogger(__name__)
DB = db.get_driver()

MANAGERS = {'workflows': Manager()}


class WorkflowEventHandlerTask(celery.Task):
    """"Celery Task Event Handlers for Workflows."""
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        w_id = args[0]

        if isinstance(exc, celexc.MaxRetriesExceededError):
            error = exc.__repr__()
            LOG.error("Workflow %s has reached the maximum number of "
                      "permissible retries!", w_id)
        else:
            error = exc.__repr__()
        if kwargs.get('apply_callbacks'):
            update_deployment.delay(args[0], error=error)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        self.on_success(None, task_id, args, kwargs)

    def on_success(self, retval, task_id, args, kwargs):
        if kwargs.get('apply_callbacks'):
            update_deployment.delay(args[0])


@celtask.task(default_retry_delay=10, max_retries=10, ignore_result=True)
@statsd.collect
def update_deployment(w_id, error=None):
    """Update the deployment progress and status depending on the status of
    the workflow
    :param w_id: Workflow to update the deployment from
    :param error: Additional errors that need to be updated
    """
    driver = db.get_driver(api_id=w_id)
    workflow = MANAGERS['workflows'].get_workflow(w_id)
    serializer = DictionarySerializer()
    d_wf = Workflow.deserialize(serializer, workflow)

    dep_id = d_wf.get_attribute("deploymentId") or w_id
    tenant_id = d_wf.get_attribute("tenant_id")
    status = d_wf.get_attribute('status')
    total = d_wf.get_attribute('total')
    completed = d_wf.get_attribute('completed')
    wf_type = d_wf.get_attribute('type')
    dep_status = None

    if d_wf.is_completed():
        dep_status = cmdep.OPERATION_DEPLOYMENT_STATUS_MAP.get(wf_type, None)
        cmtasks.update_operation.delay(
            dep_id, w_id, driver=driver, deployment_status=dep_status,
            status=status,
            tasks=total,
            complete=completed)
    else:
        status_info = {}
        wf_errors = cmwf.get_errors(d_wf, tenant_id)
        if error:
            wf_errors.append(cmwf.convert_exc_to_dict(error, None, tenant_id,
                                                      w_id, None))
        if wf_errors:
            status_info = cmops.get_status_info(wf_errors, tenant_id, w_id)
            dep_status = "FAILED"

        operation_kwargs = {'status': status,
                            'tasks': total,
                            'complete': completed,
                            'errors': wf_errors}
        operation_kwargs.update(status_info)
        cmtasks.update_operation.delay(dep_id, w_id, driver=driver,
                                       deployment_status=dep_status,
                                       **operation_kwargs)


@celtask.task(base=WorkflowEventHandlerTask, default_retry_delay=10,
              max_retries=300, time_limit=3600)
@statsd.collect
def cycle_workflow(w_id, context, wait=1, apply_callbacks=True):
    """Loop through trying to complete the workflow and periodically log
    status updates. Each time we cycle through, if nothing happens we
    extend the wait time between cycles so we don't load the system.

    :param w_id: the workflow id
    :param wait: how long to wait between runs. Grows without activity
    :param apply_callbacks: whether to apply success and failure callbacks
    """
    utils.match_celery_logging(LOG)
    key = None
    try:
        workflow, key = MANAGERS['workflows'].lock_workflow(w_id,
                                                            with_secrets=True)
        serializer = DictionarySerializer()
        d_wf = Workflow.deserialize(serializer, workflow)
        driver = MANAGERS['workflows'].select_driver(w_id)

        initial_wf_state = cmwf.update_workflow_status(d_wf)
        d_wf.complete_all()
        final_workflow_state = cmwf.update_workflow_status(d_wf)
        errored_tasks_ids = final_workflow_state.get('errored_tasks')

        if initial_wf_state != final_workflow_state:
            if errored_tasks_ids:
                handlers = cmexch.get_handlers(
                    d_wf, errored_tasks_ids, context, driver)
                for handler in handlers:
                    handler_wf_id = handler.handle()
                    if handler_wf_id:
                        cycle_workflow.apply_async(
                            args=[handler_wf_id, context],
                            kwargs={'apply_callbacks': False},
                            task_id=handler_wf_id)

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
        if key:
            MANAGERS['workflows'].unlock_workflow(w_id, key)

    LOG.debug("Finished run of workflow '%s'. Waiting %i seconds to "
              "next run. Retries done: %s", w_id, wait,
              cycle_workflow.request.retries)
    cycle_workflow.retry([w_id, context],
                         kwargs={
                             'wait': wait,
                             'apply_callbacks': apply_callbacks
                         },
                         countdown=wait)


@celtask.task(default_retry_delay=10, max_retries=10)
def reset_task_tree(w_id, task_id):
    """
    Resets the tree for a spiff task for it to rerun
    :param w_id: workflow id
    :param task_id: task id
    :return:
    """
    utils.match_celery_logging(LOG)
    key = None
    try:
        workflow, key = MANAGERS['workflows'].lock_workflow(w_id,
                                                            with_secrets=True)
        serializer = DictionarySerializer()
        d_wf = Workflow.deserialize(serializer, workflow)
        wf_task = d_wf.get_task(task_id)
        cmwf.reset_task_tree(wf_task)
        MANAGERS['workflows'].save_spiff_workflow(d_wf)
    except db.ObjectLockedError:
        reset_task_tree.retry()
    finally:
        if key:
            MANAGERS['workflows'].unlock_workflow(w_id, key)


@celtask.task(default_retry_delay=10, max_retries=300)
@statsd.collect
def run_workflow(w_id, timeout=900, wait=1, counter=1, driver=DB):
    """DEPRECATED: Please use cycle_workflow in checkmate.workflows.tasks
    """
    LOG.warn('DEPRECATED method run_workflow called for workflow %s', w_id)
    cycle_workflow.delay(w_id, wait=wait)


@celtask.task
@statsd.collect
def run_one_task(context, workflow_id, task_id, timeout=60, driver=DB):
    """Attempt to complete one task.
    returns True/False indicating if task completed
    """
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
            LOG.debug("Progressing task '%s' (%s)", task_id,
                      wf_task.get_state_name())
            if isinstance(context, dict):
                context = cmmid.RequestContext(**context)
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
            LOG.debug("Completing task '%s' (%s)", task_id,
                      wf_task.get_state_name())
            result = d_wf.complete_task_from_id(task_id)
        else:
            LOG.warn("Task '%s' in Workflow '%s' is in state %s and cannot be "
                     "progressed", task_id, workflow_id,
                     wf_task.get_state_name())
            return False
        cmwf.update_workflow_status(d_wf)
        updated = d_wf.serialize(serializer)
        if original != updated:
            LOG.debug("Task '%s' in Workflow '%s' completion result: %s",
                      task_id, workflow_id, result)
            msg = "Saving: %s" % d_wf.get_dump()
            LOG.debug(msg)
            #TODO(any): make DRY
            body, secrets = utils.extract_sensitive_data(updated)
            body['tenantId'] = workflow.get('tenantId')
            body['id'] = workflow_id
            #TODO(any): remove these from this whole class to the db layer
            driver.save_workflow(workflow_id, body, secrets)
        return result
    finally:
        if key:
            driver.unlock_workflow(workflow_id, key)


@celtask.task(default_retry_delay=10, max_retries=30)  # five minutes
@statsd.collect
def pause_workflow(w_id, driver=DB, retry_counter=0):
    """Waits for all the waiting celery tasks to move to ready and then marks
    the operation as paused
    :param w_id: Workflow id
    :param driver: DB driver
    :return:
    """
    number_of_waiting_celery_tasks = 0
    try:
        workflow, key = driver.lock_workflow(w_id, with_secrets=True)
    except db.common.ObjectLockedError:
        pause_workflow.retry()

    deployment_id = workflow["attributes"].get("deploymentId") or w_id
    deployment = driver.get_deployment(deployment_id)
    _, _, operation = cmops.get_operation(cmdep.Deployment(deployment), w_id)

    action = operation.get("action")

    if action and action == "PAUSE":
        if operation.get("action-response") != "ACK":
            kwargs = {"action-response": "ACK"}
            if 'celery_task_id' in workflow:
                revoke_task.delay(workflow['celery_task_id'])
            cmtasks.update_operation.delay(deployment_id, w_id,
                                           driver=driver, **kwargs)
    elif operation.get("status") == "COMPLETE":
        LOG.warn("Received a pause workflow request for a completed "
                 "operation for deployment %s. Ignoring the request",
                 deployment_id)
        driver.unlock_workflow(w_id, key)
        return True
    elif retry_counter >= 10:
        LOG.debug("Skipping waiting for Operation Action to turn to PAUSE - "
                  "pause_workflow for workflow %s has already been retried %s "
                  "times", w_id, retry_counter)
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
    final_tasks = cmwf.find_tasks(d_wf, state=Task.WAITING, tag='final')

    for final_task in final_tasks:
        if (isinstance(final_task.task_spec, Celery) and
                not cmwf.is_failed_task(final_task)):
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

        cmtasks.update_operation.delay(deployment_id, w_id, driver=driver,
                                       **kwargs)
        cmwf.update_workflow(d_wf, workflow.get("tenantId"),
                             status="PAUSED", workflow_id=w_id)
        driver.unlock_workflow(w_id, key)
        return True
    else:
        cmtasks.update_operation.delay(deployment_id, w_id, driver=driver,
                                       **kwargs)
        cmwf.update_workflow(d_wf, workflow.get("tenantId"),
                             workflow_id=w_id)
        driver.unlock_workflow(w_id, key)
        pause_workflow.retry([w_id], kwargs={
            'retry_counter': retry_counter,
            'driver': driver
        })


@celtask.task
def revoke_task(task_id):
    """Revoke a celery task
    :param task_id: Task Id of the task to revoke
    :return:
    """
    if task_id:
        celery.current_app.control.revoke(task_id)
        LOG.debug("Revoked task %s", task_id)
    else:
        LOG.error("No task id passed to revoke_task")
