'''
All the Deployments things
'''
from .manager import Manager
from .router import Router
from .plan import Plan

# Legacy compatibility with Celery tasks for deployments
#
# DEPRECATED - DO NOT ADD/EDIT.
# REMOVE once all existing deployments before June 2013 are updated
from celery.task import task
from .tasks import (
    update_operation as _update_operation,
    delete_deployment_task as _delete_deployment_task,
    alt_resource_postback as _alt_resource_postback,
    update_all_provider_resources as _update_all_provider_resources,
    resource_postback as _resource_postback,
)


@task
def update_operation(deployment_id, driver=None, **kwargs):
    '''DEPRECATED: for compatibility with pre v0.14'''
    if driver:
        return _update_operation(deployment_id, driver=driver, **kwargs)
    else:
        return _update_operation(deployment_id, **kwargs)


@task(default_retry_delay=2, max_retries=60)
def delete_deployment_task(dep_id, driver=None):
    '''DEPRECATED: for compatibility with pre v0.14'''
    if driver:
        return _delete_deployment_task(dep_id, driver=driver)
    else:
        return _delete_deployment_task(dep_id)


@task(default_retry_delay=0.25, max_retries=4)
def alt_resource_postback(contents, deployment_id, driver=None):
    '''DEPRECATED: for compatibility with pre v0.14'''
    if driver:
        return _alt_resource_postback(contents, deployment_id, driver=driver)
    else:
        return _alt_resource_postback(contents, deployment_id)


@task(default_retry_delay=0.25, max_retries=4)
def update_all_provider_resources(provider, deployment_id, status,
                                  message=None, error_trace=None, driver=None):
    '''DEPRECATED: for compatibility with pre v0.14'''
    if driver:
        return _update_all_provider_resources(provider, deployment_id, status,
                                              message=message,
                                              error_trace=error_trace,
                                              driver=driver)
    else:
        return _update_all_provider_resources(provider, deployment_id, status,
                                              message=message,
                                              error_trace=error_trace)


@task(default_retry_delay=0.5, max_retries=6)
def resource_postback(deployment_id, contents, driver=None):
    '''DEPRECATED: for compatibility with pre v0.14'''
    if driver:
        return _resource_postback(deployment_id, contents, driver=driver)
    else:
        return _resource_postback(deployment_id, contents)
