""" Workflow handling

This module uses SpiffWorkflow to create, manage, and run workflows for
Checkmate
"""
# pylint: disable=E0611
from bottle import get, post, put, route, request, response, abort
import copy
import logging
import uuid

try:
    from SpiffWorkflow.specs import WorkflowSpec, Merge, Simple, Join
except ImportError:
    #TODO(zns): remove this when Spiff incorporates the code in it
    print "Get SpiffWorkflow with the Celery spec in it from here: "\
            "https://github.com/ziadsawalha/SpiffWorkflow/tree/celery"
    raise

from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.storage import DictionarySerializer

from checkmate.db import get_driver, any_id_problems
from checkmate.exceptions import CheckmateException
from checkmate.utils import write_body, read_body, extract_sensitive_data,\
        merge_dictionary, with_tenant
from checkmate import orchestrator

db = get_driver()

LOG = logging.getLogger(__name__)


#
# Workflows
#
@get('/workflows')
@with_tenant
def get_workflows(tenant_id=None):
    if 'with_secrets' in request.query:
        if request.context.is_admin == True:
            LOG.info("Administrator accessing workflows with secrets: %s" %
                    request.context.username)
            results = db.get_workflows(tenant_id=tenant_id,
                    with_secrets=True)
        else:
            abort(403, "Administrator privileges needed for this operation")
    else:
        results = db.get_workflows(tenant_id=tenant_id)
    return write_body(results, request, response)


@post('/workflows')
@with_tenant
def add_workflow(tenant_id=None):
    entity = read_body(request)
    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    body, secrets = extract_sensitive_data(entity)
    results = db.save_workflow(entity['id'], body, secrets=secrets,
            tenant_id=tenant_id)

    return write_body(results, request, response)


@route('/workflows/<id>', method=['POST', 'PUT'])
@with_tenant
def save_workflow(id, tenant_id=None):
    entity = read_body(request)

    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    body, secrets = extract_sensitive_data(entity)
    results = db.save_workflow(id, body, secrets, tenant_id=tenant_id)

    return write_body(results, request, response)


@get('/workflows/<id>')
@with_tenant
def get_workflow(id, tenant_id=None):
    if 'with_secrets' in request.query:
        if request.context.is_admin == True:
            LOG.info("Administrator accessing workflow %s with secrets: %s" %
                    (id, request.context.username))
            results = db.get_workflow(id, with_secrets=True)
        else:
            abort(403, "Administrator privileges needed for this operation")
    else:
        results = db.get_workflow(id)
    if not results:
        abort(404, 'No workflow with id %s' % id)
    if 'id' not in results:
        results['id'] = str(id)
    assert tenant_id is None or tenant_id == results.get('tenant_id',
            tenant_id)
    return write_body(results, request, response)


@get('/workflows/<id>/status')
@with_tenant
def get_workflow_status(id, tenant_id=None):
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)
    return write_body(get_SpiffWorkflow_status(wf), request, response)


@route('/workflows/<id>/+execute', method=['GET', 'POST'])
@with_tenant
def execute_workflow(id, tenant_id=None):
    """Process a checkmate deployment workflow

    Executes and moves the workflow forward.
    Retrieves results (final or intermediate) and updates them into
    deployment.

    :param id: checkmate workflow id
    """
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    async_call = orchestrator.run_workflow.delay(id, timeout=10)
    LOG.debug("Executed run workflow task: %s" % async_call)
    entity = db.get_workflow(id)
    return write_body(entity, request, response)


#
# Workflow Tasks
#

@route('/workflows/<id>/tasks/<task_id:int>', method=['GET', 'POST'])
@with_tenant
def get_workflow_task(id, task_id, tenant_id=None):
    """Get a workflow task

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    if 'with_secrets' in request.query:  # TODO: verify admin-ness
        entity = db.get_workflow(id, with_secrets=True)
    else:
        entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = id  # so we know which workflow it came from
    spec = task.task_spec.serialize(serializer)
    data['spec'] = spec
    return write_body(data, request, response)


@post('/workflows/<id>/tasks/<task_id:int>')
@with_tenant
def post_workflow_task(id, task_id, tenant_id=None):
    """Update a workflow task

    Attributes that can be updated are:
    - attributes
    - state
    - internal_attributes

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    entity = read_body(request)

    # Extracting with secrets
    workflow = db.get_workflow(id, with_secrets=True)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, workflow)

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
    serializer = DictionarySerializer()
    body, secrets = extract_sensitive_data(wf.serialize(serializer))

    updated = db.save_workflow(id, body, secrets)
    # Updated does not have secrets, so we deserialize that
    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, updated)
    task = wf.get_task(task_id)
    results = serializer._serialize_task(task, skip_children=True)
    results['workflow_id'] = id
    return write_body(results, request, response)


@route('/workflows/<id>/tasks/<task_id:int>/+reset', method=['GET', 'POST'])
@with_tenant
def reset_workflow_task(id, task_id, tenant_id=None):
    """Reset a Celery workflow task and retry it

    Checks if task is a celery task in waiting state.
    Resets parent to READY and task to FUTURE.
    Removes existing celery task ID.

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """

    workflow = db.get_workflow(id, with_secrets=True)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, workflow)

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

    serializer = DictionarySerializer()
    entity = wf.serialize(serializer)
    body, secrets = extract_sensitive_data(entity)
    db.save_workflow(id, body, secrets)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    # Return cleaned data (no credentials)
    data = serializer._serialize_task(task, skip_children=True)
    body, secrets = extract_sensitive_data(data)
    body['workflow_id'] = id  # so we know which workflow it came from
    return write_body(body, request, response)


@route('/workflows/<id>/tasks/<task_id:int>/+resubmit', method=['GET', 'POST'])
@with_tenant
def resubmit_workflow_task(id, task_id, tenant_id=None):
    """Reset a Celery workflow task and retry it

    Checks if task is a celery task in waiting state.
    Clears Celery info and retries the task.

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """

    workflow = db.get_workflow(id, with_secrets=True)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, workflow)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    if task.task_spec.__class__.__name__ != 'Celery':
        abort(406, "You can only reset Celery tasks. This is a '%s' task" %
            task.task_spec.__class__.__name__)

    if task.state != Task.WAITING:
        abort(406, "You can only reset WAITING tasks. This task is in '%s'" %
            task.get_state_name())

    task.task_spec.retry_fire(task)

    serializer = DictionarySerializer()
    entity = wf.serialize(serializer)
    body, secrets = extract_sensitive_data(entity)
    db.save_workflow(id, body, secrets)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    # Return cleaned data (no credentials)
    data = serializer._serialize_task(task, skip_children=True)
    body, secrets = extract_sensitive_data(data)
    body['workflow_id'] = id  # so we know which workflow it came from
    return write_body(body, request, response)


@route('/workflows/<id>/tasks/<task_id:int>/+execute', method=['GET', 'POST'])
@with_tenant
def execute_workflow_task(id, task_id, tenant_id=None):
    """Process a checkmate deployment workflow task

    :param id: checkmate workflow id
    :param task_id: task id
    """
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    #Synchronous call
    orchestrator.run_one_task(id, task_id, timeout=10)
    entity = db.get_workflow(id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)

    task = wf.get_task(task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = id  # so we know which workflow it came from
    return write_body(data, request, response)


#
# Workflow functions
#
def get_SpiffWorkflow_status(workflow):
    """
    Returns the subtree as a string for debugging.

    :param workflow: a SpiffWorkflow Workflow
    @rtype:  dict
    @return: The debug information.
    """
    def get_task_status(task, output):
        """Recursively fills task data into dict"""
        my_dict = {}
        my_dict['id'] = task.id
        my_dict['threadId'] = task.thread_id
        my_dict['state'] = task.get_state_name()
        output[task.get_name()] = my_dict
        for child in task.children:
            get_task_status(child, my_dict)

    result = {}
    task = workflow.task_tree
    get_task_status(task, result)
    return result


def create_workflow(deployment, context):
    """Creates a SpiffWorkflow from a Checkmate deployment dict

    :returns: SpiffWorkflow.Workflow"""
    LOG.info("Creating workflow for deployment '%s'" % deployment['id'])
    blueprint = deployment['blueprint']
    environment = deployment.environment()

    # Build a workflow spec (the spec is the design of the workflow)
    wfspec = WorkflowSpec(name="%s Workflow" % blueprint['name'])

    #
    # Create the tasks that make the async calls
    #

    # Get list of providers
    providers = {}  # Unique providers used in this deployment

    provider_keys = set()
    for key, resource in deployment.get('resources', {}).iteritems():
        if key != 'connections' and resource['provider'] not in provider_keys:
            provider_keys.add(resource['provider'])

    for key in provider_keys:
        provider = environment.get_provider(key)
        providers[provider.key] = provider
        prep_result = provider.prep_environment(wfspec, deployment, context)
        # Wire up tasks if not wired in somewhere
        if prep_result and not prep_result['root'].inputs:
            wfspec.start.connect(prep_result['root'])

    #build sorted list of resources based on dependencies
    sorted_resources = []

    def recursive_add_host(sorted_list, resource_key, resources, stack):
        resource = resources[resource_key]
        for key, relation in resource.get('relations', {}).iteritems():
                if 'target' in relation:
                    if relation['target'] not in sorted_list:
                        if relation['target'] in stack:
                            raise CheckmateException("Circular dependency in "
                                    "resources between %s and %s " % (
                                    resource_key, relation['target']))
                        stack.append(resource_key)
                        recursive_add_host(sorted_resources,
                                relation['target'], resources, stack)
        if resource_key not in sorted_list:
            sorted_list.append(resource_key)

    for key, resource in deployment.get('resources', {}).iteritems():
        if key != 'connections':
            recursive_add_host(sorted_resources, key, deployment['resources'],
                    [])

    # Do resources
    for key in sorted_resources:
        resource = deployment['resources'][key]
        provider = providers[resource['provider']]
        provider_result = provider.add_resource_tasks(resource,
                key, wfspec, deployment, context)

        if provider_result and provider_result.get('root') and \
                not provider_result['root'].inputs:
            # Attach unattached tasks
            wfspec.start.connect(provider_result['root'])
        # Process hosting relationship before the hosted resource
        if 'hosts' in resource:
            for index in resource['hosts']:
                hr = deployment['resources'][index]
                relation = hr['relations']['host']
                provider = providers[hr['provider']]
                provider_result = provider.add_connection_tasks(hr,
                        index, relation, 'host', wfspec, deployment, context)
                if provider_result and provider_result.get('root') and \
                        not provider_result['root'].inputs:
                    # Attach unattached tasks
                    LOG.debug("Attaching '%s' to 'Start'" %
                            provider_result['root'].name)
                    wfspec.start.connect(provider_result['root'])

    # Do relations
    for key, resource in deployment.get('resources', {}).iteritems():
        if 'relations' in resource:
            for name, relation in resource['relations'].iteritems():
                # Process where this is a source (host relations done above)
                if 'target' in relation and name != 'host':
                    provider = providers[resource['provider']]
                    provider_result = provider.add_connection_tasks(resource,
                            key, relation, name, wfspec, deployment, context)
                    if provider_result and provider_result.get('root') and \
                            not provider_result['root'].inputs:
                        # Attach unattached tasks
                        LOG.debug("Attaching '%s' to 'Start'" %
                                provider_result['root'].name)
                        wfspec.start.connect(provider_result['root'])

    # Check that we have a at least one task. Workflow fails otherwise.
    if not wfspec.start.outputs:
        noop = Simple(wfspec, "end")
        wfspec.start.connect(noop)

    results = wfspec.validate()
    if results:
        LOG.debug("Errors in Workflow: %s" % '\n'.join(results))
        raise CheckmateException('. '.join(results))

    workflow = Workflow(wfspec)
    #Pass in the initial deployemnt dict (task 2 is the Start task)
    runtime_context = copy.copy(deployment.settings())
    runtime_context['token'] = context.auth_token
    workflow.get_task(2).set_attribute(**runtime_context)

    # Calculate estimated_duration
    root = workflow.task_tree
    root._set_internal_attribute(estimated_completed_in=0)
    tasks = root.children[:]
    overall = 0
    while tasks:
        task = tasks.pop(0)
        tasks.extend(task.children)
        expect_to_take = task.parent._get_internal_attribute(
                'estimated_completed_in') +\
                task.task_spec.get_property('estimated_duration', 0)
        if expect_to_take > overall:
            overall = expect_to_take
        task._set_internal_attribute(estimated_completed_in=expect_to_take)
    LOG.debug("Workflow %s estimated duration: %s" % (deployment['id'],
            overall))
    workflow.attributes['estimated_duration'] = overall

    return workflow


def wait_for(wf_spec, task, wait_list, name=None, **kwargs):
    """Wires up tasks so that 'task' will wait for all tasks in 'wait_list' to
    complete before proceeding.

    If wait_list has more than one task, we'll use a Merge task. If wait_list
    only contains one task, we'll just wire them up directly. If task input is
    already a join, we'll tap into that.

    :param wf_spec: the workflow spec being worked on
    :param task: the task that will be waiting
    :param wait_list: a list of tasks to wait on
    :param name: the name of the merge task (autogenerated if not supplied)
    :param kwargs: all additional kwargs are passed to Merge.__init__
    :returns: the final task or the task itself if no waiting needs to happen
    """
    if wait_list:
        join_task = None
        if task.inputs:
            # Move inputs to join
            for input in task.inputs:
                # If input is a Join, keep it as an input and use it
                if isinstance(input, Join):
                    if join_task:
                        LOG.warning("Task %s seems to have to Join inputs" %
                                task.name)
                    else:
                        LOG.debug("Using existing Join task %s" % input.name)
                        join_task = input
                        continue
                if input not in wait_list:
                    wait_list.append(input)
                # remove it from the other tasks outputs
                input.outputs.remove(task)
            if join_task:
                task.inputs = [join_task]
            else:
                task.inputs = []

        if len(wait_list) > 1:
            if not join_task:
                # Create a new Merge task since it doesn't exist
                if not name:
                    name = "After %s run %s" % (",".join([str(t.id)
                            for t in wait_list]), task.id)
                join_task = Merge(wf_spec, name, **kwargs)
            if task not in join_task.outputs:
                task.follow(join_task)
            for t in wait_list:
                if t not in join_task.ancestors():
                    t.connect(join_task)
            return join_task
        elif join_task:
            wait_list[0].connect(join_task)
            return join_task
        else:
            task.follow(wait_list[0])
            return wait_list[0]
    else:
        return task
