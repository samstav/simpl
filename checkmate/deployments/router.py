'''
Deployments Resource Router

Handles API calls to /deployments and routes them appropriately
'''
import copy
import logging
import os
import uuid

import bottle  # pylint: disable=E0611

from SpiffWorkflow.storage import DictionarySerializer

from checkmate import blueprints
from checkmate.common import config
from checkmate.common import tasks as common_tasks
from checkmate import db
from checkmate import deployment as cmdeploy
from checkmate import operations
from checkmate import utils
from checkmate import workflow
from checkmate import workflows
from checkmate.deployments import tasks
from checkmate.workflows import tasks as wf_tasks
from checkmate.exceptions import (
    CheckmateBadState,
    CheckmateDoesNotExist,
    CheckmateValidationException,
)

LOG = logging.getLogger(__name__)
DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))
DRIVERS = {'default': DB, 'simulation': SIMULATOR_DB}


#
# Shared Functions
#
def _content_to_deployment(request=bottle.request, deployment_id=None,
                           tenant_id=None):
    '''Receives request content and puts it in a deployment.

    :param bottle_request: the bottlepy request object
    :param deployment_id: the expected/requested ID
    :param tenant_id: the tenant ID in the request

    '''
    entity = utils.read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']  # Unwrap if wrapped

    if request.headers and 'X-Source-Untrusted' in request.headers:
        LOG.info("X-Source-Untrusted: Validating Blueprint against "
                 "Checkmate's cached version.")
        _validate_blueprint(entity)
        LOG.info("X-Source-Untrusted: Validating blueprint is "
                 "self-consistent.")
        _validate_inputs_against_blueprint(entity, tenant_id)

    if 'id' not in entity:
        entity['id'] = deployment_id or uuid.uuid4().hex
    if db.any_id_problems(entity['id']):
        raise CheckmateValidationException(db.any_id_problems(entity['id']))
    deployment = cmdeploy.Deployment(entity)  # Also validates syntax
    if 'includes' in deployment:
        del deployment['includes']
    if 'tenantId' in deployment and tenant_id:
        if deployment['tenantId'] != tenant_id:
            raise CheckmateValidationException("tenantId must match "
                                               "with current tenant ID")
    else:
        assert tenant_id, "Tenant ID must be specified in deployment."
        deployment['tenantId'] = tenant_id
    if 'created-by' not in deployment:
        deployment['created-by'] = request.context.username
    return deployment


def _validate_blueprint(deployment):
    '''Someone could have tampered with the blueprint!'''
    curr_config = config.current()
    if curr_config.github_api is None:
        raise CheckmateValidationException('Cannot validate blueprint.')
    github_manager = blueprints.GitHubManager(DRIVERS, curr_config)
    if github_manager.blueprint_is_invalid(deployment):
        LOG.info("X-Source-Untrusted: Passed in Blueprint did not match "
                 "anything in Checkmate's cache.")
        raise CheckmateValidationException('Invalid Blueprint.')


def _validate_inputs_against_blueprint(deployment, tenant_id):
    """Only used for extra checking when X-Source-Unstrusted header found."""
    inputs = deployment.get('inputs', {})
    # Make sure 'blueprint' is the only key directly under 'inputs'
    if not inputs.get('blueprint') or len(inputs) > 1:
        LOG.info('X-Source-Untrusted: invalid input section. Tenant ID: %s.',
                 tenant_id)
        raise CheckmateValidationException(
            'POST deployment: malformed inputs.')

    # Make sure 'inputs->blueprint' only contains valid options
    delta = (
        set(inputs['blueprint'].keys()) -
        set(deployment['blueprint']['options'].keys())
    )
    if delta:
        LOG.info('X-Source-Untrusted: invalid blueprint options found. '
                 'Tenant ID: %s.', tenant_id)
        raise CheckmateValidationException(
            'POST deployment: inputs not valid.')

    # Check valid options: value must be less than 4k characters
    for _, value in inputs['blueprint'].items():
        if len(value) > 4096:
            LOG.info('X-Source-Untrusted: value to large (%d characters). '
                     'Tenant ID: %s.', len(value), tenant_id)
            raise CheckmateValidationException(
                'POST deployment: cannot parse values.')


def write_deploy_headers(deployment_id, tenant_id=None):
    '''Write new resource location and link headers.'''
    if tenant_id:
        bottle.response.add_header('Location', "/%s/deployments/%s" %
                                   (tenant_id, deployment_id))
        bottle.response.add_header('Link', '</%s/workflows/%s>; '
                                   'rel="workflow"; title="Deploy"' %
                                   (tenant_id, deployment_id))
    else:
        bottle.response.add_header(
            'Location', "/deployments/%s" % deployment_id)
        bottle.response.add_header('Link', '</workflows/%s>; '
                                   'rel="workflow"; title="Deploy"' %
                                   deployment_id)


class Router(object):
    '''Route /deployments/ calls.'''

    def __init__(self, app, manager):
        '''Takes a bottle app and routes traffic for it.'''
        self.app = app
        self.manager = manager

        # Deployment list
        app.route('/deployments', 'GET', self.get_deployments)
        app.route('/deployments', 'POST', self.post_deployment)
        app.route('/deployments/simulate', 'POST', self.simulate)
        app.route('/deployments/count', 'GET', self.get_count)
        app.route('/deployments/+parse', 'POST', self.parse_deployment)
        app.route('/deployments/+preview', 'POST', self.preview_deployment)

        # Deployment Resource
        app.route('/deployments/<api_id>', 'GET', self.get_deployment)
        app.route('/deployments/<api_id>', 'PUT', self.update_deployment)
        app.route('/deployments/<api_id>', 'DELETE', self.delete_deployment)

        # Actions
        app.route('/deployments/<api_id>/+clone', 'POST',
                  self.clone_deployment)
        app.route('/deployments/<api_id>/+plan', ['POST', 'GET'],
                  self.plan_deployment)
        app.route('/deployments/<api_id>/+sync', ['POST', 'GET'],
                  self.sync_deployment)
        app.route('/deployments/<api_id>/+deploy', ['POST', 'GET'],
                  self.deploy_deployment)
        app.route('/deployments/<api_id>/+add-nodes', ['POST', 'GET'],
                  self.add_nodes)

        # Secrets
        app.route('/deployments/<api_id>/secrets', 'GET',
                  self.get_deployment_secrets)
        app.route('/deployments/<api_id>/secrets', 'POST',
                  self.update_deployment_secrets)

        # Resources
        app.route('/deployments/<api_id>/resources', 'GET',
                  self.get_deployment_resources)
        app.route('/deployments/<api_id>/resources/status', 'GET',
                  self.get_resources_statuses)
        app.route('/deployments/<api_id>/resources/<rid>', 'GET',
                  self.get_resource)

    params_whitelist = ['search', 'name', 'blueprint.name', 'status']

    @utils.with_tenant
    @utils.formatted_response('deployments', with_pagination=True)
    def get_deployments(self, tenant_id=None, offset=None, limit=None):
        '''Get existing deployments.'''
        limit = utils.cap_limit(limit, tenant_id)  # Avoid DoS from huge limit
        show_deleted = bottle.request.query.get('show_deleted')
        statuses = bottle.request.query.getall('status')
        params = bottle.request.query.dict
        query = utils.QueryParams.parse(params, self.params_whitelist)
        return self.manager.get_deployments(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit,
            with_deleted=show_deleted == '1',
            status=statuses,
            query=query,
        )

    @utils.with_tenant
    def post_deployment(self, tenant_id=None):
        '''Creates deployment and workflow.

        Triggers workflow execution.
        '''
        deployment = _content_to_deployment(tenant_id=tenant_id)

        is_simulation = bottle.request.context.simulation
        if is_simulation:
            deployment['id'] = utils.get_id(is_simulation)
        api_id = str(deployment['id'])
        if bottle.request.query.get('asynchronous') == '1':
            self.manager.save_deployment(deployment, api_id=api_id,
                                         tenant_id=tenant_id)
            request_context = copy.deepcopy(bottle.request.context)
            tasks.process_post_deployment.delay(deployment, request_context)
        else:
            tasks.process_post_deployment(deployment, bottle.request.context,
                                          driver=self.manager
                                          .select_driver(api_id))
        bottle.response.status = 202
        write_deploy_headers(api_id, tenant_id=tenant_id)
        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def simulate(self, tenant_id=None):
        '''Run a simulation.'''
        bottle.request.context.simulation = True
        return self.post_deployment(tenant_id=tenant_id)

    @utils.with_tenant
    def get_count(self, tenant_id=None):
        '''Get existing deployment count.'''
        result = self.manager.count(tenant_id=tenant_id)
        return utils.write_body(
            {'count': result}, bottle.request, bottle.response)

    @utils.with_tenant
    def parse_deployment(self, tenant_id=None):
        '''Parse a deployment and return the parsed response.'''
        if bottle.request.query.get('check_limits') == "0":
            check_limits = False
        else:
            check_limits = True
        if bottle.request.query.get('check_access') == "0":
            check_access = False
        else:
            check_access = True
        deployment = _content_to_deployment(tenant_id=tenant_id)
        results = self.manager.plan(deployment, bottle.request.context,
                                    check_limits=check_limits,
                                    check_access=check_access,
                                    parse_only=True)
        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def preview_deployment(self, tenant_id=None):
        '''Parse and preview a deployment and its workflow.'''
        deployment = _content_to_deployment(tenant_id=tenant_id)
        results = self.manager.plan(deployment, bottle.request.context)
        spec = workflows.WorkflowSpec.create_workflow_spec_deploy(
            results, bottle.request.context)
        serializer = DictionarySerializer()
        serialized_spec = spec.serialize(serializer)
        results['workflow'] = dict(wf_spec=serialized_spec)

        # Return any errors found
        errors = spec.validate()
        if errors:
            results['messages'] = errors

        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def get_deployment(self, api_id, tenant_id=None):
        '''Return deployment with given ID.'''
        try:
            # TODO(any): verify admin-ness
            if 'with_secrets' in bottle.request.query:
                entity = self.manager.get_deployment(api_id, tenant_id,
                                                     with_secrets=True)
            else:
                entity = self.manager.get_deployment(api_id, tenant_id,
                                                     with_secrets=False)

        except CheckmateDoesNotExist:
            bottle.abort(404)
        if tenant_id is not None and tenant_id != entity.get('tenantId'):
            LOG.warning("Attempt to access deployment %s from wrong tenant %s "
                        "by %s", api_id,
                        tenant_id, bottle.request.context.username)
            bottle.abort(404)

        return utils.write_body(entity, bottle.request, bottle.response)

    @utils.with_tenant
    def update_deployment(self, api_id, tenant_id=None):
        '''Store a deployment on this server'''
        deployment = _content_to_deployment(
            deployment_id=api_id, tenant_id=tenant_id)
        try:
            entity = self.manager.get_deployment(api_id)
        except CheckmateDoesNotExist:
            entity = None
        results = self.manager.save_deployment(deployment,
                                               api_id=api_id,
                                               tenant_id=tenant_id)
        # Return response (with new resource location in header)
        if entity:
            bottle.response.status = 200  # OK - updated
        else:
            bottle.response.status = 201  # Created
            if tenant_id:
                bottle.response.add_header('Location', "/%s/deployments/%s" %
                                           (tenant_id, api_id))
            else:
                bottle.response.add_header(
                    'Location', "/deployments/%s" % api_id)
        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def add_nodes(self, api_id, tenant_id=None):
        """Add nodes to deployment identified by api_id."""
        LOG.debug("[AddNodes] Received a call to add_nodes")
        if utils.is_simulation(api_id):
            bottle.request.context.simulation = True
        deployment = self.manager.get_deployment(api_id, tenant_id=tenant_id,
                                                 with_secrets=True)
        if not deployment:
            raise CheckmateDoesNotExist("No deployment with id %s" % api_id)
        deployment = cmdeploy.Deployment(deployment)
        body = utils.read_body(bottle.request)
        if 'service_name' in body:
            service_name = body['service_name']
        if 'count' in body:
            count = int(body['count'])

        LOG.debug("Add %s nodes for service %s", count, service_name)

        #Should error out if the deployment is building
        if not service_name or not count:
            bottle.abort(400, "Invalid input, service_name and count is not "
                              "provided in the query string")
        deployment = self.manager.plan_add_nodes(deployment,
                                                 bottle.request.context,
                                                 service_name,
                                                 count)
        self.manager.deploy_add_nodes(deployment, bottle.request.context,
                                      tenant_id)
        deployment = self.manager.save_deployment(deployment, api_id=api_id,
                                                  tenant_id=tenant_id)
        add_nodes_wf_id = deployment['operation']['workflow-id']
        wf_tasks.run_workflow.delay(
            add_nodes_wf_id, timeout=3600, driver=self.manager.select_driver(
                api_id))

        # Set headers
        location = "/deployments/%s" % api_id
        link = "/workflows/%s" % add_nodes_wf_id
        if tenant_id:
            location = "/%s%s" % (tenant_id, location)
            link = "/%s%s" % (tenant_id, link)
        bottle.response.set_header("Location", location)
        bottle.response.set_header("Link", '<%s>; rel="workflow"; '
                                   'title="Delete Deployment"' % link)
        bottle.response.set_header("Location", location)

        bottle.response.status = 202  # Accepted (i.e. not done yet)
        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def delete_deployment(self, api_id, tenant_id=None):
        '''Delete the specified deployment.'''
        if utils.is_simulation(api_id):
            bottle.request.context.simulation = True
        deployment = self.manager.get_deployment(api_id)
        if not deployment:
            raise CheckmateDoesNotExist("No deployment with id %s" % api_id)
        deployment = cmdeploy.Deployment(deployment)
        if bottle.request.query.get('force') != '1':
            if not deployment.fsm.permitted('DELETED'):
                bottle.abort(
                    400,
                    "Deployment %s cannot be deleted while in status %s." % (
                        api_id, deployment.get('status', 'UNKNOWN')))
        operation = deployment.get('operation')

        #TODO(any): driver will come from workflow manager once we create that
        driver = self.manager.select_driver(api_id)
        if (operation and operation.get('action') != 'PAUSE' and
                operation['status'] not in ('PAUSED', 'COMPLETE')):
            common_tasks.update_operation.delay(api_id, api_id, driver=driver,
                                                action='PAUSE')
        delete_workflow_spec = (
            workflows.WorkflowSpec.create_delete_deployment_workflow_spec(
                deployment, bottle.request.context))
        spiff_workflow = workflow.create_workflow(
            delete_workflow_spec, deployment, bottle.request.context,
            driver=driver)
        workflow_id = spiff_workflow.attributes.get('id')
        operations.create.delay(api_id, workflow_id, "DELETE", tenant_id)
        wf_tasks.run_workflow.delay(workflow_id, timeout=3600, driver=driver)
        # Set headers
        location = "/deployments/%s" % api_id
        link = "/workflows/%s" % workflow_id
        if tenant_id:
            location = "/%s%s" % (tenant_id, location)
            link = "/%s%s" % (tenant_id, link)
        bottle.response.set_header("Location", location)
        bottle.response.set_header("Link", '<%s>; rel="workflow"; '
                                   'title="Delete Deployment"' % link)
        bottle.response.set_header("Location", location)

        bottle.response.status = 202  # Accepted (i.e. not done yet)
        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def clone_deployment(self, api_id, tenant_id=None):
        '''Creates deployment and wokflow from a deleted deployment.'''
        assert api_id, "Deployment ID cannot be empty"
        deployment = self.manager.clone(
            api_id,
            bottle.request.context,
            tenant_id=tenant_id,
            simulate=bottle.request.context.simulation
        )
        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def plan_deployment(self, api_id, tenant_id=None):
        '''Plan a NEW deployment and save it as PLANNED.'''
        if db.any_id_problems(api_id):
            bottle.abort(406, db.any_id_problems(api_id))
        entity = self.manager.get_deployment(api_id, with_secrets=True)
        if not entity:
            raise CheckmateDoesNotExist('No deployment with id %s' % api_id)
        if entity.get('status', 'NEW') != 'NEW':
            raise CheckmateBadState("Deployment '%s' is in '%s' status and "
                                    "must be in 'NEW' to be planned" %
                                    (api_id, entity.get('status')))
        deployment = cmdeploy.Deployment(entity)  # Also validates syntax
        planned_deployment = self.manager.plan(
            deployment, bottle.request.context)
        results = self.manager.save_deployment(planned_deployment,
                                               deployment_id=api_id,
                                               tenant_id=tenant_id)
        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def sync_deployment(self, api_id, tenant_id=None):
        '''Sync existing deployment objects with current cloud status.'''
        if db.any_id_problems(api_id):
            bottle.abort(406, db.any_id_problems(api_id))
        entity = self.manager.get_deployment(api_id)
        if not entity:
            raise CheckmateDoesNotExist('No deployment with id %s' % api_id)
        deployment = cmdeploy.Deployment(entity)
        context = bottle.request.context
        context['deployment'] = api_id
        statuses = deployment.get_statuses(bottle.request.context)
        for key, value in statuses.get('resources').iteritems():
            tasks.resource_postback.delay(api_id, {key: value})
        common_tasks.update_operation(api_id, deployment.current_workflow_id(),
                                      deployment_status=statuses[
                                          'deployment_status'],
                                      status=statuses['operation_status'])
        return utils.write_body(
            statuses.get('resources'), bottle.request, bottle.response)

    @utils.with_tenant
    def deploy_deployment(self, api_id, tenant_id=None):
        '''Deploy a NEW or PLANNED deployment and save it as DEPLOYED.'''
        if db.any_id_problems(api_id):
            raise CheckmateValidationException(db.any_id_problems(api_id))
        entity = self.manager.get_deployment(api_id, with_secrets=True)
        if not entity:
            CheckmateDoesNotExist('No deployment with id %s' % api_id)
        deployment = cmdeploy.Deployment(entity)  # Also validates syntax
        if entity.get('status', 'NEW') == 'NEW':
            deployment = self.manager.plan(deployment, bottle.request.context)
        if entity.get('status') != 'PLANNED':
            raise CheckmateBadState("Deployment '%s' is in '%s' status and "
                                    "must be in 'PLANNED' or 'NEW' status to "
                                    "be deployed" % (api_id,
                                                     entity.get('status')))

        # Create a 'new deployment' workflow
        self.manager.deploy(deployment, bottle.request.context)

        # Trigger the workflow
        async_task = self.manager.execute(api_id)
        LOG.debug("Triggered workflow (task='%s')", async_task)

        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def get_deployment_secrets(self, api_id, tenant_id=None):
        '''Return deployment secrets.'''
        try:
            entity = self.manager.get_deployment(api_id, tenant_id=tenant_id)
        except CheckmateDoesNotExist:
            bottle.abort(404)
        if tenant_id is not None and tenant_id != entity.get('tenantId'):
            LOG.warning("Attempt to access deployment %s from wrong tenant %s "
                        "by %s", api_id, tenant_id,
                        bottle.request.context.username)
            bottle.abort(404)

        if not (bottle.request.context.is_admin is True or
                ('created-by' in entity and
                 entity['created-by'] is not None and
                 bottle.request.context.username == entity.get('created-by'))):
            bottle.abort(401, "You must be the creator of a deployment or an "
                              "admin to retrieve its secrets")
        data = self.manager.get_deployment_secrets(api_id, tenant_id=tenant_id)
        return utils.write_body(data, bottle.request, bottle.response)

    @utils.with_tenant
    def update_deployment_secrets(self, api_id, tenant_id=None):
        '''Update/Lock deployment secrets.'''
        partial = utils.read_body(bottle.request)
        try:
            entity = self.manager.get_deployment(api_id,
                                                 tenant_id=tenant_id,
                                                 with_secrets=False)
        except CheckmateDoesNotExist:
            bottle.abort(404)
        if tenant_id is not None and tenant_id != entity.get('tenantId'):
            LOG.warning("Attempt to access deployment %s from wrong tenant %s "
                        "by %s", api_id, tenant_id,
                        bottle.request.context.username)
            bottle.abort(404)

        if not (bottle.request.context.is_admin is True or
                ('created-by' in entity and
                 entity['created-by'] is not None and
                 bottle.request.context.username == entity.get('created-by'))):
            bottle.abort(401, "You must be the creator of a deployment or an "
                         "admin to retrieve its secrets")

        if not partial:
            bottle.abort(400, "No data provided")
        if 'secrets' not in partial:
            bottle.abort(406, "Must supply 'secrets' to be locked")

        results = self.manager.update_deployment_secrets(api_id, partial,
                                                         tenant_id=tenant_id)
        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def get_deployment_resources(self, api_id, tenant_id=None):
        '''Return the resources for a deployment.'''
        # TODO(any): verify admin-ness
        if 'with_secrets' in bottle.request.query:
            deployment = self.manager.get_deployment(api_id, tenant_id,
                                                     with_secrets=True)
        else:
            deployment = self.manager.get_deployment(api_id, tenant_id,
                                                     with_secrets=False)

        resources = self.manager._get_dep_resources(deployment)
        return utils.write_body(resources, bottle.request, bottle.response)

    @utils.with_tenant
    def get_resources_statuses(self, api_id, tenant_id=None):
        '''Get basic status of all deployment resources.'''
        # TODO(any): verify admin-ness
        if 'with_secrets' in bottle.request.query:
            deployment = self.manager.get_deployment(api_id, tenant_id,
                                                     with_secrets=True)
        else:
            deployment = self.manager.get_deployment(api_id, tenant_id,
                                                     with_secrets=False)
        resources = self.manager._get_dep_resources(deployment)
        resp = {}

        for key, val in resources.iteritems():
            if key.isdigit():
                resp.update({
                    key: {
                        'service': val.get('service', 'UNKNOWN'),
                        'status': val.get('status'),
                        'status-message': val.get('status-message'),
                        'error-message': val.get('error-message'),
                        'type': val.get('type', 'UNKNOWN'),
                        'component': val.get('component', 'UNKNOWN'),
                        'provider': val.get('provider', 'core')
                    }
                })

        for val in resp.values():
            if not val.get('status'):
                val['status'] = 'UNKNOWN'
            if 'message' in val and not val.get('message'):
                del val['message']
        return utils.write_body(resp, bottle.request, bottle.response)

    @utils.with_tenant
    def get_resource(self, api_id, rid, tenant_id=None):
        '''Get a specific resource from a deployment.'''
        try:
            result = self.manager.get_resource_by_id(api_id, rid, tenant_id)
            return utils.write_body(result, bottle.request, bottle.response)
        except ValueError as not_found:
            bottle.abort(404, not_found.value)
