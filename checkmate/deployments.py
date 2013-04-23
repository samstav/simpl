import copy
import logging
import os
import time
import uuid

from bottle import request, response, abort, get, post, delete, route
from celery.task import task
from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.storage import DictionarySerializer

from checkmate import orchestrator
from checkmate.db import get_driver, any_id_problems
from checkmate.exceptions import (
    CheckmateDoesNotExist,
    CheckmateValidationException,
    CheckmateBadState,
    CheckmateException,
)
from checkmate.workflows import (
    create_workflow_deploy,
    create_workflow_spec_deploy,
)
from checkmate.utils import (
    write_body,
    read_body,
    extract_sensitive_data,
    with_tenant,
    match_celery_logging,
    is_simulation,
    get_time_string,
)
from checkmate.plan import Plan
from checkmate.deployment import Deployment, generate_keys
from celery.canvas import chord

LOG = logging.getLogger(__name__)
DB = get_driver()
SIMULATOR_DB = get_driver(
    connection_string=os.environ.get('CHECKMATE_SIMULATOR_CONNECTION_STRING',
                                     'sqlite://'))


def _content_to_deployment(bottle_request, deployment_id=None, tenant_id=None):
    """Receives request content and puts it in a deployment

    :param bottle_request: the bottlepy request object
    :param deployment_id: the expected/requested ID
    :param tenant_id: the tenant ID in the request

    """
    entity = read_body(bottle_request)
    if 'deployment' in entity:
        entity = entity['deployment']  # Unwrap if wrapped
    if 'id' not in entity:
        entity['id'] = deployment_id or uuid.uuid4().hex
    if any_id_problems(entity['id']):
        raise CheckmateValidationException(any_id_problems(entity['id']))
    deployment = Deployment(entity)  # Also validates syntax
    if 'includes' in deployment:
        del deployment['includes']
    if 'tenantId' in deployment and tenant_id:
        assert deployment['tenantId'] == tenant_id, ("tenantId must match "
                                                     "with current tenant ID")
    else:
        assert tenant_id, "Tenant ID must be specified in deployment "
        deployment['tenantId'] = tenant_id
    return deployment


def _save_deployment(deployment, deployment_id=None, tenant_id=None,
                     driver=DB):
    """Sync ID and tenant and save deployment

    :returns: saved deployment
    """
    if not deployment_id:
        if 'id' not in deployment:
            deployment_id = uuid.uuid4().hex
            deployment['id'] = deployment_id
        else:
            deployment_id = deployment['id']
    else:
        if 'id' not in deployment:
            deployment['id'] = deployment_id
        else:
            assert deployment_id == deployment['id'], ("Deployment ID does "
                                                       "not match "
                                                       "deploymentId")
    if 'tenantId' in deployment:
        if tenant_id:
            assert deployment['tenantId'] == tenant_id, ("tenantId must match "
                                                         "with current tenant "
                                                         "ID")
        else:
            tenant_id = deployment['tenantId']
    else:
        assert tenant_id, "Tenant ID must be specified in deployment"
        deployment['tenantId'] = tenant_id
    body, secrets = extract_sensitive_data(deployment)
    return driver.save_deployment(deployment_id, body, secrets,
                                  tenant_id=tenant_id, partial=False)


def _create_deploy_workflow(deployment, context):
    """ Create and return serialized workflow """
    workflow = create_workflow_deploy(deployment, context)
    serializer = DictionarySerializer()
    serialized_workflow = workflow.serialize(serializer)
    return serialized_workflow


def _deploy(deployment, context, driver=DB):
    """Deploys a deployment and returns the workflow"""
    if deployment.get('status') != 'PLANNED':
        raise CheckmateBadState("Deployment '%s' is in '%s' status and must "
                                "be in 'PLANNED' status to be deployed" %
                                (deployment['id'], deployment.get('status')))
    deployment_keys = generate_keys(deployment)
    workflow = _create_deploy_workflow(deployment, context)
    workflow['id'] = deployment['id']  # TODO: need to support multi workflows
    deployment['workflow'] = workflow['id']
    # deployment['status'] = "LAUNCHED"

    body, secrets = extract_sensitive_data(workflow)
    driver.save_workflow(workflow['id'], body, secrets,
                         tenant_id=deployment['tenantId'])

    deployment['display-outputs'] = deployment.calculate_outputs()
    _save_deployment(deployment, driver=driver)

    return workflow


#
# Deployments
#
@get('/deployments')
@with_tenant
def get_deployments(tenant_id=None, driver=DB):
    """ Get existing deployments """
    offset = request.query.get('offset')
    limit = request.query.get('limit')
    if offset:
        offset = int(offset)
    if limit:
        limit = int(limit)
    return write_body(driver.get_deployments(tenant_id=tenant_id,
                                             offset=offset,
                                             limit=limit),
                      request, response)


@get('/deployments/count')
@with_tenant
def get_deployments_count(tenant_id=None, driver=DB):
    """
    Get the number of deployments. May limit response to include all
    deployments for a particular tenant and/or blueprint

    :param:tenant_id: the (optional) tenant
    """
    count = len(driver.get_deployments(tenant_id=tenant_id))
    return write_body({"count": count}, request, response)


@get("/deployments/count/<blueprint_id>")
@with_tenant
def get_deployments_by_bp_count(blueprint_id, tenant_id=None, driver=DB):
    """
    Return the number of times the given blueprint appears
    in saved deployments
    """
    ret = {"count": 0}
    deployments = driver.get_deployments(tenant_id=tenant_id)
    if not deployments:
        LOG.debug("No deployments")
    for dep_id, dep in deployments.items():
        if "blueprint" in dep:
            LOG.debug("Found blueprint {} in deployment {}"
                      .format(dep.get("blueprint"), dep_id))
            if ((blueprint_id == dep["blueprint"]) or
                    ("id" in dep["blueprint"] and
                     blueprint_id == dep["blueprint"]["id"])):
                ret["count"] += 1
        else:
            LOG.debug("No blueprint defined in deployment {}".format(dep_id))
    return write_body(ret, request, response)


@post('/deployments')
@with_tenant
def post_deployment(tenant_id=None, driver=DB):
    """
    Creates deployment and wokflow based on sent information
    and triggers workflow execution
    """
    deployment = _content_to_deployment(request, tenant_id=tenant_id)
    if request.context.simulation is True:
        deployment['id'] = 'simulate%s' % uuid.uuid4().hex[0:12]
    oid = str(deployment['id'])
    _save_deployment(deployment, deployment_id=oid, tenant_id=tenant_id,
                     driver=driver)
    # Return response (with new resource location in header)
    if tenant_id:
        response.add_header('Location', "/%s/deployments/%s" % (tenant_id,
                                                                oid))
        response.add_header('Link', '</%s/workflows/%s>; '
                            'rel="workflow"; title="Deploy"' % (tenant_id,
                                                                oid))
    else:
        response.add_header('Location', "/deployments/%s" % oid)
        response.add_header('Link', '</workflows/%s>; '
                            'rel="workflow"; title="Deploy"' % oid)

    # can't pass actual request
    request_context = copy.deepcopy(request.context)
    async_task = execute_plan(oid, request_context, driver=driver,
                              asynchronous=('asynchronous' in request.query))

    response.status = 202

    return write_body(deployment, request, response)


@post('/deployments/simulate')
@with_tenant
def simulate(tenant_id=None):
    """ Run a simulation """
    request.context.simulation = True
    return post_deployment(tenant_id=tenant_id, driver=SIMULATOR_DB)


def execute_plan(depid, request_context, driver=DB, asynchronous=False):
    if any_id_problems(depid):
        abort(406, any_id_problems(depid))

    deployment = driver.get_deployment(depid)
    if not deployment:
        abort(404, 'No deployment with id %s' % depid)

    if asynchronous is True:
        process_post_deployment.delay(deployment, request_context,
                                      driver=driver)
    else:
        process_post_deployment(deployment, request_context, driver=driver)


@task
def process_post_deployment(deployment, request_context, driver=DB):
    match_celery_logging(LOG)

    deployment = Deployment(deployment)

    #Assess work to be done & resources to be created
    parsed_deployment = plan(deployment, request_context)

    # Create a 'new deployment' workflow
    _deploy(parsed_deployment, request_context, driver=driver)

    #Trigger the workflow in the queuing service
    async_task = execute(deployment['id'], driver=driver)
    LOG.debug("Triggered workflow (task='%s')", async_task)


@post('/deployments/+parse')
@with_tenant
def parse_deployment(tenant_id=None):
    """Parse a deployment and return the parsed response"""
    deployment = _content_to_deployment(request, tenant_id=tenant_id)
    results = plan(deployment, request.context)
    return write_body(results, request, response)


@post('/deployments/+preview')
@with_tenant
def preview_deployment(tenant_id=None):
    """Parse and preview a deployment and its workflow"""
    deployment = _content_to_deployment(request, tenant_id=tenant_id)
    results = plan(deployment, request.context)
    spec = create_workflow_spec_deploy(results, request.context)
    serializer = DictionarySerializer()
    serialized_spec = spec.serialize(serializer)
    results['workflow'] = dict(wf_spec=serialized_spec)

    # Return any errors found
    errors = spec.validate()
    if errors:
        results['messages'] = errors

    return write_body(results, request, response)


@route('/deployments/<oid>', method=['PUT'])
@with_tenant
def update_deployment(oid, tenant_id=None, driver=DB):
    """Store a deployment on this server"""
    if is_simulation(oid):
        driver = SIMULATOR_DB
    deployment = _content_to_deployment(request, deployment_id=oid,
                                        tenant_id=tenant_id)
    entity = driver.get_deployment(oid)
    results = _save_deployment(deployment, deployment_id=oid,
                               tenant_id=tenant_id, driver=driver)
    # Return response (with new resource location in header)
    if entity:
        response.status = 200  # OK - updated
    else:
        response.status = 201  # Created
        if tenant_id:
            response.add_header('Location', "/%s/deployments/%s" % (tenant_id,
                                                                    oid))
        else:
            response.add_header('Location', "/deployments/%s" % oid)
    return write_body(results, request, response)


@route('/deployments/<oid>/+plan', method=['POST', 'GET'])
@with_tenant
def plan_deployment(oid, tenant_id=None, driver=DB):
    """Plan a NEW deployment and save it as PLANNED"""
    if is_simulation(oid):
        driver = SIMULATOR_DB
    if any_id_problems(oid):
        abort(406, any_id_problems(oid))
    entity = driver.get_deployment(oid, with_secrets=True)
    if not entity:
        raise CheckmateDoesNotExist('No deployment with id %s' % oid)
    if entity.get('status', 'NEW') != 'NEW':
        raise CheckmateBadState("Deployment '%s' is in '%s' status and must "
                                "be in 'NEW' to be planned" %
                                (oid, entity.get('status')))
    deployment = Deployment(entity)  # Also validates syntax
    planned_deployment = plan(deployment, request.context)
    results = _save_deployment(planned_deployment, deployment_id=oid,
                               tenant_id=tenant_id, driver=driver)
    return write_body(results, request, response)


@route('/deployments/<oid>/+deploy', method=['POST', 'GET'])
@with_tenant
def deploy_deployment(oid, tenant_id=None, driver=DB):
    """Deploy a NEW or PLANNED deployment and save it as DEPLOYED"""
    if is_simulation(oid):
        driver = SIMULATOR_DB
    if any_id_problems(oid):
        raise CheckmateValidationException(any_id_problems(oid))
    entity = driver.get_deployment(oid, with_secrets=True)
    if not entity:
        CheckmateDoesNotExist('No deployment with id %s' % oid)
    deployment = Deployment(entity)  # Also validates syntax
    if entity.get('status', 'NEW') == 'NEW':
        deployment = plan(deployment, request.context)
    if entity.get('status') != 'PLANNED':
        raise CheckmateBadState("Deployment '%s' is in '%s' status and must "
                                "be in 'PLANNED' or 'NEW' status to be "
                                "deployed" % (oid, entity.get('status')))

    # Create a 'new deployment' workflow
    workflow = _deploy(deployment, request.context, driver=driver)

    #Trigger the workflow
    async_task = execute(oid, driver=driver)
    LOG.debug("Triggered workflow (task='%s')" % async_task)

    return write_body(deployment, request, response)


@get('/deployments/<oid>')
@with_tenant
def get_deployment(oid, tenant_id=None, driver=DB):
    """Return deployment with given ID"""
    if is_simulation(oid):
        driver = SIMULATOR_DB
    return write_body(_get_a_deployment(oid, tenant_id=tenant_id,
                      driver=driver), request, response)


def _get_a_deployment(oid, tenant_id=None, driver=DB):
    """ Lookup a deployment with secrets if needed """
    if 'with_secrets' in request.query:  # TODO: verify admin-ness
        entity = driver.get_deployment(oid, with_secrets=True)
    else:
        entity = driver.get_deployment(oid)
    if not entity or (tenant_id and tenant_id != entity.get("tenantId")):
        raise CheckmateDoesNotExist('No deployment with id %s' % oid)
    return entity


def _get_dep_resources(deployment):
    """ Return the resources for the deployment or abort if not found """
    if deployment and "resources" in deployment:
        return deployment.get("resources")
    abort(404, "No resources found for deployment %s" % deployment.get("id"))


@get('/deployments/<oid>/resources')
@with_tenant
def get_deployment_resources(oid, tenant_id=None, driver=DB):
    """ Return the resources for a deployment """
    if is_simulation(oid):
        driver = SIMULATOR_DB
    deployment = _get_a_deployment(oid, tenant_id=tenant_id, driver=driver)
    resources = _get_dep_resources(deployment)
    return write_body(resources, request, response)


@get('/deployments/<oid>/resources/status')
@with_tenant
def get_resources_statuses(oid, tenant_id=None, driver=DB):
    """ Get basic status of all deployment resources """
    if is_simulation(oid):
        driver = SIMULATOR_DB
    deployment = _get_a_deployment(oid, tenant_id=tenant_id, driver=driver)
    resources = _get_dep_resources(deployment)
    resp = {}

    for key, val in resources.iteritems():
        if key.isdigit():
            resp.update({
                key: {
                    'service': val.get('service', 'UNKNOWN'),
                    "status": (val.get("status") or
                               val.get("instance", {}).get("status")),
                    'message': (val.get('errmessage') or
                                val.get('instance', {}).get("errmessage") or
                                val.get('statusmsg') or
                                val.get("instance", {}).get("statusmsg")),
                    "type": val.get("type", "UNKNOWN"),
                    "component": val.get("component", "UNKNOWN"),
                    "provider": val.get("provider", "core")
                }
            })
            if ("trace" in request.query_string and
                    ('trace' in val or
                     'trace' in val.get('instance', {}))):
                resp.get(key, {})['trace'] = (val.get('trace') or
                                              val.get('instance',
                                                      {}).get('trace'))
    for val in resp.values():
        if not val.get('status'):
            val['status'] = 'UNKNOWN'
        if 'message' in val and not val.get('message'):
            del val['message']
    return write_body(resp, request, response)


@get('/deployments/<oid>/resources/<rid>')
@with_tenant
def get_resource(oid, rid, tenant_id=None, driver=DB):
    """ Get a specific resource from a deployment """
    if is_simulation(oid):
        driver = SIMULATOR_DB
    deployment = _get_a_deployment(oid, tenant_id=tenant_id, driver=driver)
    resources = _get_dep_resources(deployment)
    if rid in resources:
        return write_body(resources.get(rid), request, response)
    abort(404, "No resource %s in deployment %s" % (rid, oid))


@delete('/deployments/<oid>')
@with_tenant
def delete_deployment(oid, tenant_id=None, driver=DB):
    """
    Delete the specified deployment
    """
    if is_simulation(oid):
        request.context.simulation = True
        driver = SIMULATOR_DB
    deployment = driver.get_deployment(oid, with_secrets=True)
    if not deployment:
        abort(404, "No deployment with id %s" % oid)
    deployment = Deployment(deployment)
    if 'force' not in request.query_string:
        del_statuses = ["PLANNED", "NEW", "RUNNING", "ERROR", "ACTIVE"]
        if deployment.get("status", "UNKNOWN") not in del_statuses:
            abort(400, "Deployment %s cannot be deleted while in status %s. "
                  "A deployment must have one of the following statuses "
                  "before being deleted: [%s]" %
                  (oid, deployment.get("status", "UNKNOWN"),
                   ", ".join(del_statuses)))
    loc = "/deployments/%s" % oid
    link = "/canvases/%s" % oid
    if tenant_id:
        loc = "/%s%s" % (tenant_id, loc)
        link = "/%s%s" % (tenant_id, link)
    planner = Plan(deployment)
    tasks = planner.plan_delete(request.context)
    if tasks:
        update_deployment_status.s(oid, "DELETING", driver=driver).delay()
        chord(tasks)(delete_deployment_task.si(oid, driver=driver), interval=2,
                     max_retries=120)
    else:
        LOG.warn("No delete tasks for deployment %s", oid)
        delete_deployment_task.delay(oid, driver=driver)
    response.set_header("Location", loc)
    response.set_header("Link", '<%s>; rel="canvas"; title="Delete Deployment"'
                        % loc)

    response.status = 202  # Accepted (i.e. not done yet)
    return write_body(deployment, request, response)


@get('/deployments/<oid>/status')
@with_tenant
def get_deployment_status(oid, tenant_id=None, driver=DB):
    """Return workflow status of given deployment"""
    if is_simulation(oid):
        driver = SIMULATOR_DB
    deployment = driver.get_deployment(oid)
    if not deployment:
        abort(404, 'No deployment with id %s' % oid)

    resources = deployment.get('resources', {})
    results = {}
    results['status'] = deployment.get('status')
    workflow_id = deployment.get('workflow')
    if workflow_id:
        workflow = driver.get_workflow(workflow_id)
        serializer = DictionarySerializer()
        wf = Workflow.deserialize(serializer, workflow)
        for task in wf.get_tasks(state=Task.ANY_MASK):
            if 'resource' in task.task_spec.defines:
                resource_id = str(task.task_spec.defines['resource'])
                resource = resources.get(resource_id, None)
                if resource:
                    result = {}
                    result['state'] = task.get_state_name()
                    error = task.get_attribute('error', None)
                    if error is not None:  # Show empty strings too
                        result['error'] = error
                    result['output'] = {key: task.attributes[key] for key
                                        in task.attributes if key
                                        not in['deployment',
                                        'token', 'error']}
                    if 'tasks' not in resource:
                        resource['tasks'] = {}
                    resource['tasks'][task.get_name()] = result
            else:
                result = {}
                result['state'] = task.get_state_name()
                error = task.get_attribute('error', None)
                if error is not None:  # Show empty strings too
                    result['error'] = error
                if 'tasks' not in results:
                    results['tasks'] = {}
                results['tasks'][task.get_name()] = result

    results['resources'] = resources

    return write_body(results, request, response)


def execute(oid, timeout=180, tenant_id=None, driver=DB):
    """Process a checkmate deployment workflow

    Executes and moves the workflow forward.
    Retrieves results (final or intermediate) and updates them into
    deployment.

    :param id: checkmate deployment id
    :returns: the async task
    """
    if any_id_problems(oid):
        abort(406, any_id_problems(oid))

    deployment = driver.get_deployment(oid)
    if not deployment:
        abort(404, 'No deployment with id %s' % oid)

    result = orchestrator.run_workflow.delay(oid, timeout=3600, driver=driver)
    return result


def plan(deployment, context):
    """Process a new checkmate deployment and plan for execution.

    This creates templates for resources and connections that will be used for
    the actual creation of resources.

    :param deployment: checkmate deployment instance (dict)
    :param context: RequestContext (auth data, etc) for making API calls
    """
    assert context.__class__.__name__ == 'RequestContext'
    assert deployment.get('status') == 'NEW'
    assert isinstance(deployment, Deployment)
    if "chef-local" in deployment.environment().get_providers(context):
        abort(406, "Provider 'chef-local' deprecated. Use 'chef-solo' "
              "instead.")

    # Analyze Deployment and Create plan
    planner = Plan(deployment)
    resources = planner.plan(context)

    # Store plan results in deployment
    if resources:
        deployment['resources'] = resources

    # Mark deployment as planned and return it (nothing has been saved so far)
    deployment['status'] = 'PLANNED'
    LOG.info("Deployment '%s' planning complete and status changed to %s" %
            (deployment['id'], deployment['status']))
    return deployment


def deployment_operation(dep_id, driver=DB):
    """Return the operation dictionary for a given deployment.

    Example:

    "operation": {
        "type": "deploy",
        "status": "IN PROGRESS",
        "estimated-duration": 2400,
        "tasks": 175,
        "complete": 100,
        "link": "/v1/{tenant_id}/workflows/982h3f28937h4f23847"
    }
    """
    operation = {}

    # Fetch workflow & deployment data
    raw_workflow = driver.get_workflow(dep_id)
    if not raw_workflow:
        return
    serializer = DictionarySerializer()
    workflow = Workflow.deserialize(serializer, raw_workflow)
    tasks = workflow.task_tree.children
    deployment = driver.get_deployment(dep_id)

    # Loop through tasks and calculate statistics
    spiff_status = {
        1: "FUTURE",
        2: "LIKELY",
        4: "MAYBE",
        8: "WAITING",
        16: "READY",
        32: "CANCELLED",
        64: "COMPLETED",
        128: "TRIGGERED"
    }
    duration = 0
    complete = 0
    failure = 0
    total = 0
    last_change = 0
    while tasks:
        task = tasks.pop(0)
        tasks.extend(task.children)
        status = spiff_status[task._state]
        if status == "COMPLETED":
            complete += 1
        elif status == "FAILURE":
            failure += 1
        duration += task._get_internal_attribute('estimated_completed_in')
        if task.last_state_change > last_change:
            last_change = task.last_state_change
        total += 1
    operation['tasks'] = total
    operation['complete'] = complete
    operation['estimated-duration'] = duration
    operation['last-change'] = get_time_string(time=time.gmtime(last_change))
    if failure > 0:
        operation['status'] = "ERROR"
    elif total > complete:
        operation['status'] = "IN PROGRESS"
    elif total == complete:
        operation['status'] = "COMPLETE"
    else:
        operation['status'] = "UNKNOWN"

    # Operation link
    operation['link'] = "/%s/workflows/%s" % (deployment['tenantId'], dep_id)

    # Operation type
    status_type = {
        "ACTIVE": "deploy",
        "BUILD": "deploy",
        "CONFIGURE": "deploy",
        "DELETED": "delete",
        "DELETING": "delete",
        "LAUNCHED": "deploy",
        "NEW": "deploy",
        "PLANNED": "deploy",
        "RUNNING": "deploy"
    }
    operation['type'] = status_type[deployment['status']]

    return operation


@task
def update_deployment_status(deployment_id, new_status, error_message=None,
                             driver=DB):
    """ Update the status of the specified deployment """
    match_celery_logging(LOG)
    if is_simulation(deployment_id):
        driver = SIMULATOR_DB

    if new_status:
        deployment = driver.get_deployment(deployment_id)
        if deployment:
            deployment['status'] = new_status
            if error_message:
                deployment['errmessage'] = error_message
            driver.save_deployment(deployment_id, deployment)


@task(default_retry_delay=2, max_retries=60)
def delete_deployment_task(dep_id, driver=DB):
    """ Mark the specified deployment as deleted """
    match_celery_logging(LOG)
    if is_simulation(dep_id):
        driver = SIMULATOR_DB
    deployment = driver.get_deployment(dep_id)
    if not deployment:
        raise CheckmateException("Could not finalize delete for deployment %s."
                                 " The deployment was not found.")
    deployment['status'] = "DELETED"
    if "resources" in deployment:
        deletes = []
        for key, resource in deployment.get('resources').items():
            if not str(key).isdigit():
                deletes.append(key)
            else:
                if resource.get('status', 'DELETED') != 'DELETED':
                    resource['statusmsg'] = ('WARNING: Resource should have '
                                             'been in status DELETED but was '
                                             'in %s.' % resource.get('status'))
                    resource['status'] = 'ERROR'
                else:
                    resource['status'] = 'DELETED'
                    resource.pop('instance', None)
        for key in deletes:
            deployment['resources'].pop(key, None)

    return driver.save_deployment(dep_id, deployment, secrets={})


@task(default_retry_delay=0.25, max_retries=4)
def alt_resource_postback(contents, deployment_id, driver=DB):
    """ This is just an argument shuffle to make it easier
    to chain this with other tasks """
    match_celery_logging(LOG)
    if is_simulation(deployment_id):
        driver = SIMULATOR_DB
    resource_postback.delay(deployment_id, contents, driver=driver)


@task(default_retry_delay=0.25, max_retries=4)
def update_all_provider_resources(provider, deployment_id, status,
                                  message=None, trace=None, driver=DB):
    match_celery_logging(LOG)
    if is_simulation(deployment_id):
        driver = SIMULATOR_DB
    dep = driver.get_deployment(deployment_id)
    if dep:
        rupdate = {'status': status}
        if message:
            rupdate['statusmsg'] = message
        if trace:
            rupdate['trace'] = trace
        ret = {}
        for resource in [res for res in dep.get('resources', {}).values()
                         if res.get('provider') == provider]:
            rkey = "instance:%s" % resource.get('index')
            ret.update({rkey: rupdate})
        if ret:
            resource_postback.delay(deployment_id, ret, driver=driver)
            return ret


@task(default_retry_delay=0.25, max_retries=4)
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
    - a connection value (under connection\:name):
        {'connection:web-backend':
            {'interface': 'mysql',
            'field_name': value}
        }
        Note: connection 'interface' is always included.
        Note: connection:host always refers to the hosting connection if there

    The contents are a hash (dict) of all the above
    """
    match_celery_logging(LOG)
    if is_simulation(deployment_id):
        driver = SIMULATOR_DB

    deployment = driver.get_deployment(deployment_id, with_secrets=True)
    deployment = Deployment(deployment)
    updates = {}

    # Update operation
    operation = deployment_operation(deployment_id, driver=driver)
    if operation:
        updates['operation'] = operation

    # Update deployment status

    assert isinstance(contents, dict), "Must postback data in dict"

    # Set status of resource if post_back includes status
    for key, value in contents.items():
        if 'status' in value:
            r_id = key.split(':')[1]
            r_status = value.get('status')
            write_path(updates, 'resources/%s/status' % r_id, r_status)
            # Don't want to write status to resource instance
            value.pop('status', None)
            if r_status == "ERROR":
                r_msg = value.get('errmessage')
                write_path(updates, 'resources/%s/errmessage' % r_id, r_msg)
                value.pop('errmessage', None)
                updates['status'] = "ERROR"
                updates['errmessage'] = deployment.get('errmessage', [])
                if r_msg not in updates['errmessage']:
                    updates['errmessage'].append(r_msg)

    # Create new contents dict if values existed
    # TODO: make this smarter
    new_contents = {}
    for key, value in contents.items():
        if value:
            new_contents[key] = value

    if new_contents:
        deployment.on_resource_postback(new_contents, target=updates)

    status, error_messages = calculate_deployment_status(deployment)

    if status:
        updates['status'] = status
    if error_messages:
        updates['error_messages'] = error_messages

    if updates:
        body, secrets = extract_sensitive_data(updates)
        driver.save_deployment(deployment_id, body, secrets, partial=True)

        LOG.debug("Updated deployment %s with post-back", deployment_id,
                  extra=dict(data=contents))


def calculate_deployment_status(deployment):
    '''Check all resources statuses and calculate a deployment status

    :param deployment: the deployment to calculate
    :returns: tuple of (status, error_message_list)
    '''
    count = 0
    statuses = {
        "NEW": 0,
        "BUILD": 0,
        "CONFIGURE": 0,
        "ACTIVE": 0,
        'PLANNED': 0,
        'ERROR': 0,
        'DELETED': 0,
        'DELETING': 0,
    }

    status = None
    error_messages = deployment.get('errmessage', [])
    resources = deployment['resources']
    for key, value in resources.items():
        if key.isdigit():
            r_status = resources[key].get('status')
            if r_status == "ERROR":
                r_msg = resources[key].get('errmessage')
                if r_msg not in error_messages:
                    error_messages.append(r_msg)
            statuses[r_status] += 1
            count += 1

    if deployment['status'] != "ERROR":
        if statuses['DELETING'] >= 1:
            status = "DELETING"
        elif statuses['DELETED'] == count:
            status = "DELETED"
        elif statuses['PLANNED'] == count:
            status = "PLANNED"
        elif statuses['NEW'] == count:
            status = "NEW"
        elif statuses['ACTIVE'] == count:
            status = "ACTIVE"
        elif statuses['CONFIGURE'] >= 1:
            status = "CONFIGURE"
        elif statuses['BUILD'] >= 1:
            status = "BUILD"
        else:
            LOG.debug("Could not identify a deployment status update")
    return (status, error_messages)
