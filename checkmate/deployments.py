import copy
import logging
import os
import uuid

from bottle import request, response, abort, get, post, delete, route
from celery.canvas import chord
from celery.task import task
from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.storage import DictionarySerializer

from checkmate import orchestrator
from checkmate.db import get_driver, any_id_problems
from checkmate.db.common import ObjectLockedError
from checkmate.deployment import (
    Deployment,
    generate_keys,
    update_operation as new_update_operation,
)
from checkmate.exceptions import (
    CheckmateDoesNotExist,
    CheckmateValidationException,
    CheckmateBadState,
    CheckmateException,
)
from checkmate.workflow import (
    create_workflow_deploy,
    create_workflow_spec_deploy,
    init_operation,
)
from checkmate.utils import (
    write_body,
    read_body,
    extract_sensitive_data,
    with_tenant,
    match_celery_logging,
    is_simulation,
    write_path,
    write_pagination_headers,
)
from checkmate.plan import Plan

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


def create_deploy_operation(deployment, context, tenant_id=None, driver=DB):
    '''Create Workflow Operation'''
    workflow_id = deployment['id']
    spiff_wf = create_workflow_deploy(deployment, context)
    spiff_wf.attributes['id'] = workflow_id
    serializer = DictionarySerializer()
    workflow = spiff_wf.serialize(serializer)
    workflow['id'] = workflow_id  # TODO: need to support multi workflows
    deployment['workflow'] = workflow_id
    operation = init_operation(spiff_wf, operation_type="BUILD",
                               tenant_id=tenant_id)
    if 'operation' in deployment:
        history = deployment.get('operations-history') or []
        history.append(deployment['operation'])
        deployment['operations-history'] = history
    deployment['operation'] = operation

    body, secrets = extract_sensitive_data(workflow)
    driver.save_workflow(workflow_id, body, secrets,
                         tenant_id=deployment['tenantId'])

    return operation


def _deploy(deployment, context, driver=DB):
    """Deploys a deployment and returns the operation"""
    if deployment.get('status') != 'PLANNED':
        raise CheckmateBadState("Deployment '%s' is in '%s' status and must "
                                "be in 'PLANNED' status to be deployed" %
                                (deployment['id'], deployment.get('status')))
    generate_keys(deployment)

    deployment['display-outputs'] = deployment.calculate_outputs()

    operation = create_deploy_operation(deployment, context,
                                        tenant_id=deployment['tenantId'],
                                        driver=driver)

    _save_deployment(deployment, driver=driver)

    return operation


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

    deployments = driver.get_deployments(tenant_id=tenant_id,
                                         offset=offset,
                                         limit=limit)

    write_pagination_headers(deployments,
                             request,
                             response,
                             "deployments",
                             tenant_id)
    return write_body(deployments,
                      request,
                      response)


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

    try:
        # Create a 'new deployment' workflow
        _deploy(parsed_deployment, request_context, driver=driver)
    except ObjectLockedError:
        LOG.warn("Object lock collision in process_post_deployment on "
                 "Deployment %s", deployment.get('id'))
        resource_postback.retry()

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
    _deploy(deployment, request.context, driver=driver)

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
    return write_body(_get_a_deployment_with_request(oid, tenant_id=tenant_id,
                      driver=driver), request, response)


def _get_a_deployment_with_request(oid, tenant_id=None, driver=DB):
    """ 
    Lookup a deployment with secrets if needed. With secrets is stored
    on the request.
    """
    if 'with_secrets' in request.query:  # TODO: verify admin-ness
        return get_a_deployment(oid, tenant_id, driver, with_secrets=True)
    else:
        return get_a_deployment(oid, tenant_id, driver, with_secrets=False)

def get_a_deployment(oid, tenant_id=None, driver=DB, with_secrets=False):
    """
    Get a single deployment by id.
    """
    entity = driver.get_deployment(oid, with_secrets=with_secrets)
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
    deployment = _get_a_deployment_with_request(oid, tenant_id=tenant_id, 
                                                driver=driver)
    resources = _get_dep_resources(deployment)
    return write_body(resources, request, response)


@get('/deployments/<oid>/resources/status')
@with_tenant
def get_resources_statuses(oid, tenant_id=None, driver=DB):
    """ Get basic status of all deployment resources """
    if is_simulation(oid):
        driver = SIMULATOR_DB
    deployment = _get_a_deployment_with_request(oid, tenant_id=tenant_id, driver=driver)
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
    try:
        return write_body(get_resource_by_id(oid, rid, tenant_id, driver),
                        request, response)
    except ValueError as not_found:
        abort(404, not_found.value)

def get_resource_by_id(oid, rid, tenant_id=None, driver=DB):
    if is_simulation(oid):
        driver = SIMULATOR_DB
    deployment = get_a_deployment(oid, tenant_id=tenant_id, driver=driver)
    resources = deployment.get("resources")
    if rid in resources:
        return resources.get(rid)
    raise ValueError("No resource %s in deployment %s" % (rid, oid))

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
        if not deployment.fsm.has_path_to('DELETED'):
            abort(400, "Deployment %s cannot be deleted while in status %s." %
                  (oid, deployment.get("status", "UNKNOWN")))
    loc = "/deployments/%s" % oid
    link = "/canvases/%s" % oid
    if tenant_id:
        loc = "/%s%s" % (tenant_id, loc)
        link = "/%s%s" % (tenant_id, link)
    planner = Plan(deployment)
    tasks = planner.plan_delete(request.context)
    if tasks:
        update_operation.s(oid, status="IN PROGRESS", driver=driver).delay()
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

    # Save plan details for future rehydration/use
    deployment['plan'] = planner._data  # get the dict so we can serialize it

    # Mark deployment as planned and return it (nothing has been saved so far)
    deployment['status'] = 'PLANNED'
    LOG.info("Deployment '%s' planning complete and status changed to %s" %
            (deployment['id'], deployment['status']))
    return deployment


@task
def update_operation(deployment_id, driver=DB, **kwargs):
    # TODO: Deprecate this
    return new_update_operation(deployment_id, driver=driver, **kwargs)


@task(default_retry_delay=2, max_retries=60)
def delete_deployment_task(dep_id, driver=DB):
    """ Mark the specified deployment as deleted """
    match_celery_logging(LOG)
    if is_simulation(dep_id):
        driver = SIMULATOR_DB
    deployment = Deployment(driver.get_deployment(dep_id))
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

    try:
        return driver.save_deployment(dep_id, deployment, secrets={})
    except ObjectLockedError:
        LOG.warn("Object lock collision in delete_deployment_task on "
                 "Deployment %s", dep_id)
        delete_deployment_task.retry()


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
    - a connection value (under connection.name):
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

    if updates:
        body, secrets = extract_sensitive_data(updates)
        try:
            driver.save_deployment(deployment_id, body, secrets, partial=True)

            LOG.debug("Updated deployment %s with post-back", deployment_id,
                      extra=dict(data=contents))
        except ObjectLockedError:
            LOG.warn("Object lock collision in resource_postback on "
                     "Deployment %s", deployment_id)
            resource_postback.retry()
