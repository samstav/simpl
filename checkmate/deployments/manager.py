'''
Deployments Manager

Handles deployment logic
'''

import copy
import logging
import uuid
import os

import eventlet
from SpiffWorkflow.storage import DictionarySerializer

from .plan import Plan
from checkmate import (
    db,
    utils,
    operations,
    orchestrator,
)
from checkmate.base import ManagerBase
from checkmate.deployment import (
    Deployment,
    generate_keys,
)
from checkmate.exceptions import (
    CheckmateException,
    CheckmateBadState,
    CheckmateDoesNotExist,
    CheckmateValidationException,
)
from checkmate.workflow import create_workflow_deploy, init_operation
from checkmate.db.common import ObjectLockedError

LOG = logging.getLogger(__name__)
DRIVERS = {}
DB = DRIVERS['default'] = db.get_driver()
SIMULATOR_DB = DRIVERS['simulation'] = db.get_driver(
    connection_string=os.environ.get(
        'CHECKMATE_SIMULATOR_CONNECTION_STRING',
        os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')
    )
)

class Manager(ManagerBase):
    '''Contains Deployments Model and Logic for Accessing Deployments'''

    def count(self, tenant_id=None, blueprint_id=None):
        '''Return count of deployments filtered by passed in parameters'''
        # TODO: This should be a filter at the database layer. Example:
        # get_deployments(tenant_id=tenant_id, blueprint_id=blueprint_id)
        deployments = self.driver.get_deployments(tenant_id=tenant_id)
        count = 0
        if blueprint_id:
            if not deployments:
                LOG.debug("No deployments")
            for dep_id, dep in deployments.items():
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
            count = len(deployments)
        return count

    def get_deployments(self, tenant_id=None, offset=None, limit=None,
                        with_deleted=False):
        ''' Get existing deployments '''
        return self.driver.get_deployments(
            tenant_id=tenant_id,
            offset=offset,
            limit=limit,
            with_deleted=with_deleted
        )

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
        '''Deploys a deployment and returns the operation'''
        if deployment.get('status') != 'PLANNED':
            raise CheckmateBadState("Deployment '%s' is in '%s' status and "
                                    "must be in 'PLANNED' status to be "
                                    "deployed" % (deployment['id'],
                                    deployment.get('status')))
        generate_keys(deployment)

        deployment['display-outputs'] = deployment.calculate_outputs()

        operation = self.create_deploy_operation(deployment, context,
                                                 tenant_id=
                                                 deployment['tenantId'])

        self.save_deployment(deployment)

        return operation

    def get_a_deployment(self, api_id, tenant_id=None, with_secrets=False):
        '''
        Get a single deployment by id.
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

    def get_a_deployments_secrets(self, api_id, tenant_id=None):
        '''
        Get the passwords and keys of a single deployment by id.
        '''
        entity = self.select_driver(api_id).get_deployment(api_id,
                                                           with_secrets=True)
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

    get_deployment = get_a_deployment

    def get_resource_by_id(self, api_id, rid, tenant_id=None):
        '''Attempt to retrieve a resource from a deployment'''
        deployment = self.get_a_deployment(api_id, tenant_id=tenant_id)
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

        deployment = self.get_a_deployment(api_id)
        if not deployment:
            raise CheckmateDoesNotExist('No deployment with id %s' % api_id)

        driver = self.select_driver(api_id)
        result = orchestrator.run_workflow.delay(api_id, timeout=3600,
                                                 driver=driver)
        return result

    def clone(self, api_id, context, tenant_id=None, simulate=False):
        '''Launch a new deployment from a deleted one'''
        deployment = self.get_a_deployment(api_id, tenant_id=tenant_id)

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

        return self.get_a_deployment(deployment['id'], tenant_id=tenant_id)

    @staticmethod
    def _get_dep_resources(deployment):
        ''' Return the resources for the deployment or abort if not found '''
        if deployment and "resources" in deployment:
            return deployment.get("resources")
        raise CheckmateDoesNotExist("No resources found for deployment %s" %
                                    deployment.get("id"))

    @staticmethod
    def plan(deployment, context, check_limits=False, check_access=False):
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
        deployment['plan'] = planner._data  # get dict so we can serialize it

        # Mark deployment as planned and return it (nothing has been saved yet)
        deployment['status'] = 'PLANNED'
        LOG.info("Deployment '%s' planning complete and status changed to %s",
                 deployment['id'], deployment['status'])
        return deployment

    #
    # Operations - this should eventually move to operations.py
    #
    def create_deploy_operation(self, deployment, context, tenant_id=None):
        '''Create Deploy Operation (Workflow)'''
        api_id = workflow_id = deployment['id']
        spiff_wf = create_workflow_deploy(deployment, context)
        spiff_wf.attributes['id'] = workflow_id
        serializer = DictionarySerializer()
        workflow = spiff_wf.serialize(serializer)
        workflow['id'] = workflow_id  # TODO: need to support multi workflows
        deployment['workflow'] = workflow_id
        wf_data = init_operation(spiff_wf, tenant_id=tenant_id)
        operation = operations.add_operation(deployment, 'BUILD', **wf_data)

        body, secrets = utils.extract_sensitive_data(workflow)
        driver = self.select_driver(api_id)
        driver.save_workflow(workflow_id, body, secrets,
                             tenant_id=deployment['tenantId'])

        return operation

    def reset_failed_resource(self, deployment_id, resource_id):
        '''
        Creates a copy of a failed resource and appends it at the end of the
        resources collection
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

    def create_delete_operation(self, deployment, tenant_id=None):
        '''Create Delete Operation (Canvas)'''
        if tenant_id:
            link = "/%s/canvases/%s" % (tenant_id, deployment['id'])
        else:
            link = "/canvases/%s" % deployment['id']
        task_count = len(deployment.get('resources', {}))
        operation = operations.add_operation(deployment, 'DELETE', link=link,
                                             status='NEW',
                                             tasks=task_count,
                                             complete=0)
        return operation
    
    @staticmethod    
    def postback(deployment_id, contents, driver=DB):
        #FIXME: we need to receive a context and check access?
        """This is a generic postback intended to replace all postback calls.
        Accepts back results from a remote call and updates the deployment with
        the result data.
        
        Use deployments.tasks.postback for calling as a task

        The data updated must be a dict containing any/all of the following:
        - a deployment status: must be checkmate valid
        - a operation: dict containing operation data
            "operation": {
                "status": "COMPLETE",
                "tasks": 64,
                "complete": 64,
                "type": "BUILD"
            }
        - a resources dict containing resources data
            "resources": {
                "1": {
                    "status": "ACTIVE",
                    "status-message": ""
                    "instance": {
                        "status": "ACTIVE"
                        "status-message": ""
                    }
                }
            }
        """

        utils.match_celery_logging(LOG)
        if utils.is_simulation(deployment_id):
            driver = SIMULATOR_DB

        deployment = driver.get_deployment(deployment_id, with_secrets=True)
        deployment = Deployment(deployment)
    
        if not isinstance(contents, dict):
            raise CheckmateException("Contents passed to deployment_postback "
                                     "is invalid")
    
        keys = ['status','resources','operation']
        if (key in contents for key in keys):
            deployment.on_postback(contents, target=deployment)
            try:
                body, secrets = utils.extract_sensitive_data(deployment)
                driver.save_deployment(deployment_id, body, secrets,
                    partial=True)

                LOG.debug("Updated deployment %s with post-back",
                    deployment_id, extra=dict(data=contents))
            except ObjectLockedError:
                LOG.warn("Object lock collision in postback on "
                         "Deployment %s", deployment_id)
                postback.retry()
        else:
            raise CheckmateException("Contents passed to postback is invalid")
