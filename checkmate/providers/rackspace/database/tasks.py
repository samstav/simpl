# encoding: utf-8
"""
Rackspace Cloud Databases provider tasks
"""
from celery.task import task

from checkmate.providers.base import ProviderTask
from checkmate.providers.rackspace.database import Manager
from checkmate.providers.rackspace.database import Provider


# Disable pylint on api and callback as their passed in from ProviderTask
# pylint: disable=W0613
@task(base=ProviderTask, default_retry_delay=30, max_retries=120,
      acks_late=True, provider=Provider)
def wait_on_build(context, instance_id, api=None, callback=None):
    '''Checks db instance build succeeded.'''
    return Manager.wait_on_build(instance_id, wait_on_build.api,
                                 wait_on_build.partial,
                                 context.simulation)


# Disable pylint on api and callback as their passed in from ProviderTask
# pylint: disable=W0613
@task(base=ProviderTask, provider=Provider)
def sync_resource_task(context, resource, api=None, callback=None):
    '''Task to handle syncing remote status with checkmate status.'''
    return Manager.sync_resource(resource, sync_resource_task.api,
                                 context.simulation)
