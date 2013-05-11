'''
Common code, utilities, and classes for managing the 'operation' object
'''
import logging
import os

from checkmate import db
from checkmate import utils

LOG = logging.getLogger(__name__)
DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))


def update_operation(deployment_id, driver=DB, **kwargs):
    '''Update the the operation in the deployment

    :param deployment_id: the string ID of the deployment
    :param driver: the backend driver to use to get the deployments
    :param kwargs: the key/value pairs to write into the operation

    Note: exposed in common.tasks as a celery task
    '''
    if kwargs:
        if utils.is_simulation(deployment_id):
            driver = SIMULATOR_DB
        delta = {'operation': dict(kwargs)}
        try:
            driver.save_deployment(deployment_id, delta, partial=True)
        except db.ObjectLockedError:
            LOG.warn("Object lock collision in update_operation on "
                     "Deployment %s", deployment_id)
            raise
