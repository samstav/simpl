import logging

from SpiffWorkflow.storage import DictionarySerializer

from checkmate import base
from checkmate import db
from checkmate import utils

LOG = logging.getLogger(__name__)


class Manager(object):

    def get_workflows(self, tenant_id=None, offset=None, limit=None,
                      with_secrets=None):
        return db.get_driver().get_workflows(tenant_id=tenant_id,
                                             with_secrets=with_secrets,
                                             offset=offset, limit=limit)

    def get_workflow(self, api_id, with_secrets=None):
        return db.get_driver(api_id=api_id).get_workflow(
            api_id, with_secrets=with_secrets)

    def safe_workflow_save(self, obj_id, body, secrets=None, tenant_id=None):
        """Locks, saves, and unlocks a workflow.
        TODO: should this be moved to the db layer?
        """
        driver = db.get_driver(api_id=obj_id)
        try:
            _, key = self.lock_workflow(obj_id)
            results = self.save_workflow(obj_id, body, secrets=secrets,
                                         tenant_id=tenant_id)
            driver.unlock_workflow(obj_id, key)
        except ValueError:
            #the object has never been saved
            results = self.save_workflow(obj_id, body, secrets=secrets,
                                         tenant_id=tenant_id)
        return results

    def lock_workflow(self, api_id, with_secrets=None, key=None):
        return db.get_driver(api_id=api_id).lock_workflow(
            api_id, with_secrets=with_secrets, key=key)

    def unlock_workflow(self, api_id, key):
        return db.get_driver(api_id=api_id).unlock_workflow(api_id, key)

    def save_spiff_workflow(self, d_wf, **kwargs):
        '''Serializes a spiff worklfow and save it. Worflow status can be
        overriden by providing a custom value for the 'status' parameter.

        :param d_wf: De-serialized workflow
        :param tenant_id: Tenant Id
        :param status: A custom value that can be passed, which would be set
            as the workflow status. If this value is not provided, the workflow
            status would be set with regard to the current statuses of the
            tasks associated with the workflow.
        :param driver: DB driver
        :return:
        '''
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

    def save_workflow(self, obj_id, body, secrets=None, tenant_id=None):
        return db.get_driver(api_id=obj_id).save_workflow(obj_id, body,
                                                        secrets=secrets,
                                                        tenant_id=tenant_id)
