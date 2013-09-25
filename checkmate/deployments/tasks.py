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

"""
Deployments Asynchronous tasks
"""

import logging

from celery.task import task

from checkmate import celeryglobal as celery
from checkmate import db
from checkmate import utils

from checkmate.common import statsd
from checkmate.common import tasks as common_tasks
from checkmate.db.common import ObjectLockedError
from checkmate.deployment import Deployment
from checkmate.deployments import Manager
from checkmate.exceptions import CheckmateException
from checkmate import operations


LOG = logging.getLogger(__name__)

LOCK_DB = db.get_lock_db_driver()

MANAGERS = {'deployments': Manager()}


@task(base=celery.SingleTask, default_retry_delay=2, max_retries=10,
      lock_db=LOCK_DB, lock_key="async_dep_writer:{args[0]}", lock_timeout=5)
def reset_failed_resource_task(deployment_id, resource_id):
    """Creates a copy of a failed resource and appends it at the end of
        the resources collection.

    :param deployment_id:
    :param resource_id:
    :return:
    """
    MANAGERS['deployments'].reset_failed_resource(deployment_id, resource_id)


@task(default_retry_delay=2, max_retries=50)
def wait_for_resource_status(deployment_id, resource_id, expected_status):
    """Wait for a deployment resource to move to expected_status
    :param deployment_id: deployment containing the resource
    :param resource_id: resource to check the status for
    :param expected_status: expected status
    :return:
    """
    deployment = MANAGERS['deployments'].get_deployment(deployment_id)
    resource = deployment['resources'].get(resource_id)
    if resource and resource.get('status') != expected_status:
        msg = "Resource is in %s status. Waiting for %s resource" % (
            resource.get('status'), expected_status)
        wait_for_resource_status.retry(exc=CheckmateException(msg))


@task
@statsd.collect
def process_post_deployment(deployment, context, driver=None):
    """Assess deployment, then create and trigger a workflow."""
    utils.match_celery_logging(LOG)

    if driver is not None:
        LOG.warn("LEGACY TASK: process_post_deployment called with driver %s "
                 "passed in. This parameter has been deprecated.", driver)

    deployment = Deployment(deployment)

    #Assess work to be done & resources to be created
    parsed_deployment = MANAGERS['deployments'].plan(deployment, context)

    # Create a 'new deployment' workflow
    operation = MANAGERS['deployments'].deploy(parsed_deployment, context)

    #Trigger the workflow in the queuing service
    async_task = MANAGERS['deployments'].execute(
        deployment['id'], context, timeout=operation.get('estimated-duration'))
    LOG.debug("Triggered workflow (task='%s')", async_task)


@task
@statsd.collect
def update_operation(deployment_id, workflow_id, driver=None, **kwargs):
    """Wrapper for common_tasks.update_operation."""
    # TODO(any): Deprecate this
    driver = db.get_driver(api_id=deployment_id)
    return common_tasks.update_operation(deployment_id, workflow_id,
                                         driver=driver, **kwargs)


@task(default_retry_delay=2, max_retries=60)
@statsd.collect
def delete_deployment_task(dep_id, driver=None):
    """Mark the specified deployment as deleted."""
    utils.match_celery_logging(LOG)
    driver = db.get_driver(api_id=dep_id)
    deployment = Deployment(driver.get_deployment(dep_id))
    if not deployment:
        raise CheckmateException("Could not finalize delete for deployment "
                                 "%s. The deployment was not found.")
    if "resources" in deployment:
        deletes = []
        for key, resource in deployment.get('resources').items():
            if not str(key).isdigit():
                deletes.append(key)
            else:
                updates = {}
                if resource.get('status', 'DELETED') != 'DELETED':
                    updates['status-message'] = (
                        'WARNING: Resource should have been in status DELETED '
                        'but was in %s.' % resource.get('status')
                    )
                    updates['status'] = 'ERROR'
                    contents = {
                        'instance:%s' % resource['index']: updates,
                    }
                    resource_postback.delay(dep_id, contents, driver=driver)

    common_tasks.update_operation.delay(dep_id,
                                        operations.current_workflow_id(
                                            deployment),
                                        status="COMPLETE",
                                        driver=driver,
                                        deployment_status="DELETED",
                                        complete=len(deployment.get(
                                                     'resources', {}))
                                        )


@task(default_retry_delay=0.25, max_retries=4)
@statsd.collect
def alt_resource_postback(contents, deployment_id, driver=None):
    """This is just an argument shuffle to make it easier
    to chain this with other tasks.
    """
    utils.match_celery_logging(LOG)
    driver = db.get_driver(api_id=deployment_id)
    resource_postback.delay(deployment_id, contents, driver=driver)


@task(default_retry_delay=0.25, max_retries=4)
@statsd.collect
def update_all_provider_resources(provider, deployment_id, status,
                                  message=None, trace=None, driver=None):
    """Given a deployment, update all resources
    associated with a given provider
    """
    utils.match_celery_logging(LOG)
    driver = db.get_driver(api_id=deployment_id)
    dep = driver.get_deployment(deployment_id)
    if dep:
        rupdate = {'status': status}
        if message:
            rupdate['status-message'] = message
        ret = {}
        for resource in [res for res in dep.get('resources', {}).values()
                         if res.get('provider') == provider]:
            rkey = "instance:%s" % resource.get('index')
            ret.update({rkey: rupdate})
        if ret:
            resource_postback.delay(deployment_id, ret, driver=driver)
            return ret


@task(default_retry_delay=0.5, max_retries=6)
@statsd.collect
def postback(deployment_id, contents):
    """Exposes DeploymentsManager.postback as a task."""
    utils.match_celery_logging(LOG)
    MANAGERS['deployments'].postback(deployment_id, contents)


@task(default_retry_delay=0.5, max_retries=6)
@statsd.collect
def resource_postback(deployment_id, contents, driver=None, check_results=None):
    #FIXME: we need to receive a context and check access
    """Accepts back results from a remote call and updates the deployment with
    the result data for a specific resource.

    The data updated can be:
    - a value: usually not tied to a resource or relation
    - an instance value (with the instance id appended with a colon):]
        {'instance:0':
            {'field_name': value}
        }
    - an interface value (under interfaces/interface_name)
        {'instance:0':
            {'interfaces':
                {'mysql':
                    {'username': 'johnny', ...}
                }
            }
        }
    - a connection value (under connection.name):
        {'connection:web-backend':
            {'interface': 'mysql',
            'field_name': value}
        }
        Note: connection 'interface' is always included.
        Note: connection:host always refers to the hosting connection if there

    The contents are a hash (dict) of all the above
    """
    utils.match_celery_logging(LOG)
    driver = db.get_driver(api_id=deployment_id)

    deployment = driver.get_deployment(deployment_id, with_secrets=True)
    deployment = Deployment(deployment)
    updates = {}

    assert isinstance(contents, dict), "Must postback data in dict"

    # Set status of resource if post_back includes status
    for key, value in contents.items():
        if 'status' in value:
            r_id = key.split(':')[1]
            r_status = value.get('status')
            utils.write_path(updates, 'resources/%s/status' % r_id, r_status)
            # Don't want to write status to resource instance
            value.pop('status', None)
            if 'error-message' in value:
                r_msg = value.get('error-message')
                utils.write_path(updates, 'resources/%s/error-message' % r_id,
                                 r_msg)
                value.pop('error-message', None)
            if r_status == "ERROR":
                if deployment.fsm.permitted("FAILED"):
                    updates['status'] = 'FAILED'

    # Create new contents dict if values existed
    # TODO(any): make this smarter
    new_contents = {}
    for key, value in contents.items():
        if value:
            new_contents[key] = value

    if new_contents:
        deployment.on_resource_postback(new_contents, target=updates)

    if updates and check_results is None:
        if check_results is None:
            body, secrets = utils.extract_sensitive_data(updates)
            try:
                driver.save_deployment(deployment_id, body, secrets, partial=True,
                                       tenant_id=deployment['tenantId'])

                LOG.debug("Updated deployment %s with post-back", deployment_id,
                          extra=dict(data=contents))
            except ObjectLockedError:
                LOG.warn("Object lock collision in resource_postback on "
                         "Deployment %s", deployment_id)
                resource_postback.retry()
        else:
            check_results = updates
