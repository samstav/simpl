import logging

from checkmate.providers import ProviderBase
from checkmate.utils import match_celery_logging

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    name = 'files'
    vendor = 'rackspace'

"""
  Celery tasks to manipulate Rackspace Cloud Files.
"""

import cloudfiles
from celery.task import task


def _connect(deployment):
    try:
        api = cloudfiles.get_connection(deployment['username'],
                                         deployment['apikey'],
                                         timeout=15)
    except cloudfiles.errors.AuthenticationFailed, e:
        LOG.error('Cloud Files authentication failed.')
        raise e
    except cloudfiles.errors.AuthenticationError, e:
        LOG.error('Cloud Files authentication error.')
        raise e
    except Exception, e:
        LOG.error('Error connecting to Cloud Files: %s' % e)
        raise e

    return api

""" Celery tasks """


@task
def create_container(deployment, name, api=None):
    """Creates a new container"""
    match_celery_logging(LOG)
    if api is None:
        api = _connect(deployment)

    meta = deployment.get("metadata", None)
        if meta:
            new_meta = {}
            for key in meta:
                new_meta["x-container-meta-"+key] = meta[key]
            api.create_container(name, metadata=new_meta)
        else:
            api.create_container(name)
        LOG.debug('Created container %s.' % name)
    except cloudfiles.errors.InvalidContainerName as e:
        LOG.error('Invalid container name: %s' % name)
        raise e
    except cloudfiles.errors.ContainerExists as e:
        LOG.error('Container %s already exists.' % name)
        raise e


@task
def delete_container(deployment, name, api=None):
    """Deletes a container"""
    match_celery_logging(LOG)
    if api is None:
        api = _connect(deployment)

    try:
        api.delete_container(name)
        LOG.debug('Deleted container %s.' % name)
    except cloudfiles.errors.ContainerNotEmpty as e:
        LOG.error('Cannot delete container %s because it is not empty.' % name)
        raise e
    except cloudfiles.errors.NoSuchContainer as e:
        LOG.error('Canot delete container %s because it does not exist.' %
                name)
        raise e
