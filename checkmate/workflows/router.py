# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Workflows Router."""

# pylint: disable=W0110,W0141,W0212,W0613,R0914
import logging
import uuid

import bottle

import SpiffWorkflow as spiff
from SpiffWorkflow.storage import DictionarySerializer
from SpiffWorkflow import Task

from checkmate.common import tasks as common_tasks
from checkmate import db
from checkmate import deployment as cmdep
from checkmate import operations
from checkmate import utils
from checkmate import workflow as cm_wf
from checkmate.workflows.tasks import cycle_workflow
from checkmate.workflows.tasks import pause_workflow
from checkmate.workflows.tasks import run_one_task

LOG = logging.getLogger(__name__)


class Router(object):

    """Route /deployments/ calls."""

    def __init__(self, app, manager, deployment_manager):
        """Take a bottle app and routes traffic for it."""
        self.app = app
        self.manager = manager
        self.deployment_manager = deployment_manager

        # Workflow
        app.route('/workflows', 'GET', self.get_workflows)
        app.route('/workflows', 'POST', self.add_workflow)
        app.route('/workflows/<api_id>', ['PUT', 'POST'], self.save_workflow)
        app.route('/workflows/<api_id>', 'GET', self.get_workflow)
        app.route('/workflows/<api_id>/status', 'GET',
                  self.get_workflow_status)
        app.route('/workflows/<workflow_id>/specs/<spec_id>', 'POST',
                  self.post_workflow_spec)

        # Actions
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

        # Tasks
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
        """Get all the workflows for a tenant.

        :param tenant_id: tenant id
        :param offset: start record index
        :param limit: Max number of records to return
        :return: Workflows for the tenant
        """
        limit = utils.cap_limit(limit, tenant_id)  # Avoid DoS from huge limit
        if 'with_secrets' in bottle.request.query:
            if bottle.request.environ['context'].is_admin is True:
                LOG.info("Administrator accessing workflows with secrets: %s",
                         bottle.request.environ['context'].username)
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
        """Add a new workflow.

        :param tenant_id: tenant id
        :return: workflow document
        """
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
        """Save a workflow.

        :param api_id: id of the workflow
        :param tenant_id: tenant id
        :return: workflow document
        """
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
            with self.manager.workflow_lock(api_id):
                results = self.manager.save_workflow(str(api_id), body,
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
        """Get a workflow.

        :param api_id: Workflow id
        :param tenant_id: tenant id
        :return: workflow document
        """
        if 'with_secrets' in bottle.request.query:
            LOG.info("Administrator accessing workflow %s with secrets: %s",
                     api_id, bottle.request.environ['context'].username)
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
                        bottle.request.environ['context'].username)
            bottle.abort(404)
        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def get_workflow_status(self, api_id, tenant_id=None):
        """Get the status of a workflow.

        :param api_id: workflow id
        :param tenant_id: tenant id
        :return: workflow status
        """
        entity = self.manager.get_workflow(api_id)
        if not entity:
            bottle.abort(404, 'No workflow with id %s' % api_id)
        serializer = DictionarySerializer()
        wflow = spiff.Workflow.deserialize(serializer, entity)
        return utils.write_body(cm_wf.get_spiff_workflow_status(wflow),
                                bottle.request, bottle.response)

    @utils.with_tenant
    def execute_workflow(self, api_id, tenant_id=None):
        """Process a checkmate deployment workflow.

        Executes and moves the workflow forward.
        Retrieves results (final or intermediate) and updates them into
        deployment.

        :param api_id: checkmate workflow id
        """
        workflow = self.manager.get_workflow(api_id)
        if not workflow:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        context = bottle.request.environ['context']
        celery_task_id = workflow.get('celery_task_id')

        if celery_task_id:
            async_result = cycle_workflow.AsyncResult(celery_task_id)
            if not async_result.ready():
                bottle.abort(406, 'Workflow %s is already in progress with '
                                  'state %s' % (api_id, async_result.state))
        cycle_workflow.delay(api_id, context.get_queued_task_dict())
        LOG.debug("Executed a task to run workflow '%s'", api_id)
        workflow = self.manager.get_workflow(api_id)
        return utils.write_body(workflow, bottle.request, bottle.response)

    @utils.with_tenant
    def pause_workflow(self, api_id, tenant_id=None):
        """Pause the workflow.

        Updates the operation status to pauses when done

        :param api_id: checkmate workflow id
        """
        workflow = self.manager.get_workflow(api_id)
        if not workflow:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        workflow = self.manager.get_workflow(api_id)
        dep_id = workflow["attributes"].get("deploymentId") or api_id
        deployment = self.deployment_manager.get_deployment(
            dep_id, tenant_id=tenant_id)
        deployment = cmdep.Deployment(deployment)
        operation = deployment.get("operation")

        if (operation and operation.get('action') != 'PAUSE' and
                operation['status'] not in ('PAUSED', 'COMPLETE')):
            common_tasks.update_operation.delay(
                dep_id, operations.current_workflow_id(deployment),
                action='PAUSE')
            pause_workflow.delay(api_id)
        return utils.write_body(workflow, bottle.request, bottle.response)

    @utils.with_tenant
    def resume_workflow(self, api_id, tenant_id=None):
        """Process a checkmate deployment workflow.

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
            context = bottle.request.environ['context']
            async_call = cycle_workflow.delay(api_id,
                                              context.get_queued_task_dict())
            LOG.debug("Executed a task to run workflow '%s'", async_call)
            workflow = self.manager.get_workflow(api_id)
        return utils.write_body(workflow, bottle.request, bottle.response)

    @utils.with_tenant
    def retry_all_failed_tasks(self, api_id, tenant_id=None):
        """Reset all the failed tasks in a workflow.

        :param api_id: workflow id
        :param tenant_id: tenant id
        :return: workflow document
        """
        try:
            with self.manager.workflow_lock(api_id):
                workflow = self.manager.get_workflow(api_id)
                if not workflow:
                    bottle.abort(404, 'No workflow with id %s' % api_id)

                serializer = DictionarySerializer()
                wflow = spiff.Workflow.deserialize(serializer, workflow)

                dep_id = workflow["attributes"]["deploymentId"] or api_id
                deployment = self.deployment_manager.get_deployment(
                    dep_id, tenant_id=tenant_id)
                operation = deployment.get("operation")

                if operation.get("errors"):
                    retriable_errors = filter(lambda x: x.get("retriable",
                                                              False),
                                              operation.get("errors"))
                    for error in retriable_errors:
                        task_id = error["task-id"]
                        task = wflow.get_task(task_id)
                        LOG.debug("Resetting task %s for workflow %s",
                                  task_id, id)
                        cm_wf.reset_task_tree(task)

                    cm_wf.update_workflow_status(wflow)
                    workflow = self.manager.save_spiff_workflow(wflow)
        except db.ObjectLockedError:
            bottle.abort(404, "The workflow is already locked, cannot obtain"
                              " lock.")
        return utils.write_body(workflow, bottle.request, bottle.response)

    @utils.with_tenant
    def resume_all_failed_tasks(self, api_id, tenant_id=None):
        """Resume all the failed tasks in a workflow.

        :param api_id: workflow id
        :param tenant_id: tenant id
        :return: workflow document
        """
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
                run_one_task.delay(bottle.request.environ['context'], api_id,
                                   task_id, timeout=10)

            workflow = self.manager.get_workflow(id)

        return utils.write_body(workflow, bottle.request, bottle.response)

    @utils.with_tenant
    def post_workflow_spec(self, workflow_id, spec_id, tenant_id=None):
        """Update a workflow spec.

        :param workflow_id: checkmate workflow id
        :param spec_id: checkmate workflow spec id (a string)
        """
        entity = utils.read_body(bottle.request)

        # Extracting with secrets
        try:
            with self.manager.workflow_lock(workflow_id):
                workflow = self.manager.get_workflow(workflow_id,
                                                     with_secrets=True)
                if not workflow:
                    bottle.abort(404, 'No workflow with id %s' % workflow_id)

                spec = workflow['wf_spec']['task_specs'].get(spec_id)
                if not spec:
                    bottle.abort(404, 'No spec with id %s' % spec_id)

                LOG.debug("Updating spec '%s' in workflow '%s'", spec_id,
                          workflow_id,
                          extra=dict(data=dict(old=spec, new=entity)))
                workflow['wf_spec']['task_specs'][spec_id] = entity

                # Save workflow (with secrets)
                body, secrets = utils.extract_sensitive_data(workflow)
                body['tenantId'] = workflow.get('tenantId', tenant_id)
                body['id'] = workflow_id
                result = self.manager.save_workflow(workflow_id, body,
                                                    secrets=secrets,
                                                    tenant_id=tenant_id)
        except db.ObjectLockedError:
            bottle.abort(404, "The workflow is already locked, cannot obtain "
                              "lock.")

        return utils.write_body(result, bottle.request, bottle.response)

    @utils.with_tenant
    def get_workflow_task(self, api_id, task_id, tenant_id=None):
        """Get a workflow task.

        :param api_id: checkmate workflow id
        :param task_id: checkmate workflow task id
        """
        # TODO(zns): verify admin-ness
        if 'with_secrets' in bottle.request.query:
            entity = self.manager.get_workflow(api_id, with_secrets=True)
        else:
            entity = self.manager.get_workflow(api_id)
        if not entity:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        serializer = DictionarySerializer()
        wflow = spiff.Workflow.deserialize(serializer, entity)

        task = wflow.get_task(task_id)
        if not task:
            bottle.abort(404, 'No task with id %s' % task_id)
        data = serializer._serialize_task(task, skip_children=True)
        data['workflow_id'] = api_id  # so we know which workflow it came from
        spec = task.task_spec.serialize(serializer)
        data['spec'] = spec  # include a copy of the spec
        return utils.write_body(data, bottle.request, bottle.response)

    @utils.with_tenant
    def post_workflow_task(self, api_id, task_id, tenant_id=None):
        """Update a workflow task.

        Attributes that can be updated are:
        - attributes
        - state
        - internal_attributes

        :param api_id: checkmate workflow id
        :param task_id: checkmate workflow task id
        """
        entity = utils.read_body(bottle.request)

        # Extracting with secrets
        try:
            with(self.manager.workflow_lock(api_id)):
                workflow = self.manager.get_workflow(api_id, with_secrets=True)
                if not workflow:
                    bottle.abort(404, 'No workflow with id %s' % api_id)

                serializer = DictionarySerializer()
                d_wf = spiff.Workflow.deserialize(serializer, workflow)

                task = d_wf.get_task(task_id)
                if not task:
                    bottle.abort(404, 'No task with id %s' % task_id)

                if 'attributes' in entity:
                    if not isinstance(entity['attributes'], dict):
                        bottle.abort(406, "'attribues' must be a dict")
                    # Don't do a simple overwrite since incoming may not have
                    # secrets and we don't want to stomp on them
                    _, secrets = utils.extract_sensitive_data(
                        task.attributes)
                    updated = utils.merge_dictionary(secrets or {},
                                                     entity['attributes'])
                    task.attributes = updated

                if 'internal_attributes' in entity:
                    if not isinstance(entity['internal_attributes'], dict):
                        bottle.abort(406, "'internal_attribues' must be a "
                                          "dict")
                    task.internal_attributes = entity['internal_attributes']

                if 'state' in entity:
                    if not isinstance(entity['state'], (int, long)):
                        bottle.abort(406, "'state' must be an int")
                    task._state = entity['state']

                # Save workflow (with secrets)
                cm_wf.update_workflow_status(d_wf)
                updated = self.manager.save_spiff_workflow(d_wf)
        except db.ObjectLockedError:
            bottle.abort(404, "The workflow is already locked, cannot obtain "
                              "lock.")

        # Updated does not have secrets, so we deserialize that
        serializer = DictionarySerializer()
        wflow = spiff.Workflow.deserialize(serializer, updated)
        task = wflow.get_task(task_id)
        results = serializer._serialize_task(task, skip_children=True)
        results['workflow_id'] = api_id
        return utils.write_body(results, bottle.request, bottle.response)

    @utils.with_tenant
    def reset_workflow_task(self, api_id, task_id, tenant_id=None):
        """Reset a Celery workflow task and retry it.

        Checks if task is a celery task in waiting state.
        Resets parent to READY and task to FUTURE.
        Removes existing celery task ID.

        :param api_id: checkmate workflow id
        :param task_id: checkmate workflow task id
        """
        try:
            with self.manager.workflow_lock(api_id):
                workflow = self.manager.get_workflow(api_id, with_secrets=True)
                if not workflow:
                    bottle.abort(404, 'No workflow with id %s' % api_id)

                serializer = DictionarySerializer()
                wflow = spiff.Workflow.deserialize(serializer, workflow)

                task = wflow.get_task(task_id)
                if not task:
                    bottle.abort(404, 'No task with id %s' % task_id)

                if task.task_spec.__class__.__name__ != 'Celery':
                    bottle.abort(406, "You can only reset Celery tasks. This "
                                      "is a '%s' task" %
                                      task.task_spec.__class__.__name__)

                if task.state != Task.WAITING:
                    bottle.abort(406, "You can only reset WAITING tasks. This "
                                      "task is in '%s'" %
                                      task.get_state_name())

                task.task_spec._clear_celery_task_data(task)

                task._state = Task.FUTURE
                task.parent._state = Task.READY

                cm_wf.update_workflow_status(wflow)
                self.manager.save_spiff_workflow(wflow)
        except db.ObjectLockedError:
            bottle.abort(404, "The workflow is already locked, cannot obtain "
                              "lock.")

        task = wflow.get_task(task_id)
        if not task:
            bottle.abort(404, 'No task with id %s' % task_id)

        # Return cleaned data (no credentials)
        data = serializer._serialize_task(task, skip_children=True)
        body, _ = utils.extract_sensitive_data(data)
        body['workflow_id'] = api_id  # so we know which workflow it came from
        return utils.write_body(body, bottle.request, bottle.response)

    @utils.with_tenant
    def reset_task_tree(self, api_id, task_id, tenant_id=None):
        """Reset task_id and all parent tasks until root task is reset.

        :param api_id: checkmate workflow id
        :param task_id: checkmate workflow task id
        """
        context = bottle.request.environ['context']
        if utils.is_simulation(api_id):
            context.simulation = True
        if utils.is_simulation(api_id):
            bottle.request.environ['context'].simulation = True
        try:
            with(self.manager.workflow_lock(api_id)):
                workflow = self.manager.get_workflow(api_id, with_secrets=True)
                if not workflow:
                    bottle.abort(404, 'No workflow with id %s' % api_id)
                serializer = DictionarySerializer()
                wflow = spiff.Workflow.deserialize(serializer, workflow)

                task = wflow.get_task(task_id)
                if not task:
                    bottle.abort(404, 'No task with id %s' % task_id)

                if task.task_spec.__class__.__name__ != 'Celery':
                    bottle.abort(406, "You can only reset Celery tasks. This "
                                      "is a '%s' task" %
                                      task.task_spec.__class__.__name__)

                if task.state != Task.WAITING:
                    bottle.abort(406, "You can only reset WAITING tasks. This "
                                      "task is in '%s'" %
                                      task.get_state_name())

                driver = db.get_driver(api_id=api_id)
                reset_tree_wf = cm_wf.create_reset_failed_task_wf(
                    wflow, api_id, context, task, driver=driver)
                w_id = reset_tree_wf.get_attribute("id")
                cm_wf.add_subworkflow(wflow, w_id, task_id)
                cycle_workflow.apply_async(args=[w_id, context],
                                           kwargs={'apply_callbacks': False},
                                           task_id=w_id)

                serializer = DictionarySerializer()
                entity = wflow.serialize(serializer)
                body, _ = utils.extract_sensitive_data(entity)
                body['tenantId'] = workflow.get('tenantId', tenant_id)
                body['id'] = api_id

                updated = self.manager.save_spiff_workflow(wflow)
        except db.ObjectLockedError:
            bottle.abort(404, "The workflow is already locked, cannot obtain "
                              "lock.")

        return utils.write_body(updated, bottle.request, bottle.response)

    @utils.with_tenant
    def resubmit_workflow_task(self, api_id, task_id, tenant_id=None):
        """Reset a Celery workflow task and retry it.

        Checks if task is a celery task in waiting state.
        Clears Celery info and retries the task.

        :param api_id: checkmate workflow id
        :param task_id: checkmate workflow task id
        """
        body = None
        try:
            with(self.manager.workflow_lock(api_id)):
                workflow = self.manager.get_workflow(api_id, with_secrets=True)
                if not workflow:
                    bottle.abort(404, "No workflow with id '%s' found" %
                                      api_id)
                serializer = DictionarySerializer()
                wflow = spiff.Workflow.deserialize(serializer, workflow)

                task = wflow.get_task(task_id)
                if not task:
                    bottle.abort(404, 'No task with id %s' % task_id)

                if task.task_spec.__class__.__name__ != 'Celery':
                    bottle.abort(406, "You can only reset Celery tasks. This "
                                      "is a '%s' task" %
                                      task.task_spec.__class__.__name__)

                if task.state != Task.WAITING:
                    bottle.abort(406, "You can only reset WAITING tasks. This "
                                      "task is in '%s'" %
                                      task.get_state_name())

                # Refresh token if it exists in args[0]['auth_token]
                if (hasattr(task.task_spec, 'args') and task.task_spec.args
                    and len(task.task_spec.args) > 0 and
                        isinstance(task.task_spec.args[0], dict) and
                        task.task_spec.args[0].get('auth_token') !=
                        bottle.request.environ['context'].auth_token):
                    task.task_spec.args[0]['auth_token'] = (
                        bottle.request.environ['context'].auth_token)
                    LOG.debug("Updating task auth token with new caller token")
                if task.task_spec.retry_fire(task):
                    LOG.debug("Progressing task '%s' (%s)", task_id,
                              task.get_state_name())
                    task.task_spec._update_state(task)

                cm_wf.update_workflow_status(wflow)
                self.manager.save_spiff_workflow(wflow)
                task = wflow.get_task(task_id)
                if not task:
                    bottle.abort(404, "No task with id '%s' found" % task_id)

                # Return cleaned data (no credentials)
                data = serializer._serialize_task(task, skip_children=True)
                body, _ = utils.extract_sensitive_data(data)
                # so we know which workflow it came from
                body['workflow_id'] = api_id
        except db.ObjectLockedError:
            bottle.abort(406, "Cannot retry task(%s) while workflow(%s) is "
                              "executing." % (task_id, api_id))
        return utils.write_body(body, bottle.request, bottle.response)

    @utils.with_tenant
    def execute_workflow_task(self, api_id, task_id, tenant_id=None):
        """Process a checkmate deployment workflow task.

        :param api_id: checkmate workflow id
        :param task_id: task id
        """
        entity = self.manager.get_workflow(api_id)
        if not entity:
            bottle.abort(404, 'No workflow with id %s' % api_id)

        serializer = DictionarySerializer()
        workflow = spiff.Workflow.deserialize(serializer, entity)
        task = workflow.get_task(task_id)
        if not task:
            bottle.abort(404, 'No task with id %s' % task_id)

        try:
            # Synchronous call
            run_one_task(bottle.request.environ['context'], api_id, task_id,
                         timeout=10)
        except db.ObjectLockedError:
            bottle.abort(404, "Cannot execute task(%s) while workflow(%s) is "
                              "executing." % (task_id, api_id))

        entity = self.manager.get_workflow(api_id)

        workflow = spiff.Workflow.deserialize(serializer, entity)

        task = workflow.get_task(task_id)
        data = serializer._serialize_task(task, skip_children=True)
        data['workflow_id'] = api_id  # so we know which workflow it came from
        return utils.write_body(data, bottle.request, bottle.response)
