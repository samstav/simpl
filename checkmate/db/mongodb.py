'''
Driver for MongoDB

TODO:
- Fix mapping between API ID and mongoDB _id field
- Check indeces; if we fix mapping do we still need an index on workflow.id?

'''
import copy
import logging
import pymongo
import time
import uuid

from SpiffWorkflow.util import merge_dictionary as collate

from checkmate.classes import ExtensibleDict
from checkmate.db.common import DbBase, ObjectLockedError, InvalidKeyError
from checkmate.exceptions import (
    CheckmateDatabaseConnectionError,
    CheckmateException,
)
from checkmate.db.db_lock import DbLock
from checkmate.utils import flatten
from checkmate.utils import merge_dictionary

LOG = logging.getLogger(__name__)


class Driver(DbBase):
    '''MongoDB Database Driver'''
    _workflow_collection_name = "workflows"
    _blueprint_collection_name = "blueprints"
    _deployment_collection_name = "deployments"
    _resource_collection_name = "resources"
    _environment_collection_name = "environments"

    #db fields we do not want returned to the client
    _object_projection = {'_lock': 0, '_lock_timestamp': 0, '_id': 0}

    _deployment_projection = copy.deepcopy(_object_projection)
    _deployment_projection['blueprint.documentation'] = 0
    _deployment_projection['blueprint.options'] = 0
    _deployment_projection['blueprint.services'] = 0
    _deployment_projection['blueprint.resources'] = 0
    _deployment_projection['environment.providers'] = 0
    _deployment_projection['inputs'] = 0
    _deployment_projection['plan'] = 0
    _deployment_projection['display-outputs'] = 0
    _deployment_projection['resources'] = 0

    _workflow_projection = copy.deepcopy(_object_projection)
    _workflow_projection['wf_spec.specs'] = 0
    _workflow_projection['task_tree'] = 0

    def __init__(self, connection_string, driver=None, *args, **kwargs):
        '''Initializes globals for this driver'''
        DbBase.__init__(self, connection_string, driver=driver, *args,
                        **kwargs)

        self.db_name = pymongo.uri_parser.parse_uri(
            self.connection_string).get('database', 'checkmate')
        self._database = None
        self._connection = None
        self._client = None
        try:
            self.tune()
        except Exception as exc:  # pylint: disable=W0703
            LOG.warn("Error tuning mongodb database: %s", exc)

    def tune(self):
        '''Documenting & Automating Index Creation'''
        LOG.debug("Tuning database")
        self.database()[self._deployment_collection_name].create_index(
            [("created", pymongo.DESCENDING)],
            background=True,
            name="deployments_created",
        )
        self.database()[self._deployment_collection_name].create_index(
            [("tenantId", pymongo.DESCENDING)],
            background=True,
            name="deployments_tenantId",
        )
        self.database()[self._workflow_collection_name].create_index(
            [("tenantId", pymongo.DESCENDING)],
            background=True,
            name="workflows_tenantId",
        )
        self.database()[self._workflow_collection_name].create_index(
            [('id', pymongo.ASCENDING)],
            background=True,
            name='workflows_id',
        )

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

    def _get_client(self):
        '''Get pymongo client (connect is not already connected)'''
        if self._client is None:
            try:
                self._client = (pymongo.MongoClient(
                    self.connection_string))
            except pymongo.errors.AutoReconnect as exc:
                raise CheckmateDatabaseConnectionError(exc.__str__())
        return self._client

    def database(self):
        ''' Connects to and returns mongodb database object '''
        if self._database is None:
            self._database = self._get_client()[self.db_name]
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

    def lock(self, key, timeout):
        return DbLock(self, key, timeout)

    def unlock(self, key):
        return self.release_lock(key)

    def acquire_lock(self, key, timeout):
        existing_lock = self.database()['locks'].find_one({'_id': key})
        result = self.database()['locks'].find_and_modify(
            query={'_id': key, 'expires_at': {'$lt': time.time()}},
            update={'_id': key, 'expires_at': (time.time() + timeout)},
            upsert=existing_lock is None,
            new=True
        )
        if not result:
            raise ObjectLockedError(
                "Can't lock %s as it is already locked!" % key)

    def release_lock(self, key):
        result = self.database()['locks'].remove({'_id': key}, True)
        if result['n'] != 1:
            raise InvalidKeyError("Cannot unlock %s, as key does not exist!"
                                  % key)

    # TENANTS
    def save_tenant(self, tenant):
        if tenant and tenant.get('tenant_id'):
            tenant_id = tenant.get("tenant_id")
            ten = {"tenant_id": tenant_id}
            if tenant.get('tags'):
                ten['tags'] = tenant.get('tags')
            resp = self.database()['tenants'].find_and_modify(
                query={'tenant_id': tenant_id},
                update=ten,
                upsert=True,
                new=True
            )
            LOG.debug("Saved tenant: %s", resp)
        else:
            raise CheckmateException("Must provide a tenant id")

    def list_tenants(self, *args):
        ret = {}
        find = {}
        if args:
            find = {"tags": {"$all": args}}
        results = self.database()['tenants'].find(find, {"_id": 0})
        for result in results:
            ret.update({result['tenant_id']: result})
        return ret

    def get_tenant(self, tenant_id):
        LOG.debug("Looking for tenant %s", tenant_id)
        return self.database()['tenants'].find_one({"tenant_id": tenant_id},
                                                   {"_id": 0})

    def add_tenant_tags(self, tenant_id, *args):
        if tenant_id:
            tenant = (self.database()['tenants']
                      .find_one({"tenant_id": tenant_id}))
            if not tenant:
                tenant = {"tenant_id": tenant_id}
            if args and tenant:
                if 'tags' not in tenant:
                    tenant['tags'] = []
                tags = tenant['tags']
                tags.extend([t for t in args if t not in tags])
                self.database()['tenants'].save(tenant)
        else:
            raise CheckmateException("Must provide a tenant with a tenant id")

    # ENVIRONMENTS
    def get_environment(self, oid, with_secrets=None):
        return self._get_object(self._environment_collection_name, oid,
                                with_secrets=with_secrets)

    def get_environments(self, tenant_id=None, with_secrets=None):
        return self._get_objects(
            self._environment_collection_name,
            tenant_id,
            with_secrets=with_secrets
        )

    def save_environment(self, api_id, body, secrets=None, tenant_id=None):
        return self._save_object(self._environment_collection_name, api_id,
                                 body, secrets, tenant_id)

    # DEPLOYMENTS
    def _dereferenced_resources(self, deployment, with_secrets=False):
        '''
        Replaces the resource ids within a deployment with actual resource
        defintions

        :param deployment: Deployment with resource_id references
        :param with_secrets: defines whether to get the resources with secrets
        :return: deployment with resources_ids replaces with actual resource
        defintions
        '''
        resources = self._get_resources(deployment.get("resources", None),
                                        with_ids=False,
                                        with_secrets=with_secrets)
        flat = flatten(resources)
        if flat:
            self.convert_data('resources', flat)
        return flat

    def get_deployment(self, api_id, with_secrets=None):
        deployment = self._get_object(self._deployment_collection_name, api_id,
                                      with_secrets=with_secrets)
        if (deployment and 'resources' in deployment and
                not self._has_legacy_resources(deployment)):
            deployment["resources"] = self._dereferenced_resources(
                deployment,
                with_secrets=with_secrets)

        return deployment

    def get_deployments(self, tenant_id=None, with_secrets=None, limit=0,
                        offset=0, with_count=True, with_deleted=False):
        deployments = self._get_objects(self._deployment_collection_name,
                                        tenant_id, with_secrets=with_secrets,
                                        offset=offset,
                                        limit=limit, with_count=with_count,
                                        with_deleted=with_deleted)
        return deployments

    def _remove_all(self, collection_name, ids):
        '''Remove all objects with the ids in the ids list supplied'''
        if ids:
            self.database()[collection_name].remove({"_id": {'$in': ids}})

    def save_deployment(self, api_id, body, secrets=None, tenant_id=None,
                        partial=True):
        '''
        Saves the deployment by splitting the body into deployment and
        resources. Resources and deployment are saved in separate
        collections. Secrets are also split into deployment and resource
        secrets and are saved in separate collections.

        :param api_id: Id of deployment
        :param body: data to be saved/updated
        :param secrets: secrets
        :param tenant_id:
        :param partial: True if its a partial update
        :return: saved deployment as a hash
        '''
        existing_deployment = self._get_object(
            self._deployment_collection_name, api_id)
        is_legacy_resources_format = (
            self._has_legacy_resources(existing_deployment))
        resources = body.get("resources", None)
        resource_secrets = {}
        deployment_secrets = None
        if secrets:
            resource_secrets = secrets.pop('resources', {})
            deployment_secrets = secrets

        if resources:
            body['resources'] = self._save_resources(resources,
                                                     existing_deployment,
                                                     tenant_id,
                                                     partial,
                                                     resource_secrets)

        #If there is a partial update for a single resource don't update the
        # deployment
        if (len(body) == 1 and body.get('resources', None) and
                not is_legacy_resources_format) and not deployment_secrets:
            deployment = existing_deployment
        #Deployment is saved when its a full update or a partial update
        #involving deployment data or deployment secrets
        else:
            deployment = self._save_object(self._deployment_collection_name,
                                           api_id, body, deployment_secrets,
                                           tenant_id, merge_existing=partial)

        if not partial and existing_deployment:
             # Deleting old/orphaned documents
            self._remove_all('resources',
                             existing_deployment.get('resources', None))
            self._remove_all('deployments_secrets', [deployment["id"]])
            self._remove_all('resources_secrets',
                             existing_deployment.get('resources', None))

        if deployment.get('resources', None):
            deployment["resources"] = self._dereferenced_resources(deployment)
        return deployment

    def _save_resources(self, incoming_resources, deployment, tenant_id,
                        partial, secrets):
        resource_ids = []
        resource_secret = None
        if partial and deployment:
            if self._has_legacy_resources(deployment):
                deployment_secrets = self._get_object('deployments_secrets',
                                                      deployment["id"])
                deployment["resources"] = self. \
                    _save_resources(deployment["resources"],
                                    deployment, tenant_id, False,
                                    deployment_secrets)
                self._remove_all('deployments_secrets', [deployment["id"]])

            resource_ids = deployment["resources"]
            existing_resources = self._get_resources(resource_ids)
            resources = self._relate_resources(existing_resources,
                                               incoming_resources,
                                               secrets)
            for resource in resources:
                self._save_resource(resource['id'], resource['body'],
                                    tenant_id=tenant_id, partial=partial,
                                    secrets=resource["secret"])
        else:
            for key, resource in incoming_resources.iteritems():
                resource_id = uuid.uuid4().hex
                resource_ids.append(resource_id)
                if secrets and key in secrets:
                    resource_secret = {key: secrets[key]}
                self._save_resource(resource_id,
                                    {key: resource, "id": resource_id},
                                    tenant_id=tenant_id, partial=partial,
                                    secrets=resource_secret)
        return resource_ids

    @staticmethod
    def _has_legacy_resources(deployment):
        '''
        Checks whether a deployment has resources with definition inside the
        deployment and not just references for resources

        :param deployment: deployment to check
        :return: (True of False)
        '''
        if deployment:
            return isinstance(deployment.get("resources", None), dict)
        return False

    def _relate_resources(self, existing, incoming, secrets=None):
        resources = []
        resource_secret = None

        for key, incoming_resource in incoming.iteritems():
            for existing_resource in existing:
                if key in existing_resource:
                    if key in secrets:
                        resource_secret = {key: secrets.get(key)}
                    resources.append({'id': existing_resource["id"],
                                      'body': {key: incoming_resource},
                                      'secret': resource_secret})
        return resources

    def _get_resources(self, resource_ids, with_ids=True, with_secrets=False):
        resources = []
        if resource_ids:
            resources_cursor = self.database()[self._resource_collection_name]\
                .find({'id': {'$in': resource_ids}}, {"tenantId": 0, "_id": 0})
            for resource in resources_cursor:
                if with_secrets:
                    self.merge_secrets(self._resource_collection_name,
                                       resource["id"], resource)
                if not with_ids:
                    resource.pop("id")
                resources.append(resource)
        return resources

    def _save_resource(self, resource_id, body, tenant_id=None, partial=True,
                       secrets=None):
        resource = self._save_object(self._resource_collection_name,
                                     resource_id, body, tenant_id=tenant_id,
                                     merge_existing=partial,
                                     secrets=secrets)
        return resource

    #BLUEPRINTS
    def get_blueprint(self, api_id, with_secrets=None):
        return self._get_object(self._blueprint_collection_name, api_id,
                                with_secrets=with_secrets)

    def get_blueprints(self, tenant_id=None, with_secrets=None):
        return self._get_objects(self._blueprint_collection_name, tenant_id,
                                 with_secrets=with_secrets)

    def save_blueprint(self, api_id, body, secrets=None, tenant_id=None):
        return self._save_object(self._blueprint_collection_name, api_id, body,
                                 secrets, tenant_id)

    # WORKFLOWS
    def get_workflow(self, api_id, with_secrets=None):
        return self._get_object(self._workflow_collection_name, api_id,
                                with_secrets=with_secrets)

    def get_workflows(self, tenant_id=None, with_secrets=None,
                      limit=0, offset=0):
        return self._get_objects(self._workflow_collection_name, tenant_id,
                                 with_secrets=with_secrets,
                                 offset=offset, limit=limit)

    def save_workflow(self, api_id, body, secrets=None, tenant_id=None):
        current = self._get_object(self._workflow_collection_name, api_id,
                                   projection={'_lock': 1,
                                   '_lock_timestamp': 1})
        if current and '_lock' in current:
            body['_lock'] = current['_lock']
            body['_lock_timestamp'] = current.get('_lock_timestamp')
        return self._save_object(self._workflow_collection_name, api_id, body,
                                 secrets, tenant_id)

    def lock_workflow(self, api_id, with_secrets=None, key=None):
        '''
        :param api_id: the object's API id.
        :param with_secrets: true if secrets should be merged into the results.
        :param key: if the object has already been locked, the key used must be
            passed in
        :returns (locked_object, key): a tuple of the locked_object and the
            key that should be used to unlock it.
        '''
        return self.lock_object(self._workflow_collection_name, api_id,
                                with_secrets=with_secrets, key=key)

    def unlock_workflow(self, api_id, key):
        '''
        :param api_id: the object's API ID.
        :param key: the key used to lock the object (see lock_object()).
        '''
        return self.unlock_object(self._workflow_collection_name, api_id,
                                  key=key)

    def lock_object(self, klass, api_id, with_secrets=None, key=None):
        '''
        :param klass: the class of the object to unlock.
        :param api_id: the object's API ID.
        :param with_secrets: true if secrets should be merged into the results.
        :param key: if the object has already been locked, the key used must be
            passed in
        :returns (locked_object, key): a tuple of the locked_object and the
            key that should be used to unlock it.
        '''
        if with_secrets:
            locked_object, key = self._lock_find_object(klass, api_id, key=key)
            return self.merge_secrets(klass, api_id, locked_object), key
        return self._lock_find_object(klass, api_id, key=key)

    def unlock_object(self, klass, api_id, key):
        '''
        Unlocks a locked object if the key is correct.

        :param klass: the class of the object to unlock.
        :param api_id: the object's API ID.
        :param key: the key used to lock the object (see lock_object()).
        :raises InvalidKeyError: If the unlocked object does not exist or the
            lock key did not match.
        '''
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
        '''
        Finds, attempts to lock, and returns an object by id.

        :param klass: the class of the object unlock.
        :param api_id: the object's API ID.
        :param key: if the object has already been locked, the key used must be
            passed in
        :raises ValueError: if the api_id is of a non-existent object
        :returns (locked_object, key): a tuple of the locked_object and the
            key that should be used to unlock it.
        '''
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
            query={
                '_id': api_id,
                '$or': [{'_lock': {'$exists': False}}, {'_lock': 0}]
            },
            update=lock_update,
            fields=self._object_projection
        )
        if locked_object:
            # We were able to lock the object
            return (locked_object, key)

        else:
            # Could not get the lock
            object_exists = self.database()[klass].find_one({'_id': api_id})
            if object_exists:
                # Object exists but we were not able to get the lock
                if '_lock' in object_exists:
                    lock_time_delta = (lock_timestamp -
                                       object_exists['_lock_timestamp'])

                    if lock_time_delta >= 5:
                        # Key is stale, force the lock
                        LOG.warning("%s(%s) had a stale lock of %s seconds!",
                                    klass, api_id, lock_time_delta)
                        locked_object = self.database()[klass] \
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
                    # use existing _save_object
                    return (locked_object, key)

            else:
                # New object
                raise ValueError("Cannot get the object:%s that has never "
                                 "been saved" % api_id)

    def _get_object(self, klass, api_id, with_secrets=None, projection=None):
        '''
        Get an object by klass and api_id. We are filtering out the
        mongo _id field with a projection on all db queries.

        :param klass: The klass to query from
        :param api_id: The klass item to get
        :param with_secrets: Merge secrets with the results
        '''
        if not projection:
            projection = self._object_projection
        with self._get_client().start_request():
            results = self.database()[klass].find_one({'_id': api_id},
                                                      projection)

            if results:
                if with_secrets is True:
                    self.merge_secrets(klass, api_id, results)
                self.convert_data(klass, results)

        return results

    def merge_secrets(self, klass, api_id, body):
        secrets = (self.database()['%s_secrets' % klass].find_one(
            {'_id': api_id}, {'_id': 0}))
        if secrets:
            merge_dictionary(body, secrets)
        return body

    def _get_objects(self, klass, tenant_id=None, with_secrets=None, offset=0,
                     limit=0, with_count=True, with_deleted=False):
        if klass == self._deployment_collection_name:
            projection = self._deployment_projection
            sort_key = 'created'
            sort_direction = pymongo.DESCENDING
        elif klass == self._workflow_collection_name:
            projection = self._workflow_projection
            sort_key = 'id'
            sort_direction = pymongo.ASCENDING
        else:
            projection = self._object_projection
            sort_key = None
        response = {}
        if offset is None:
            offset = 0
        if limit is None:
            limit = 0
        with self._get_client().start_request():
            results = self.database()[klass].find(self._build_filters(
                klass, tenant_id, with_deleted), projection)
            if sort_key:
                results.sort(sort_key, sort_direction)
            results = results.skip(offset).limit(limit)

            response['_links'] = {}  # To be populated soon!
            response['results'] = {}

            for entry in results:
                if with_secrets is True:
                    entry = self.merge_secrets(klass, entry['id'], entry)
                self.convert_data(klass, entry)
                response['results'][entry['id']] = entry

            if with_count:
                response['collection-count'] = self._get_count(
                    klass, tenant_id, with_deleted)
        return response

    def _get_count(self, klass, tenant_id, with_deleted):
        return self.database()[klass].find(
            self._build_filters(klass, tenant_id, with_deleted),
            self._object_projection
        ).count()

    @staticmethod
    def _build_filters(klass, tenant_id, with_deleted):
        filters = {}
        if tenant_id:
            filters['tenantId'] = tenant_id
        if klass == Driver._deployment_collection_name and not with_deleted:
            filters['status'] = {'$ne': 'DELETED'}
        return filters

    def _save_object(self, klass, api_id, body, secrets=None, tenant_id=None,
                     merge_existing=False):
        '''Clients that wish to save the body but do/did not have access to
        secrets will by default send in None for secrets. We must not have that
        overwrite the secrets. To clear the secrets for an object, a non-None
        dict needs to be passed in: ex. {}.
        '''
        if isinstance(body, ExtensibleDict):
            body = body.__dict__()
        assert isinstance(body, dict), "dict required by backend"
        assert 'id' in body or merge_existing is True, ("id required to be in "
                                                        "body by backend")
        with self._get_client().start_request():
            if merge_existing:
                current = self._get_object(klass, api_id)

                if current:
                    merge_dictionary(current, body)
                    body = current
                else:
                    merge_existing = False  # so we can create a new one

            if secrets is not None:
                if not secrets:
                    LOG.warning("Clearing secrets for %s:%s", klass, api_id)
                    self.database()['%s_secrets' % klass].remove()
                else:
                    cur_secrets = self.database()['%s_secrets' % klass]. \
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
                self.database()['%s_secrets' % klass].update({'_id': api_id},
                                                             secrets, True,
                                                             False)
            del body['_id']

        return body
