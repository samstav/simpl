"""
  Celery tasks to orchestrate a sophisticated deployment
"""
import logging
import time

from celery.task import task

from checkmate.workflows import tasks
from checkmate.utils import match_celery_logging


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
    '''
    DEPRECATED: To be removed after the running celery tasks complete. Please
     use run_workflow in checkmate.workflows.tasks
    '''
    LOG.warn('DEPRECATED method run_workflow called for workflow %s', w_id)
    tasks.run_workflow.delay(w_id, timeout=timeout, wait=wait,
                             counter=counter, driver=driver)


@task
def run_one_task(context, workflow_id, task_id, timeout=60, driver=None):
    '''
    DEPRECATED: To be removed after the running celery tasks complete. Please
     use run_one_task in checkmate.workflows.tasks
    '''
    LOG.warn('DEPRECATED method run_one_task called for workflow %s and task '
             '%s', workflow_id, task_id)
    tasks.run_one_task.delay(context, workflow_id, task_id, timeout=timeout,
                             driver=driver)
