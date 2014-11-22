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

"""Get Handlers for cycle_workflow. The handlers would be used to create new
 workflows that are going to be executed by cylce_workflow"""

import logging

from checkmate import task
from checkmate.workflows.exception_handlers.automatic_reset_and_retry import \
    AutomaticResetAndRetryHandler

LOG = logging.getLogger(__name__)

HANDLERS = [AutomaticResetAndRetryHandler]


def get_handlers(workflow, failed_tasks_ids, context, driver):
    """Get an exception handler based on the task_state exception.

    Also updates the friendly error message using the handler's formatter.

    :param workflow: The SpiffWorkflow
    :param failed_tasks_ids: The list of failed task ID's
    :param context:
    :param driver: DB driver
    :returns:
    """
    results = []

    for failed_task_id in failed_tasks_ids:
        try:
            failed_task = workflow.get_task(failed_task_id)
            exception = task.get_exception(failed_task)
            for handler in HANDLERS:
                if handler.can_handle(failed_task, exception):
                    instance = handler(workflow, failed_task, context, driver)
                    results.append(instance)
        except Exception as exc:  # pylint: disable=W0703
            LOG.warn("Exception finding handler: %s", exc)
    return results
