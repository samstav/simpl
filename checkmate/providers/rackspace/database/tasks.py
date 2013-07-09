# encoding: utf-8
"""
Rackspace Cloud Databases provider tasks
"""
from celery.task import task

from checkmate import exceptions
from checkmate.providers.base import ProviderTask
from checkmate.providers.rackspace.database import Manager
from checkmate.providers.rackspace.database import Provider

MANAGER = Manager()


@task(base=ProviderTask, default_retry_delay=30, max_retries=120,
      acks_late=True, provider=Provider)
def wait_on_build(context, instance_id, region, api=None, callback=None):
    '''Checks db instance build succeeded.'''
    data = {}
    try:
        data['status'] = MANAGER.wait_on_build(instance_id, api, callback,
                                                   context.get('simulation',
                                                               False))
        if data['status'] in ['ACTIVE', 'DELETED']:
            data['status-message'] = ''
    except StandardError as exc:
        data['status'] = 'ERROR'
        data['status-message'] = 'Error waiting on resource to build'
        data['error-message'] = exc.message
        raise exc
    except exceptions.CheckmateException as exc:
        data['status'] = 'ERROR'
        data['status-message'] = 'Instance went into status ERROR'
        raise exceptions.CheckmateRedoResourceException(exc)
    finally:
        return data


@task(base=ProviderTask, provider=Provider)
def sync_resource_task(context, resource, resource_key, api=None,
                        callback=None):
    results = MANAGER.sync_resource(resource, resource_key,
                                        sync_resource_task2.api,
                                        context.get('simulation', False))
    return results
