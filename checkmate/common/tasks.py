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
import os

from celery.task import task

from checkmate import celeryglobal as celery  # module to be renamed
from checkmate import db
from checkmate import operations, deployment


LOCK_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_LOCK_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING')))


@task(base=celery.SingleTask, default_retry_delay=2, max_retries=20,
      lock_db=LOCK_DB, lock_key="async_dep_writer:{args[0]}", lock_timeout=2)
def update_operation(deployment_id, driver=None, deployment_status=None,
                     **kwargs):
    '''
    Exposes operations.update_operation as a task

    :param deployment_id: Deployment Id
    :param driver: DB driver
    :param deployment_status: If provided, updates the deployment status also
    :param kwargs: Additional parameters
    :return:

    Notes: has a high retry rate to make sure the status gets updated.
    Otherwise the deployment will appear to never complete.
    '''
    operations.update_operation(deployment_id, driver=driver,
                                deployment_status=deployment_status, **kwargs)


@task(base=celery.SingleTask, default_retry_delay=3, max_retries=10,
      lock_db=LOCK_DB, lock_key="async_dep_writer:{args[0]}", lock_timeout=2)
def update_deployment_status(deployment_id, new_status, driver=None):
    '''

    DEPRECATED  will be removed around v0.14

    Use checkmate.common.tasks.update_operation and pass in a deployment
    status

    '''
    # TODO: rename without _new
    return deployment.update_deployment_status_new(deployment_id,
                                                   new_status,
                                                   driver=driver)
