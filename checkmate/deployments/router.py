# pylint: disable=E1101,R0913,W0212,W0613
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
"""Deployments Resource Router

Handles API calls to /deployments and routes them appropriately
"""
import copy
import logging
import random
import time
import uuid

import bottle
from SpiffWorkflow.storage import DictionarySerializer

from checkmate import blueprints
from checkmate.common import config
from checkmate.common import statsd
from checkmate.common import tasks as common_tasks
from checkmate import db
from checkmate import deployment as cmdeploy
from checkmate.deployments import tasks
from checkmate import exceptions
from checkmate import operations
from checkmate import stacks
from checkmate import utils
from checkmate import workflow
from checkmate import workflow_spec
from checkmate.workflows import tasks as wf_tasks

LOG = logging.getLogger(__name__)


#
# Shared Functions
#
def _content_to_deployment(request=bottle.request, deployment_id=None,
                           tenant_id=None):
    """Receives request content and puts it in a deployment.

    :param bottle_request: the bottlepy request object
    :param deployment_id: the expected/requested ID
    :param tenant_id: the tenant ID in the request

    """
    entity = utils.read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']  # Unwrap if wrapped

    if request.headers and 'X-Source-Untrusted' in request.headers:
        LOG.info("X-Source-Untrusted: Validating Blueprint against "
                 "Checkmate's cached version.")
        _validate_blueprint(entity)
        LOG.info("X-Source-Untrusted: Validating blueprint is "
                 "self-consistent.")
        _validate_blueprint_inputs(entity, tenant_id)

    if 'heat_template_version' in entity:
        raise exceptions.CheckmateHOTTemplateException()
    if 'id' not in entity:
        entity['id'] = deployment_id or uuid.uuid4().hex
    if db.any_id_problems(entity['id']):
        raise exceptions.CheckmateValidationException(
            db.any_id_problems(entity['id']))
    if 'includes' in entity:
        del entity['includes']
    if 'tenantId' in entity and tenant_id:
        if entity['tenantId'] != tenant_id:
            msg = "tenantId must match with current tenant ID"
            raise exceptions.CheckmateValidationException(
                msg, friendly_message=msg)
    else:
        assert tenant_id, "Tenant ID must be specified in deployment."
        entity['tenantId'] = tenant_id
    if 'created-by' not in entity:
        entity['created-by'] = request.environ['context'].username
    deployment = cmdeploy.Deployment(entity)  # Also validates syntax
    return deployment


def _validate_blueprint(deployment):
    """Someone could have tampered with the blueprint!"""
    curr_config = config.current()
    if curr_config.github_api is None:
        raise exceptions.CheckmateValidationException(
            'Cannot validate blueprint.')
    github_manager = blueprints.GitHubManager(curr_config)
    if github_manager.blueprint_is_invalid(deployment):
        LOG.info("X-Source-Untrusted: Passed in Blueprint did not match "
                 "anything in Checkmate's cache.")
        raise exceptions.CheckmateValidationException('Invalid Blueprint.')


def _validate_blueprint_inputs(deployment, tenant_id):
    """Only used for extra checking when X-Source-Unstrusted header found."""
    inputs = deployment.get('inputs', {})
    # Make sure 'blueprint' is the only key directly under 'inputs'
    if not inputs.get('blueprint') or len(inputs) > 1:
        LOG.info('X-Source-Untrusted: invalid input section. Tenant ID: %s.',
                 tenant_id)
        raise exceptions.CheckmateValidationException(
            'POST deployment: malformed inputs.')

    # Make sure 'inputs->blueprint' only contains valid options
    delta = (
        set(inputs['blueprint'].keys()) -
        set(deployment['blueprint']['options'].keys())
    )
    if delta:
        LOG.info('X-Source-Untrusted: invalid blueprint options found. '
                 'Tenant ID: %s.', tenant_id)
        raise exceptions.CheckmateValidationException(
            'POST deployment: inputs not valid.')

    # Check valid options: value must be less than 4k characters
    for _, value in inputs['blueprint'].items():
        if isinstance(value, basestring) and len(value) > 4096:
            LOG.info('X-Source-Untrusted: value to large (%d characters). '
                     'Tenant ID: %s.', len(value), tenant_id)
            raise exceptions.CheckmateValidationException(
                'POST deployment: cannot parse values.')


def write_deploy_headers(deployment_id, tenant_id=None):
    """Write new resource location and link headers."""
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
    """Route /deployments/ calls."""

    def __init__(self, app, manager):
        """Takes a bottle app and routes traffic for it."""
        self.app = app
        self.manager = manager

        # Deployment list
        app.route('/deployments', 'GET', self.get_deployments)
        app.route('/deployments', 'POST', self.post_deployment)
        app.route('/deployments', 'PUT', self.update_deployment)
        app.route('/deployments/simulate', 'POST', self.simulate)
        app.route('/deployments/count', 'GET', self.get_count)
        app.route('/deployments/+parse', 'POST', self.parse_deployment)
        app.route('/deployments/+preview', 'POST', self.preview_deployment)

        # Deployment Resource
        app.route('/deployments/<api_id>', 'GET', self.get_deployment)
        app.route('/deployments/<api_id>', 'PUT', self.update_deployment)
        app.route('/deployments/<api_id>', 'DELETE', self.delete_deployment)

        # Actions
        app.route('/deployments/<api_id>/+check', ['POST', 'GET'],
                  self.check_deployment)
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
        app.route('/deployments/<api_id>/+delete-nodes', ['POST', 'GET'],
                  self.delete_nodes)

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
        app.route('/deployments/<api_id>/resources/<r_id>/+take-offline',
                  'POST', self.take_resource_offline)
        app.route('/deployments/<api_id>/resources/<r_id>/+bring-online',
                  'POST', self.bring_resource_online)
        self.stack_router = stacks.Router(self.app, stacks.Manager())

    param_whitelist = ['search', 'name', 'blueprint.name', 'status',
                       'start_date', 'end_date']

    @utils.with_tenant
    @utils.formatted_response('deployments', with_pagination=True)
    def get_deployments(self, tenant_id=None, offset=None, limit=None):
        """Get existing deployments."""
        limit = utils.cap_limit(limit, tenant_id)  # Avoid DoS from huge limit
        show_deleted = bottle.request.query.get('show_deleted')
        statuses = bottle.request.query.getall('status')
        params = copy.deepcopy(bottle.request.query.dict)
        query = utils.QueryParams.parse(params, self.param_whitelist)
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
        """Creates deployment and workflow.

        Triggers workflow execution.
        """
        try:
            deployment = _content_to_deployment(bottle.request,
                                                tenant_id=tenant_id)
        except exceptions.CheckmateHOTTemplateException:
            return self.stack_router.post_stack_compat(tenant_id=tenant_id)

        is_simulation = bottle.request.environ['context'].simulation
        if is_simulation:
            deployment['id'] = utils.get_id(is_simulation)
        api_id = str(deployment['id'])
        if bottle.request.query.get('asynchronous') == '1':
            self.manager.save_deployment(deployment, api_id=api_id,
                                         tenant_id=tenant_id)
            request_context = copy.deepcopy(bottle.request.environ['context'])
            tasks.process_post_deployment.delay(deployment, request_context)
        else:
            tasks.process_post_deployment(deployment,
                                          bottle.request.environ['context'])
        bottle.response.status = 202
        write_deploy_headers(api_id, tenant_id=tenant_id)
        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def simulate(self, tenant_id=None):
        """Run a simulation."""
        bottle.request.environ['context'].simulation = True
        return self.post_deployment(tenant_id=tenant_id)

    @utils.with_tenant
    def get_count(self, tenant_id=None):
        """Get existing deployment count."""
        result = self.manager.count(tenant_id=tenant_id)
        return utils.write_body(
            {'count': result}, bottle.request, bottle.response)

    @utils.with_tenant
    @statsd.collect
    def parse_deployment(self, tenant_id=None):
        """Parse a deployment and return the parsed response."""
        if bottle.request.query.get('check_limits') == "1":
            check_limits = True
        else:
            check_limits = False
        if bottle.request.query.get('check_access') == "1":
            check_access = True
        else:
            check_access = False
        start = time.time()
        deployment = _content_to_deployment(tenant_id=tenant_id)
        results = self.manager.plan(deployment,
                                    bottle.request.environ['context'],
                                    check_limits=check_limits,
                                    check_access=check_access,
                                    parse_only=True)
        duration = time.time() - start
        if duration <= 1:
            LOG.debug("Parse took less than one second: %d", duration)
        elif duration <= 12:
            LOG.warn("Parse took more than one second: %d", duration)
        else:
            LOG.error("Parse took more than 12 seconds: %d", duration)

        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def preview_deployment(self, tenant_id=None):
        """Parse and preview a deployment and its workflow."""
        deployment = _content_to_deployment(tenant_id=tenant_id)
        context = bottle.request.environ['context']
        results = self.manager.plan(deployment, bottle.request.context)
        spec = workflow_spec.WorkflowSpec.create_build_spec(
            results, context)
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
        """Return deployment with given ID."""
        try:
            # TODO(any): verify admin-ness
            if 'with_secrets' in bottle.request.query:
                entity = self.manager.get_deployment(api_id, tenant_id,
                                                     with_secrets=True)
            else:
                entity = self.manager.get_deployment(api_id, tenant_id,
                                                     with_secrets=False)

        except exceptions.CheckmateDoesNotExist:
            bottle.abort(404)
        if tenant_id is not None and tenant_id != entity.get('tenantId'):
            LOG.warning("Attempt to access deployment %s from wrong tenant %s "
                        "by %s", api_id,
                        tenant_id, bottle.request.environ['context'].username)
            bottle.abort(404)

        return utils.write_body(entity, bottle.request, bottle.response)

    @utils.with_tenant
    def update_deployment(self, api_id=None, tenant_id=None):
        """Store a deployment on this server."""
        deployment = _content_to_deployment(
            deployment_id=api_id, tenant_id=tenant_id)

        existing_deployment = None
        if api_id:
            try:
                existing_deployment = self.manager.get_deployment(api_id)
            except exceptions.CheckmateDoesNotExist:
                LOG.debug("Deployment not found: %s", api_id)

        results = self.manager.save_deployment(deployment,
                                               api_id=api_id,
                                               tenant_id=tenant_id)

        # Return response (with new resource location in header)
        if existing_deployment:
            bottle.response.status = 200  # OK - updated
        else:
            bottle.response.status = 201  # Created
            location = []
            if tenant_id:
                location.append('/%s' % tenant_id)
            location.append('/deployments/%s' % results['id'])
            bottle.response.add_header('Location', "".join(location))

        return utils.write_body(results, bottle.request, bottle.response)

    @staticmethod
    def _validate_delete_node_request(api_id, deployment_info,
                                      deployment, service_name, count,
                                      victim_list):
        """Check that a delete node request is valid."""
        if not service_name or not count:
            raise exceptions.CheckmateValidationException(
                "'service_name' and 'count' are required in the request body")

        victim_list_size = len(victim_list)
        if victim_list_size < 0 or victim_list_size > count:
            raise exceptions.CheckmateValidationException(
                "The victim list has more elements than the count")

        if not deployment_info:
            raise exceptions.CheckmateDoesNotExist(
                "No deployment with id %s" % api_id)

        try:
            if service_name not in deployment['blueprint']['services']:
                raise exceptions.CheckmateValidationException(
                    "The specified service does not exist for the deployment")
        except KeyError:
            raise exceptions.CheckmateValidationException(
                "The specified service does not exist for the deployment")

        resources = deployment.get_resources_for_service(service_name)
        service_resources = resources.keys()
        for resource_key in victim_list:
            if resource_key not in service_resources:
                raise exceptions.CheckmateValidationException(
                    "The resource specified in the victim list is not valid")

        return True

    @utils.with_tenant
    def delete_nodes(self, api_id, tenant_id=None):
        """Deletes nodes from a  deployment, based on the resource ids that
        are to be provided in the request body.
        :param api_id:
        :param tenant_id:
        :return:
        """
        context = bottle.request.environ['context']
        if utils.is_simulation(api_id):
            context.simulation = True

        body = utils.read_body(bottle.request)
        service_name = body.get('service_name')
        count = int(body.get('count', 0))
        victim_list = body.get('victim_list', [])
        deployment_info = self.manager.get_deployment(api_id,
                                                      tenant_id=tenant_id,
                                                      with_secrets=True)
        deployment = cmdeploy.Deployment(deployment_info)
        self._validate_delete_node_request(api_id, deployment_info, deployment,
                                           service_name, count, victim_list)

        LOG.debug("Received request to delete %s nodes for service %s for "
                  "deployment %s", count, service_name, deployment['id'])
        resources_for_service = deployment.get_resources_for_service(
            service_name).keys()
        resources_for_service = list(set(resources_for_service) - set(
            victim_list))
        random.shuffle(resources_for_service)
        victim_list.extend(resources_for_service[:(count - len(victim_list))])
        operation = self.manager.deploy_workflow(context, deployment,
                                                 tenant_id, "SCALE DOWN",
                                                 victim_list=victim_list)

        delete_nodes_wf_id = operation['workflow-id']
        wf_tasks.cycle_workflow.delay(delete_nodes_wf_id,
                                      context.get_queued_task_dict())

        # Set headers
        location = "/deployments/%s" % api_id
        link = "/workflows/%s" % delete_nodes_wf_id
        if tenant_id:
            location = "/%s%s" % (tenant_id, location)
            link = "/%s%s" % (tenant_id, link)
        bottle.response.set_header("Location", location)
        bottle.response.set_header("Link", '<%s>; rel="workflow"; '
                                   'title="Delete Nodes"' % link)
        bottle.response.set_header("Location", location)

        bottle.response.status = 202  # Accepted (i.e. not done yet)
        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def add_nodes(self, api_id, tenant_id=None):
        """Add nodes to deployment identified by api_id."""
        if utils.is_simulation(api_id):
            bottle.request.environ['context'].simulation = True
        deployment = self.manager.get_deployment(api_id, tenant_id=tenant_id,
                                                 with_secrets=True)
        if not deployment:
            raise exceptions.CheckmateDoesNotExist(
                "No deployment with id %s" % api_id)
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
                              "provided in the request body")
        context = bottle.request.environ['context']
        deployment = self.manager.plan_add_nodes(deployment,
                                                 context,
                                                 service_name,
                                                 count)
        operation = self.manager.deploy_workflow(context,
                                                 deployment,
                                                 tenant_id, "SCALE UP")
        add_nodes_wf_id = operation['workflow-id']
        wf_tasks.cycle_workflow.delay(add_nodes_wf_id,
                                      context.get_queued_task_dict())

        # Set headers
        location = "/deployments/%s" % api_id
        link = "/workflows/%s" % add_nodes_wf_id
        if tenant_id:
            location = "/%s%s" % (tenant_id, location)
            link = "/%s%s" % (tenant_id, link)
        bottle.response.set_header("Location", location)
        bottle.response.set_header("Link", '<%s>; rel="workflow"; '
                                   'title="Add Nodes"' % link)
        bottle.response.set_header("Location", location)

        bottle.response.status = 202  # Accepted (i.e. not done yet)
        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def delete_deployment(self, api_id, tenant_id=None):
        """Delete the specified deployment."""
        request_context = bottle.request.environ['context']
        if utils.is_simulation(api_id):
            request_context.simulation = True
        deployment = self.manager.get_deployment(api_id)
        if not deployment:
            raise exceptions.CheckmateDoesNotExist(
                "No deployment with id %s" % api_id)
        deployment = cmdeploy.Deployment(deployment)
        if bottle.request.query.get('force') != '1':
            if deployment.get('status') == "DELETED":
                bottle.abort(400, "This deployment has already been deleted.")
            if not deployment.fsm.permitted('DELETED'):
                bottle.abort(
                    400,
                    "Deployment %s cannot be deleted while in status %s." % (
                        api_id, deployment.get('status', 'UNKNOWN')))
        operation = deployment.get('operation')
        if (operation and operation.get("type") == "DELETE"
                and operation.get("status") != "COMPLETE"):
            bottle.abort(400, "This deployment is already in the process of "
                         "being deleted.")

        #TODO(any): driver will come from workflow manager once we create that
        driver = db.get_driver(api_id=api_id)
        if (operation and operation.get('action') != 'PAUSE' and
                operation['status'] not in ('PAUSED', 'COMPLETE')):
            current_wf_id = operations.current_workflow_id(deployment)
            common_tasks.update_operation.delay(api_id, current_wf_id,
                                                driver=driver, action='PAUSE')
        delete_workflow_spec = (
            workflow_spec.WorkflowSpec.create_delete_dep_wf_spec(
                deployment, request_context))
        spiff_workflow = workflow.create_workflow(
            delete_workflow_spec, deployment, request_context,
            driver=driver, wf_type="DELETE")
        workflow_id = spiff_workflow.attributes.get('id')
        LOG.debug("Workflow %s created for deleting deployment %s",
                  workflow_id, api_id)
        operations.create.delay(api_id, workflow_id, "DELETE", tenant_id)
        wf_tasks.cycle_workflow.delay(workflow_id,
                                      request_context.get_queued_task_dict())
        # Set headers
        location = "/deployments/%s" % api_id
        link = "/workflows/%s" % workflow_id
        if tenant_id:
            location = "/%s%s" % (tenant_id, location)
            link = "/%s%s" % (tenant_id, link)
        bottle.response.set_header("Link", '<%s>; rel="workflow"; '
                                   'title="Delete Deployment"' % link)
        bottle.response.set_header("Location", location)

        bottle.response.status = 202  # Accepted (i.e. not done yet)
        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def clone_deployment(self, api_id, tenant_id=None):
        """Creates deployment and wokflow from a deleted deployment."""
        assert api_id, "Deployment ID cannot be empty"
        deployment = self.manager.clone(
            api_id,
            bottle.request.environ['context'],
            tenant_id=tenant_id,
            simulate=bottle.request.environ['context'].simulation
        )
        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def plan_deployment(self, api_id, tenant_id=None):
        """Plan a NEW deployment and save it as PLANNED."""
        if db.any_id_problems(api_id):
            bottle.abort(406, db.any_id_problems(api_id))
        entity = self.manager.get_deployment(api_id, with_secrets=True)
        if not entity:
            raise exceptions.CheckmateDoesNotExist(
                'No deployment with id %s' % api_id)
        if entity.get('status', 'NEW') != 'NEW':
            raise exceptions.CheckmateBadState(
                "Deployment '%s' is in '%s' status and must be in 'NEW' to "
                "be planned" % (api_id, entity.get('status')))
        deployment = cmdeploy.Deployment(entity)  # Also validates syntax
        planned_deployment = self.manager.plan(
            deployment, bottle.request.environ['context'])
        results = self.manager.save_deployment(planned_deployment,
                                               deployment_id=api_id,
                                               tenant_id=tenant_id)
        return utils.write_body(results, bottle.request, bottle.response)

    def _setup_deployment(self, api_id, tenant_id):
        """Basic deployment setup for sync_deployment and check_deployment."""
        if db.any_id_problems(api_id):
            bottle.abort(406, db.any_id_problems(api_id))
        entity = self.manager.get_deployment(api_id)
        if not entity:
            raise exceptions.CheckmateDoesNotExist(
                'No deployment with id %s' % api_id)
        deployment = cmdeploy.Deployment(entity)
        if utils.is_simulation(api_id):
            bottle.request.environ['context'].simulation = True
        bottle.request.environ['context']['deployment'] = api_id
        return deployment

    @utils.with_tenant
    def sync_deployment(self, api_id, tenant_id=None):
        """Sync existing deployment objects with current cloud status."""
        updates = {'meta-data': {'requested-sync': utils.get_time_string()}}
        deployment = self._setup_deployment(api_id, tenant_id)
        try:
            statuses = deployment.get_statuses(
                bottle.request.environ['context'])
            updates['resources'] = statuses['resources']
            updates.update(
                common_tasks.update_operation(
                    api_id,
                    operations.current_workflow_id(deployment),
                    deployment_status=statuses['deployment_status'],
                    status=statuses['operation_status'],
                    check_only=True
                )
            )
            updates['meta-data']['last-sync'] = utils.get_time_string()
        finally:
            db.get_driver(api_id=api_id).save_deployment(api_id, updates,
                                                         partial=True)
        return utils.write_body(
            statuses['resources'], bottle.request, bottle.response)

    @utils.with_tenant
    def check_deployment(self, api_id, tenant_id=None):
        """Check instance statuses."""
        deployment = self._setup_deployment(api_id, tenant_id)
        deployment.get_statuses(bottle.request.environ['context'])
        return utils.write_body(
            utils.format_check(deployment.get('resources')),
            bottle.request,
            bottle.response
        )

    @utils.with_tenant
    def deploy_deployment(self, api_id, tenant_id=None):
        """Deploy a NEW or PLANNED deployment and save it as DEPLOYED."""
        if db.any_id_problems(api_id):
            raise exceptions.CheckmateValidationException(
                db.any_id_problems(api_id))
        entity = self.manager.get_deployment(api_id, with_secrets=True)
        if not entity:
            exceptions.CheckmateDoesNotExist(
                'No deployment with id %s' % api_id)
        deployment = cmdeploy.Deployment(entity)  # Also validates syntax
        context = bottle.request.environ['context']
        if entity.get('status', 'NEW') == 'NEW':
            deployment = self.manager.plan(deployment, context)
        if entity.get('status') != 'PLANNED':
            raise exceptions.CheckmateBadState(
                "Deployment '%s' is in '%s' status and must be in 'PLANNED' "
                "or 'NEW' status to be deployed" % (api_id,
                                                    entity.get('status')))

        # Create a 'new deployment' workflow
        self.manager.deploy(deployment, context)

        # Trigger the workflow
        async_task = self.manager.execute(api_id, context)
        LOG.debug("Triggered workflow (task='%s')", async_task)

        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def get_deployment_secrets(self, api_id, tenant_id=None):
        """Return deployment secrets."""
        try:
            entity = self.manager.get_deployment(api_id, tenant_id=tenant_id)
        except exceptions.CheckmateDoesNotExist:
            bottle.abort(404)
        context = bottle.request.environ['context']
        if tenant_id is not None and tenant_id != entity.get('tenantId'):
            LOG.warning("Attempt to access deployment %s from wrong tenant %s "
                        "by %s", api_id, tenant_id,
                        context.username)
            bottle.abort(404)

        if not (context.is_admin is True or
                ('created-by' in entity and
                 entity['created-by'] is not None and
                 context.username == entity.get('created-by'))):
            bottle.abort(401, "You must be the creator of a deployment or an "
                              "admin to retrieve its secrets")
        data = self.manager.get_deployment_secrets(api_id, tenant_id=tenant_id)
        return utils.write_body(data, bottle.request, bottle.response)

    @utils.with_tenant
    def update_deployment_secrets(self, api_id, tenant_id=None):
        """Update/Lock deployment secrets."""
        partial = utils.read_body(bottle.request)
        try:
            entity = self.manager.get_deployment(api_id,
                                                 tenant_id=tenant_id,
                                                 with_secrets=False)
        except exceptions.CheckmateDoesNotExist:
            bottle.abort(404)
        context = bottle.request.environ['context']
        if tenant_id is not None and tenant_id != entity.get('tenantId'):
            LOG.warning("Attempt to access deployment %s from wrong tenant %s "
                        "by %s", api_id, tenant_id,
                        context.username)
            bottle.abort(404)

        if not (context.is_admin is True or
                ('created-by' in entity and
                 entity['created-by'] is not None and
                 context.username == entity.get('created-by'))):
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
        """Return the resources for a deployment."""
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
        """Get basic status of all deployment resources."""
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
        """Get a specific resource from a deployment."""
        try:
            result = self.manager.get_resource_by_id(api_id, rid, tenant_id)
            return utils.write_body(result, bottle.request, bottle.response)
        except ValueError as not_found:
            bottle.abort(404, not_found.value)

    @utils.with_tenant
    def take_resource_offline(self, api_id, r_id, tenant_id=None):
        """Creates and executes the workflow for taking the passed in
        resource offline.
        """
        if utils.is_simulation(api_id):
            bottle.request.environ['context'].simulation = True
        deployment = self.manager.get_deployment(api_id, tenant_id=tenant_id)
        deployment = cmdeploy.Deployment(deployment)
        resource = deployment.get('resources').get(r_id)
        if not resource:
            bottle.abort(404, "No resource %s in deployment %s" %
                              (r_id, api_id))
        self._validate_node_update_call(deployment, resource)
        context = bottle.request.environ['context']
        operation = self.manager.deploy_workflow(context, deployment,
                                                 tenant_id, "TAKE OFFLINE",
                                                 resource_id=r_id)
        wf_tasks.cycle_workflow.delay(operation['workflow-id'],
                                      context.get_queued_task_dict())
        return utils.write_body(deployment, bottle.request, bottle.response)

    @utils.with_tenant
    def bring_resource_online(self, api_id, r_id, tenant_id=None):
        """Creates and executes the workflow for getting the passed in
        resource online.
        """
        if utils.is_simulation(api_id):
            bottle.request.environ['context'].simulation = True
        deployment = self.manager.get_deployment(api_id, tenant_id=tenant_id)
        deployment = cmdeploy.Deployment(deployment)
        resource = deployment.get('resources').get(r_id)
        if not resource:
            bottle.abort(404, "No resource %s in deployment %s" %
                              (r_id, api_id))
        self._validate_node_update_call(deployment, resource)
        context = bottle.request.environ['context']
        operation = self.manager.deploy_workflow(context, deployment,
                                                 tenant_id, "BRING ONLINE",
                                                 resource_id=r_id)
        wf_tasks.cycle_workflow.delay(operation['workflow-id'],
                                      context.get_queued_task_dict())
        return utils.write_body(deployment, bottle.request, bottle.response)

    @staticmethod
    def _validate_node_update_call(deployment, resource):
        """Validates lb node status update calls."""
        service = resource.get('service')
        index = resource.get('index')
        valid_resource_keys = deployment.get_resources_for_service(
            service).keys()
        if index not in valid_resource_keys:
            raise exceptions.CheckmateValidationException(
                "Resource id %s is not valid" % index)
