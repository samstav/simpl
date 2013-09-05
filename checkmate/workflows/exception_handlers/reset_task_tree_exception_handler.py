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
# pylint: disable=R0903
'''Reset Task Tree Exception Handler - Used to reset task tree for failed
tasks in the workflow
'''
import logging

from celery.result import AsyncResult

from checkmate import workflow as cmwf
from checkmate.workflows.exception_handlers.exception_handler import \
    ExceptionHandler

LOG = logging.getLogger(__name__)


class ResetTaskTreeExceptionHandler(ExceptionHandler):
    """Handles a reset task tree exception"""
    MAX_RETRIES_FOR_TASK = 3

    def handle(self):
        """Handler method that does the required actions with the task
        :return:
        """
        failed_task = self.d_wf.get_task(self.task_id)
        LOG.debug("Mock failed task %s", failed_task)
        task_spec = failed_task.task_spec
        LOG.debug("Mock spec %s", task_spec)
        task_retry_count = task_spec.get_property("task_retry_count",
                                                  default=0)
        if (task_retry_count
                >= ResetTaskTreeExceptionHandler.MAX_RETRIES_FOR_TASK):
            LOG.debug("RetryTaskTreeExceptionHandler will not handle task %s"
                      " in workflow %s, as it has crossed the maximum "
                      "retries permissible %s", self.task_id,
                      self.d_wf.get_attribute('id'),
                      ResetTaskTreeExceptionHandler.MAX_RETRIES_FOR_TASK)
            return

        reset_workflow_celery_id = cmwf.get_subworkflow(self.d_wf,
                                                        self.task_id)
        if reset_workflow_celery_id and not AsyncResult(
                reset_workflow_celery_id).ready():
            LOG.debug("RetryTaskTreeExceptionHandler ignoring the handle "
                      "request for task %s in workflow %s as there is a "
                      "existing workflow in progress", self.task_id,
                      self.d_wf.get_attribute('id'))
            return

        dep_id = self.d_wf.get_attribute("deploymentId")
        LOG.debug("Dep id %s", dep_id)
        reset_wf = cmwf.create_reset_failed_task_workflow(
            self.d_wf, dep_id, self.context, failed_task, driver=self.driver)

        reset_wf_id = reset_wf.get_attribute('id')
        cmwf.add_subworkflow(self.d_wf, reset_wf_id, self.task_id)

        task_spec.set_property(task_retry_count=task_retry_count + 1)
        return reset_wf_id
