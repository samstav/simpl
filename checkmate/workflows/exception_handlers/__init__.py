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

from checkmate.exceptions import CheckmateRetriableException
from checkmate.workflows.exception_handlers.automatic_reset_and_retry_handler \
    import AutomaticResetAndRetryHandler
from checkmate.workflows.exception_handlers.exception_handler import \
    ExceptionHandler


LOG = logging.getLogger(__name__)


def get_handlers(d_wf, failed_tasks_ids, context, driver):
    """Gets an exception handler based on the task_state exception.
    @param d_wf: Workflows
    @param failed_tasks_ids: Failed task Ids
    @param context:
    @param driver: DB driver
    @return:
    """
    handlers = []

    for failed_task_id in failed_tasks_ids:
        try:
            failed_task = d_wf.get_task(failed_task_id)
            task_state = failed_task._get_internal_attribute("task_state")
            info = task_state["info"]
            exception = eval(info)

            auto_retry_count = failed_task.task_spec.get_property(
                "auto_retry_count")
            if (isinstance(exception, CheckmateRetriableException) and
                    auto_retry_count):
                handlers.append(AutomaticResetAndRetryHandler(
                    d_wf, failed_task_id, context, driver))
        except Exception as exp:
            LOG.debug("ExceptionHandlerBase raised exception %s", str(exp))
    return handlers
