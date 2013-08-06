'''
Deployments Manager

Handles deployment logic
'''

import copy
import logging
import uuid

import eventlet

from .planner import Planner
from checkmate import base
from checkmate import db
from checkmate import operations
from checkmate import utils
from checkmate import workflow
from checkmate import workflows
from checkmate.workflows import tasks
from checkmate.deployment import (
    Deployment,
    generate_keys,
)
from checkmate.exceptions import (
    CheckmateBadState,
    CheckmateDoesNotExist,
    CheckmateValidationException,
)

LOG = logging.getLogger(__name__)


class Manager(base.ManagerBase):
    '''Contains Deployments Model and Logic for Accessing Deployments.'''

    def count(self, tenant_id=None, blueprint_id=None, status=None,
              query=None):
        '''Return count of deployments filtered by passed in parameters.'''
        # TODO: This should be a filter at the database layer. Example:
        # get_deployments(tenant_id=tenant_id, blueprint_id=blueprint_id)
        deployments = self.driver.get_deployments(tenant_id=tenant_id,
                                                  with_count=True,
                                                  status=status,
                                                  query=query)
        count = 0
        if blueprint_id:
            if not deployments:
                LOG.debug("No deployments")
            for dep_id, dep in deployments['results'].items():
                if "blueprint" in dep:
                    LOG.debug("Found blueprint %s in deployment %s",
                              dep.get("blueprint"), dep_id)
                    if ((blueprint_id == dep["blueprint"]) or
                            ("id" in dep["blueprint"] and
                             blueprint_id == dep["blueprint"]["id"])):
                        count += 1
                else:
                    LOG.debug("No blueprint defined in deployment %s", dep_id)
        else:
            count = deployments['collection-count']
        return count

    def get_deployments(self, tenant_id=None, offset=None, limit=None,
                        with_deleted=False, status=None, query=None):
        '''Get existing deployments..'''
        results = self.driver.get_deployments(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit,
            with_deleted=with_deleted,
            status=status,
            query=query,
        )
        #FIXME: inefficient and not fail-safe. We need better secrets handling
        for dep in results['results'].itervalues():
            outputs = dep.get('display-outputs')
            if outputs:
                for output in outputs.itervalues():
                    if ('value' in output and
                            (output.get('status') == 'LOCKED' or
                             output.get('is-secret') is True)):
                        del output['value']

        return results

    def save_deployment(self, deployment, api_id=None, tenant_id=None,
                        partial=False):
        '''Sync ID and tenant and save deployment

        :returns: saved deployment
        '''
        if not api_id:
            if 'id' not in deployment:
                api_id = uuid.uuid4().hex
                deployment['id'] = api_id
            else:
                api_id = deployment['id']
        else:
            if 'id' not in deployment:
                deployment['id'] = api_id
            else:
                assert api_id == deployment['id'], ("Deployment ID (%s) "
                                                    "does not match "
                                                    "deploymentId (%s)",
                                                    (api_id,
                                                     deployment['id']))
        if 'tenantId' in deployment:
            if tenant_id:
                assert deployment['tenantId'] == tenant_id, (
                    "tenantId must match with current tenant ID")
            else:
                tenant_id = deployment['tenantId']
        else:
            assert tenant_id, "Tenant ID must be specified in deployment"
            deployment['tenantId'] = tenant_id
        body, secrets = utils.extract_sensitive_data(deployment)
        return self.select_driver(api_id).save_deployment(api_id, body,
                                                          secrets,
                                                          tenant_id=tenant_id,
                                                          partial=partial)

    def deploy(self, deployment, context):
        '''Deploys a deployment and returns the operation.'''
        if deployment.get('status') != 'PLANNED':
            raise CheckmateBadState("Deployment '%s' is in '%s' status and "
                                    "must be in 'PLANNED' status to be "
                                    "deployed" % (deployment['id'],
                                    deployment.get('status')))
        generate_keys(deployment)
        deployment['display-outputs'] = deployment.calculate_outputs()

        deploy_spec = workflows.WorkflowSpec.create_workflow_spec_deploy(
            deployment, context)
        spiff_wf = workflow.create_workflow(
            deploy_spec, deployment, context, driver=self.select_driver(
                deployment['id']), workflow_id=deployment['id'])
        deployment['workflow'] = spiff_wf.attributes['id']
        operations.add(deployment, spiff_wf, "BUILD",
                       tenant_id=deployment['tenantId'])
        self.save_deployment(deployment)

    def get_deployment(self, api_id, tenant_id=None, with_secrets=False):
        '''Get a single deployment by id.
        '''
        entity = self.select_driver(api_id).get_deployment(api_id,
                                                           with_secrets=
                                                           with_secrets)
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

    def get_deployment_secrets(self, api_id, tenant_id=None):
        '''Get the passwords and keys of a single deployment by id.
        '''
        entity = self.select_driver(api_id).get_deployment(api_id,
                                                           with_secrets=True)
        if not entity or (tenant_id and tenant_id != entity.get("tenantId")):
            raise CheckmateDoesNotExist('No deployment with id %s' % api_id)

        secret_outputs = {
            key: value
            for key, value in entity.get('display-outputs', {}).items()
            if value.get('is-secret', False) is True
        }

        for value in secret_outputs.values():
            if 'value' in value and value.get('status') == 'LOCKED':
                del value['value']

        data = {
            'id': api_id,
            'tenantId': tenant_id,
            'secrets': secret_outputs,
        }

        return data

    def update_deployment_secrets(self, api_id, data, tenant_id=None):
        '''Update the passwords and keys of a single deployment.
        '''
        #FIXME: test this
        entity = self.get_deployment(api_id, tenant_id=tenant_id,
                                     with_secrets=True)
        updates = {}
        for output, value in data['secrets'].items():
            if 'status' in value and value['status'] == 'LOCKED':
                if output not in entity.get('display-outputs', {}):
                    raise CheckmateValidationException("No secret called '%s'"
                                                       % output)
                if entity['display-outputs'][output].get('status') != 'LOCKED':
                    if 'display-outputs' not in updates:
                        updates['display-outputs'] = {}
                    if output not in updates['display-outputs']:
                        updates['display-outputs'][output] = {}
                    updates['display-outputs'][output]['status'] = 'LOCKED'
                    updates['display-outputs'][output]['last-locked'] = \
                        utils.get_time_string()

        if updates:
            self.save_deployment(updates, api_id=api_id, tenant_id=tenant_id,
                                 partial=True)
        return {'secrets': updates.get('display-outputs')}

    def get_resource_by_id(self, api_id, rid, tenant_id=None):
        '''Attempt to retrieve a resource from a deployment.'''
        deployment = self.get_deployment(api_id, tenant_id=tenant_id)
        resources = deployment.get("resources")
        if rid in resources:
            return resources.get(rid)
        raise ValueError("No resource %s in deployment %s" % (rid, api_id))

    def execute(self, api_id, timeout=180, tenant_id=None):
        '''Process a checkmate deployment workflow

        Executes and moves the workflow forward.
        Retrieves results (final or intermediate) and updates them into
        deployment.

        :param id: checkmate deployment id
        :returns: the async task
        '''
        if db.any_id_problems(api_id):
            raise CheckmateValidationException(db.any_id_problems(api_id))

        deployment = self.get_deployment(api_id)
        if not deployment:
            raise CheckmateDoesNotExist('No deployment with id %s' % api_id)

        driver = self.select_driver(api_id)
        result = tasks.run_workflow.delay(api_id, timeout=3600, driver=driver)
        return result

    def clone(self, api_id, context, tenant_id=None, simulate=False):
        '''Launch a new deployment from a deleted one.'''
        deployment = self.get_deployment(api_id, tenant_id=tenant_id)

        if deployment['status'] != 'DELETED':
            raise CheckmateBadState(
                "Deployment '%s' is in '%s' status and must be "
                "in 'DELETED' to recreate" % (api_id, deployment['status'])
            )

        if simulate is True:
            deployment['id'] = 'simulate%s' % uuid.uuid4().hex[0:12]
        else:
            deployment['id'] = uuid.uuid4().hex

        # delete resources
        if 'resources' in deployment:
            del deployment['resources']

        if 'operation' in deployment:
            del deployment['operation']

        deployment['status'] = 'NEW'

        self.deploy(deployment, context)

        return self.get_deployment(deployment['id'], tenant_id=tenant_id)

    @staticmethod
    def _get_dep_resources(deployment):
        '''Return the resources for the deployment or abort if not found..'''
        if deployment and "resources" in deployment:
            return deployment.get("resources")
        raise CheckmateDoesNotExist("No resources found for deployment %s" %
                                    deployment.get("id"))

    @staticmethod
    def plan(deployment, context, check_limits=False, check_access=False,
             parse_only=False):
        '''Process a new checkmate deployment and plan for execution.

        This creates templates for resources and connections that will be used
        for the actual creation of resources.

        :param deployment: checkmate deployment instance (dict)
        :param context: RequestContext (auth data, etc) for making API calls
        '''
        assert context.__class__.__name__ == 'RequestContext'
        assert deployment.get('status') == 'NEW'
        assert isinstance(deployment, Deployment)
        if "chef-local" in deployment.environment().get_providers(context):
            raise CheckmateValidationException("Provider 'chef-local' "
                                               "deprecated. Use 'chef-solo' "
                                               "instead.")

        # Analyze Deployment and Create plan
        planner = Planner(deployment, parse_only=parse_only)
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
        deployment['plan'] = planner._data  # get dict so we can serialize it

        # Mark deployment as planned and return it (nothing has been saved yet)
        deployment['status'] = 'PLANNED'
        LOG.info("Deployment '%s' planning complete and status changed to %s",
                 deployment['id'], deployment['status'])
        return deployment

    def reset_failed_resource(self, deployment_id, resource_id):
        '''Creates a copy of a failed resource and appends it at the end of
        the resources collection.

        :param deployment_id:
        :param resource_id:
        :return:
        '''
        #TODO: Need to move the logic to find whether a resource should be
        # reset or not to the providers
        deployment = self.get_deployment(deployment_id)
        tenant_id = deployment["tenantId"]
        resource = deployment['resources'].get(resource_id, None)
        if (resource.get('instance') and resource['instance'].get('id')
                and resource.get('status') == "ERROR"):
            failed_resource = copy.deepcopy(resource)
            resource['status'] = 'PLANNED'
            resource['instance'] = None
            if 'relations' in failed_resource:
                failed_resource.pop('relations')
            failed_resource['index'] = (
                str(len([res for res in deployment.get("resources").keys()
                         if res.isdigit()])))

            deployment_body = {
                "id": deployment_id,
                "tenantId": tenant_id,
                "resources": {
                    failed_resource['index']: failed_resource,
                    resource_id: resource
                }
            }
            self.save_deployment(deployment_body, api_id=deployment_id,
                                 partial=True)

    def postback(self, deployment_id, contents):
        #FIXME: we need to receive a context and check access?
        '''This is a generic postback intended to replace all postback calls.
        Accepts back results from a remote call and updates the deployment with
        the result data.

        Use deployments.tasks.postback for calling as a task

        The data updated must be a dict containing any/all of the following:
        - a deployment status: must be checkmate valid
        - a operation: dict containing operation data
            'operation': {
                'status': 'COMPLETE',
                'tasks': 64,
                'complete': 64,
                'type': 'BUILD'
            }
        - a resources dict containing resources data
            'resources': {
                '1': {
                    'status': 'ACTIVE',
                    'status-message': ''
                    'instance': {
                        'status': 'ACTIVE'
                        'status-message': ''
                    }
                }
            }
        '''

        deployment = self.select_driver(
            deployment_id).get_deployment(deployment_id, with_secrets=True)
        deployment = Deployment(deployment)

        if not isinstance(contents, dict):
            raise CheckmateValidationException("Postback contents is not "
                                               "type dictionary")

        deployment.on_postback(contents, target=deployment)

        body, secrets = utils.extract_sensitive_data(deployment)
        self.driver.save_deployment(deployment_id, body, secrets,
                                    partial=True,
                                    tenant_id=deployment['tenantId'])

        LOG.debug("Updated deployment %s with postback", deployment_id,
                  extra=dict(data=contents))

    def plan_add_nodes(self, deployment, context, service_name, count,
                       parse_only=False):
        '''Process a new checkmate deployment and plan for execution.

        This creates templates for resources and connections that will be used
        for the actual creation of resources.

        :param deployment: checkmate deployment instance (dict)
        :param context: RequestContext (auth data, etc) for making API calls
        '''
        assert context.__class__.__name__ == 'RequestContext'
        assert isinstance(deployment, Deployment)

        # Analyze Deployment and Create plan
        planner = Planner(deployment, parse_only, deployment.get('plan', {}))
        resources = planner.plan_additional_nodes(context, service_name, count)
        if resources:
            deployment.get('resources', {}).update(resources)

        # Save plan details for future rehydration/use
        deployment['plan'] = planner._data  # get dict so we can serialize it

        # Mark deployment as planned and return it (nothing has been saved yet)
        LOG.info("Deployment '%s' planning complete and status changed to %s",
                 deployment['id'], deployment['status'])
        return deployment

    def delete_nodes(self, deployment, context, resource_ids, tenant_id):
        '''Delete the passed in resources from a deployment
        :param deployment: Deployment to delete resources from
        :param context: RequestContext
        :param resource_ids: Resources to delete
        :param tenant_id: TenantId of the customer
        :return:
        '''
        driver = self.select_driver(deployment["id"])
        wf_spec = workflows.WorkflowSpec.create_delete_node_spec(
            deployment, resource_ids, context)
        delete_node_workflow = workflow.create_workflow(wf_spec, deployment,
                                                        context,
                                                        driver=driver)
        operations.add(deployment, delete_node_workflow, "SCALE DOWN",
                       tenant_id)

    def deploy_add_nodes(self, deployment, context, tenant_id):
        driver = self.select_driver(deployment["id"])
        add_node_workflow_spec = (workflows.WorkflowSpec
                                  .create_workflow_spec_deploy(deployment,
                                                               context))
        add_node_workflow = workflow.create_workflow(add_node_workflow_spec,
                                                     deployment, context,
                                                     driver=driver)
        operations.add(deployment, add_node_workflow, "SCALE UP", tenant_id)
