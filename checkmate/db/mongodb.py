import pymongo
import logging
import os
import time
import uuid

from checkmate.classes import ExtensibleDict
from checkmate.db.common import DbBase, ObjectLockedError, InvalidKeyError
from checkmate.exceptions import CheckmateDatabaseConnectionError
from checkmate.utils import merge_dictionary
from SpiffWorkflow.util import merge_dictionary as collate


LOG = logging.getLogger(__name__)

class Driver(DbBase):
    """MongoDB Database Driver"""
    _connection = None
    _client = None
    #db fields we do not want returned to the client
    _object_projection = {'_lock':0, '_lock_timestamp': 0, '_id': 0}

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
            self._database = self._client[self.db_name]
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
        '''
        Pull current deployment in DB incase another task has modified its' 
        contents
        '''

        return self.save_object('deployments', id, body, secrets, tenant_id,
                                merge_existing=True)

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

    def lock_workflow(self, obj_id, with_secrets=None, key=None):
        """ 
        :param obj_id: the object's _id.
        :param with_secrets: true if secrets should be merged into the results.
        :param key: if the object has already been locked, the key used must be
            passed in
        :returns (locked_object, key): a tuple of the locked_object and the
            key that should be used to unlock it.
        """
        return self.lock_object('workflows', obj_id, with_secrets=with_secrets, 
                                key=key)

    def unlock_workflow(self, obj_id, key):
        """
        :param obj_id: the object's _id.
        :param key: the key used to lock the object (see lock_object()).
        """
        return self.unlock_object('workflows', obj_id, key=key)

    def lock_object(self, klass, obj_id, with_secrets=None, key=None):
        """
        :param klass: the class of the object to unlock.
        :param obj_id: the object's _id.
        :param with_secrets: true if secrets should be merged into the results.
        :param key: if the object has already been locked, the key used must be
            passed in
        :returns (locked_object, key): a tuple of the locked_object and the
            key that should be used to unlock it.
        """
        if with_secrets:
            locked_object, key = self._lock_find_object(klass, obj_id, key=key)
            return (self.merge_secrets(klass, obj_id, locked_object), key)
        return self._lock_find_object(klass, obj_id, key=key)


    def unlock_object(self, klass, obj_id, key):
        """
        Unlocks a locked object if the key is correct.

        :param klass: the class of the object to unlock.
        :param obj_id: the object's _id.
        :param key: the key used to lock the object (see lock_object()).
        :raises ValueError: If the unlocked object does not exist or the lock
            was incorrect.
        """

        unlocked_object = self.database()[klass].find_and_modify(
                                        query={
                                            '_id': obj_id, 
                                            '_lock': key
                                        }, 
                                        update={'_lock': 0},
                                        fields=self._object_projection
                                    )
        #remove state added to passed in dict
        if unlocked_object:
            return unlocked_object
        else:
            raise InvalidKeyError("The lock was invalid or the object %s "
                                    "does not exist." % (obj_id))


    def _lock_find_object(self, klass, obj_id, key=None):
        """
        Finds, attempts to lock, and returns an object by id.

        :param klass: the class of the object unlock.
        :param obj_id: the object's _id.
        :param key: if the object has already been locked, the key used must be
            passed in
        :raises ValueError: if the obj_id is of a non-existent object
        :returns (locked_object, key): a tuple of the locked_object and the
            key that should be used to unlock it.
        """
        assert klass, "klass must not be None."
        assert obj_id, "obj_id must not be None"

        lock_timestamp = time.time()
        if key:
            # The object has already been locked
            # TODO: see if we can merge the existing key logic into below
            locked_object = self.database()[klass].find_and_modify(
                                            query={
                                                '_id': obj_id, 
                                                '_lock': key
                                            },
                                            update={
                                                '$set': {
                                                    '_lock_timestamp': 
                                                        lock_timestamp
                                                }
                                            },
                                            fields=self._object_projection,
                                            new=True
                                        )
            if locked_object:
                # The passed in key matched
                return (locked_object, key) 
            else:
                raise InvalidKeyError("The key:%s could not unlock: %s(%s)" % (
                                    key, klass, obj_id))

        # A key was not passed in
        key = str(uuid.uuid4())
        lock_update = {
                        '$set' : {
                            '_lock': key,
                            '_lock_timestamp': lock_timestamp
                        }
                    }

        locked_object = self.database()[klass].find_and_modify(
                                            query={'_id': obj_id, '_lock': 0}, 
                                            update=lock_update,
                                            fields=self._object_projection
                                        )
        if(locked_object):
            # We were able to lock the object
            return (locked_object, key)

        else:
            # Could not get the lock
            object_exists = self.database()[klass].find_one({'_id': obj_id})
            if(object_exists):
                # Object exists but we were not able to get the lock
                if '_lock' in object_exists:
                    lock_time_delta = (lock_timestamp - 
                            object_exists['_lock_timestamp']) 
                    
                    # The lock is stale if it is greater than two hours old
                    if lock_time_delta >= 30:
                        # Key is stale, force the lock
                        LOG.warning("%s(%s) had a stale lock of %s seconds!" %(
                                    klass, obj_id, lock_time_delta))
                        locked_object = self.database()[klass].find_and_modify(
                                                query={'_id': obj_id}, 
                                                update=lock_update,
                                                fields=self._object_projection
                                            )
                        return (locked_object, key)
                    else:
                        # Lock is not stale
                        raise ObjectLockedError("%s(%s) was already locked!" %(
                                                klass, obj_id)) 

                else:
                    # Object has no _lock field
                    locked_object = self.database()[klass].find_and_modify(
                                                query={'_id': obj_id}, 
                                                update=lock_update,
                                                fields=self._object_projection,
                                                new=True
                                            ) 
                    # Delete instead of projection so that we can 
                    # use existing save_object
                    return (locked_object, key)

            else:
                # New object
                raise ValueError("Cannot get the object:%s that has"
                                " never been saved" % obj_id)


    def get_object(self, klass, id, with_secrets=None):
        '''
        Get an object by klass and id. We are filtering out the 
        _id field with a projection on all db queries.

        :param klass: The collection to query from
        :param id: The collection item to get
        :param with_secrets: Merge secrets with the results
        '''

        if not self._client:
            self.database()
        client = self._client
        with client.start_request():
            results = self.database()[klass].find_one({'_id': id}, 
                                                    self._object_projection)

            if results:
                if with_secrets is True:
                    self.merge_secrets(klass, id, results)

        if results:
            return results
        else:
            return {}

    def merge_secrets(self, klass, obj_id, body):
        secrets = (self.database()['%s_secrets' % klass].find_one(
            {'_id': obj_id}, {'_id': 0}))
        if secrets:
            merge_dictionary(body, secrets)
        return body

    def get_objects(self, klass, tenant_id=None, with_secrets=None,
                    offset=None, limit=None):
        if not self._client:
            self.database()
        client = self._client
        with client.start_request():
            if tenant_id:
                if limit:
                    if offset is None:
                        offset = 0
                    results = (self.database()[klass].find(
                                                {'tenantId': tenant_id},
                                                self._object_projection
                                            ).skip(offset).limit(limit))

                elif offset and (limit is None):
                    results = (self.database()[klass].find(
                                                    {'tenantId': tenant_id},
                                                    self._object_projection
                                                ).skip(offset))
                else:
                    results = (self.database()[klass].find(
                                                    {'tenantId': tenant_id},
                                                    self._object_projection)
                                                )
            else:
                if limit:
                    if offset is None:
                        offset = 0
                    results = (self.database()[klass].find(
                                                        None,
                                                        self._object_projection
                                                    ).skip(offset
                                                    ).limit(limit))
                elif offset and (limit is None):
                    results = (self.database()[klass].find(
                                                        None,
                                                        self._object_projection
                                                    ).skip(offset))
                else:
                    results = self.database()[klass].find(
                                                        None, 
                                                        self._object_projection
                                                    )
            if results:
                response = {}
                if with_secrets is True:
                    for entry in results:
                        response[entry['id']] = self.merge_secrets(klass, 
                                                            entry['id'], entry)
                else:
                    for entry in results:
                        response[entry['id']] = entry
        if results:
            if response:
                return response
        else:
            return {}

    def save_object(self, klass, obj_id, body, secrets=None, tenant_id=None, 
                    merge_existing=False):
        """Clients that wish to save the body but do/did not have access to
        secrets will by default send in None for secrets. We must not have that
        overwrite the secrets. To clear the secrets for an object, a non-None
        dict needs to be passed in: ex. {}.        
        """
        if isinstance(body, ExtensibleDict):
            body = body.__dict__()
        assert isinstance(body, dict), "dict required by backend"
        assert 'id' in body, "id required to be in body by backend"
        if not self._client:
            self.database()
        client = self._client
        with client.start_request():

            # TODO: pull this out of save_object
            if klass == 'workflows':
                current = self.database()[klass].find_one({'_id': obj_id})
                if current and '_lock' in current:
                    body['_lock'] = current['_lock']
                    body['_lock_timestamp'] = current['_lock_timestamp']

            if merge_existing:
                current = self.get_object(klass, obj_id)

                if current:
                    merge_dictionary(current, body)
                    body = current

            if secrets is not None:
                if not secrets:
                    LOG.warning("Clearing secrets for %s:%s" % (klass, obj_id))
                    self.database()['%s_secrets' % klass].remove()
                else:
                    cur_secrets = (self.database()['%s_secrets' % klass].find_one(
                                   {'_id': obj_id}, {'_id': 0}))
                    if cur_secrets:
                        collate(cur_secrets, secrets, extend_lists=False)
                        secrets = cur_secrets
            if tenant_id:
                body['tenantId'] = tenant_id
            assert tenant_id or 'tenantId' in body, "tenantId must be specified"
            body['_id'] = obj_id
            self.database()[klass].update({'_id': obj_id}, body, True, False, check_keys=False)
            if secrets:
                secrets['_id'] = obj_id
                self.database()['%s_secrets' % klass].update({'_id': obj_id},
                                                             secrets, True, False)
            del body['_id']

        return body

    def delete_object(self, klass, id, body):
        result = self.database()[klass].remove(body)

   
