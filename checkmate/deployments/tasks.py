'''
Deployments Asynchronous tasks
'''
import logging
import os

from celery.task import task

from checkmate import celeryglobal as celery
from checkmate import db
from checkmate import utils
from checkmate.common import tasks as common_tasks
from checkmate.common import statsd
from checkmate.deployments import Manager
from checkmate.db.common import ObjectLockedError
from checkmate.deployment import Deployment
from checkmate.exceptions import CheckmateException


LOG = logging.getLogger(__name__)
DRIVERS = {}
DB = DRIVERS['default'] = db.get_driver()
SIMULATOR_DB = DRIVERS['simulation'] = db.get_driver(
    connection_string=os.environ.get(
        'CHECKMATE_SIMULATOR_CONNECTION_STRING',
        os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')
    )
)

LOCK_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_LOCK_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING')))

MANAGERS = {'deployments': Manager(DRIVERS)}


@task(base=celery.SingleTask, default_retry_delay=2, max_retries=10,
    lock_db=LOCK_DB, lock_key="async_dep_writer:{args[0]}", lock_timeout=5)
def reset_failed_resource_task(deployment_id, resource_id):
    MANAGERS['deployments'].reset_failed_resource(deployment_id, resource_id)


@task
@statsd.collect
def process_post_deployment(deployment, request_context, driver=DB):
    '''Assess deployment, then create and trigger a workflow.'''
    utils.match_celery_logging(LOG)

    deployment = Deployment(deployment)

    #Assess work to be done & resources to be created
    parsed_deployment = MANAGERS['deployments'].plan(deployment,
                                                     request_context)

    # Create a 'new deployment' workflow
    MANAGERS['deployments'].deploy(parsed_deployment, request_context)

    #Trigger the workflow in the queuing service
    async_task = MANAGERS['deployments'].execute(deployment['id'])
    LOG.debug("Triggered workflow (task='%s')", async_task)


@task
@statsd.collect
def update_operation(deployment_id, driver=DB, **kwargs):
    '''Wrapper for common_tasks.update_operation.'''
    # TODO(any): Deprecate this
    return common_tasks.update_operation(deployment_id, driver=driver,
                                         **kwargs)


@task(default_retry_delay=2, max_retries=60)
@statsd.collect
def delete_deployment_task(dep_id, driver=DB):
    """Mark the specified deployment as deleted."""
    utils.match_celery_logging(LOG)
    if utils.is_simulation(dep_id):
        driver = SIMULATOR_DB
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

    common_tasks.update_operation.delay(dep_id, status="COMPLETE",
                                        deployment_status="DELETED",
                                        complete=len(deployment.get(
                                                     'resources', {})),
                                        driver=driver)


@task(default_retry_delay=0.25, max_retries=4)
@statsd.collect
def alt_resource_postback(contents, deployment_id, driver=DB):
    '''This is just an argument shuffle to make it easier
    to chain this with other tasks.
    '''
    utils.match_celery_logging(LOG)
    if utils.is_simulation(deployment_id):
        driver = SIMULATOR_DB
    resource_postback.delay(deployment_id, contents, driver=driver)


@task(default_retry_delay=0.25, max_retries=4)
@statsd.collect
def update_all_provider_resources(provider, deployment_id, status,
                                  message=None, trace=None, driver=DB):
    '''Given a deployment, update all resources
    associated with a given provider
    '''
    utils.match_celery_logging(LOG)
    if utils.is_simulation(deployment_id):
        driver = SIMULATOR_DB
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
    '''Exposes DeploymentsManager.postback as a task.'''
    utils.match_celery_logging(LOG)
    MANAGERS['deployments'].postback(deployment_id, contents)


@task(default_retry_delay=0.5, max_retries=6)
@statsd.collect
def resource_postback(deployment_id, contents, driver=DB):
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
    if utils.is_simulation(deployment_id):
        driver = SIMULATOR_DB

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
            if r_status == "ERROR":
                r_msg = value.get('error-message')
                utils.write_path(updates, 'resources/%s/error-message' % r_id,
                                 r_msg)
                value.pop('error-message', None)
                updates['status'] = "FAILED"
                updates['error-message'] = deployment.get('error-message', [])
                if r_msg not in updates['error-message']:
                    updates['error-message'].append(r_msg)

    # Create new contents dict if values existed
    # TODO(any): make this smarter
    new_contents = {}
    for key, value in contents.items():
        if value:
            new_contents[key] = value

    if new_contents:
        deployment.on_resource_postback(new_contents, target=updates)

    if updates:
        body, secrets = utils.extract_sensitive_data(updates)
        try:
            driver.save_deployment(deployment_id, body, secrets, partial=True)

            LOG.debug("Updated deployment %s with post-back", deployment_id,
                      extra=dict(data=contents))
        except ObjectLockedError:
            LOG.warn("Object lock collision in resource_postback on "
                     "Deployment %s", deployment_id)
            resource_postback.retry()
