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

"""
Workflows Manager

Handles workflow logic
"""
import logging

from SpiffWorkflow.storage import DictionarySerializer

from checkmate import db
from checkmate import utils

LOG = logging.getLogger(__name__)


class Manager(object):
    """Contains Workflows Model and Logic for Accessing Workflows."""

    @staticmethod
    def get_workflows(tenant_id=None, offset=None, limit=None,
                      with_secrets=None):
        """Return all workflows associated with the given tenant ID."""
        return db.get_driver().get_workflows(tenant_id=tenant_id,
                                             with_secrets=with_secrets,
                                             offset=offset, limit=limit)

    @staticmethod
    def get_workflow(api_id, with_secrets=None):
        """Get the workflow specified by api_id."""
        return db.get_driver(api_id=api_id).get_workflow(
            api_id, with_secrets=with_secrets)

    def workflow_lock(self, workflow_id):
        """Returns a lock object for locking the workflow and unlocking it
        :param workflow_id: workflow id
        :return: a lock object for locking the workflow and unlocking it
        """
        lock_key = "async_wf_writer:%s" % workflow_id
        return db.get_lock_db_driver().lock(lock_key, 5)

    def save_spiff_workflow(self, d_wf, **kwargs):
        """Serializes a spiff worklfow and save it. Worflow status can be
        overriden by providing a custom value for the 'status' parameter.

        :param d_wf: De-serialized workflow
        :param tenant_id: Tenant Id
        :param status: A custom value that can be passed, which would be set
            as the workflow status. If this value is not provided, the workflow
            status would be set with regard to the current statuses of the
            tasks associated with the workflow.
        :param driver: DB driver
        :return:
        """
        serializer = DictionarySerializer()
        updated = d_wf.serialize(serializer)
        body, secrets = utils.extract_sensitive_data(updated)
        workflow_id = d_wf.get_attribute('id')
        tenant_id = d_wf.get_attribute('tenant_id')
        if 'celery_task_id' in kwargs:
            body['celery_task_id'] = kwargs['celery_task_id']
        body['id'] = workflow_id
        return self.save_workflow(workflow_id, body,
                                  secrets=secrets,
                                  tenant_id=tenant_id)

    @staticmethod
    def save_workflow(obj_id, body, secrets=None, tenant_id=None):
        """Store the workflow details specified in body. Store by obj_id."""
        return db.get_driver(api_id=obj_id).save_workflow(obj_id, body,
                                                          secrets=secrets,
                                                          tenant_id=tenant_id)
