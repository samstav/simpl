'''
Driver for MongoDB

TODO:
- Fix mapping between API ID and mongoDB _id field

'''
import pymongo
import logging
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
    #db fields we do not want returned to the client
    _object_projection = {'_lock': 0, '_lock_timestamp': 0, '_id': 0}

    def __init__(self, connection_string, driver=None, *args, **kwargs):
        '''Initializes globals for this driver'''
        DbBase.__init__(self, connection_string, driver=driver, *args,
                        **kwargs)

        self.db_name = pymongo.uri_parser.parse_uri(self.connection_string
                                                    ).get('database',
                                                          'checkmate')
        self._database = None
        self._connection = None
        self._client = None

    def __getstate__(self):
        '''Support serializing to connection string'''
        data = DbBase.__getstate__(self)
        data['db_name'] = self.db_name
        return data

    def __setstate__(self, dict):  # pylint: disable=W0622
        '''Support deserializing from connection string'''
        DbBase.__setstate__(self, dict)
        self.db_name = dict['db_name']
        self._database = None
        self._connection = None
        self._client = None

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
            LOG.info("Connected to mongodb on %s (database=%s)",
                     self.connection_string, self.db_name)
        return self._database

    def dump(self):
        response = {}
        response['environments'] = self.get_environments()
        response['deployments'] = self.get_deployments()
        response['blueprints'] = self.get_blueprints()
        response['workflows'] = self.get_workflows()
        return response

    # ENVIRONMENTS
    def get_environment(self, oid, with_secrets=None):
        return self.get_object('environments', oid, with_secrets)

    def get_environments(self, tenant_id=None, with_secrets=None):
        return self.get_objects('environments', tenant_id, with_secrets)

    def save_environment(self, api_id, body, secrets=None, tenant_id=None):
        return self.save_object('environments', api_id, body, secrets,
                                tenant_id)

    # DEPLOYMENTS
    def get_deployment(self, api_id, with_secrets=None):
        return self.get_object('deployments', api_id, with_secrets)

    def get_deployments(self, tenant_id=None, with_secrets=None,
                        limit=None, offset=None):
        return self.get_objects('deployments', tenant_id, with_secrets,
                                offset=offset, limit=limit)

    def save_deployment(self, api_id, body, secrets=None, tenant_id=None,
                        partial=True):
        '''
        Pull current deployment in DB incase another task has modified its'
        contents
        '''

        # If the deployment exists, lock it!
        if self.get_deployment(api_id, with_secrets=secrets):
            key, deployment = self.lock_object('deployments',
                                               api_id, with_secrets=secrets)

        return self.save_object('deployments', api_id, body, secrets,
                                  tenant_id, merge_existing=partial)


    #BLUEPRINTS
    def get_blueprint(self, api_id, with_secrets=None):
        return self.get_object('blueprints', api_id, with_secrets)

    def get_blueprints(self, tenant_id=None, with_secrets=None):
        return self.get_objects('blueprints', tenant_id, with_secrets)

    def save_blueprint(self, api_id, body, secrets=None, tenant_id=None):
        return self.save_object('blueprints', api_id, body, secrets, tenant_id)

    # WORKFLOWS
    def get_workflow(self, api_id, with_secrets=None):
        return self.get_object('workflows', api_id, with_secrets=with_secrets)

    def get_workflows(self, tenant_id=None, with_secrets=None,
                      limit=None, offset=None):
        return self.get_objects('workflows', tenant_id, with_secrets,
                                offset=offset, limit=limit)

    def save_workflow(self, api_id, body, secrets=None, tenant_id=None):
        return self.save_object('workflows', api_id, body, secrets, tenant_id)

    def lock_workflow(self, api_id, with_secrets=None, key=None):
        """
        :param api_id: the object's API id.
        :param with_secrets: true if secrets should be merged into the results.
        :param key: if the object has already been locked, the key used must be
            passed in
        :returns (locked_object, key): a tuple of the locked_object and the
            key that should be used to unlock it.
        """
        return self.lock_object('workflows', api_id, with_secrets=with_secrets,
                                key=key)

    def unlock_workflow(self, api_id, key):
        """
        :param api_id: the object's API ID.
        :param key: the key used to lock the object (see lock_object()).
        """
        return self.unlock_object('workflows', api_id, key=key)

    def lock_object(self, klass, api_id, with_secrets=None, key=None):
        """
        :param klass: the class of the object to unlock.
        :param api_id: the object's API ID.
        :param with_secrets: true if secrets should be merged into the results.
        :param key: if the object has already been locked, the key used must be
            passed in
        :returns (locked_object, key): a tuple of the locked_object and the
            key that should be used to unlock it.
        """

        if with_secrets:
            locked_object, key = self._lock_find_object(klass, api_id, key=key)
            return (self.merge_secrets(klass, api_id, locked_object), key)
        return self._lock_find_object(klass, api_id, key=key)

    def unlock_object(self, klass, api_id, key):
        """
        Unlocks a locked object if the key is correct.

        :param klass: the class of the object to unlock.
        :param api_id: the object's API ID.
        :param key: the key used to lock the object (see lock_object()).
        :raises ValueError: If the unlocked object does not exist or the lock
            was incorrect.
        """
        unlocked_object = self.database()[klass].find_and_modify(
            query={
                '_id': api_id,
                '_lock': key
            },
            update={
                '$set': {
                    '_lock': 0,
                },
            },
            fields=self._object_projection
        )
        #remove state added to passed in dict
        if unlocked_object:
            return unlocked_object
        else:
            raise InvalidKeyError("The lock was invalid or the object %s does "
                                  "not exist." % api_id)

    def _lock_find_object(self, klass, api_id, key=None):
        """
        Finds, attempts to lock, and returns an object by id.

        :param klass: the class of the object unlock.
        :param api_id: the object's API ID.
        :param key: if the object has already been locked, the key used must be
            passed in
        :raises ValueError: if the api_id is of a non-existent object
        :returns (locked_object, key): a tuple of the locked_object and the
            key that should be used to unlock it.
        """
        assert klass, "klass must not be None."
        assert api_id, "api_id must not be None"

        lock_timestamp = time.time()
        if key:
            # The object has already been locked
            # TODO: see if we can merge the existing key logic into below
            locked_object = self.database()[klass].find_and_modify(
                query={
                    '_id': api_id,
                    '_lock': key
                },
                update={
                    '$set': {
                        '_lock_timestamp': lock_timestamp
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
                                      key, klass, api_id))

        # A key was not passed in
        key = str(uuid.uuid4())
        lock_update = {
            '$set': {
                '_lock': key,
                '_lock_timestamp': lock_timestamp
            }
        }

        locked_object = self.database()[klass].find_and_modify(
            query={'_id': api_id, '_lock': 0},
            update=lock_update,
            fields=self._object_projection
        )
        if(locked_object):
            # We were able to lock the object
            return (locked_object, key)

        else:
            # Could not get the lock
            object_exists = self.database()[klass].find_one({'_id': api_id})
            if(object_exists):
                # Object exists but we were not able to get the lock
                if '_lock' in object_exists:
                    lock_time_delta = (lock_timestamp -
                                       object_exists['_lock_timestamp'])

                    if lock_time_delta >= 5:
                        # Key is stale, force the lock
                        LOG.warning("%s(%s) had a stale lock of %s seconds!",
                                    klass, api_id, lock_time_delta)
                        locked_object = self.database()[klass]\
                            .find_and_modify(
                                query={'_id': api_id},
                                update=lock_update,
                                fields=self._object_projection
                            )
                        return (locked_object, key)
                    else:
                        # Lock is not stale
                        raise ObjectLockedError("%s(%s) was already locked!" %
                                                (klass, api_id))

                else:
                    # Object has no _lock field
                    locked_object = self.database()[klass].find_and_modify(
                        query={'_id': api_id},
                        update=lock_update,
                        fields=self._object_projection,
                        new=True
                    )
                    # Delete instead of projection so that we can
                    # use existing save_object
                    return (locked_object, key)

            else:
                # New object
                raise ValueError("Cannot get the object:%s that has never "
                                 "been saved" % api_id)

    def get_object(self, klass, api_id, with_secrets=None):
        '''
        Get an object by klass and api_id. We are filtering out the
        mongo _id field with a projection on all db queries.

        :param klass: The klass to query from
        :param api_id: The klass item to get
        :param with_secrets: Merge secrets with the results
        '''
        if not self._client:
            self.database()
        client = self._client
        with client.start_request():
            results = self.database()[klass].find_one({
                '_id': api_id}, self._object_projection)

            if results:
                if with_secrets is True:
                    self.merge_secrets(klass, api_id, results)

        if results:
            return results
        else:
            return {}

    def merge_secrets(self, klass, api_id, body):
        secrets = (self.database()['%s_secrets' % klass].find_one(
            {'_id': api_id}, {'_id': 0}))
        if secrets:
            merge_dictionary(body, secrets)
        return body

    def get_objects(self, klass, tenant_id=None, with_secrets=None,
                    offset=None, limit=None, include_total_count=True):
        if not self._client:
            self.database()
        client = self._client
        with client.start_request():
            count = self.database()[klass].count()
            if limit:
                if offset is None:
                    offset = 0
                results = self.database()[klass].find(
                    {'tenantId': tenant_id} if tenant_id else None,
                    self._object_projection
                ).skip(offset).limit(limit)

            elif offset and (limit is None):
                results = self.database()[klass].find(
                    {'tenantId': tenant_id} if tenant_id else None,
                    self._object_projection
                ).skip(offset)
            else:
                results = self.database()[klass].find(
                    {'tenantId': tenant_id} if tenant_id else None,
                    self._object_projection
                )

            if results:
                response = {}
                if with_secrets is True:
                    for entry in results:
                        response[entry['id']] = self.merge_secrets(
                            klass, entry['id'], entry)
                else:
                    for entry in results:
                        response[entry['id']] = entry

        if results:
            if response:
                if include_total_count:
                    response['collection-count'] = count
                return response
        return {}

    def save_object(self, klass, api_id, body, secrets=None, tenant_id=None,
                    merge_existing=False):
        """Clients that wish to save the body but do/did not have access to
        secrets will by default send in None for secrets. We must not have that
        overwrite the secrets. To clear the secrets for an object, a non-None
        dict needs to be passed in: ex. {}.
        """
        if isinstance(body, ExtensibleDict):
            body = body.__dict__()
        assert isinstance(body, dict), "dict required by backend"
        assert 'id' in body or merge_existing is True, ("id required to be in "
                                                        "body by backend")
        if not self._client:
            self.database()
        client = self._client
        with client.start_request():

            # TODO: pull this out of save_object
            if klass == 'workflows':
                current = self.database()[klass].find_one({'_id': api_id})
                if current and '_lock' in current:
                    body['_lock'] = current['_lock']
                    body['_lock_timestamp'] = current.get('_lock_timestamp')

            if merge_existing:
                current = self.get_object(klass, api_id)

                if current:
                    merge_dictionary(current, body)
                    body = current

            if secrets is not None:
                if not secrets:
                    LOG.warning("Clearing secrets for %s:%s", klass, api_id)
                    self.database()['%s_secrets' % klass].remove()
                else:
                    cur_secrets = self.database()['%s_secrets' % klass].\
                        find_one({'_id': api_id}, {'_id': 0})
                    if cur_secrets:
                        collate(cur_secrets, secrets, extend_lists=False)
                        secrets = cur_secrets
            if tenant_id:
                body['tenantId'] = tenant_id
            assert tenant_id or 'tenantId' in body, ("tenantId must be "
                                                     "specified")
            body['_id'] = api_id
            self.database()[klass].update({'_id': api_id}, body,
                                          not merge_existing,  # Upsert new
                                          False, check_keys=False)
            if secrets:
                secrets['_id'] = api_id
                self.database()['%s_secrets' % klass].update({
                    '_id': api_id}, secrets, True, False)
            del body['_id']

        return body
