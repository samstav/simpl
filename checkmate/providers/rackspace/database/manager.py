# encoding: utf-8
'''
Rackspace Cloud Databases provider manager.
'''
import logging

from clouddb import errors as cdb_errors

from checkmate.exceptions import (
    CheckmateException,
    CheckmateResumableException,
    CheckmateDoesNotExist,
)

LOG = logging.getLogger(__name__)


class Manager(object):
    '''Contains database provider model and logic for interaction.'''

    def wait_on_build(self, instance_id, api, callback, simulate=False):
        '''Checks provider resource.  Returns True when built otherwise False.
        If resource goes into error state, raises exception.
        '''
        assert api, "API is required in wait_on_build_pop"

        try:
            if simulate:
                status = 'ACTIVE'
            else:
                status = api.get_instance(instance_id).status
        except cdb_errors.ResponseError as exc:
            raise CheckmateResumableException(exc.reason, str(exc.status),
                                              'RS_DB_ResponseError')

        callback({'status': status})

        if status == 'ERROR':
            raise CheckmateException('Resource in ERROR state')

        return status == 'ACTIVE'

    def sync_resource(self, resource, api, simulate=False):
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
