'''
Common tasks

Tasks here generally:
- are loaded by the engine
- have access to the backend database
- do not belong to a specific porovider


Tasks are wrapped by a base task class we create that will capture exceptions
and retry the task. That allows the called function to raise exceptions without
having special logic around celery.
'''
from celery.task import task

from checkmate import celeryglobal as celery  # module to be renamed
from checkmate import operations


@task(base=celery.AlwaysRetryTask, default_retry_delay=0.3, max_retries=2)
def update_operation(deployment_id, driver=None, **kwargs):
    '''Exposes operations.update_operation as a task'''
    return operations.update_operation(deployment_id, driver=driver, **kwargs)
