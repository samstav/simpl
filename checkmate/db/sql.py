'''
Driver for SQL ALchemy
'''
import copy
import json
import logging
import time
import uuid

from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String,
    Text,
    PickleType,
    Float,
    event
)
from sqlalchemy import create_engine
from sqlalchemy.engine.base import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session, relationship
from sqlalchemy.pool import StaticPool

from SpiffWorkflow.util import merge_dictionary as collate
import sqlite3

from checkmate.classes import ExtensibleDict
from checkmate.db.common import (
    DbBase,
    DEFAULT_RETRIES,
    DEFAULT_STALE_LOCK_TIMEOUT,
    DEFAULT_TIMEOUT,
    DatabaseTimeoutException,
    ObjectLockedError,
    InvalidKeyError
)
from checkmate.exceptions import CheckmateException
from checkmate import utils


__all__ = ['Environment', 'Blueprint', 'Deployment', 'Workflow']

LOG = logging.getLogger(__name__)
BASE = declarative_base()


def filter_custom_comparison(query_obj, field, value):
    '''Return a sqlalchemy filter based on `value`

    The following are accepted forms of filtering:
        VALUE, !VALUE, >=VALUE, >VALUE, <=VALUE, <VALUE
    '''
    if value.startswith('!'):
        return query_obj.filter("%s != '%s'" % (field, value[1:]))
    elif field.startswith('>='):
        return query_obj.filter("%s >= '%s'" % (field, value[2:]))
    elif field.startswith('>'):
        return query_obj.filter("%s > '%s'" % (field, value[1:]))
    elif field.startswith('<='):
        return query_obj.filter("%s <= '%s'" % (field, value[2:]))
    elif field.startswith('<'):
        return query_obj.filter("%s < '%s'" % (field, value[1:]))
    else:
        return query_obj.filter("%s == '%s'" % (field, value))


class TextPickleType(PickleType):
    '''Type that can be set to dict and stored in the database as Text.

    This allows us to read and write the 'body' attribute as dicts
    '''
    impl = Text


class Tenant(BASE):
    '''Class to encapsulate tenants table.'''
    __tablename__ = "tenants"
    id = Column(String(255), primary_key=True)
    tags = relationship("TenantTag", cascade="all, delete, delete-orphan")


class TenantTag(BASE):
    '''Class to encapsulate tenant_tags table.'''
    __tablename__ = "tenant_tags"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant = Column(
        String(255),
        ForeignKey(
            'tenants.id',
            ondelete="CASCADE",
            onupdate="RESTRICT"
        )
    )
    tag = Column(String(255), index=True)


class Environment(BASE):
    '''Class to encapsulate environments table.'''
    __tablename__ = 'environments'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    locked = Column(Float, default=0)
    lock = Column(String, default=0)
    lock_timestamp = Column(Integer, default=0)
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


class Deployment(BASE):
    '''Class to encapsulate deployments table.'''
    __tablename__ = 'deployments'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    created = Column(String(255), index=False)
    locked = Column(Float, default=0)
    lock = Column(String, default=0)
    lock_timestamp = Column(Integer, default=0)
    tenant_id = Column(String(255), index=True)
    status = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


class Blueprint(BASE):
    '''Class to encapsulate blueprints table.'''
    __tablename__ = 'blueprints'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    locked = Column(Float, default=0)
    lock = Column(String, default=0)
    lock_timestamp = Column(Integer, default=0)
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


class Workflow(BASE):
    '''Class to encapsulate workflows table.'''
    __tablename__ = 'workflows'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    locked = Column(Float, default=0)
    lock = Column(String, default=0)
    lock_timestamp = Column(Integer, default=0)
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    '''Turn on fk for sqlite.'''
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Driver(DbBase):
    '''Driver class for SQL database abstraction.'''
    def __init__(self, connection_string, driver=None, *args, **kwargs):
        '''Initializes globals for this driver'''
        DbBase.__init__(self, connection_string, driver=driver, *args,
                        **kwargs)

        if connection_string == 'sqlite://':
            self.engine = create_engine(connection_string,
                                        connect_args={
                                            'check_same_thread': False
                                        },
                                        poolclass=StaticPool)
            message = ("Checkmate is connected to an in-memory sqlite "
                       "database. No data will be persisted. To store your "
                       "data, set the CHECKMATE_CONNECTION_STRING environment "
                       "variable to a valid sqlalchemy connection string")
            LOG.warning(message)
            print message
        else:
            self.engine = create_engine(connection_string)
            LOG.info("Connected to '%s'", connection_string)
        self.session = scoped_session(sessionmaker(self.engine))
        BASE.metadata.create_all(self.engine)

    def __setstate__(self, dict):  # pylint: disable=W0622
        '''Support deserializing from connection string.'''
        DbBase.__setstate__(self, dict)
        #FIXME: make DRY
        if self.connection_string == 'sqlite://':
            self.engine = create_engine(self.connection_string,
                                        connect_args={
                                            'check_same_thread': False
                                        },
                                        poolclass=StaticPool)
            message = ("Checkmate is connected to an in-memory sqlite "
                       "database. No  data will be persisted. To store your "
                       "data, set the CHECKMATE_CONNECTION_STRING environment "
                       "variable to a valid sqlalchemy connection string")
            LOG.warning(message)
            print message
        else:
            self.engine = create_engine(self.connection_string)
            LOG.info("Connected to '%s'", self.connection_string)

        self.session = scoped_session(sessionmaker(self.engine))
        BASE.metadata.create_all(self.engine)

    def dump(self):
        '''Get all the things.'''
        response = {}
        response['environments'] = self.get_environments()
        response['deployments'] = self.get_deployments()
        response['blueprints'] = self.get_blueprints()
        response['workflows'] = self.get_workflows()
        return response

    # TENANTS
    def save_tenant(self, tenant):
        '''Save a tenant in the tenants table.'''
        if tenant and tenant.get('id'):
            tenant_id = tenant.get('id')
            current = (
                self.session.query(Tenant).filter(
                    Tenant.id == tenant_id).first()
            )
            if not current:
                current = Tenant(
                    id=tenant_id,
                    tags=[
                        TenantTag(tag=tag) for tag in tenant.get('tags', [])
                    ] or None
                )
                self.session.add(current)
            else:
                del current.tags[0:len(current.tags)]
                current.tags = ([TenantTag(tag=tag)
                                for tag in tenant.get('tags', [])]
                                or None)
            self.session.commit()
        else:
            raise CheckmateException("Must provide a tenant id")

    def list_tenants(self, *args):
        '''Retrieve all tenants from the tenants table.'''
        query = self.session.query(Tenant)
        if args:
            for arg in args:
                query = query.filter(Tenant.tags.any(TenantTag.tag == arg))
        tenants = query.all()
        ret = {}
        for tenant in tenants:
            ret.update({tenant.id: self._fix_tenant(tenant)})
        return ret

    def _fix_tenant(self, tenant):
        '''Rearrange tag information in tenant record.'''
        if tenant:
            tags = [tag.tag for tag in tenant.tags or []]
            ret = {'id': tenant.id}
            if tags:
                ret['tags'] = tags
            return ret
        return None

    def get_tenant(self, tenant_id):
        '''Retrieve a tenant by tenant_id.'''
        tenant = (self.session.query(Tenant).filter_by(id=tenant_id)
                  .first())
        return self._fix_tenant(tenant)

    def add_tenant_tags(self, tenant_id, *args):
        '''Add tags to an existing tenant.'''
        if tenant_id:
            tenant = (self.session.query(Tenant)
                      .filter(Tenant.id == tenant_id)
                      .first())
            new_tags = set(args or [])
            if not tenant:
                tenant = Tenant(id=tenant_id,
                                tags=[TenantTag(tag=tag) for tag in new_tags]
                                or None)
                self.session.add(tenant)
            elif new_tags:
                if not tenant.tags:
                    tenant.tags = []
                tenant.tags.extend([
                    TenantTag(tag=ntag) for ntag in new_tags
                    if ntag not in [tag.tag for tag in tenant.tags]
                ])
            self.session.commit()
        else:
            raise CheckmateException("Must provide a tenant with a tenant id")

    # ENVIRONMENTS
    def get_environment(self, id, with_secrets=None):
        '''Retrieve an environment by environment id.'''
        return self._get_object(Environment, id, with_secrets=with_secrets)

    def get_environments(self, tenant_id=None, with_secrets=None):
        '''Retrieve all environment records for a given tenant id'''
        return self._get_objects(
            Environment,
            tenant_id,
            with_secrets=with_secrets
        )

    def save_environment(self, id, body, secrets=None, tenant_id=None):
        '''Save an environment to the database.'''
        return self._save_object(Environment, id, body, secrets, tenant_id)

    # DEPLOYMENTS
    def get_deployment(self, id, with_secrets=None):
        '''Retrieve a deployment by deployment id.'''
        return self._get_object(Deployment, id, with_secrets=with_secrets)

    def get_deployments(self, tenant_id=None, with_secrets=None, offset=None,
                        limit=None, with_count=True, with_deleted=False,
                        status=None):
        '''Retrieve all deployments for a given tenant id.'''
        return self._get_objects(
            Deployment,
            tenant_id,
            with_secrets=with_secrets,
            offset=offset,
            limit=limit,
            with_count=with_count,
            with_deleted=with_deleted,
            status=status
        )

    def save_deployment(self, id, body, secrets=None, tenant_id=None,
                        partial=False):
        '''Save a deployment to the database.'''
        return self._save_object(
            Deployment,
            id,
            body,
            secrets,
            tenant_id,
            merge_existing=partial
        )

    #BLUEPRINTS
    def get_blueprint(self, id, with_secrets=None):
        '''Retrieve a blueprint by blueprint id.'''
        return self._get_object(Blueprint, id, with_secrets=with_secrets)

    def get_blueprints(self, tenant_id=None, with_secrets=None, limit=None,
                       offset=None, with_count=True):
        return self._get_objects(Blueprint, tenant_id,
                                 with_secrets=with_secrets, limit=limit,
                                 offset=offset, with_count=with_count)

    def save_blueprint(self, api_id, body, secrets=None, tenant_id=None):
        '''Save a blueprint to the database.'''
        return self._save_object(Blueprint, api_id, body, secrets, tenant_id)

    # WORKFLOWS
    def get_workflow(self, id, with_secrets=None):
        '''Retrieve a workflow by workflow id.'''
        return self._get_object(Workflow, id, with_secrets=with_secrets)

    def get_workflows(self, tenant_id=None, with_secrets=None,
                      offset=None, limit=None):
        '''Retrieve all workflows for a given tenant id'''
        return self._get_objects(
            Workflow,
            tenant_id,
            with_secrets=with_secrets,
            offset=offset, limit=limit
        )

    def save_workflow(self, id, body, secrets=None, tenant_id=None):
        '''Save a workflow to the database.'''
        return self._save_object(Workflow, id, body, secrets, tenant_id)

    def unlock_workflow(self, api_id, key):
        '''Remove a lock from a workflow.'''
        return self.unlock_object(Workflow, api_id, key)

    def lock_workflow(self, api_id, with_secrets=None, key=None):
        '''Add a lock to a workflow.'''
        return self.lock_object(Workflow, api_id, with_secrets=with_secrets,
                                key=key)

    # GENERIC
    def _get_object(self, klass, id, with_secrets=None):
        '''Retrieve a record by id from a given table.'''
        results = self.session.query(klass).filter_by(id=id)
        if results and results.count() > 0:
            first = results.first()
            body = first.body
            self.convert_data(klass.__tablename__, body)
            if "tenantId" in body:
                first.tenant_id = body["tenantId"]
            elif first.tenant_id:
                body['tenantId'] = first.tenant_id
            if with_secrets is True:
                if first.secrets:
                    return utils.merge_dictionary(body, first.secrets)
                else:
                    return body
            else:
                return body

    def _get_objects(self, klass, tenant_id=None, with_secrets=None,
                     offset=None, limit=None, with_count=True,
                     with_deleted=False, status=None):
        '''Retrieve all recrods from a given table for a given tenant id.'''
        response = {}
        response['_links'] = {}  # To be populated soon!
        response['results'] = {}
        results = self._add_filters(
            klass, self.session.query(klass), tenant_id, with_deleted, status)
        if klass is Deployment:
            results = results.order_by(Deployment.created.desc())
        elif klass is Workflow:
            results = results.order_by(Workflow.id)
        if results and results.count() > 0:
            results = results.limit(limit).offset(offset).all()

            for entry in results:
                self.convert_data(klass.__tablename__, entry.body)
                if with_secrets is True:
                    if entry.secrets:
                        response['results'][entry.id] = utils.merge_dictionary(
                            entry.body,
                            entry.secrets
                        )
                    else:
                        response['results'][entry.id] = entry.body
                else:
                    response['results'][entry.id] = entry.body
                if entry.tenant_id is not None:
                    response['results'][entry.id]['tenantId'] = entry.tenant_id
        if with_count:
            response['collection-count'] = self._get_count(
                klass, tenant_id, with_deleted, status)
        return response

    def _add_filters(self, klass, query, tenant_id, with_deleted, status=None):
        if tenant_id:
            query = query.filter_by(tenant_id=tenant_id)
        if klass is Deployment and (not with_deleted or status):
            if not status:
                status = "!DELETED"
            query = filter_custom_comparison(query, 'deployments_status',
                                             status)
        return query

    def _get_count(self, klass, tenant_id, with_deleted, status=None):
        return self._add_filters(
            klass, self.session.query(klass), tenant_id, with_deleted,
            status).count()

    def _save_object(self, klass, api_id, body, secrets=None,
                     tenant_id=None, merge_existing=False):
        '''Save any object to the database.

        Clients that wish to save the body but do/did not have access to
        secrets will by default send in None for secrets. We must not have that
        overwrite the secrets. To clear the secrets for an object, a non-None
        dict needs to be passed in: ex. {}
        '''
        if isinstance(body, ExtensibleDict):
            body = body.__dict__()
        assert isinstance(body, dict), "dict required by sqlalchemy backend"

        #object locking logic
        results = None
        tries = 0
        lock_timestamp = time.time()
        while tries < DEFAULT_RETRIES:
            #try to get the lock
            updated = self.session.query(klass).filter_by(
                id=api_id,
                locked=0
            ).update({'locked': lock_timestamp})
            self.session.commit()

            if updated > 0:
                #get the object that we just locked
                results = self.session.query(klass).filter_by(id=api_id,
                                                              locked=
                                                              lock_timestamp)
                assert results.count() > 0, ("There was a fatal error. The "
                                             "object %s with id %s could not "
                                             "be locked!" % (klass, api_id))
                break
            else:
                existing_object = self.session.query(klass)\
                    .filter_by(id=api_id).first()
                if not existing_object:
                    #this is a new object
                    break

                elif ((lock_timestamp - existing_object.locked) >=
                      DEFAULT_STALE_LOCK_TIMEOUT):

                    #the lock is stale, remove it
                    stale_lock_object = \
                        self.session.query(klass).filter_by(
                            id=api_id,
                            locked=existing_object.locked
                        ).update({'locked': lock_timestamp})
                    self.session.commit()

                    results = self.session.query(klass).filter_by(id=api_id)

                    if stale_lock_object:
                        #updated the stale lock
                        break

                if (tries + 1) == DEFAULT_TIMEOUT:
                    raise DatabaseTimeoutException("Attempted to query the "
                                                   "database the maximum "
                                                   "amount of retries.")
                time.sleep(DEFAULT_TIMEOUT)
                tries += 1

        if results and results.count() > 0:
            e = results.first()
            e.locked = 0

            if merge_existing:
                saved_body = copy.deepcopy(e.body)
                collate(saved_body, body)
                e.body = saved_body
            else:  # Merge not specified, so replace
                e.body = body

            if tenant_id:
                e.tenant_id = tenant_id
            elif "tenantId" in body:
                e.tenant_id = body.get("tenantId")

            assert klass is Blueprint or tenant_id or e.tenant_id,\
                "tenantId must be specified"

            if secrets is not None:
                if not secrets:
                    LOG.warning("Clearing secrets for %s:%s", klass.__name__,
                                api_id)
                    e.secrets = None
                else:
                    if not e.secrets:
                        e.secrets = {}
                    new_secrets = copy.deepcopy(e.secrets)
                    collate(new_secrets, secrets, extend_lists=False)
                    e.secrets = new_secrets

        else:
            assert klass is Blueprint or tenant_id or 'tenantId' in body, \
                "tenantId must be specified"
            #new item
            e = klass(id=api_id, body=body, tenant_id=tenant_id,
                      secrets=secrets, locked=0)

        # As of v0.13, status is saved in Deployment object
        if klass is Deployment:
            e.status = body.get('status')
            e.created = body.get('created')

        self.session.add(e)
        self.session.commit()
        return body

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
            return (self.merge_secrets(klass, api_id, locked_object), key)
        return self._lock_find_object(klass, api_id, key=key)

    def unlock_object(self, klass, api_id, key):
        '''
        Unlocks a locked object if the key is correct.

        :param klass: the class of the object to unlock.
        :param api_id: the object's API ID.
        :param key: the key used to lock the object (see lock_object()).
        :raises ValueError: If the unlocked object does not exist or the lock
            was incorrect.
        '''
        query = self.session.query(klass).filter_by(
            id=api_id,
            lock=key
        )
        unlocked_object = query.first()
        results = query.update({'lock': 0})
        self.session.commit()
        #remove state added to passed in dict
        if results > 0:
            return unlocked_object.body
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
            query = self.session.query(klass).filter_by(
                id=api_id,
                lock=key
            )
            locked_object = query.first()
            result = query.update({'lock_timestamp': lock_timestamp})
            self.session.commit()

            if result > 0:
                # The passed in key matched
                return (locked_object.body, key)
            else:
                raise InvalidKeyError("The key:%s could not unlock: %s(%s)" % (
                                      key, klass, api_id))

        # A key was not passed in
        key = str(uuid.uuid4())
        query = self.session.query(klass).filter_by(
            id=api_id,
            lock=0
        )
        locked_object = query.first()
        result = query.update(
            {'lock': key, 'lock_timestamp': lock_timestamp}
        )
        self.session.commit()

        if result > 0:
            # We were able to lock the object
            return (locked_object.body, key)

        else:
            # Could not get the lock
            object_exists = (
                self.session.query(klass).filter_by(id=api_id).first()
            )
            if object_exists:
                # Object exists but we were not able to get the lock
                lock_time_delta = (
                    lock_timestamp - object_exists.lock_timestamp
                )
                if lock_time_delta >= 5:
                    # Key is stale, force the lock
                    LOG.warning("%s(%s) had a stale lock of %s seconds!",
                                klass, api_id, lock_time_delta)

                    query = self.session.query(klass).filter_by(id=api_id)
                    locked_object = query.first()
                    result = query.update(
                        {'lock': key, 'lock_timestamp': lock_timestamp}
                    )
                    self.session.commit()

                    return (locked_object.body, key)
                else:
                    # Lock is not stale
                    raise ObjectLockedError(
                        "%s(%s) was already locked!", klass, api_id
                    )
            else:
                # New object
                raise ValueError("Cannot get the object:%s that has never "
                                 "been saved" % api_id)

    def convert_data(self, klass, body):
        DbBase.convert_data(self, klass, body)
        if klass == 'deployments':
            if 'blueprint' in body:
                blueprint = body['blueprint']
                if 'documentation' in blueprint:
                    del blueprint['documentation']
                if 'options' in blueprint:
                    del blueprint['options']
                if 'services' in blueprint:
                    del blueprint['services']
                if 'resources' in blueprint:
                    del blueprint['resources']
            if 'environment' in body and 'providers' in body['environment']:
                del body['environment']['providers']
            if 'inputs' in body:
                del body['inputs']
            if 'plan' in body:
                del body['plan']
            if 'display-outputs' in body:
                del body['display-outputs']
            if 'resources' in body:
                del body['resources']
        elif klass == "workflows":
            if 'wf_spec' in body:
                if 'specs' in body['wf_spec']:
                    del body['wf_spec']['specs']
            if 'task_tree' in body:
                del body['task_tree']
