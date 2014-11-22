# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""All the Deployments things."""

from checkmate.deployments.manager import Manager
from checkmate.deployments.router import Router
from checkmate.deployments.planner import Planner

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
def update_operation(deployment_id, workflow_id, driver=None, **kwargs):
    """DEPRECATED: for compatibility with pre v0.14."""
    if driver:
        return _update_operation(deployment_id, workflow_id, driver=driver,
                                 **kwargs)
    else:
        return _update_operation(deployment_id, workflow_id, **kwargs)


@task(default_retry_delay=4, max_retries=30)
def delete_deployment_task(dep_id, driver=None):
    """DEPRECATED: for compatibility with pre v0.14."""
    if driver:
        return _delete_deployment_task(dep_id, driver=driver)
    else:
        return _delete_deployment_task(dep_id)


@task(default_retry_delay=0.25, max_retries=4)
def alt_resource_postback(contents, deployment_id, driver=None):
    """DEPRECATED: for compatibility with pre v0.14."""
    if driver:
        return _alt_resource_postback(contents, deployment_id, driver=driver)
    else:
        return _alt_resource_postback(contents, deployment_id)


@task(default_retry_delay=0.25, max_retries=4)
def update_all_provider_resources(provider, deployment_id, status,
                                  message=None, trace=None, driver=None):
    """DEPRECATED: for compatibility with pre v0.14."""
    if driver:
        return _update_all_provider_resources(provider, deployment_id, status,
                                              message=message, trace=trace,
                                              driver=driver)
    else:
        return _update_all_provider_resources(provider, deployment_id, status,
                                              message=message, trace=trace)


@task(default_retry_delay=0.5, max_retries=6)
def resource_postback(deployment_id, contents, driver=None):
    """DEPRECATED: for compatibility with pre v0.14."""
    if driver:
        return _resource_postback(deployment_id, contents, driver=driver)
    else:
        return _resource_postback(deployment_id, contents)
