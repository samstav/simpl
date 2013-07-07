# encoding: utf-8
import logging

from clouddb import errors as cdb_errors

from checkmate.exceptions import (
    CheckmateException,
    CheckmateResumableException,
    CheckmateDoesNotExist,
)

LOG = logging.getLogger(__name__)

'''
Rackspace Cloud Databases provider manager.
'''


class Manager(object):
    '''Contains database provider model and logic for interaction.'''

    def wait_on_build_pop(self, instance_id, api, callback, simulate=False):
        '''Checks provider resource.  Returns True when built otherwise False.
        If resource goes into error state, raises exception.
        '''
        assert api, "API is required in wait_on_build_pop"

        try:
            if simulate:
                instance = type("myobj", (object,), dict(status='ACTIVE'))
            else:
                instance = api.get_instance(instance_id)
        except cdb_errors.ResponseError as exc:
            raise CheckmateResumableException(exc.reason, str(exc.status),
                                              'RS_DB_ResponseError')

        callback({'status': instance.status})

        if instance.status == 'ERROR':
            raise CheckmateException('Resource in ERROR state')

        return instance.status == 'ACTIVE'

    def sync_resource_pop(self, resource, resource_key, api, callback,
                          simulate=False):
        '''Syncronizes provider status with checkmate resource status.'''
        if simulate:
            results = {'status': 'ACTIVE'}
        else:
            instance = resource.get("instance") or {}
            instance_id = instance.get("id")
            try:
                if not instance_id:
                    raise CheckmateDoesNotExist("Instance is blank or has no "
                                                "ID.")
                database = api.get_instance(instance_id)
                LOG.info("Marking database instance %s as %s", instance_id,
                         database.status)
                results = {'status': database.status}
            except (cdb_errors.ResponseError, CheckmateDoesNotExist):
                LOG.info("Marking database instance %s as DELETED",
                         instance_id)
                results = {'status': 'DELETED'}
        return results
