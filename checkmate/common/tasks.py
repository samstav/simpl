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

"""Common tasks.

Tasks here generally:
- are loaded by the engine
- have access to the backend database
- do not belong to a specific provider

Tasks are wrapped by a base task class we create that will capture exceptions
and retry the task. That allows the called function to raise exceptions without
having special logic around celery.
"""
from celery import task

from checkmate import celeryglobal as celery  # module to be renamed
from checkmate.common import statsd
from checkmate import db
from checkmate import deployment
from checkmate import operations


LOCK_DB = db.get_lock_db_driver()


@task.task(base=celery.SingleTask, default_retry_delay=2, max_retries=20,
           lock_db=LOCK_DB, lock_key="async_dep_writer:{args[0]}",
           lock_timeout=2)
@statsd.collect
def update_operation(deployment_id, workflow_id, driver=None,
                     deployment_status=None, **kwargs):
    """Expose operations.update_operation as a task.

    :param deployment_id: Deployment Id
    :param driver: DB driver
    :param deployment_status: If provided, updates the deployment status also
    :param kwargs: Additional parameters
    :return:

    Notes: has a high retry rate to make sure the status gets updated.
    Otherwise the deployment will appear to never complete.
    """
    return operations.update_operation(deployment_id, workflow_id,
                                       driver=driver,
                                       deployment_status=deployment_status,
                                       **kwargs)
