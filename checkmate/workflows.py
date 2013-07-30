"""Workflow handling

This module uses SpiffWorkflow to create, manage, and run workflows for
Checkmate
"""
# pylint: disable=E0611
import bottle
import logging
import os
import uuid

from SpiffWorkflow import Workflow as SpiffWorkflow, Task
from SpiffWorkflow.storage import DictionarySerializer

from checkmate.common import tasks
from checkmate import db
from checkmate import deployment as cm_dep
from checkmate import orchestrator
from checkmate import workflow as cm_wf
from checkmate import workflows_new as workflow_tasks
from checkmate.db import (
    InvalidKeyError,
    ObjectLockedError,
)
from checkmate import utils

DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))

LOG = logging.getLogger(__name__)


#
# Workflows
#
@bottle.get('/workflows')
@utils.with_tenant
@utils.formatted_response('workflows', with_pagination=True)
def get_workflows(tenant_id=None, offset=None, limit=None, driver=DB):
    """Get all workflows for the given Tenant ID."""
    if 'with_secrets' in bottle.request.query:
        if bottle.request.context.is_admin is True:
            LOG.info("Administrator accessing workflows with secrets: %s",
                     bottle.request.context.username)
            results = driver.get_workflows(tenant_id=tenant_id,
                                           with_secrets=True,
                                           offset=offset, limit=limit)
        else:
            bottle.abort(
                403, "Administrator privileges needed for this operation")
    else:
        results = driver.get_workflows(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit
        )
    return results


def safe_workflow_save(obj_id, body, secrets=None, tenant_id=None, driver=DB):
    """Locks, saves, and unlocks a workflow."""
    # TODO(any): should this be moved to the db layer?
    results = None
    try:
        _, key = driver.lock_workflow(obj_id)
        results = driver.save_workflow(obj_id, body, secrets=secrets,
                                       tenant_id=tenant_id)
        driver.unlock_workflow(obj_id, key)

    except ValueError:
        #the object has never been saved
        results = driver.save_workflow(obj_id, body, secrets=secrets,
                                       tenant_id=tenant_id)
    except ObjectLockedError:
        bottle.abort(
            404, "The workflow is already locked, cannot obtain lock.")

    return results


@bottle.post('/workflows')
@utils.with_tenant
def add_workflow(tenant_id=None, driver=DB):
    """Post the workflow provided in the request."""
    entity = utils.read_body(bottle.request)
    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if db.any_id_problems(entity['id']):
        bottle.abort(406, db.any_id_problems(entity['id']))

    body, secrets = utils.extract_sensitive_data(entity)

    key = None
    results = None
    if driver.get_workflow(entity['id']):
        # TODO(any): this case should be considered invalid
        # trying to add an existing workflow
        _, key = driver.lock_workflow(entity['id'])

    results = driver.save_workflow(entity['id'], body, secrets=secrets)

    if key:
        driver.unlock_workflow(entity['id'], key)

    return utils.write_body(results, bottle.request, bottle.response)


@bottle.route('/workflows/<api_id>', method=['POST', 'PUT'])
@utils.with_tenant
def save_workflow(api_id, tenant_id=None, driver=DB):
    """Save the workflow passed in the request's body."""
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB
    entity = utils.read_body(bottle.request)

    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if db.any_id_problems(api_id):
        bottle.abort(406, db.any_id_problems(api_id))
    if 'id' not in entity:
        entity['id'] = str(api_id)

    body, secrets = utils.extract_sensitive_data(entity)

    existing = driver.get_workflow(api_id)
    results = safe_workflow_save(str(api_id), body, secrets=secrets,
                                 tenant_id=tenant_id, driver=driver)
    if existing:
        bottle.response.status = 200  # OK - updated
    else:
        bottle.response.status = 201  # Created

    return utils.write_body(results, bottle.request, bottle.response)


@bottle.get('/workflows/<api_id>')
@utils.with_tenant
def get_workflow(api_id, tenant_id=None, driver=DB):
    """Get the status of the worfklow identified by id."""
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB

    if 'with_secrets' in bottle.request.query:
        LOG.info("Administrator accessing workflow %s with secrets: %s",
                 api_id, bottle.request.context.username)
        results = driver.get_workflow(api_id, with_secrets=True)
    else:
        results = driver.get_workflow(api_id)
    if not results:
        bottle.abort(404, 'No workflow with id %s' % api_id)
    if 'id' not in results:
        results['id'] = str(api_id)
    if tenant_id is not None and tenant_id != results.get('tenantId'):
        LOG.warning("Attempt to access workflow %s from wrong tenant %s by "
                    "%s", api_id, tenant_id, bottle.request.context.username)
        bottle.abort(404)
    return utils.write_body(results, bottle.request, bottle.response)


@bottle.get('/workflows/<api_id>/status')
@utils.with_tenant
def get_workflow_status(api_id, tenant_id=None, driver=DB):
    """Get the status of the worfklow identified by api_id."""
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB
    entity = driver.get_workflow(api_id)
    if not entity:
        bottle.abort(404, 'No workflow with id %s' % api_id)
    serializer = DictionarySerializer()
    sw_wf = SpiffWorkflow.deserialize(serializer, entity)
    return utils.write_body(cm_wf.get_SpiffWorkflow_status(sw_wf),
                            bottle.request, bottle.response)


@bottle.route('/workflows/<api_id>/+execute', method=['GET', 'POST'])
@utils.with_tenant
def execute_workflow(api_id, tenant_id=None, driver=DB):
    """Process a checkmate deployment workflow

    Executes and moves the workflow forward.
    Retrieves results (final or intermediate) and updates them into
    deployment.

    :param api_id: checkmate workflow id
    """
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB
    entity = driver.get_workflow(api_id)
    if not entity:
        bottle.abort(404, 'No workflow with id %s' % api_id)

    async_call = orchestrator.run_workflow.delay(api_id, timeout=1800,
                                                 driver=driver)
    LOG.debug("Executed a task to run workflow '%s'", async_call)
    entity = driver.get_workflow(api_id)
    return utils.write_body(entity, bottle.request, bottle.response)


@bottle.route('/workflows/<api_id>/+pause', method=['GET', 'POST'])
@utils.with_tenant
def pause_workflow(api_id, tenant_id=None, driver=DB):
    '''Pauses the workflow.
    Updates the operation status to pauses when done

    :param api_id: checkmate workflow id
    '''
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB
    workflow = driver.get_workflow(api_id)
    if not workflow:
        bottle.abort(404, 'No workflow with id %s' % api_id)

    dep_id = workflow["attributes"]["deploymentId"] or api_id
    deployment = driver.get_deployment(dep_id)
    deployment = cm_dep.Deployment(deployment)

    operation = deployment.get("operation")

    if (operation and operation.get('action') != 'PAUSE' and
            operation['status'] not in ('PAUSED', 'COMPLETE')):
        tasks.update_operation.delay(dep_id, deployment.current_workflow_id(),
                                     driver=driver, action='PAUSE')
        workflow_tasks.pause_workflow.delay(api_id, driver)
    return utils.write_body(workflow, bottle.request, bottle.response)


@bottle.route('/workflows/<api_id>/+resume', method=['GET', 'POST'])
@utils.with_tenant
def resume_workflow(api_id, tenant_id=None, driver=DB):
    """Process a checkmate deployment workflow

    Executes the workflow again

    :param api_id: checkmate workflow id
    """
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB
    workflow = driver.get_workflow(api_id)
    if not workflow:
        bottle.abort(404, 'No workflow with id %s' % api_id)

    dep_id = workflow["attributes"]["deploymentId"] or api_id
    deployment = driver.get_deployment(dep_id)
    operation = deployment.get("operation")
    if operation and operation.get('status') == 'PAUSED':
        async_call = orchestrator.run_workflow.delay(api_id, timeout=1800,
                                                     driver=driver)
        LOG.debug("Executed a task to run workflow '%s'", async_call)
        workflow = driver.get_workflow(api_id)
    return utils.write_body(workflow, bottle.request, bottle.response)


@bottle.route('/workflows/<api_id>/+retry-failed-tasks', method=['GET',
                                                                 'POST'])
@utils.with_tenant
def retry_all_failed_tasks(api_id, tenant_id=None, driver=DB):
    """Retry all retriable tasks."""
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB

    workflow = driver.get_workflow(api_id)
    if not workflow:
        bottle.abort(404, 'No workflow with id %s' % api_id)

    serializer = DictionarySerializer()
    sw_wf = SpiffWorkflow.deserialize(serializer, workflow)

    dep_id = workflow["attributes"]["deploymentId"] or api_id
    deployment = driver.get_deployment(dep_id)
    operation = deployment.get("operation")

    if operation.get("errors"):
        retriable_errors = filter(lambda x: x.get("retriable", False),
                                  operation.get("errors"))
        for error in retriable_errors:
            task_id = error["task-id"]
            task = sw_wf.get_task(task_id)
            LOG.debug("Resetting task %s for workflow %s", task_id, api_id)
            cm_wf.reset_task_tree(task)

        cm_wf.update_workflow_status(sw_wf, tenant_id=tenant_id)
        entity = sw_wf.serialize(serializer)
        body, secrets = utils.extract_sensitive_data(entity)
        body['tenantId'] = workflow.get('tenantId', tenant_id)
        body['id'] = api_id
        workflow = safe_workflow_save(api_id, body, secrets=secrets,
                                      tenant_id=tenant_id, driver=driver)
    return utils.write_body(workflow, bottle.request, bottle.response)


@bottle.route('/workflows/<api_id>/+resume-failed-tasks', method=['GET',
                                                                 'POST'])
@utils.with_tenant
def resume_all_failed_tasks(api_id, tenant_id=None, driver=DB):
    """Check all tasks: if retriable, resume the task."""
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB

    workflow = driver.get_workflow(api_id)
    if not workflow:
        bottle.abort(404, 'No workflow with id %s' % api_id)

    dep_id = workflow["attributes"]["deploymentId"] or api_id
    deployment = driver.get_deployment(dep_id)
    operation = deployment.get("operation")

    if operation.get("errors"):
        retriable_errors = filter(lambda x: x.get("resumable", False),
                                  operation.get("errors"))
        for error in retriable_errors:
            task_id = error["task-id"]
            LOG.debug("Resuming task %s for workflow %s", task_id, api_id)
            orchestrator.run_one_task.delay(bottle.request.context, api_id,
                                            task_id, timeout=10,
                                            driver=driver)

        workflow = driver.get_workflow(api_id)

    return utils.write_body(workflow, bottle.request, bottle.response)


@bottle.post('/workflows/<workflow_id>/specs/<spec_id>')
@utils.with_tenant
def post_workflow_spec(workflow_id, spec_id, tenant_id=None, driver=DB):
    """Update a workflow spec

    :param workflow_id: checkmate workflow id
    :param spec_id: checkmate workflow spec id (a string)
    """
    if utils.is_simulation(workflow_id):
        driver = SIMULATOR_DB
    entity = utils.read_body(bottle.request)

    # Extracting with secrets
    workflow = driver.get_workflow(workflow_id, with_secrets=True)
    if not workflow:
        bottle.abort(404, 'No workflow with id %s' % workflow_id)

    spec = workflow['wf_spec']['task_specs'].get(spec_id)
    if not spec:
        bottle.abort(404, 'No spec with id %s' % spec_id)

    LOG.debug("Updating spec '%s' in workflow '%s'", spec_id, workflow_id,
              extra=dict(data=dict(old=spec, new=entity)))
    workflow['wf_spec']['task_specs'][spec_id] = entity

    # Save workflow (with secrets)
    body, secrets = utils.extract_sensitive_data(workflow)
    body['tenantId'] = workflow.get('tenantId', tenant_id)
    body['id'] = workflow_id
    safe_workflow_save(workflow_id, body, secrets=secrets, tenant_id=tenant_id,
                       driver=driver)

    return utils.write_body(entity, bottle.request, bottle.response)


#
# Workflow Tasks
#
@bottle.get('/workflows/<api_id>/tasks/<task_id:int>')
@utils.with_tenant
def get_workflow_task(api_id, task_id, tenant_id=None, driver=DB):
    """Get a workflow task

    :param api_id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB
    if 'with_secrets' in bottle.request.query:  # TODO(any): verify admin-ness
        entity = driver.get_workflow(api_id, with_secrets=True)
    else:
        entity = driver.get_workflow(api_id)
    if not entity:
        bottle.abort(404, 'No workflow with id %s' % api_id)

    serializer = DictionarySerializer()
    sw_wf = SpiffWorkflow.deserialize(serializer, entity)

    task = sw_wf.get_task(task_id)
    if not task:
        bottle.abort(404, 'No task with id %s' % task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = api_id  # so we know which workflow it came from
    spec = task.task_spec.serialize(serializer)
    data['spec'] = spec  # include a copy of the spec
    return utils.write_body(data, bottle.request, bottle.response)


@bottle.post('/workflows/<api_id>/tasks/<task_id:int>')
@utils.with_tenant
def post_workflow_task(api_id, task_id, tenant_id=None, driver=DB):
    """Update a workflow task

    Attributes that can be updated are:
    - attributes
    - state
    - internal_attributes

    :param api_id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB
    entity = utils.read_body(bottle.request)

    # Extracting with secrets
    workflow = driver.get_workflow(api_id, with_secrets=True)
    if not workflow:
        bottle.abort(404, 'No workflow with id %s' % api_id)

    serializer = DictionarySerializer()
    sw_wf = SpiffWorkflow.deserialize(serializer, workflow)

    task = sw_wf.get_task(task_id)
    if not task:
        bottle.abort(404, 'No task with id %s' % task_id)

    if 'attributes' in entity:
        if not isinstance(entity['attributes'], dict):
            bottle.abort(406, "'attribues' must be a dict")
        # Don't do a simple overwrite since incoming may not have secrets and
        # we don't want to stomp on them
        body, secrets = utils.extract_sensitive_data(task.attributes)
        updated = utils.merge_dictionary(secrets or {}, entity['attributes'])
        task.attributes = updated

    if 'internal_attributes' in entity:
        if not isinstance(entity['internal_attributes'], dict):
            bottle.abort(406, "'internal_attribues' must be a dict")
        task.internal_attributes = entity['internal_attributes']

    if 'state' in entity:
        if not isinstance(entity['state'], (int, long)):
            bottle.abort(406, "'state' must be an int")
        task._state = entity['state']

    # Save workflow (with secrets)
    cm_wf.update_workflow_status(sw_wf, tenant_id=tenant_id)
    serializer = DictionarySerializer()
    body, secrets = utils.extract_sensitive_data(sw_wf.serialize(serializer))
    body['tenantId'] = workflow.get('tenantId', tenant_id)
    body['id'] = api_id

    updated = safe_workflow_save(api_id, body, secrets=secrets,
                                 tenant_id=tenant_id, driver=driver)
    # Updated does not have secrets, so we deserialize that
    serializer = DictionarySerializer()
    sw_wf = SpiffWorkflow.deserialize(serializer, updated)
    task = sw_wf.get_task(task_id)
    results = serializer._serialize_task(task, skip_children=True)
    results['workflow_id'] = api_id
    return utils.write_body(results, bottle.request, bottle.response)


@bottle.route('/workflows/<api_id>/tasks/<task_id:int>/+reset',
              method=['GET', 'POST'])
@utils.with_tenant
def reset_workflow_task(api_id, task_id, tenant_id=None, driver=DB):
    """Reset a Celery workflow task and retry it

    Checks if task is a celery task in waiting state.
    Resets parent to READY and task to FUTURE.
    Removes existing celery task ID.

    :param api_id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB

    workflow = driver.get_workflow(api_id, with_secrets=True)
    if not workflow:
        bottle.abort(404, 'No workflow with id %s' % api_id)

    serializer = DictionarySerializer()
    sw_wf = SpiffWorkflow.deserialize(serializer, workflow)

    task = sw_wf.get_task(task_id)
    if not task:
        bottle.abort(404, 'No task with id %s' % task_id)

    if task.task_spec.__class__.__name__ != 'Celery':
        bottle.abort(406, "You can only reset Celery tasks. This is a '%s' "
                     "task" % task.task_spec.__class__.__name__)

    if task.state != Task.WAITING:
        bottle.abort(406, "You can only reset WAITING tasks. This task is in "
                     "'%s'" % task.get_state_name())

    task.task_spec._clear_celery_task_data(task)

    task._state = Task.FUTURE
    task.parent._state = Task.READY

    cm_wf.update_workflow_status(sw_wf, tenant_id=tenant_id)
    serializer = DictionarySerializer()
    entity = sw_wf.serialize(serializer)
    body, secrets = utils.extract_sensitive_data(entity)
    body['tenantId'] = workflow.get('tenantId', tenant_id)
    body['id'] = api_id
    safe_workflow_save(api_id, body, secrets=secrets, tenant_id=tenant_id,
                       driver=driver)

    task = sw_wf.get_task(task_id)
    if not task:
        bottle.abort(404, 'No task with id %s' % task_id)

    # Return cleaned data (no credentials)
    data = serializer._serialize_task(task, skip_children=True)
    body, secrets = utils.extract_sensitive_data(data)
    body['workflow_id'] = api_id  # so we know which workflow it came from
    return utils.write_body(body, bottle.request, bottle.response)


@bottle.route('/workflows/<api_id>/tasks/<task_id:int>/+reset-task-tree',
              method=['GET', 'POST'])
@utils.with_tenant
def reset_task_tree(api_id, task_id, tenant_id=None, driver=DB):
    '''Resets all the tasks starting from the passed in task_id and going up
    the chain till the root task is reset

    :param api_id: checkmate workflow id
    :param task_id: checkmate workflow task id
    '''
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB

    workflow = driver.get_workflow(api_id, with_secrets=True)
    if not workflow:
        bottle.abort(404, 'No workflow with id %s' % api_id)

    serializer = DictionarySerializer()
    sw_wf = SpiffWorkflow.deserialize(serializer, workflow)

    task = sw_wf.get_task(task_id)
    if not task:
        bottle.abort(404, 'No task with id %s' % task_id)

    if task.task_spec.__class__.__name__ != 'Celery':
        bottle.abort(406, "You can only reset Celery tasks. This is a '%s' "
                     "task" % task.task_spec.__class__.__name__)

    if task.state != Task.WAITING:
        bottle.abort(406, "You can only reset WAITING tasks. This task is in "
                     "'%s'" % task.get_state_name())

    cm_wf.reset_task_tree(task)

    cm_wf.update_workflow_status(sw_wf, tenant_id=tenant_id)
    serializer = DictionarySerializer()
    entity = sw_wf.serialize(serializer)
    body, secrets = utils.extract_sensitive_data(entity)
    body['tenantId'] = workflow.get('tenantId', tenant_id)
    body['id'] = api_id
    updated = safe_workflow_save(api_id, body, secrets=secrets,
                                 tenant_id=tenant_id, driver=driver)

    return utils.write_body(updated, bottle.request, bottle.response)


@bottle.route('/workflows/<workflow_id>/tasks/<task_id:int>/+resubmit',
              method=['GET', 'POST'])
@utils.with_tenant
def resubmit_workflow_task(workflow_id, task_id, tenant_id=None, driver=DB):
    """Reset a Celery workflow task and retry it

    Checks if task is a celery task in waiting state.
    Clears Celery info and retries the task.

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    key = None
    body = None
    try:
        if utils.is_simulation(workflow_id):
            driver = SIMULATOR_DB
        workflow, key = driver.lock_workflow(workflow_id, with_secrets=True)
        if not workflow:
            bottle.abort(404, "No workflow with id '%s' found" % workflow_id)
        serializer = DictionarySerializer()
        sw_wf = SpiffWorkflow.deserialize(serializer, workflow)

        task = sw_wf.get_task(task_id)
        if not task:
            bottle.abort(404, 'No task with id %s' % task_id)

        if task.task_spec.__class__.__name__ != 'Celery':
            bottle.abort(406, "You can only reset Celery tasks. This is a "
                         "'%s' task" % task.task_spec.__class__.__name__)

        if task.state != Task.WAITING:
            bottle.abort(406, "You can only reset WAITING tasks. This task is "
                         "in '%s'" % task.get_state_name())

        # Refresh token if it exists in args[0]['auth_token]
        if hasattr(task.task_spec, 'args') and task.task_spec.args and \
                len(task.task_spec.args) > 0 and \
                isinstance(task.task_spec.args[0], dict) and \
                task.task_spec.args[0].get('auth_token') != \
                bottle.request.context.auth_token:
            task.task_spec.args[0]['auth_token'] = (
                bottle.request.context.auth_token)
            LOG.debug("Updating task auth token with new caller token")
        if task.task_spec.retry_fire(task):
            LOG.debug("Progressing task '%s' (%s)", task_id,
                      task.get_state_name())
            task.task_spec._update_state(task)

        cm_wf.update_workflow_status(sw_wf, tenant_id=tenant_id)
        serializer = DictionarySerializer()
        entity = sw_wf.serialize(serializer)
        body, secrets = utils.extract_sensitive_data(entity)
        body['tenantId'] = workflow.get('tenantId', tenant_id)
        body['id'] = workflow_id
        driver.save_workflow(workflow_id, body, secrets=secrets,
                             tenant_id=tenant_id)
        task = sw_wf.get_task(task_id)
        if not task:
            bottle.abort(404, "No task with id '%s' found" % task_id)

        # Return cleaned data (no credentials)
        data = serializer._serialize_task(task, skip_children=True)
        body, secrets = utils.extract_sensitive_data(data)
        # so we know which workflow it came from
        body['workflow_id'] = workflow_id
    except ObjectLockedError:
        bottle.abort(406, "Cannot retry task(%s) while workflow(%s) is "
                     "executing." % (task_id, workflow_id))
    finally:
        if key:
            driver.unlock_workflow(workflow_id, key)
    return utils.write_body(body, bottle.request, bottle.response)


@bottle.route('/workflows/<api_id>/tasks/<task_id:int>/+execute',
              method=['GET', 'POST'])
@utils.with_tenant
def execute_workflow_task(api_id, task_id, tenant_id=None, driver=DB):
    """Process a checkmate deployment workflow task

    :param api_id: checkmate workflow id
    :param task_id: task id
    """
    if utils.is_simulation(api_id):
        driver = SIMULATOR_DB

    entity = driver.get_workflow(api_id)
    if not entity:
        bottle.abort(404, 'No workflow with id %s' % api_id)

    serializer = DictionarySerializer()
    workflow = SpiffWorkflow.deserialize(serializer, entity)
    task = workflow.get_task(task_id)
    if not task:
        bottle.abort(404, 'No task with id %s' % task_id)

    try:
        #Synchronous call
        orchestrator.run_one_task(bottle.request.context, api_id, task_id,
                                  timeout=10, driver=driver)
    except InvalidKeyError:
        bottle.abort(404, "Cannot execute task(%s) while workflow(%s) is "
                     "executing." % (task_id, api_id))

    entity = driver.get_workflow(api_id)

    workflow = SpiffWorkflow.deserialize(serializer, entity)

    task = workflow.get_task(task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = api_id  # so we know which workflow it came from
    return utils.write_body(data, bottle.request, bottle.response)
