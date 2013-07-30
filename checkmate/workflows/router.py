#pylint: disable=W0212
import logging
import uuid

#pylint: disable=E0611
import bottle

from SpiffWorkflow import (
    Workflow as SpiffWorkflow,
    Task,
)
from SpiffWorkflow.storage import DictionarySerializer

from checkmate import utils
from checkmate import db
from checkmate import workflow as cm_wf
from checkmate.common import tasks as common_tasks
from checkmate.deployment import Deployment
from checkmate.workflows import tasks

LOG = logging.getLogger(__name__)


class Router(object):
    '''Route /deployments/ calls.'''

    def __init__(self, app, manager, deployment_manager):
        '''Takes a bottle app and routes traffic for it.'''
        self.app = app
        self.manager = manager
        self.deployment_manager = deployment_manager

        #Workflow
        app.route('/workflows', 'GET', self.get_workflows)
        app.route('/workflows', 'POST', self.add_workflow)
        app.route('/workflows/<api_id>', ['PUT', 'POST'], self.save_workflow)
        app.route('/workflows/<api_id>', 'GET', self.get_workflow)
        app.route('/workflows/<api_id>/status', 'GET',
                  self.get_workflow_status)
        app.route('/workflows/<workflow_id>/specs/<spec_id>', 'POST',
                  self.post_workflow_spec)

        #Actions
        app.route('/workflows/<api_id>/+execute', ['GET', 'POST'],
                  self.execute_workflow)
        app.route('/workflows/<api_id>/+pause', ['GET', 'POST'],
                  self.pause_workflow)
        app.route('/workflows/<api_id>/+resume', ['GET', 'POST'],
                  self.resume_workflow)
        app.route('/workflows/<api_id>/+retry-failed-tasks', ['GET', 'POST'],
                  self.retry_all_failed_tasks)
        app.route('/workflows/<api_id>/+resume-failed-tasks', ['GET', 'POST'],
                  self.resume_all_failed_tasks)

        #Tasks
        app.route('/workflows/<api_id>/tasks/<task_id:int>', 'GET',
                  self.get_workflow_task)
        app.route('/workflows/<api_id>/tasks/<task_id:int>', 'POST',
                  self.post_workflow_task)
        app.route('/workflows/<api_id>/tasks/<task_id:int>/+reset',
                  ['GET', 'POST'], self.reset_workflow_task)
        app.route('/workflows/<api_id>/tasks/<task_id:int>/+reset-task-tree',
                  ['GET', 'POST'], self.reset_task_tree)
        app.route('/workflows/<api_id>/tasks/<task_id:int>/+resubmit',
                  ['GET', 'POST'], self.resubmit_workflow_task)
        app.route('/workflows/<api_id>/tasks/<task_id:int>/+execute',
                  ['GET', 'POST'], self.execute_workflow_task)

    @utils.with_tenant
    @utils.formatted_response('workflows', with_pagination=True)
    def get_workflows(self, tenant_id=None, offset=None, limit=None):
        if 'with_secrets' in bottle.request.query:
            if bottle.request.context.is_admin is True:
                LOG.info("Administrator accessing workflows with secrets: %s",
                         bottle.request.context.username)
                results = self.manager.get_workflows(tenant_id=tenant_id,
                                                     with_secrets=True,
                                                     offset=offset,
                                                     limit=limit)
            else:
                bottle.abort(403, "Administrator privileges needed for this "
                                  "operation")
        else:
            results = self.manager.get_workflows(
                tenant_id=tenant_id,
                offset=offset,
                limit=limit
            )
        return results

    @utils.with_tenant
    def add_workflow(self, tenant_id=None):
        entity = utils.read_body(bottle.request)
        if 'workflow' in entity and isinstance(entity['workflow'], dict):
            entity = entity['workflow']

        if 'id' not in entity:
            entity['id'] = uuid.uuid4().hex
        if db.any_id_problems(entity['id']):
            bottle.abort(406, db.any_id_problems(entity['id']))

        body, secrets = utils.extract_sensitive_data(entity)
        results = self.manager.save_workflow(entity['id'], body,
                                             secrets=secrets)

        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def save_workflow(self, api_id, tenant_id=None):
        entity = utils.read_body(bottle.request)

        if 'workflow' in entity and isinstance(entity['workflow'], dict):
            entity = entity['workflow']

        problems = db.any_id_problems(api_id)
        if problems:
            bottle.abort(406, problems)
        if 'id' not in entity:
            entity['id'] = str(api_id)

        body, secrets = utils.extract_sensitive_data(entity)

        existing = self.manager.get_workflow(api_id)
        try:
            results = self.manager.safe_workflow_save(str(api_id), body,
                                                      secrets=secrets,
                                                      tenant_id=tenant_id)
        except db.ObjectLockedError:
            bottle.abort(404, "The workflow is already locked, cannot obtain "
                              "lock.")
        if existing:
            bottle.response.status = 200  # OK - updated
        else:
            bottle.response.status = 201  # Created

        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def get_workflow(self, api_id, tenant_id=None):
        if 'with_secrets' in bottle.request.query:
            LOG.info("Administrator accessing workflow %s with secrets: %s",
                     api_id, bottle.request.context.username)
            results = self.manager.get_workflow(api_id, with_secrets=True)
        else:
            results = self.manager.get_workflow(api_id)
        if not results:
            bottle.abort(404, 'No workflow with id %s' % api_id)
        if 'id' not in results:
            results['id'] = str(api_id)
        if tenant_id is not None and tenant_id != results.get('tenantId'):
            LOG.warning("Attempt to access workflow %s from wrong tenant %s by"
                        " %s", api_id, tenant_id,
                        bottle.request.context.username)
            bottle.abort(404)
        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def get_workflow_status(self, api_id, tenant_id=None):
        entity = self.manager.get_workflow(api_id)
        if not entity:
            bottle.abort(404, 'No workflow with id %s' % api_id)
        serializer = DictionarySerializer()
        wf = SpiffWorkflow.deserialize(serializer, entity)
        return utils.write_body(cm_wf.get_SpiffWorkflow_status(wf),
                                bottle.request, bottle.response)

    @utils.with_tenant
    def execute_workflow(self, api_id, tenant_id=None):
        """Process a checkmate deployment workflow

        Executes and moves the workflow forward.
        Retrieves results (final or intermediate) and updates them into
        deployment.

        :param id: checkmate workflow id
        """
        entity = self.manager.get_workflow(api_id)
        if not entity:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        async_call = tasks.run_workflow.delay(api_id, timeout=1800)
        LOG.debug("Executed a task to run workflow '%s'", async_call)
        entity = self.manager.get_workflow(api_id)
        return utils.write_body(entity, bottle.request, bottle.response)

    @utils.with_tenant
    def pause_workflow(self, api_id, tenant_id=None):
        '''Pauses the workflow.
        Updates the operation status to pauses when done

        :param api_id: checkmate workflow id
        '''
        workflow = self.manager.get_workflow(api_id)
        if not workflow:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        workflow = self.manager.get_workflow(api_id)
        dep_id = workflow["attributes"].get("deploymentId") or api_id
        deployment = self.deployment_manager.get_deployment(
            dep_id, tenant_id=tenant_id)
        deployment = Deployment(deployment)
        operation = deployment.get("operation")

        if (operation and operation.get('action') != 'PAUSE' and
                operation['status'] not in ('PAUSED', 'COMPLETE')):
            common_tasks.update_operation.delay(
                dep_id, deployment.current_workflow_id(), action='PAUSE')
            tasks.pause_workflow.delay(api_id)
        return utils.write_body(workflow, bottle.request, bottle.response)

    @utils.with_tenant
    def resume_workflow(self, api_id, tenant_id=None):
        """Process a checkmate deployment workflow

        Executes the workflow again

        :param api_id: checkmate workflow id
        """
        workflow = self.manager.get_workflow(api_id)
        if not workflow:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        dep_id = workflow["attributes"]["deploymentId"] or api_id
        deployment = self.deployment_manager.get_deployment(
            dep_id, tenant_id=tenant_id)
        operation = deployment.get("operation")
        if operation and operation.get('status') == 'PAUSED':
            async_call = tasks.run_workflow.delay(api_id, timeout=1800)
            LOG.debug("Executed a task to run workflow '%s'", async_call)
            workflow = self.manager.get_workflow(api_id)
        return utils.write_body(workflow, bottle.request, bottle.response)

    @utils.with_tenant
    def retry_all_failed_tasks(self, api_id, tenant_id=None):
        workflow = self.manager.get_workflow(api_id)
        if not workflow:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        serializer = DictionarySerializer()
        wf = SpiffWorkflow.deserialize(serializer, workflow)

        dep_id = workflow["attributes"]["deploymentId"] or api_id
        deployment = self.deployment_manager.get_deployment(
            dep_id, tenant_id=tenant_id)
        operation = deployment.get("operation")

        if operation.get("errors"):
            retriable_errors = filter(lambda x: x.get("retriable", False),
                                      operation.get("errors"))
            for error in retriable_errors:
                task_id = error["task-id"]
                task = wf.get_task(task_id)
                LOG.debug("Resetting task %s for workflow %s", task_id, id)
                cm_wf.reset_task_tree(task)

            cm_wf.update_workflow_status(wf, tenant_id=tenant_id)
            entity = wf.serialize(serializer)
            body, secrets = utils.extract_sensitive_data(entity)
            body['tenantId'] = workflow.get('tenantId', tenant_id)
            body['id'] = api_id
            try:
                workflow = self.manager.safe_workflow_save(api_id, body,
                                                           secrets=secrets,
                                                           tenant_id=tenant_id)
            except db.ObjectLockedError:
                bottle.abort(404, "The workflow is already locked, "
                                  "cannot obtain lock.")
        return utils.write_body(workflow, bottle.request, bottle.response)

    @utils.with_tenant
    def resume_all_failed_tasks(self, api_id, tenant_id=None):
        workflow = self.manager.get_workflow(api_id)
        if not workflow:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        dep_id = workflow["attributes"]["deploymentId"] or api_id
        deployment = self.deployment_manager.get_deployment(dep_id, tenant_id)
        operation = deployment.get("operation")

        if operation.get("errors"):
            retriable_errors = filter(lambda x: x.get("resumable", False),
                                      operation.get("errors"))
            for error in retriable_errors:
                task_id = error["task-id"]
                LOG.debug("Resuming task %s for workflow %s", task_id, id)
                tasks.run_one_task.delay(bottle.request.context, api_id,
                                         task_id, timeout=10)

            workflow = self.manager.get_workflow(id)

        return utils.write_body(workflow, bottle.request, bottle.response)

    @utils.with_tenant
    def post_workflow_spec(self, workflow_id, spec_id, tenant_id=None):
        """Update a workflow spec

        :param workflow_id: checkmate workflow id
        :param spec_id: checkmate workflow spec id (a string)
        """
        entity = utils.read_body(bottle.request)

        # Extracting with secrets
        workflow = self.manager.get_workflow(workflow_id, with_secrets=True)
        if not workflow:
            bottle.abort(404, 'No workflow with id %s' % workflow_id)

        spec = workflow['wf_spec']['task_specs'].get(spec_id)
        if not spec:
            bottle.abort(404, 'No spec with id %s' % spec_id)

        LOG.debug("Updating spec '%s' in workflow '%s'", spec_id, workflow_id,
                  extra=dict(data=dict(old=spec, new=entity)))
        workflow['wf_spec']['task_specs'][spec_id] = entity

        # Save workflow (with secrets)
        body, secrets = utils.extract_sensitive_data(workflow)
        body['tenantId'] = workflow.get('tenantId', tenant_id)
        body['id'] = workflow_id
        try:
            result = self.manager.safe_workflow_save(workflow_id, body,
                                                     secrets=secrets,
                                                     tenant_id=tenant_id)
        except db.ObjectLockedError:
            bottle.abort(404, "The workflow is already locked, cannot obtain "
                              "lock.")

        return utils.write_body(result, bottle.request, bottle.response)

    @utils.with_tenant
    def get_workflow_task(self, api_id, task_id, tenant_id=None):
        """Get a workflow task

        :param api_id: checkmate workflow id
        :param task_id: checkmate workflow task id
        """
        if 'with_secrets' in bottle.request.query:  # TODO: verify admin-ness
            entity = self.manager.get_workflow(api_id, with_secrets=True)
        else:
            entity = self.manager.get_workflow(api_id)
        if not entity:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        serializer = DictionarySerializer()
        wf = SpiffWorkflow.deserialize(serializer, entity)

        task = wf.get_task(task_id)
        if not task:
            bottle.abort(404, 'No task with id %s' % task_id)
        data = serializer._serialize_task(task, skip_children=True)
        data['workflow_id'] = api_id  # so we know which workflow it came from
        spec = task.task_spec.serialize(serializer)
        data['spec'] = spec  # include a copy of the spec
        return utils.write_body(data, bottle.request, bottle.response)

    @utils.with_tenant
    def post_workflow_task(self, api_id, task_id, tenant_id=None):
        """Update a workflow task

        Attributes that can be updated are:
        - attributes
        - state
        - internal_attributes

        :param api_id: checkmate workflow id
        :param task_id: checkmate workflow task id
        """
        entity = utils.read_body(bottle.request)

        # Extracting with secrets
        workflow = self.manager.get_workflow(api_id, with_secrets=True)
        if not workflow:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        serializer = DictionarySerializer()
        wf = SpiffWorkflow.deserialize(serializer, workflow)

        task = wf.get_task(task_id)
        if not task:
            bottle.abort(404, 'No task with id %s' % task_id)

        if 'attributes' in entity:
            if not isinstance(entity['attributes'], dict):
                bottle.abort(406, "'attribues' must be a dict")
            # Don't do a simple overwrite since incoming may not have secrets
            # and we don't want to stomp on them
            body, secrets = utils.extract_sensitive_data(task.attributes)
            updated = utils.merge_dictionary(secrets or {},
                                             entity['attributes'])
            task.attributes = updated

        if 'internal_attributes' in entity:
            if not isinstance(entity['internal_attributes'], dict):
                bottle.abort(406, "'internal_attribues' must be a dict")
            task.internal_attributes = entity['internal_attributes']

        if 'state' in entity:
            if not isinstance(entity['state'], (int, long)):
                bottle.abort(406, "'state' must be an int")
            task._state = entity['state']

        # Save workflow (with secrets)
        cm_wf.update_workflow_status(wf, tenant_id=tenant_id)
        serializer = DictionarySerializer()
        body, secrets = utils.extract_sensitive_data(wf.serialize(serializer))
        body['tenantId'] = workflow.get('tenantId', tenant_id)
        body['id'] = api_id

        try:
            updated = self.manager.safe_workflow_save(api_id, body,
                                                      secrets=secrets,
                                                      tenant_id=tenant_id)
        except db.ObjectLockedError:
            bottle.abort(404, "The workflow is already locked, cannot obtain "
                              "lock.")
        # Updated does not have secrets, so we deserialize that
        serializer = DictionarySerializer()
        wf = SpiffWorkflow.deserialize(serializer, updated)
        task = wf.get_task(task_id)
        results = serializer._serialize_task(task, skip_children=True)
        results['workflow_id'] = api_id
        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def reset_workflow_task(self, api_id, task_id, tenant_id=None):
        """Reset a Celery workflow task and retry it

        Checks if task is a celery task in waiting state.
        Resets parent to READY and task to FUTURE.
        Removes existing celery task ID.

        :param api_id: checkmate workflow id
        :param task_id: checkmate workflow task id
        """
        workflow = self.manager.get_workflow(api_id, with_secrets=True)
        if not workflow:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        serializer = DictionarySerializer()
        wf = SpiffWorkflow.deserialize(serializer, workflow)

        task = wf.get_task(task_id)
        if not task:
            bottle.abort(404, 'No task with id %s' % task_id)

        if task.task_spec.__class__.__name__ != 'Celery':
            bottle.abort(406, "You can only reset Celery tasks. This is a "
                              "'%s' task" % task.task_spec.__class__.__name__)

        if task.state != Task.WAITING:
            bottle.abort(406, "You can only reset WAITING tasks. This task is"
                              " in '%s'" % task.get_state_name())

        task.task_spec._clear_celery_task_data(task)

        task._state = Task.FUTURE
        task.parent._state = Task.READY

        cm_wf.update_workflow_status(wf, tenant_id=tenant_id)
        serializer = DictionarySerializer()
        entity = wf.serialize(serializer)
        body, secrets = utils.extract_sensitive_data(entity)
        body['tenantId'] = workflow.get('tenantId', tenant_id)
        body['id'] = api_id
        try:
            self.manager.safe_workflow_save(api_id, body, secrets=secrets,
                                            tenant_id=tenant_id,)
        except db.ObjectLockedError:
            bottle.abort(404, "The workflow is already locked, cannot obtain "
                              "lock.")

        task = wf.get_task(task_id)
        if not task:
            bottle.abort(404, 'No task with id %s' % task_id)

        # Return cleaned data (no credentials)
        data = serializer._serialize_task(task, skip_children=True)
        body, secrets = utils.extract_sensitive_data(data)
        body['workflow_id'] = api_id  # so we know which workflow it came from
        return utils.write_body(body, bottle.request, bottle.response)

    @utils.with_tenant
    def reset_task_tree(self, api_id, task_id, tenant_id=None):
        '''Resets all the tasks starting from the passed in task_id and going
        up the chain till the root task is reset

        :param api_id: checkmate workflow id
        :param task_id: checkmate workflow task id
        '''
        workflow = self.manager.get_workflow(api_id, with_secrets=True)
        if not workflow:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        serializer = DictionarySerializer()
        wf = SpiffWorkflow.deserialize(serializer, workflow)

        task = wf.get_task(task_id)
        if not task:
            bottle.abort(404, 'No task with id %s' % task_id)

        if task.task_spec.__class__.__name__ != 'Celery':
            bottle.abort(406, "You can only reset Celery tasks. This is a "
                              "'%s' task" % task.task_spec.__class__.__name__)

        if task.state != Task.WAITING:
            bottle.abort(406, "You can only reset WAITING tasks. This task is"
                              " in '%s'" % task.get_state_name())

        cm_wf.reset_task_tree(task)
        cm_wf.update_workflow_status(wf, tenant_id=tenant_id)
        serializer = DictionarySerializer()
        entity = wf.serialize(serializer)
        body, secrets = utils.extract_sensitive_data(entity)
        body['tenantId'] = workflow.get('tenantId', tenant_id)
        body['id'] = api_id
        try:
            updated = self.manager.safe_workflow_save(api_id, body,
                                                      secrets=secrets,
                                                      tenant_id=tenant_id)
        except db.ObjectLockedError:
            bottle.abort(404, "The workflow is already locked, cannot obtain "
                              "lock.")

        return utils.write_body(updated, bottle.request, bottle.response)

    @utils.with_tenant
    def resubmit_workflow_task(self, api_id, task_id, tenant_id=None):
        """Reset a Celery workflow task and retry it

        Checks if task is a celery task in waiting state.
        Clears Celery info and retries the task.

        :param api_id: checkmate workflow id
        :param task_id: checkmate workflow task id
        """
        key = None
        body = None
        try:
            workflow, key = self.manager.lock_workflow(api_id,
                                                       with_secrets=True)
            if not workflow:
                bottle.abort(404, "No workflow with id '%s' found" % api_id)
            serializer = DictionarySerializer()
            wf = SpiffWorkflow.deserialize(serializer, workflow)

            task = wf.get_task(task_id)
            if not task:
                bottle.abort(404, 'No task with id %s' % task_id)

            if task.task_spec.__class__.__name__ != 'Celery':
                bottle.abort(406, "You can only reset Celery tasks. This is a"
                                  " '%s' task" %
                                  task.task_spec.__class__.__name__)

            if task.state != Task.WAITING:
                bottle.abort(406, "You can only reset WAITING tasks. This "
                                  "task is in '%s'" % task.get_state_name())

            # Refresh token if it exists in args[0]['auth_token]
            if hasattr(task.task_spec, 'args') and task.task_spec.args and \
                    len(task.task_spec.args) > 0 and \
                    isinstance(task.task_spec.args[0], dict) and \
                    task.task_spec.args[0].get('auth_token') != \
                    bottle.request.context.auth_token:
                task.task_spec.args[0]['auth_token'] = (bottle.request.context
                    .auth_token)
                LOG.debug("Updating task auth token with new caller token")
            if task.task_spec.retry_fire(task):
                LOG.debug("Progressing task '%s' (%s)", task_id,
                          task.get_state_name())
                task.task_spec._update_state(task)

            cm_wf.update_workflow_status(wf, tenant_id=tenant_id)
            serializer = DictionarySerializer()
            entity = wf.serialize(serializer)
            body, secrets = utils.extract_sensitive_data(entity)
            body['tenantId'] = workflow.get('tenantId', tenant_id)
            body['id'] = api_id
            self.manager.save_workflow(api_id, body, secrets=secrets,
                                       tenant_id=tenant_id)
            task = wf.get_task(task_id)
            if not task:
                bottle.abort(404, "No task with id '%s' found" % task_id)

            # Return cleaned data (no credentials)
            data = serializer._serialize_task(task, skip_children=True)
            body, secrets = utils.extract_sensitive_data(data)
            # so we know which workflow it came from
            body['workflow_id'] = api_id
        except db.ObjectLockedError:
            bottle.abort(406, "Cannot retry task(%s) while workflow(%s) is "
                              "executing." % (task_id, api_id))
        finally:
            if key:
                self.manager.unlock_workflow(api_id, key)
        return utils.write_body(body, bottle.request, bottle.response)

    @utils.with_tenant
    def execute_workflow_task(self, api_id, task_id, tenant_id=None):
        """Process a checkmate deployment workflow task

        :param api_id: checkmate workflow id
        :param task_id: task id
        """
        entity = self.manager.get_workflow(api_id)
        if not entity:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        serializer = DictionarySerializer()
        workflow = SpiffWorkflow.deserialize(serializer, entity)
        task = workflow.get_task(task_id)
        if not task:
            bottle.abort(404, 'No task with id %s' % task_id)

        try:
            #Synchronous call
            tasks.run_one_task(bottle.request.context, api_id, task_id,
                               timeout=10)
        except db.InvalidKeyError:
            bottle.abort(404, "Cannot execute task(%s) while workflow(%s) is "
                              "executing." % (task_id, api_id))

        entity = self.manager.get_workflow(api_id)

        workflow = SpiffWorkflow.deserialize(serializer, entity)

        task = workflow.get_task(task_id)
        data = serializer._serialize_task(task, skip_children=True)
        data['workflow_id'] = api_id  # so we know which workflow it came from
        return utils.write_body(data, bottle.request, bottle.response)
