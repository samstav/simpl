"""
Workflow handling

This module uses SpiffWorkflow to create, manage, and run workflows for
Checkmate
"""
# pylint: disable=E0611
from bottle import get, post, route, request, response, abort
import logging
import os
import uuid

from SpiffWorkflow import Workflow as SpiffWorkflow, Task, Workflow
from SpiffWorkflow.storage import DictionarySerializer

from checkmate.common.tasks import update_operation
from checkmate.db import (
    get_driver,
    any_id_problems,
    InvalidKeyError,
    ObjectLockedError,
)
from checkmate import orchestrator
from checkmate.utils import (
    extract_sensitive_data,
    formatted_response,
    is_simulation,
    merge_dictionary,
    read_body,
    with_tenant,
    write_body,
)
from checkmate import workflow as wf_import  # TODO: rename

DB = get_driver()
SIMULATOR_DB = get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))

LOG = logging.getLogger(__name__)


#
# Workflows
#
@get('/workflows')
@with_tenant
@formatted_response('workflows', with_pagination=True)
def get_workflows(tenant_id=None, offset=None, limit=None, driver=DB):
    if 'with_secrets' in request.query:
        if request.context.is_admin is True:
            LOG.info("Administrator accessing workflows with secrets: %s",
                     request.context.username)
            results = driver.get_workflows(tenant_id=tenant_id,
                                           with_secrets=True,
                                           offset=offset, limit=limit)
        else:
            abort(403, "Administrator privileges needed for this operation")
    else:
        results = driver.get_workflows(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit
        )
    return results


def safe_workflow_save(obj_id, body, secrets=None, tenant_id=None, driver=DB):
    """
    Locks, saves, and unlocks a workflow.
    TODO: should this be moved to the db layer?
    """
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
        abort(404, "The workflow is already locked, cannot obtain lock.")

    return results


@post('/workflows')
@with_tenant
def add_workflow(tenant_id=None, driver=DB):
    entity = read_body(request)
    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    body, secrets = extract_sensitive_data(entity)

    key = None
    results = None
    if driver.get_workflow(entity['id']):
        # TODO: this case should be considered invalid
        # trying to add an existing workflow
        _, key = driver.lock_workflow(entity['id'])

    results = driver.save_workflow(entity['id'], body, secrets=secrets)

    if key:
        driver.unlock_workflow(entity['id'], key)

    return write_body(results, request, response)


@route('/workflows/<id>', method=['POST', 'PUT'])
@with_tenant
def save_workflow(id, tenant_id=None, driver=DB):
    if is_simulation(id):
        driver = SIMULATOR_DB
    entity = read_body(request)

    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    body, secrets = extract_sensitive_data(entity)

    existing = driver.get_workflow(id)
    results = safe_workflow_save(str(id), body, secrets=secrets,
                                 tenant_id=tenant_id, driver=driver)
    if existing:
        response.status = 200  # OK - updated
    else:
        response.status = 201  # Created

    return write_body(results, request, response)


@get('/workflows/<id>')
@with_tenant
def get_workflow(id, tenant_id=None, driver=DB):
    if is_simulation(id):
        driver = SIMULATOR_DB

    if 'with_secrets' in request.query:
        LOG.info("Administrator accessing workflow %s with secrets: %s",
                 id, request.context.username)
        results = driver.get_workflow(id, with_secrets=True)
    else:
        results = driver.get_workflow(id)
    if not results:
        abort(404, 'No workflow with id %s' % id)
    if 'id' not in results:
        results['id'] = str(id)
    if tenant_id is not None and tenant_id != results.get('tenantId'):
        LOG.warning("Attempt to access workflow %s from wrong tenant %s by "
                    "%s", id, tenant_id, request.context.username)
        abort(404)
    return write_body(results, request, response)


@get('/workflows/<id>/status')
@with_tenant
def get_workflow_status(id, tenant_id=None, driver=DB):
    if is_simulation(id):
        driver = SIMULATOR_DB
    entity = driver.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    serializer = DictionarySerializer()
    wf = SpiffWorkflow.deserialize(serializer, entity)
    return write_body(wf_import.get_SpiffWorkflow_status(wf),
                      request, response)


@route('/workflows/<id>/+execute', method=['GET', 'POST'])
@with_tenant
def execute_workflow(id, tenant_id=None, driver=DB):
    """Process a checkmate deployment workflow

    Executes and moves the workflow forward.
    Retrieves results (final or intermediate) and updates them into
    deployment.

    :param id: checkmate workflow id
    """
    if is_simulation(id):
        driver = SIMULATOR_DB
    entity = driver.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    async_call = orchestrator.run_workflow.delay(id, timeout=1800,
                                                 driver=driver)
    LOG.debug("Executed a task to run workflow '%s'", async_call)
    entity = driver.get_workflow(id)
    return write_body(entity, request, response)


@route('/workflows/<id>/+pause', method=['GET', 'POST'])
@with_tenant
def pause_workflow(id, tenant_id=None, driver=DB):
    """Process a checkmate deployment workflow

    Pauses the workflow.
    Updates the operation status to pauses when done

    :param id: checkmate workflow id
    """
    if is_simulation(id):
        driver = SIMULATOR_DB
    workflow = driver.get_workflow(id)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    dep_id = workflow["attributes"]["deploymentId"] or id
    deployment = driver.get_deployment(dep_id)
    operation = deployment.get("operation")

    if (operation and operation.get('action') != "PAUSE" and
            operation["status"] != "PAUSED"):
        update_operation.delay(dep_id, driver=driver, action='PAUSE')
    return write_body(workflow, request, response)


@route('/workflows/<id>/+resume', method=['GET', 'POST'])
@with_tenant
def resume_workflow(id, tenant_id=None, driver=DB):
    """Process a checkmate deployment workflow

    Executes the workflow again

    :param id: checkmate workflow id
    """
    if is_simulation(id):
        driver = SIMULATOR_DB
    workflow = driver.get_workflow(id)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    dep_id = workflow["attributes"]["deploymentId"] or id
    deployment = driver.get_deployment(dep_id)
    operation = deployment.get("operation")
    if operation and operation.get("status") == "PAUSED":
        async_call = orchestrator.run_workflow.delay(id, timeout=1800,
                                                     driver=driver)
        LOG.debug("Executed a task to run workflow '%s'", async_call)
        workflow = driver.get_workflow(id)
    return write_body(workflow, request, response)

#
# Workflow Specs
#
@post('/workflows/<workflow_id>/specs/<spec_id>')
@with_tenant
def post_workflow_spec(workflow_id, spec_id, tenant_id=None, driver=DB):
    """Update a workflow spec

    :param workflow_id: checkmate workflow id
    :param spec_id: checkmate workflow spec id (a string)
    """
    if is_simulation(workflow_id):
        driver = SIMULATOR_DB
    entity = read_body(request)

    # Extracting with secrets
    workflow = driver.get_workflow(workflow_id, with_secrets=True)
    if not workflow:
        abort(404, 'No workflow with id %s' % workflow_id)

    spec = workflow['wf_spec']['task_specs'].get(spec_id)
    if not spec:
        abort(404, 'No spec with id %s' % spec_id)

    LOG.debug("Updating spec '%s' in workflow '%s'", spec_id, workflow_id,
              extra=dict(data=dict(old=spec, new=entity)))
    workflow['wf_spec']['task_specs'][spec_id] = entity

    # Save workflow (with secrets)
    body, secrets = extract_sensitive_data(workflow)
    body['tenantId'] = workflow.get('tenantId', tenant_id)
    body['id'] = workflow_id
    safe_workflow_save(workflow_id, body, secrets=secrets, tenant_id=tenant_id,
                       driver=driver)

    return write_body(entity, request, response)


#
# Workflow Tasks
#
@get('/workflows/<id>/tasks/<task_id:int>')
@with_tenant
def get_workflow_task(id, task_id, tenant_id=None, driver=DB):
    """Get a workflow task

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    if is_simulation(id):
        driver = SIMULATOR_DB
    if 'with_secrets' in request.query:  # TODO: verify admin-ness
        entity = driver.get_workflow(id, with_secrets=True)
    else:
        entity = driver.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = SpiffWorkflow.deserialize(serializer, entity)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = id  # so we know which workflow it came from
    spec = task.task_spec.serialize(serializer)
    data['spec'] = spec  # include a copy of the spec
    return write_body(data, request, response)


@post('/workflows/<id>/tasks/<task_id:int>')
@with_tenant
def post_workflow_task(id, task_id, tenant_id=None, driver=DB):
    """Update a workflow task

    Attributes that can be updated are:
    - attributes
    - state
    - internal_attributes

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    if is_simulation(id):
        driver = SIMULATOR_DB
    entity = read_body(request)

    # Extracting with secrets
    workflow = driver.get_workflow(id, with_secrets=True)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = SpiffWorkflow.deserialize(serializer, workflow)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    if 'attributes' in entity:
        if not isinstance(entity['attributes'], dict):
            abort(406, "'attribues' must be a dict")
        # Don't do a simple overwrite since incoming may not have secrets and
        # we don't want to stomp on them
        body, secrets = extract_sensitive_data(task.attributes)
        updated = merge_dictionary(secrets or {}, entity['attributes'])
        task.attributes = updated

    if 'internal_attributes' in entity:
        if not isinstance(entity['internal_attributes'], dict):
            abort(406, "'internal_attribues' must be a dict")
        task.internal_attributes = entity['internal_attributes']

    if 'state' in entity:
        if not isinstance(entity['state'], (int, long)):
            abort(406, "'state' must be an int")
        task._state = entity['state']

    # Save workflow (with secrets)
    wf_import.update_workflow_status(wf, workflow_id=workflow.id)
    serializer = DictionarySerializer()
    body, secrets = extract_sensitive_data(wf.serialize(serializer))
    body['tenantId'] = workflow.get('tenantId', tenant_id)
    body['id'] = id

    updated = safe_workflow_save(id, body, secrets=secrets,
                                 tenant_id=tenant_id, driver=driver)
    # Updated does not have secrets, so we deserialize that
    serializer = DictionarySerializer()
    wf = SpiffWorkflow.deserialize(serializer, updated)
    task = wf.get_task(task_id)
    results = serializer._serialize_task(task, skip_children=True)
    results['workflow_id'] = id
    return write_body(results, request, response)


@route('/workflows/<id>/tasks/<task_id:int>/+reset', method=['GET', 'POST'])
@with_tenant
def reset_workflow_task(id, task_id, tenant_id=None, driver=DB):
    """Reset a Celery workflow task and retry it

    Checks if task is a celery task in waiting state.
    Resets parent to READY and task to FUTURE.
    Removes existing celery task ID.

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    if is_simulation(id):
        driver = SIMULATOR_DB

    workflow = driver.get_workflow(id, with_secrets=True)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = SpiffWorkflow.deserialize(serializer, workflow)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    if task.task_spec.__class__.__name__ != 'Celery':
        abort(406, "You can only reset Celery tasks. This is a '%s' task" %
              task.task_spec.__class__.__name__)

    if task.state != Task.WAITING:
        abort(406, "You can only reset WAITING tasks. This task is in '%s'" %
              task.get_state_name())

    task.task_spec._clear_celery_task_data(task)

    task._state = Task.FUTURE
    task.parent._state = Task.READY

    wf_import.update_workflow_status(wf, workflow_id=workflow.id)
    serializer = DictionarySerializer()
    entity = wf.serialize(serializer)
    body, secrets = extract_sensitive_data(entity)
    body['tenantId'] = workflow.get('tenantId', tenant_id)
    body['id'] = id
    safe_workflow_save(id, body, secrets=secrets, tenant_id=tenant_id,
                       driver=driver)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    # Return cleaned data (no credentials)
    data = serializer._serialize_task(task, skip_children=True)
    body, secrets = extract_sensitive_data(data)
    body['workflow_id'] = id  # so we know which workflow it came from
    return write_body(body, request, response)


@route('/workflows/<workflow_id>/tasks/<task_id:int>/+resubmit',
       method=['GET', 'POST'])
@with_tenant
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
        if is_simulation(workflow_id):
            driver = SIMULATOR_DB
        workflow, key = driver.lock_workflow(workflow_id, with_secrets=True)
        if not workflow:
            abort(404, "No workflow with id '%s' found" % workflow_id)
        serializer = DictionarySerializer()
        wf = SpiffWorkflow.deserialize(serializer, workflow)

        task = wf.get_task(task_id)
        if not task:
            abort(404, 'No task with id %s' % task_id)

        if task.task_spec.__class__.__name__ != 'Celery':
            abort(406, "You can only reset Celery tasks. This is a '%s' task" %
                  task.task_spec.__class__.__name__)

        if task.state != Task.WAITING:
            abort(406, "You can only reset WAITING tasks. This task is in '%s'"
                  % task.get_state_name())

        # Refresh token if it exists in args[0]['auth_token]
        if hasattr(task, 'args') and task.task_spec.args and \
                len(task.task_spec.args) > 0 and \
                isinstance(task.task_spec.args[0], dict) and \
                task.task_spec.args[0].get('auth_token') != \
                request.context.auth_token:
            task.task_spec.args[0]['auth_token'] = request.context.auth_token
            LOG.debug("Updating task auth token with new caller token")
        if task.task_spec.retry_fire(task):
            LOG.debug("Progressing task '%s' (%s)" % (task_id,
                                                      task.get_state_name()))
            task.task_spec._update_state(task)

        wf_import.update_workflow_status(wf, workflow_id=workflow_id)
        serializer = DictionarySerializer()
        entity = wf.serialize(serializer)
        body, secrets = extract_sensitive_data(entity)
        body['tenantId'] = workflow.get('tenantId', tenant_id)
        body['id'] = workflow_id
        driver.save_workflow(workflow_id, body, secrets=secrets,
                             tenant_id=tenant_id)
        task = wf.get_task(task_id)
        if not task:
            abort(404, "No task with id '%s' found" % task_id)

        # Return cleaned data (no credentials)
        data = serializer._serialize_task(task, skip_children=True)
        body, secrets = extract_sensitive_data(data)
        # so we know which workflow it came from
        body['workflow_id'] = workflow_id
    except ObjectLockedError:
        abort(406, "Cannot retry task(%s) while workflow(%s) is executing." %
              (task_id, workflow_id))
    finally:
        if key:
            driver.unlock_workflow(workflow_id, key)
    return write_body(body, request, response)


@route('/workflows/<id>/tasks/<task_id:int>/+execute', method=['GET', 'POST'])
@with_tenant
def execute_workflow_task(id, task_id, tenant_id=None, driver=DB):
    """Process a checkmate deployment workflow task

    :param id: checkmate workflow id
    :param task_id: task id
    """
    if is_simulation(id):
        driver = SIMULATOR_DB

    entity = driver.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    workflow = SpiffWorkflow.deserialize(serializer, entity)
    task = workflow.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    try:
        #Synchronous call
        orchestrator.run_one_task(request.context, id, task_id, timeout=10,
                                  driver=driver)
    except InvalidKeyError:
        abort(404, "Cannot execute task(%s) while workflow(%s) is executing." %
              (task_id, id))

    entity = driver.get_workflow(id)

    workflow = SpiffWorkflow.deserialize(serializer, entity)

    task = workflow.get_task(task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = id  # so we know which workflow it came from
    return write_body(data, request, response)
