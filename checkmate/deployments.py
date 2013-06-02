'''bottle routes and Celery tasks for deployments'''
import copy
import logging
import os
import uuid

#pylint: disable=E0611
from bottle import abort, delete, get, post, route, request, response
from celery.canvas import chord
from celery.task import task
from SpiffWorkflow import Task, Workflow
from SpiffWorkflow.storage import DictionarySerializer

from checkmate import orchestrator, operations
from checkmate.common import tasks as common_tasks
from checkmate.db import any_id_problems, get_driver
from checkmate.db.common import ObjectLockedError
from checkmate.deployment import (
    Deployment,
    generate_keys,
)
from checkmate.exceptions import (
    CheckmateBadState,
    CheckmateDoesNotExist,
    CheckmateException,
    CheckmateValidationException,
)
from checkmate.plan import Plan
from checkmate.utils import (
    extract_sensitive_data,
    formatted_response,
    read_body,
    get_time_string,
    is_simulation,
    match_celery_logging,
    with_tenant,
    write_body,
    write_path,
)
from checkmate.workflow import (
    create_workflow_deploy,
    create_workflow_spec_deploy,
    init_operation,
)
import eventlet

LOG = logging.getLogger(__name__)
DB = get_driver()
SIMULATOR_DB = get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))


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
        if deployment['tenantId'] != tenant_id:
            raise CheckmateValidationException("tenantId must match "
                                               "with current tenant ID")
    else:
        assert tenant_id, "Tenant ID must be specified in deployment "
        deployment['tenantId'] = tenant_id
    if 'created-by' not in deployment:
        deployment['created-by'] = bottle_request.context.username
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
            assert deployment_id == deployment['id'], ("Deployment ID (%s) "
                                                       "does not match "
                                                       "deploymentId (%s)",
                                                       (deployment_id,
                                                        deployment['id']))
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


#
# Operations - this should eventually move to operations.py
#
def create_deploy_operation(deployment, context, tenant_id=None, driver=DB):
    '''Create Deploy Operation (Workflow)'''
    workflow_id = deployment['id']
    spiff_wf = create_workflow_deploy(deployment, context)
    spiff_wf.attributes['id'] = workflow_id
    serializer = DictionarySerializer()
    workflow = spiff_wf.serialize(serializer)
    workflow['id'] = workflow_id  # TODO: need to support multi workflows
    deployment['workflow'] = workflow_id
    wf_data = init_operation(spiff_wf, tenant_id=tenant_id)
    operation = operations.add_operation(deployment, 'BUILD', **wf_data)

    body, secrets = extract_sensitive_data(workflow)
    driver.save_workflow(workflow_id, body, secrets,
                         tenant_id=deployment['tenantId'])

    return operation


def create_delete_operation(deployment, tenant_id=None):
    '''Create Delete Operation (Canvas)'''
    if tenant_id:
        link = "/%s/canvases/%s" % (tenant_id, deployment['id'])
    else:
        link = "/canvases/%s" % deployment['id']
    operation = operations.add_operation(deployment, 'DELETE', link=link,
                                         status='NEW',
                                         tasks=len(deployment.get('resources',
                                                   {})),
                                         complete=0)
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
@formatted_response('deployments', with_pagination=True)
def get_deployments(tenant_id=None, offset=None, limit=None, driver=DB):
    """ Get existing deployments """
    show_deleted = request.query.get('show_deleted')
    return driver.get_deployments(
        tenant_id=tenant_id,
        offset=offset,
        limit=limit,
        with_deleted=show_deleted == '1'
    )


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


def write_deploy_headers(deployment_id, tenant_id=None):
    '''Write new resource location and link headers'''
    if tenant_id:
        response.add_header('Location', "/%s/deployments/%s" % (tenant_id,
                                                                deployment_id))
        response.add_header('Link', '</%s/workflows/%s>; '
                            'rel="workflow"; title="Deploy"' % (tenant_id,
                                                                deployment_id))
    else:
        response.add_header('Location', "/deployments/%s" % deployment_id)
        response.add_header('Link', '</workflows/%s>; '
                            'rel="workflow"; title="Deploy"' % deployment_id)


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
    api_id = str(deployment['id'])
    if 'asynchronous' in request.query:
        save_deployment_and_execute_plan(tenant_id, driver, api_id, deployment)
    else:
        write_deploy_headers(api_id, tenant_id=tenant_id)
        process_post_deployment(deployment, request.context, driver=driver)
    return write_body(deployment, request, response)


@post('/deployments/<api_id>/+clone')
@with_tenant
def clone_deployment(api_id, tenant_id=None, driver=DB):
    """
    Creates deployment and wokflow based on deleted/active
    deployment information
    """
    assert api_id, "Deployment ID cannot be empty"

    deployment = get_a_deployment(api_id, tenant_id=tenant_id, driver=driver)
    if not deployment:
        abort(404, 'No deployment found with deployment id %s' % api_id)

    if deployment['status'] != 'DELETED':
        raise CheckmateBadState(
            "Deployment '%s' is in '%s' status and must be "
            "in 'DELETED' to recreate" % (api_id, deployment['status'])
        )

    # give a new deployment ID
    if request.context.simulation is True:
        deployment['id'] = 'simulate%s' % uuid.uuid4().hex[0:12]
    else:
        deployment['id'] = uuid.uuid4().hex

    new_api_id = str(deployment['id'])

    # delete resources
    if 'resources' in deployment:
        del deployment['resources']

    if 'operation' in deployment:
        del deployment['operation']

    deployment['status'] = 'NEW'

    save_deployment_and_execute_plan(tenant_id, driver, new_api_id, deployment)

    return write_body(deployment, request, response)


def save_deployment_and_execute_plan(tenant_id, driver, new_api_id,
                                     deployment):
    # save deployment
    _save_deployment(deployment, deployment_id=new_api_id, tenant_id=tenant_id,
                     driver=driver)

    write_deploy_headers(new_api_id, tenant_id=tenant_id)

    # can't pass actual request
    request_context = copy.deepcopy(request.context)
    execute_plan(new_api_id,
                 request_context,
                 driver=driver,
                 asynchronous=('asynchronous' in request.query))

    response.status = 202


@post('/deployments/simulate')
@with_tenant
def simulate(tenant_id=None):
    """ Run a simulation """
    request.context.simulation = True
    return post_deployment(tenant_id=tenant_id, driver=SIMULATOR_DB)


def execute_plan(depid, request_context, driver=DB, asynchronous=False):
    '''Using the deployment id and request, execute a planned deployment'''
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
    '''Assess deployment, then create and trigger a workflow'''
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
    if request.query.get('check_limits') == "0":
        check_limits = False
    else:
        check_limits = True
    if request.query.get('check_access') == "0":
        check_access = False
    else:
        check_access = True
    deployment = _content_to_deployment(request, tenant_id=tenant_id)
    results = plan(deployment, request.context, check_limits=check_limits,
                   check_access=check_access)
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


@route('/deployments/<api_id>', method=['PUT'])
@with_tenant
def update_deployment(api_id, tenant_id=None, driver=DB):
    """Store a deployment on this server"""
    if is_simulation(api_id):
        driver = SIMULATOR_DB
    deployment = _content_to_deployment(request, deployment_id=api_id,
                                        tenant_id=tenant_id)
    entity = driver.get_deployment(api_id)
    results = _save_deployment(deployment, deployment_id=api_id,
                               tenant_id=tenant_id, driver=driver)
    # Return response (with new resource location in header)
    if entity:
        response.status = 200  # OK - updated
    else:
        response.status = 201  # Created
        if tenant_id:
            response.add_header('Location', "/%s/deployments/%s" % (tenant_id,
                                                                    api_id))
        else:
            response.add_header('Location', "/deployments/%s" % api_id)
    return write_body(results, request, response)


@route('/deployments/<api_id>/+plan', method=['POST', 'GET'])
@with_tenant
def plan_deployment(api_id, tenant_id=None, driver=DB):
    """Plan a NEW deployment and save it as PLANNED"""
    if is_simulation(api_id):
        driver = SIMULATOR_DB
    if any_id_problems(api_id):
        abort(406, any_id_problems(api_id))
    entity = driver.get_deployment(api_id, with_secrets=True)
    if not entity:
        raise CheckmateDoesNotExist('No deployment with id %s' % api_id)
    if entity.get('status', 'NEW') != 'NEW':
        raise CheckmateBadState("Deployment '%s' is in '%s' status and must "
                                "be in 'NEW' to be planned" %
                                (api_id, entity.get('status')))
    deployment = Deployment(entity)  # Also validates syntax
    planned_deployment = plan(deployment, request.context)
    results = _save_deployment(planned_deployment, deployment_id=api_id,
                               tenant_id=tenant_id, driver=driver)
    return write_body(results, request, response)


# pylint: disable=W0613
@route('/deployments/<api_id>/+sync', method=['POST', 'GET'])
@with_tenant
def sync_deployment(api_id, tenant_id=None, driver=DB):
    """Sync existing deployment objects with current cloud status"""
    if is_simulation(api_id):
        driver = SIMULATOR_DB
    if any_id_problems(api_id):
        abort(406, any_id_problems(api_id))
    entity = driver.get_deployment(api_id)
    if not entity:
        raise CheckmateDoesNotExist('No deployment with id %s' % api_id)
    deployment = Deployment(entity)
    env = deployment.environment()
    resources = {}
    for key, resource in entity.get('resources', {}).items():
        if key.isdigit() and 'provider' in resource:
            provider = env.get_provider(resource['provider'])
            result = provider.get_resource_status(request.context,
                                                  api_id, resource, key)
            if result:
                resources.update(result)
                resource_postback.delay(api_id, result, driver=driver)
    return write_body(resources, request, response)


# pylint: disable=W0613
@route('/deployments/<api_id>/+deploy', method=['POST', 'GET'])
@with_tenant
def deploy_deployment(api_id, tenant_id=None, driver=DB):
    """Deploy a NEW or PLANNED deployment and save it as DEPLOYED"""
    if is_simulation(api_id):
        driver = SIMULATOR_DB
    if any_id_problems(api_id):
        raise CheckmateValidationException(any_id_problems(api_id))
    entity = driver.get_deployment(api_id, with_secrets=True)
    if not entity:
        CheckmateDoesNotExist('No deployment with id %s' % api_id)
    deployment = Deployment(entity)  # Also validates syntax
    if entity.get('status', 'NEW') == 'NEW':
        deployment = plan(deployment, request.context)
    if entity.get('status') != 'PLANNED':
        raise CheckmateBadState("Deployment '%s' is in '%s' status and must "
                                "be in 'PLANNED' or 'NEW' status to be "
                                "deployed" % (api_id, entity.get('status')))

    # Create a 'new deployment' workflow
    _deploy(deployment, request.context, driver=driver)

    #Trigger the workflow
    async_task = execute(api_id, driver=driver)
    LOG.debug("Triggered workflow (task='%s')", async_task)

    return write_body(deployment, request, response)


@get('/deployments/<api_id>')
@with_tenant
def get_deployment(api_id, tenant_id=None, driver=DB):
    """Return deployment with given ID"""
    if is_simulation(api_id):
        driver = SIMULATOR_DB

    try:
        entity = _get_a_deployment_with_request(api_id, tenant_id=tenant_id,
                                                driver=driver)
    except CheckmateDoesNotExist:
        abort(404)
    if tenant_id is not None and tenant_id != entity.get('tenantId'):
        LOG.warning("Attempt to access deployment %s from wrong tenant %s by "
                    "%s", api_id, tenant_id, request.context.username)
        abort(404)

    return write_body(entity, request, response)


@get('/deployments/<api_id>/secrets')
@with_tenant
def get_deployment_secrets(api_id, tenant_id=None, driver=DB):
    """Return deployment secrets"""
    if is_simulation(api_id):
        driver = SIMULATOR_DB

    try:
        entity = get_a_deployment(api_id, tenant_id=tenant_id, driver=driver)
    except CheckmateDoesNotExist:
        abort(404)
    if tenant_id is not None and tenant_id != entity.get('tenantId'):
        LOG.warning("Attempt to access deployment %s from wrong tenant %s by "
                    "%s", api_id, tenant_id, request.context.username)
        abort(404)

    if not (request.context.is_admin is True or
            ('created-by' in entity and
             entity['created-by'] is not None and
             request.context.username == entity.get('created-by'))):
        abort(401, "You must be the creator of a deployment or an admin to "
              "retrieve its secrets")

    data = get_a_deployments_secrets(api_id, tenant_id=tenant_id,
                                     driver=driver)
    return write_body(data, request, response)


@post('/deployments/<api_id>/secrets')
@with_tenant
def update_deployment_secrets(api_id, tenant_id=None, driver=DB):
    """Update/Lock deployment secrets"""
    if is_simulation(api_id):
        driver = SIMULATOR_DB

    partial = read_body(request)
    try:
        entity = get_a_deployment(api_id, tenant_id=tenant_id, driver=driver,
                                  with_secrets=True)
    except CheckmateDoesNotExist:
        abort(404)
    if tenant_id is not None and tenant_id != entity.get('tenantId'):
        LOG.warning("Attempt to access deployment %s from wrong tenant %s by "
                    "%s", api_id, tenant_id, request.context.username)
        abort(404)

    if not (request.context.is_admin is True or
            ('created-by' in entity and
             entity['created-by'] is not None and
             request.context.username == entity.get('created-by'))):
        abort(401, "You must be the creator of a deployment or an admin to "
              "retrieve its secrets")

    if not partial:
        abort(400, "No data provided")
    if 'secrets' not in partial:
        abort(406, "Must supply 'secrets' to be locked")

    #FIXME: test this, move it to a separate call
    updates = {}
    for output, value in partial['secrets'].items():
        if 'status' in value and value['status'] == 'LOCKED':
            if output not in entity.get('display-outputs', {}):
                abort(406, "No secret called '%s'" % output)
            if entity['display-outputs'][output].get('status') != 'LOCKED':
                if 'display-outputs' not in updates:
                    updates['display-outputs'] = {}
                if output not in updates['display-outputs']:
                    updates['display-outputs'][output] = {}
                updates['display-outputs'][output]['status'] = 'LOCKED'
                updates['display-outputs'][output]['last-locked'] = \
                    get_time_string()

    if updates:
        body, secrets = extract_sensitive_data(updates)
        driver.save_deployment(api_id, body, secrets, tenant_id=tenant_id,
                               partial=True)
    return write_body({'secrets': updates.get('display-outputs')}, request,
                      response)


def _get_a_deployment_with_request(api_id, tenant_id=None, driver=DB):
    """
    Lookup a deployment with secrets if needed. With secrets is stored
    on the request.
    """
    if 'with_secrets' in request.query:  # TODO: verify admin-ness
        return get_a_deployment(api_id, tenant_id, driver, with_secrets=True)
    else:
        return get_a_deployment(api_id, tenant_id, driver, with_secrets=False)


def get_a_deployment(api_id, tenant_id=None, driver=DB, with_secrets=False):
    """
    Get a single deployment by id.
    """
    entity = driver.get_deployment(api_id, with_secrets=with_secrets)
    if not entity or (tenant_id and tenant_id != entity.get("tenantId")):
        raise CheckmateDoesNotExist('No deployment with id %s' % api_id)

    # Strip secrets
    # FIXME(zns): this is not the place to do this / temp HACK to prove API
    try:
        status = "NO SECRETS"
        outputs = entity.get('display-outputs')
        if outputs:
            for _, value in outputs.items():
                if value.get('is-secret', False) is True:
                    if value.get('status') == "AVAILABLE":
                        status = "AVAILABLE"
                    elif value.get('status') == "LOCKED":
                        if status == "NO SECRETS":
                            status = "LOCKED"
                    elif value.get('status') == "GENERATING":
                        if status != "NO SECRETS":  # some AVAILABLE
                            status = "GENERATING"
                    try:
                        del value['value']
                    except KeyError:
                        pass
        entity['secrets'] = status
    except StandardError as exc:
        # Skip errors in exprimental code
        LOG.exception(exc)
    return entity


def get_a_deployments_secrets(api_id, tenant_id=None, driver=DB):
    """
    Get the passwords and keys of a single deployment by id.
    """
    entity = driver.get_deployment(api_id, with_secrets=True)
    if not entity or (tenant_id and tenant_id != entity.get("tenantId")):
        raise CheckmateDoesNotExist('No deployment with id %s' % api_id)

    secrets = {
        key: value
        for key, value in entity.get('display-outputs', {}).items()
        if value.get('is-secret', False) is True
    }
    data = {
        'id': api_id,
        'tenantId': tenant_id,
        'secrets': secrets,
    }

    return data


def _get_dep_resources(deployment):
    """ Return the resources for the deployment or abort if not found """
    if deployment and "resources" in deployment:
        return deployment.get("resources")
    abort(404, "No resources found for deployment %s" % deployment.get("id"))


@get('/deployments/<api_id>/resources')
@with_tenant
def get_deployment_resources(api_id, tenant_id=None, driver=DB):
    """ Return the resources for a deployment """
    if is_simulation(api_id):
        driver = SIMULATOR_DB
    deployment = _get_a_deployment_with_request(api_id, tenant_id=tenant_id,
                                                driver=driver)
    resources = _get_dep_resources(deployment)
    return write_body(resources, request, response)


@get('/deployments/<api_id>/resources/status')
@with_tenant
def get_resources_statuses(api_id, tenant_id=None, driver=DB):
    """ Get basic status of all deployment resources """
    if is_simulation(api_id):
        driver = SIMULATOR_DB
    deployment = _get_a_deployment_with_request(api_id, tenant_id=tenant_id,
                                                driver=driver)
    resources = _get_dep_resources(deployment)
    resp = {}

    for key, val in resources.iteritems():
        if key.isdigit():
            resp.update({
                key: {
                    'service': val.get('service', 'UNKNOWN'),
                    "status": (val.get("status") or
                               val.get("instance", {}).get("status")),
                    'message': (val.get('error-message') or
                                val.get('instance', {}).get("error-message") or
                                val.get('status-message') or
                                val.get("instance", {}).get("status-message")),
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


@get('/deployments/<api_id>/resources/<rid>')
@with_tenant
def get_resource(api_id, rid, tenant_id=None, driver=DB):
    """ Get a specific resource from a deployment """
    try:
        return write_body(get_resource_by_id(api_id, rid, tenant_id, driver),
                          request, response)
    except ValueError as not_found:
        abort(404, not_found.value)


def get_resource_by_id(api_id, rid, tenant_id=None, driver=DB):
    '''Attempt to retrieve a resource from a deployment'''
    if is_simulation(api_id):
        driver = SIMULATOR_DB
    deployment = get_a_deployment(api_id, tenant_id=tenant_id, driver=driver)
    resources = deployment.get("resources")
    if rid in resources:
        return resources.get(rid)
    raise ValueError("No resource %s in deployment %s" % (rid, api_id))


@delete('/deployments/<api_id>')
@with_tenant
def delete_deployment(api_id, tenant_id=None, driver=DB):
    """
    Delete the specified deployment
    """
    if is_simulation(api_id):
        request.context.simulation = True
        driver = SIMULATOR_DB
    deployment = driver.get_deployment(api_id)
    if not deployment:
        abort(404, "No deployment with id %s" % api_id)
    deployment = Deployment(deployment)
    if request.query_string.get('force') != '1':
        if not deployment.fsm.has_path_to('DELETED'):
            abort(400, "Deployment %s cannot be deleted while in status %s." %
                  (api_id, deployment.get("status", "UNKNOWN")))
    planner = Plan(deployment)
    tasks = planner.plan_delete(request.context)
    create_delete_operation(deployment, tenant_id=tenant_id)

    driver.save_deployment(api_id, deployment, tenant_id=tenant_id,
                           partial=False)
    if tasks:
        common_tasks.update_operation.s(api_id, status="IN PROGRESS",
                                        driver=driver).delay()
        async_task = chord(tasks)(delete_deployment_task.si(api_id,
                                                            driver=driver),
                                  interval=2, max_retries=120)
    else:
        LOG.warn("No delete tasks for deployment %s", api_id)
        async_task = delete_deployment_task.delay(api_id, driver=driver)

    # Set headers
    location = "/deployments/%s" % api_id
    link = "/canvases/%s" % async_task
    if tenant_id:
        location = "/%s%s" % (tenant_id, location)
        link = "/%s%s" % (tenant_id, link)
    response.set_header("Location", location)
    response.set_header("Link", '<%s>; rel="canvas"; title="Delete Deployment"'
                        % link)

    response.status = 202  # Accepted (i.e. not done yet)
    return write_body(deployment, request, response)


@get('/deployments/<api_id>/status')
@with_tenant
def get_deployment_status(api_id, tenant_id=None, driver=DB):
    """Return workflow status of given deployment"""
    if is_simulation(api_id):
        driver = SIMULATOR_DB
    deployment = driver.get_deployment(api_id)
    if not deployment:
        abort(404, 'No deployment with id %s' % api_id)

    resources = deployment.get('resources', {})
    results = {}
    results['status'] = deployment.get('status')
    workflow_id = deployment.get('workflow')
    if workflow_id:
        workflow = driver.get_workflow(workflow_id)
        serializer = DictionarySerializer()
        workflow = Workflow.deserialize(serializer, workflow)
        for wf_task in workflow.get_tasks(state=Task.ANY_MASK):
            if 'resource' in wf_task.task_spec.defines:
                resource_id = str(wf_task.task_spec.defines['resource'])
                resource = resources.get(resource_id, None)
                if resource:
                    result = {}
                    result['state'] = wf_task.get_state_name()
                    error = wf_task.get_attribute('error', None)
                    if error is not None:  # Show empty strings too
                        result['error'] = error
                    result['output'] = {key: wf_task.attributes[key] for key
                                        in wf_task.attributes if key
                                        not in['deployment',
                                        'token', 'error']}
                    if 'tasks' not in resource:
                        resource['tasks'] = {}
                    resource['tasks'][wf_task.get_name()] = result
            else:
                result = {}
                result['state'] = wf_task.get_state_name()
                error = wf_task.get_attribute('error', None)
                if error is not None:  # Show empty strings too
                    result['error'] = error
                if 'tasks' not in results:
                    results['tasks'] = {}
                results['tasks'][wf_task.get_name()] = result

    results['resources'] = resources

    return write_body(results, request, response)


def execute(api_id, timeout=180, tenant_id=None, driver=DB):
    """Process a checkmate deployment workflow

    Executes and moves the workflow forward.
    Retrieves results (final or intermediate) and updates them into
    deployment.

    :param id: checkmate deployment id
    :returns: the async task
    """
    if any_id_problems(api_id):
        abort(406, any_id_problems(api_id))

    deployment = driver.get_deployment(api_id)
    if not deployment:
        abort(404, 'No deployment with id %s' % api_id)

    result = orchestrator.run_workflow.delay(api_id, timeout=3600,
                                             driver=driver)
    return result


def plan(deployment, context, check_limits=False, check_access=False):
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
    if resources:
        deployment['resources'] = resources

    pool = eventlet.GreenPool()
    if check_access:
        access = pool.spawn(planner.verify_access, context)
    if check_limits:
        limits = pool.spawn(planner.verify_limits, context)
    if check_access:
        deployment['check-limit-results'] = limits.wait()
    if check_limits:
        deployment['check-access-results'] = access.wait()

    # Save plan details for future rehydration/use
    deployment['plan'] = planner._data  # get the dict so we can serialize it

    # Mark deployment as planned and return it (nothing has been saved so far)
    deployment['status'] = 'PLANNED'
    LOG.info("Deployment '%s' planning complete and status changed to %s",
             deployment['id'], deployment['status'])
    return deployment


@task
def update_operation(deployment_id, driver=DB, **kwargs):
    '''Wrapper for common_tasks.update_operation'''
    # TODO: Deprecate this
    return common_tasks.update_operation(deployment_id, driver=driver,
                                         **kwargs)


@task(default_retry_delay=2, max_retries=60)
def delete_deployment_task(dep_id, driver=DB):
    """ Mark the specified deployment as deleted """
    match_celery_logging(LOG)
    if is_simulation(dep_id):
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
                else:
                    updates['status'] = 'DELETED'
                    updates['instance'] = None
                contents = {
                    'instance:%s' % resource['index']: updates,
                }
                resource_postback.delay(dep_id, contents, driver=driver)
    common_tasks.update_deployment_status.delay(dep_id, "DELETED",
                                                driver=driver)
    common_tasks.update_operation.delay(dep_id, status="COMPLETE",
                                        complete=len(deployment.get(
                                                     'resources', {})),
                                        driver=driver)


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
    '''Given a deployment, update all resources
    associated with a given provider
    '''
    match_celery_logging(LOG)
    if is_simulation(deployment_id):
        driver = SIMULATOR_DB
    dep = driver.get_deployment(deployment_id)
    if dep:
        rupdate = {'status': status}
        if message:
            rupdate['status-message'] = message
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


@task(default_retry_delay=0.5, max_retries=6)
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
                r_msg = value.get('error-message')
                write_path(updates, 'resources/%s/error-message' % r_id, r_msg)
                value.pop('error-message', None)
                updates['status'] = "FAILED"
                updates['error-message'] = deployment.get('error-message', [])
                if r_msg not in updates['error-message']:
                    updates['error-message'].append(r_msg)

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
