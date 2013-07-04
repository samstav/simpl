'''
Workflows Asynchronous tasks
'''
import logging
import os

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
def pause_workflow(w_id, driver=None):
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
    operation_result = Deployment(deployment).get_operation(w_id)

    if "history" in operation_result:
        operation = operation_result.values()[0][-1]
    else:
        operation = operation_result.values()[0]

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
    else:
        LOG.warn("Pause Workflow called when operation's action is not PAUSE")
        driver.unlock_workflow(w_id, key)
        pause_workflow.retry()

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
        return pause_workflow.retry()