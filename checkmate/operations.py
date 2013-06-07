'''
Common code, utilities, and classes for managing the 'operation' object
'''
import logging
import os

from checkmate import db
from checkmate import utils
from checkmate.deployment import Deployment

LOG = logging.getLogger(__name__)
DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))


def add_operation(deployment, type_name, **kwargs):
    '''Adds an operation to a deployment

    Moves any existing operation to history

    :param deployment: dict or Deployment
    :param type_name: the operation name (BUILD, DELETE, etc...)
    :param kwargs: additional kwargs to add to operation
    :returns: operation
    '''
    if 'operation' in deployment:
        if 'operations-history' not in deployment:
            deployment['operations-history'] = []
        history = deployment.get('operations-history')
        history.insert(0, deployment.pop('operation'))
    operation = {'type': type_name}
    operation.update(**kwargs)
    deployment['operation'] = operation
    return operation


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
        deployment = driver.get_deployment(deployment_id, with_secrets=True)
        try:
            if 'status' in kwargs:
                if kwargs['status'] != deployment['operation']['status']:
                    deployment = Deployment(deployment)
                    delta['display-outputs'] = deployment.calculate_outputs()
        except KeyError:
            LOG.warn("Cannot update deployment outputs: %s", deployment_id)
        driver.save_deployment(deployment_id, delta, partial=True)
