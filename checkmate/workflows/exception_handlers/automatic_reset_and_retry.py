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

"""Automatic Reset and Retry Handler.

Used to reset task tree for failed
tasks in the workflow, so that they can be automatically retried in a
subsequent workflow run
"""

import logging

from celery.result import AsyncResult

from checkmate import exceptions
from checkmate import task as cmtask
from checkmate import workflow
from checkmate.workflows.exception_handlers import base

LOG = logging.getLogger(__name__)


class AutomaticResetAndRetryHandler(base.ExceptionHandlerBase):
    """Handles a reset task tree exception."""

    @staticmethod
    def _get_retry_count(failed_task):
        """Get retry count from task."""
        return failed_task.task_spec.get_property("auto_retry_count", 0)

    @staticmethod
    def can_handle(failed_task, exception):
        """Handle CheckmateExceptions that have auto_retry_counts."""
        if (isinstance(exception, exceptions.CheckmateException) and
                exception.resetable):
            if AutomaticResetAndRetryHandler._get_retry_count(failed_task):
                return True
        return False

    def friendly_message(self, exception):
        retry_count = self._get_retry_count(self.task) or "No"
        return "Retrying a failed task (%s attempts remaining)" % retry_count

    def handle(self):
        """Do the required actions with the failed task."""
        exception = cmtask.get_exception(self.task)
        auto_retry_count = self._get_retry_count(self.task) or 0
        if auto_retry_count <= 0:
            LOG.warn("AutomaticResetAndRetryHandler will not handle task %s "
                     "in workflow %s, as it has reached the maximum "
                     "retries permissible", self.task.id,
                     self.workflow.get_attribute('id'))
            max_retries_exception = exceptions.CheckmateException(
                exception.message,
                friendly_message="%s (Maximum retries reached)" %
                exception.friendly_message)
            cmtask.set_exception(max_retries_exception, self.task)
            return

        retry_exception = exceptions.CheckmateException(
            str(exception), friendly_message=self.friendly_message(exception))
        cmtask.set_exception(retry_exception, self.task)

        reset_workflow_celery_id = workflow.get_subworkflow(self.workflow,
                                                            self.task.id)
        if reset_workflow_celery_id and not AsyncResult(
                reset_workflow_celery_id).ready():
            LOG.debug("AutomaticResetAndRetryHandler ignoring the handle "
                      "request for task %s in workflow %s as there is a "
                      "existing workflow in progress", self.task.id,
                      self.workflow.get_attribute('id'))
            return

        dep_id = self.workflow.get_attribute("deploymentId")
        reset_wf = workflow.create_reset_failed_task_wf(
            self.workflow, dep_id, self.context, self.task, driver=self.driver)

        reset_wf_id = reset_wf.get_attribute('id')
        workflow.add_subworkflow(self.workflow, reset_wf_id, self.task.id)

        self.task.task_spec.set_property(auto_retry_count=auto_retry_count-1)
        return reset_wf_id
