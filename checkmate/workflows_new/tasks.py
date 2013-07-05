'''
Workflows Asynchronous tasks
'''
import logging
import os
from celery import current_task

from celery.task import task
from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.storage import DictionarySerializer
from SpiffWorkflow.specs import Celery

from checkmate import db
from checkmate import utils
from checkmate import workflow as cm_workflow
from checkmate.common import tasks as common_tasks
from checkmate.deployment import Deployment

LOG = logging.getLogger(__name__)
DRIVERS = {}
DB = DRIVERS['default'] = db.get_driver()
SIMULATOR_DB = DRIVERS['simulation'] = db.get_driver(
    connection_string=os.environ.get(
        'CHECKMATE_SIMULATOR_CONNECTION_STRING',
        os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')
    )
)


@task(default_retry_delay=10, max_retries=300)
def pause_workflow(w_id, driver=None, pause_action_update_retry_counter=0):
    '''
    Waits for all the waiting celery tasks to move to ready and then marks the
    operation as paused
    :param w_id: Workflow id
    :param driver: DB driver
    :return:
    '''
    if not driver:
        driver = DB
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
    elif pause_action_update_retry_counter >= 10:
        LOG.debug("Skipping waitiing for Operation Action to turn to PAUSE - "
                  "pause_workflow for workflow %s has already been retried %s "
                  "times", w_id, pause_action_update_retry_counter)
        pass
    else:
        LOG.warn("Pause request for workflow %s received but operation's action"
                 "is not PAUSE. Retry-Count waiting for action to turn to "
                 "PAUSE: %s  ", w_id, pause_action_update_retry_counter)
        driver.unlock_workflow(w_id, key)
        pause_action_update_retry_counter += 1
        pause_workflow.retry([w_id], kwargs={
            'pause_action_update_retry_counter': pause_action_update_retry_counter,
            'driver': driver
        })

    serializer = DictionarySerializer()
    d_wf = Workflow.deserialize(serializer, workflow)

    for task in Task.Iterator(d_wf.task_tree, Task.WAITING):
        if (isinstance(task.task_spec, Celery) and
                not cm_workflow.is_failed_task(task)):
            task.task_spec._update_state(task)
            if task._has_state(Task.WAITING):
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
            'pause_action_update_retry_counter': pause_action_update_retry_counter,
            'driver': driver
        })