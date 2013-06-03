'''
Deployments Resource Router

Handles API calls to /deployments and routes them appropriately
'''
#pylint: disable=W0212
import copy
import logging
import os
import uuid

#pylint: disable=E0611
from bottle import abort, request, response
from celery import chord
from SpiffWorkflow.storage import DictionarySerializer

from .plan import Plan
from checkmate import utils
from checkmate import db
from checkmate.common import tasks as common_tasks
from checkmate.deployment import Deployment
from checkmate.exceptions import (
    CheckmateBadState,
    CheckmateDoesNotExist,
    CheckmateValidationException,
)
from checkmate.deployments import tasks
from checkmate.utils import with_tenant, formatted_response

LOG = logging.getLogger(__name__)
DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))


#
# Shared Functions
#
def _content_to_deployment(bottle_request, deployment_id=None, tenant_id=None):
    '''Receives request content and puts it in a deployment

    :param bottle_request: the bottlepy request object
    :param deployment_id: the expected/requested ID
    :param tenant_id: the tenant ID in the request

    '''
    entity = utils.read_body(bottle_request)
    if 'deployment' in entity:
        entity = entity['deployment']  # Unwrap if wrapped
    if 'id' not in entity:
        entity['id'] = deployment_id or uuid.uuid4().hex
    if db.any_id_problems(entity['id']):
        raise CheckmateValidationException(db.any_id_problems(entity['id']))
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


class Router(object):
    '''Route /admin/ calls'''

    def __init__(self, app, manager):
        '''Takes a bottle app and routes traffic for it'''
        self.app = app
        self.manager = manager

        app.route('/deployments', 'GET', self.get_deployments)
        app.route('/deployments', 'POST', self.post_deployment)
        app.route('/deployments/simulate', 'POST', self.simulate)
        app.route('/deployments/<api_id>', 'GET', self.get_deployment)
        app.route('/deployments/<api_id>/secrets', 'GET',
                  self.get_deployment_secrets)
        app.route('/deployments/+parse', 'POST', self.parse_deployment)
        app.route('/deployments/+preview', 'POST', self.preview_deployment)
        app.route('/deployments/<api_id>', 'PUT', self.update_deployment)
        app.route('/deployments/<api_id>', 'DELETE', self.delete_deployment)
        app.route('/deployments/<api_id>/+clone', 'POST',
                  self.clone_deployment)
        app.route('/deployments/<api_id>/+plan', ['POST', 'GET'],
                  self.plan_deployment)
        app.route('/deployments/<api_id>/+sync', ['POST', 'GET'],
                  self.sync_deployment)
        app.route('/deployments/<api_id>/+deploy', ['POST', 'GET'],
                  self.deploy_deployment)
        app.route('/deployments/<api_id>/secrets', 'POST',
                  self.update_deployment_secrets)
        app.route('/deployments/<api_id>/resources', 'GET',
                  self.get_deployment_resources)
        app.route('/deployments/<api_id>/resources/status', 'GET',
                  self.get_resources_statuses)
        app.route('/deployments/<api_id>/resources/<rid>', 'GET',
                  self.get_resource)

    @with_tenant
    @formatted_response('deployments', with_pagination=True)
    def get_deployments(self, tenant_id=None, offset=None, limit=None):
        ''' Get existing deployments '''
        show_deleted = request.query.get('show_deleted')
        return self.manager.get_deployments(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit,
            with_deleted=show_deleted == '1'
        )

    @with_tenant
    def post_deployment(self, tenant_id=None):
        '''
        Creates deployment and wokflow based on sent information
        and triggers workflow execution
        '''
        deployment = _content_to_deployment(request, tenant_id=tenant_id)
        if request.context.simulation is True:
            deployment['id'] = 'simulate%s' % uuid.uuid4().hex[0:12]
        api_id = str(deployment['id'])
        if request.query.get('asynchronous') == '1':
            self.manager.save_deployment(deployment, api_id=api_id,
                                         tenant_id=tenant_id)
            write_deploy_headers(api_id, tenant_id=tenant_id)
            request_context = copy.deepcopy(request.context)
            tasks.process_post_deployment.delay(deployment, request_context)
        else:
            write_deploy_headers(api_id, tenant_id=tenant_id)
            tasks.process_post_deployment(deployment, request.context,
                                          driver=self.manager
                                          .select_driver(api_id))
        response.status = 202
        return utils.write_body(deployment, request, response)

    @with_tenant
    def simulate(self, tenant_id=None):
        ''' Run a simulation '''
        request.context.simulation = True
        return self.post_deployment(tenant_id=tenant_id)

    @with_tenant
    def parse_deployment(self, tenant_id=None):
        '''Parse a deployment and return the parsed response'''
        if request.query.get('check_limits') == "0":
            check_limits = False
        else:
            check_limits = True
        if request.query.get('check_access') == "0":
            check_access = False
        else:
            check_access = True
        deployment = _content_to_deployment(request, tenant_id=tenant_id)
        results = self.manager.plan(deployment, request.context,
                                    check_limits=check_limits,
                                    check_access=check_access)
        return utils.write_body(results, request, response)

    @with_tenant
    def preview_deployment(self, tenant_id=None):
        '''Parse and preview a deployment and its workflow'''
        deployment = _content_to_deployment(request, tenant_id=tenant_id)
        results = self.manager.plan(deployment, request.context)
        spec = self.manager.create_workflow_spec_deploy(results,
                                                           request.context)
        serializer = DictionarySerializer()
        serialized_spec = spec.serialize(serializer)
        results['workflow'] = dict(wf_spec=serialized_spec)

        # Return any errors found
        errors = spec.validate()
        if errors:
            results['messages'] = errors

        return utils.write_body(results, request, response)

    @with_tenant
    def get_deployment(self, api_id, tenant_id=None):
        '''Return deployment with given ID'''
        try:
            if 'with_secrets' in request.query:  # TODO: verify admin-ness
                entity = self.manager.get_a_deployment(api_id, tenant_id,
                                                       with_secrets=True)
            else:
                entity = self.manager.get_a_deployment(api_id, tenant_id,
                                                       with_secrets=False)

        except CheckmateDoesNotExist:
            abort(404)
        if tenant_id is not None and tenant_id != entity.get('tenantId'):
            LOG.warning("Attempt to access deployment %s from wrong tenant %s "
                        "by %s", api_id, tenant_id, request.context.username)
            abort(404)

        return utils.write_body(entity, request, response)

    @with_tenant
    def update_deployment(self, api_id, tenant_id=None):
        '''Store a deployment on this server'''
        deployment = _content_to_deployment(request, deployment_id=api_id,
                                            tenant_id=tenant_id)
        try:
            entity = self.manager.get_deployment(api_id)
        except CheckmateDoesNotExist:
            entity = None
        results = self.manager.save_deployment(deployment,
                                               api_id=api_id,
                                               tenant_id=tenant_id)
        # Return response (with new resource location in header)
        if entity:
            response.status = 200  # OK - updated
        else:
            response.status = 201  # Created
            if tenant_id:
                response.add_header('Location', "/%s/deployments/%s" %
                                    (tenant_id, api_id))
            else:
                response.add_header('Location', "/deployments/%s" % api_id)
        return utils.write_body(results, request, response)

    @with_tenant
    def delete_deployment(self, api_id, tenant_id=None):
        '''
        Delete the specified deployment
        '''
        if utils.is_simulation(api_id):
            request.context.simulation = True
        deployment = self.manager.get_deployment(api_id)
        if not deployment:
            abort(404, "No deployment with id %s" % api_id)
        deployment = Deployment(deployment)
        if request.query.get('force') != '1':
            if not deployment.fsm.has_path_to('DELETED'):
                abort(400, "Deployment %s cannot be deleted while in status "
                      "%s." % (api_id, deployment.get("status", "UNKNOWN")))

        planner = Plan(deployment)
        planned_tasks = planner.plan_delete(request.context)
        self.manager.create_delete_operation(deployment, tenant_id=tenant_id)
        self.manager.save_deployment(deployment, api_id=api_id,
                                     tenant_id=tenant_id)
        if planned_tasks:
            common_tasks.update_operation.s(api_id, status="IN PROGRESS")\
                .delay()
            async_task = chord(planned_tasks)(
                tasks.delete_deployment_task.si(api_id,),
                interval=2, max_retries=120)
        else:
            LOG.warn("No delete tasks for deployment %s", api_id)
            async_task = tasks.delete_deployment_task.delay(api_id)

        # Set headers
        location = "/deployments/%s" % api_id
        link = "/canvases/%s" % async_task
        if tenant_id:
            location = "/%s%s" % (tenant_id, location)
            link = "/%s%s" % (tenant_id, link)
        response.set_header("Location", location)
        response.set_header("Link", '<%s>; rel="canvas"; '
                            'title="Delete Deployment"' % link)

        response.status = 202  # Accepted (i.e. not done yet)
        return utils.write_body(deployment, request, response)

    @with_tenant
    def clone_deployment(self, api_id, tenant_id=None):
        '''
        Creates deployment and wokflow based on deleted/active
        deployment information
        '''
        assert api_id, "Deployment ID cannot be empty"
        deployment = self.manager.clone(api_id, request.context,
                                        tenant_id=tenant_id,
                                        simulate=request.context.simulation)
        return utils.write_body(deployment, request, response)

    @with_tenant
    def plan_deployment(self, api_id, tenant_id=None):
        '''Plan a NEW deployment and save it as PLANNED'''
        if db.any_id_problems(api_id):
            abort(406, db.any_id_problems(api_id))
        entity = self.manager.get_deployment(api_id, with_secrets=True)
        if not entity:
            raise CheckmateDoesNotExist('No deployment with id %s' % api_id)
        if entity.get('status', 'NEW') != 'NEW':
            raise CheckmateBadState("Deployment '%s' is in '%s' status and "
                                    "must be in 'NEW' to be planned" %
                                    (api_id, entity.get('status')))
        deployment = Deployment(entity)  # Also validates syntax
        planned_deployment = self.manager.plan(deployment, request.context)
        results = self.manager.save_deployment(planned_deployment,
                                               deployment_id=api_id,
                                               tenant_id=tenant_id)
        return utils.write_body(results, request, response)

    @with_tenant
    def sync_deployment(self, api_id, tenant_id=None):
        '''Sync existing deployment objects with current cloud status'''
        if db.any_id_problems(api_id):
            abort(406, db.any_id_problems(api_id))
        entity = self.manager.get_deployment(api_id)
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
                    tasks.resource_postback.delay(api_id, result)
        return utils.write_body(resources, request, response)

    @with_tenant
    def deploy_deployment(self, api_id, tenant_id=None):
        '''Deploy a NEW or PLANNED deployment and save it as DEPLOYED'''
        if db.any_id_problems(api_id):
            raise CheckmateValidationException(db.any_id_problems(api_id))
        entity = self.manager.get_deployment(api_id, with_secrets=True)
        if not entity:
            CheckmateDoesNotExist('No deployment with id %s' % api_id)
        deployment = Deployment(entity)  # Also validates syntax
        if entity.get('status', 'NEW') == 'NEW':
            deployment = self.manager.plan(deployment, request.context)
        if entity.get('status') != 'PLANNED':
            raise CheckmateBadState("Deployment '%s' is in '%s' status and "
                                    "must be in 'PLANNED' or 'NEW' status to "
                                    "be deployed" % (api_id,
                                    entity.get('status')))

        # Create a 'new deployment' workflow
        self.manager.deploy(deployment, request.context)

        #Trigger the workflow
        async_task = self.manager.execute(api_id)
        LOG.debug("Triggered workflow (task='%s')", async_task)

        return utils.write_body(deployment, request, response)

    @with_tenant
    def get_deployment_secrets(self, api_id, tenant_id=None):
        '''Return deployment secrets'''
        try:
            entity = self.manager.get_a_deployment(api_id, tenant_id=tenant_id)
        except CheckmateDoesNotExist:
            abort(404)
        if tenant_id is not None and tenant_id != entity.get('tenantId'):
            LOG.warning("Attempt to access deployment %s from wrong tenant %s "
                        "by %s", api_id, tenant_id, request.context.username)
            abort(404)

        if not (request.context.is_admin is True or
                ('created-by' in entity and
                 entity['created-by'] is not None and
                 request.context.username == entity.get('created-by'))):
            abort(401, "You must be the creator of a deployment or an admin "
                  "to retrieve its secrets")

        data = self.manager.get_a_deployments_secrets(api_id,
                                                      tenant_id=tenant_id)
        return utils.write_body(data, request, response)

    @with_tenant
    def update_deployment_secrets(self, api_id, tenant_id=None):
        '''Update/Lock deployment secrets'''
        partial = utils.read_body(request)
        try:
            entity = self.manager.get_a_deployment(api_id,
                                                   tenant_id=tenant_id,
                                                   with_secrets=True)
        except CheckmateDoesNotExist:
            abort(404)
        if tenant_id is not None and tenant_id != entity.get('tenantId'):
            LOG.warning("Attempt to access deployment %s from wrong tenant %s "
                        "by %s", api_id, tenant_id, request.context.username)
            abort(404)

        if not (request.context.is_admin is True or
                ('created-by' in entity and
                 entity['created-by'] is not None and
                 request.context.username == entity.get('created-by'))):
            abort(401, "You must be the creator of a deployment or an admin "
                  "to retrieve its secrets")

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
                        utils.get_time_string()

        if updates:
            self.manager.save_deployment(updates, api_id=api_id, tenant_id=tenant_id,
                                         partial=True)
        return utils.write_body({'secrets': updates.get('display-outputs')},
                                request, response)

    @with_tenant
    def get_deployment_resources(self, api_id, tenant_id=None):
        ''' Return the resources for a deployment '''
        if 'with_secrets' in request.query:  # TODO: verify admin-ness
            deployment = self.manager.get_a_deployment(api_id, tenant_id,
                                                       with_secrets=True)
        else:
            deployment = self.manager.get_a_deployment(api_id, tenant_id,
                                                       with_secrets=False)

        resources = self.manager._get_dep_resources(deployment)
        return utils.write_body(resources, request, response)

    @with_tenant
    def get_resources_statuses(self, api_id, tenant_id=None):
        ''' Get basic status of all deployment resources '''
        if 'with_secrets' in request.query:  # TODO: verify admin-ness
            deployment = self.manager.get_a_deployment(api_id, tenant_id,
                                                       with_secrets=True)
        else:
            deployment = self.manager.get_a_deployment(api_id, tenant_id,
                                                       with_secrets=False)
        resources = self.manager._get_dep_resources(deployment)
        resp = {}

        for key, val in resources.iteritems():
            if key.isdigit():
                resp.update({
                    key: {
                        'service': val.get('service', 'UNKNOWN'),
                        "status": (val.get("status") or
                                   val.get("instance", {}).get("status")),
                        'message': (val.get('error-message') or
                                    val.get('instance', {}).get(
                                        "error-message") or
                                    val.get('status-message') or
                                    val.get("instance", {}).get(
                                        "status-message")),
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
        return utils.write_body(resp, request, response)

    @with_tenant
    def get_resource(self, api_id, rid, tenant_id=None):
        ''' Get a specific resource from a deployment '''
        try:
            result = self.manager.get_resource_by_id(api_id, rid, tenant_id)
            return utils.write_body(result, request, response)
        except ValueError as not_found:
            abort(404, not_found.value)
