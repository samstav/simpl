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

"""Celery tasks to orchestrate a sophisticated deployment."""
import logging
import time

from celery import task as celtask

from checkmate import utils
from checkmate.workflows import tasks

LOG = logging.getLogger(__name__)


@celtask.task
def count_seconds(seconds):
    """Just for debugging and testing long-running tasks and updates."""
    utils.match_celery_logging(LOG)
    elapsed = 0
    while elapsed < seconds:
        time.sleep(1)
        elapsed += 1
        count_seconds.update_state(state="PROGRESS",
                                   meta={'complete': elapsed,
                                         'total': seconds})
    return seconds


@celtask.task(default_retry_delay=10, max_retries=300)
def run_workflow(w_id, timeout=900, wait=1, counter=1, driver=None):
    """DEPRECATED

    To be removed after the running celery tasks complete. Please
    use run_workflow in checkmate.workflows.tasks
    """
    LOG.warn('DEPRECATED method run_workflow called for workflow %s', w_id)
    tasks.run_workflow.delay(w_id, timeout=timeout, wait=wait,
                             counter=counter, driver=driver)


@celtask.task
def run_one_task(context, workflow_id, task_id, timeout=60, driver=None):
    """DEPRECATED

    To be removed after the running celery tasks complete. Please
    use run_one_task in checkmate.workflows.tasks
    """
    LOG.warn('DEPRECATED method run_one_task called for workflow %s and task '
             '%s', workflow_id, task_id)
    tasks.run_one_task.delay(context, workflow_id, task_id, timeout=timeout,
                             driver=driver)
