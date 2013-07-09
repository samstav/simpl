# encoding: utf-8
'''
Rackspace Cloud Databases provider manager.
'''
import logging

from clouddb import errors as cdb_errors

from checkmate.exceptions import (
    CheckmateResumableException,
    CheckmateRetriableException,
    CheckmateDoesNotExist,
)

LOG = logging.getLogger(__name__)


class Manager(object):
    '''Contains database provider model and logic for interaction.'''

    @staticmethod
    def wait_on_build(instance_id, api, callback, simulate=False):
        '''Checks provider resource.  Returns True when built otherwise False.
        If resource goes into error state, raises exception.
        '''
        assert api, "API is required in wait_on_build_pop"
        data = {}
        try:
            if simulate:
                data['status'] = 'ACTIVE'
            else:
                data['status'] = api.get_instance(instance_id).status
        except cdb_errors.ResponseError as exc:
            raise CheckmateResumableException(str(exc), 'Error occurred in db '
                                              'provider', type(exc).__name__)
        except StandardError as exc:
            data['status'] = 'ERROR'
            data['status-message'] = 'Error waiting on resource to build'
            data['error-message'] = exc.message
            callback(data)
            raise exc

        if data['status'] == 'ERROR':
            data['status-message'] = 'Instance went into status ERROR'
            callback(data)
            raise CheckmateRetriableException(data['status-message'],
                                              'Workflow is retriable',
                                              'Provider Error', True)
        elif data['status'] in ['ACTIVE', 'DELETED']:
            data['status-message'] = ''

        return data

    @staticmethod
    def sync_resource(resource, api, simulate=False):
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
