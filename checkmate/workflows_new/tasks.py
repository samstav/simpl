'''
Workflows Asynchronous tasks
'''
import logging

from celery.task import task

from checkmate import db
from checkmate.workflows import tasks

LOG = logging.getLogger(__name__)
DB = db.get_driver()


@task(default_retry_delay=10, max_retries=300)
def pause_workflow(w_id, driver=DB, retry_counter=0):
    '''
    DEPRECATED: To be removed after the running celery tasks complete. Please
     use pause_workflow in checkmate.workflows.tasks
    '''
    LOG.warn('DEPRECATED method run_workflow called for workflow %s', w_id)
    tasks.pause_workflow.delay(w_id, driver=driver,
                               retry_counter=retry_counter)
