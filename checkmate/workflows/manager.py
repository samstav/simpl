import logging

from checkmate import base
from checkmate import deployment as mod_deployment

LOG = logging.getLogger(__name__)


class Manager(base.ManagerBase):

    def get_workflows(self, tenant_id=None, offset=None, limit=None,
                      with_secrets=None):
        return self.driver.get_workflows(tenant_id=tenant_id,
                                         with_secrets=with_secrets,
                                         offset=offset, limit=limit)

    def get_workflow(self, api_id, with_secrets=None):
        return self.select_driver(api_id).get_workflow(
            api_id, with_secrets=with_secrets)

    def safe_workflow_save(self, obj_id, body, secrets=None, tenant_id=None):
        """
        Locks, saves, and unlocks a workflow.
        TODO: should this be moved to the db layer?
        """
        driver = self.select_driver(obj_id)
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
        return self.select_driver(api_id).lock_workflow(
            api_id, with_secrets=with_secrets, key=key)

    def unlock_workflow(self, api_id, key):
        return self.select_driver(api_id).unlock_workflow(api_id, key)

    def save_workflow(self, obj_id, body, secrets=None, tenant_id=None):
        return self.select_driver(obj_id).save_workflow(obj_id, body,
                                                        secrets=secrets,
                                                        tenant_id=tenant_id)
