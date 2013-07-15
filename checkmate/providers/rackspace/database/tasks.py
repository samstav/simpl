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
def wait_on_build(context, instance_id, region, api=None, callback=None):
    '''Checks db instance build succeeded.'''
    return Manager.wait_on_build(instance_id, wait_on_build.api,
                                 wait_on_build.partial,
                                 context.simulation)


# Disable on api and callback.  Suppress num args
# pylint: disable=W0613,R0913
@task(base=ProviderTask, provider=Provider)
def sync_resource_task(context, resource, api=None, callback=None):
    '''Task to handle syncing remote status with checkmate status.'''
    return Manager.sync_resource(resource, sync_resource_task.api,
                                 context.simulation)


# Disable pylint on api and callback as their passed in from ProviderTask
# pylint: disable=W0613
@task(base=ProviderTask, default_retry_delay=10, max_retries=2,
      provider=Provider)
def create_instance(context, instance_name, flavor, size, databases, region,
                    api=None, callback=None):
    '''Creates a Cloud Database instance with optional initial databases.

    :param databases: an array of dictionaries with keys to set the database
    name, character set and collation.  For example:

        databases=[{'name': 'db1'},
                   {'name': 'db2', 'character_set': 'latin5',
                    'collate': 'latin5_turkish_ci'}]
    '''
    return Manager.create_instance(instance_name, flavor, size,
                                   databases, context, create_instance.api,
                                   create_instance.partial,
                                   context.simulation
