import pymongo
import logging
import os
import time
import json

from checkmate.classes import ExtensibleDict
from checkmate.db.common import DbBase, DEFAULT_RETRIES, DEFAULT_TIMEOUT, \
    DatabaseTimeoutException
from checkmate.exceptions import CheckmateDatabaseConnectionError
from checkmate.utils import merge_dictionary
from SpiffWorkflow.util import merge_dictionary as collate


LOG = logging.getLogger(__name__)


class Driver(DbBase):
    """MongoDB Database Driver"""
    _connection = None
    _client = None

    def __init__(self, *args, **kwargs):
        """Initializes globals for this driver"""
        DbBase.__init__(self, *args, **kwargs)
        self.connection_string = os.environ.get('CHECKMATE_CONNECTION_STRING',
                                                'mongodb://localhost')
        self.db_name = pymongo.uri_parser.parse_uri(self.connection_string
                                                    ).get('database',
                                                          'checkmate')
        self._database = None

    def database(self):
        """ Connects to and returns mongodb database object """
        if self._database is None:
            if self._client is None:
                try:
                    self._client = (pymongo.MongoClient(
                                    self.connection_string))
                except pymongo.errors.AutoReconnect as exc:
                    raise CheckmateDatabaseConnectionError(exc.__str__())
            client = self._client
            db_name = self.db_name
            self._database = client.db_name
            LOG.info("Connected to mongodb on %s (database=%s)" %
                     (self.connection_string, self.db_name))
        return self._database

    def dump(self):
        response = {}
        response['environments'] = self.get_environments()
        response['deployments'] = self.get_deployments()
        response['blueprints'] = self.get_blueprints()
        response['workflows'] = self.get_workflows()
        response['components'] = self.get_components()
        return response

    # ENVIRONMENTS
    def get_environment(self, id, with_secrets=None):
        return self.get_object('environments', id, with_secrets)

    def get_environments(self, tenant_id=None, with_secrets=None):
        return self.get_objects('environments', tenant_id, with_secrets)

    def save_environment(self, id, body, secrets=None, tenant_id=None):
        return self.save_object('environments', id, body, secrets, tenant_id)

    # DEPLOYMENTS
    def get_deployment(self, id, with_secrets=None):
        return self.get_object('deployments', id, with_secrets)

    def get_deployments(self, tenant_id=None, with_secrets=None,
                        limit=None, offset=None):
        return self.get_objects('deployments', tenant_id, with_secrets, 
                                offset=offset, limit=limit)

    def save_deployment(self, id, body, secrets=None, tenant_id=None):
        return self.save_object('deployments', id, body, secrets, tenant_id)

    #BLUEPRINTS
    def get_blueprint(self, id, with_secrets=None):
        return self.get_object('blueprints', id, with_secrets)

    def get_blueprints(self, tenant_id=None, with_secrets=None):
        return self.get_objects('blueprints', tenant_id, with_secrets)

    def save_blueprint(self, id, body, secrets=None, tenant_id=None):
        return self.save_object('blueprints', id, body, secrets, tenant_id)

    # COMPONENTS
    def get_component(self, id, with_secrets=None):
        return self.get_object('components', id, with_secrets)

    def get_components(self, tenant_id=None, with_secrets=None):
        return self.get_objects('components', tenant_id, with_secrets)

    def save_component(self, id, body, secrets=None, tenant_id=None):
        return self.save_object('components', id, body, secrets, tenant_id)

    # WORKFLOWS
    def get_workflow(self, id, with_secrets=None):
        return self.get_object('workflows', id, with_secrets)

    def get_workflows(self, tenant_id=None, with_secrets=None,
                      limit=None, offset=None):
        return self.get_objects('workflows', tenant_id, with_secrets,
                                offset=offset, limit=limit)

    def save_workflow(self, id, body, secrets=None, tenant_id=None):
        return self.save_object('workflows', id, body, secrets, tenant_id)

    # GENERIC
    def retry_for_lock(self, id, query):
        '''
        Retries the specified query, just incase a lock is blocking reads.
        :param id : used for displaying an error
        :param query: the db query to run 
        '''
        tries = 0
        results = {}
        while tries < DEFAULT_RETRIES:
            in_request = self.in_request()
            if not in_request:
                with self.start_request():
                    results = query()
                    break
            else:
                if tries == (DEFAULT_RETRIES - 1):
                    self.in_request() # Just in case
                    raise DatabaseTimeoutException("%s not found" % id)
            tries += 1
            time.sleep(DEFAULT_TIMEOUT)
        self.in_request() # Automatically releases any current requests
        if results:
            return results
            
    def get_object(self, klass, id, with_secrets=None):
        '''
        Get an object by klass and id. We are filtering out the 
        _id field with a projection on all db queries.

        :param klass: The collection to query from
        :param id: The collection item to get
        :param with_secrets: Merge secrets with the results
        '''
        request = self.start_request()
        try:
            results = self.database().klass.find_one({'_id': id}, {'_id': 0})
        
            if results:
                if '_locked' in results:
                    del results['_locked']
  
                if with_secrets is True:
                    secrets = (self.database().('%s_secrets' % klass).find_one(
                               {'_id': id}, {'_id': 0}))
                if secrets:
                    merge_dictionary(results, secrets)
        finally:
            request.end_request()
            if results:
                return results
            else:
                return {}

    def get_objects(self, klass, tenant_id=None, with_secrets=None,
                    offset=None, limit=None):
        request = self.start_request()
        try:                       
            if tenant_id:
                if limit:
                    if offset is None:
                        offset = 0
                    results = (self.database().klass.find({'tenantId': tenant_id},
                               {'_id': 0}).skip(offset).limit(limit))
                elif offset and (limit is None):
                    results = (self.database().klass.find({'tenantId': tenant_id},
                               {'_id': 0}).skip(offset))
                else:
                    results = (self.database().klass.find({'tenantId': tenant_id},
                               {'_id': 0}))
            else:
                if limit:
                    if offset is None:
                        offset = 0
                    results = (self.database().klass.find(None,
                               {'_id': 0}).skip(offset).limit(limit))
                elif offset and (limit is None):
                    results = (self.database().klass.find(None,
                               {'_id': 0}).skip(offset))
                else:
                    results = self.database()[klass].find(None, {'_id': 0})
            if results:
                response = {}
                if with_secrets is True:
                    for entry in results:
                        secrets = (self.database().('%s_secrets' % klass).find_one(
                                   {'_id': entry['id']}, {'_id': 0}))
                        if secrets:
                            response[entry['id']] = merge_dictionary(entry,
                                                                     secrets)
                        else:
                            response[entry['id']] = entry
                else:
                    for entry in results:
                        if '_locked' in entry:
                            del entry['_locked']
                        response[entry['id']] = entry
        finally:
            request.end_request()
            if results:
                if response:
                    return response
            else:
                return {}

    def save_object(self, klass, obj_id, body, secrets=None, tenant_id=None):
        """Clients that wish to save the body but do/did not have access to
        secrets will by default send in None for secrets. We must not have that
        overwrite the secrets. To clear the secrets for an object, a non-None
        dict needs to be passed in: ex. {}. This method can only save objects
        that do not have a lock in the database. It will attempt to obtain the 
        lock for (DEFAULT_RETRIES * DEFAULT_TIMEOUT) seconds, before raising 
        an exception.
        """
        if isinstance(body, ExtensibleDict):
            body = body.__dict__()
        assert isinstance(body, dict), "dict required by backend"
        assert 'id' in body, "id required to be in body by backend"

        request = self.start_request()
        try:
            if secrets is not None:
                if not secrets:
                    LOG.warning("Clearing secrets for %s:%s" % (klass, obj_id))
                    # TODO: to catch bugs. We can remove when we're comfortable
                    assert False, "CLEARING CREDS! Is that intended?!!!!"
                else:
                    cur_secrets = (self.database().('%s_secrets' % klass).find_one(
                                   {'_id': obj_id}, {'_id': 0}))
                    if cur_secrets:
                        collate(cur_secrets, secrets, extend_lists=False)
                        secrets = cur_secrets
            if tenant_id:
                body['tenantId'] = tenant_id
            assert tenant_id or 'tenantId' in body, "tenantId must be specified"
            body['_id'] = obj_id
            body['_locked'] = 0
            self.database().klass.update({'_id': obj_id}, body, True, False)
            if secrets:
                secrets['_id'] = obj_id
                self.database().('%s_secrets' % klass).update({'_id': obj_id},
                                                             secrets, True, False)
            del body['_id']
            del body['_locked']
        finally:
            request.end_request()
            return body

    def delete_object(self, klass, id, body):
        result = self.database().klass.remove(body)
