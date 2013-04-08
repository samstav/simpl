import json
import logging
import os
import time

from sqlalchemy import Column, Integer, String, Text, PickleType, Boolean,\
    Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from copy import deepcopy

try:
    # pylint: disable=E0611
    from migrate.versioning import exceptions as versioning_exceptions
except ImportError:
    from migrate import exceptions as versioning_exceptions

from checkmate.classes import ExtensibleDict
from checkmate.db import migration
from checkmate.db.common import *
from checkmate.exceptions import CheckmateDatabaseMigrationError
from checkmate.utils import merge_dictionary
from SpiffWorkflow.util import merge_dictionary as collate


__all__ = ['Base', 'Environment', 'Blueprint', 'Deployment', 'Component',
           'Workflow']

LOG = logging.getLogger(__name__)

CONNECTION_STRING = os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')
if CONNECTION_STRING == 'sqlite://':
    _ENGINE = create_engine(CONNECTION_STRING,
                connect_args={'check_same_thread': False},
                poolclass=StaticPool)
    message = "Checkmate is connected to an in-memory sqlite database. No " \
              "data will be persisted. To store your data, set the "\
              "CHECKMATE_CONNECTION_STRING environment variable to a valid "\
              "sqlalchemy connection string"
    LOG.warning(message)
    print message
else:
    _ENGINE = create_engine(CONNECTION_STRING)
    LOG.info("Connected to '%s'" % CONNECTION_STRING)


def _init_version_control():
    """Verify the state of the database"""
    if CONNECTION_STRING == "sqlite://":
        return
    repo_path = migration.get_migrate_repo_path()

    try:
        repo_version = migration.get_repo_version(repo_path)
        db_version = migration.get_db_version(_ENGINE, repo_path)

        if repo_version != db_version:
            msg = ("Database (%s) is not up to date (current=%s, "
                "latest=%s); run `checkmate-database upgrade` or '"
                "override your migrate version manually (see docs)" %
                (CONNECTION_STRING, db_version, repo_version))
            LOG.warning(msg)
            raise CheckmateDatabaseMigrationError(msg)
    except versioning_exceptions.DatabaseNotControlledError:
        msg = ("Database (%s) is not version controlled; "
                "run `checkmate-database version_control` or "
                "override your migrate version manually (see docs)" %
                (CONNECTION_STRING))
        LOG.warning(msg)

_init_version_control()
Base = declarative_base(bind=_ENGINE)
Session = scoped_session(sessionmaker(_ENGINE))


class TextPickleType(PickleType):
    """Type that can be set to dict and stored in the database as Text.
    This allows us to read and write the 'body' attribute as dicts"""
    impl = Text


class Environment(Base):
    __tablename__ = 'environments'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    locked = Column(Float, default=0)
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


class Deployment(Base):
    __tablename__ = 'deployments'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    locked = Column(Float, default=0)
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


class Blueprint(Base):
    __tablename__ = 'blueprints'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    locked = Column(Float, default=0)
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


class Component(Base):
    __tablename__ = 'components'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    locked = Column(Float, default=0)
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


class Workflow(Base):
    __tablename__ = 'workflows'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    locked = Column(Float, default=0)
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


Base.metadata.create_all(_ENGINE)


class Driver(DbBase):
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
        return self.get_object(Environment, id, with_secrets)

    def get_environments(self, tenant_id=None, with_secrets=None):
        return self.get_objects(Environment, tenant_id, with_secrets)

    def save_environment(self, id, body, secrets=None, tenant_id=None):
        return self.save_object(Environment, id, body, secrets, tenant_id)

    # DEPLOYMENTS
    def get_deployment(self, id, with_secrets=None):
        return self.get_object(Deployment, id, with_secrets)

    def get_deployments(self, tenant_id=None, with_secrets=None,
                        offset=None, limit=None):
        return self.get_objects(Deployment, tenant_id, with_secrets,
                                offset=offset, limit=limit)

    def save_deployment(self, id, body, secrets=None, tenant_id=None):
        return self.save_object(Deployment, id, body, secrets, tenant_id)

    #BLUEPRINTS
    def get_blueprint(self, id, with_secrets=None):
        return self.get_object(Blueprint, id, with_secrets)

    def get_blueprints(self, tenant_id=None, with_secrets=None):
        return self.get_objects(Blueprint, tenant_id, with_secrets)

    def save_blueprint(self, id, body, secrets=None, tenant_id=None):
        return self.save_object(Blueprint, id, body, secrets, tenant_id)

    # COMPONENTS
    def get_component(self, id, with_secrets=None):
        return self.get_object(Component, id, with_secrets)

    def get_components(self, tenant_id=None, with_secrets=None):
        return self.get_objects(Component, tenant_id, with_secrets)

    def save_component(self, id, body, secrets=None, tenant_id=None):
        return self.save_object(Component, id, body, secrets, tenant_id)

    # WORKFLOWS
    def get_workflow(self, id, with_secrets=None):
        return self.get_object(Workflow, id, with_secrets)

    def get_workflows(self, tenant_id=None, with_secrets=None,
                      offset=None, limit=None):
        return self.get_objects(Workflow, tenant_id, with_secrets,
                                offset=offset, limit=limit)

    def save_workflow(self, id, body, secrets=None, tenant_id=None):
        return self.save_object(Workflow, id, body, secrets, tenant_id)

    # GENERIC
    def get_object(self, klass, id, with_secrets=None):
        results = Session.query(klass).filter_by(id=id)
        if results and results.count() > 0:
            first = results.first()
            body = first.body
            if "tenantId" in body:
                first.tenant_id = body["tenantId"]
            elif first.tenant_id:
                body['tenantId'] = first.tenant_id
            if with_secrets == True:
                if first.secrets:
                    return merge_dictionary(body, first.secrets)
                else:
                    return body
            else:
                return body

    def get_objects(self, klass, tenant_id=None, with_secrets=None,
                    offset=None, limit=None):
        results = Session.query(klass)
        if tenant_id:
            results = results.filter_by(tenant_id=tenant_id)
        if results and results.count() > 0:
            response = {}
            if offset and (limit is None):
                results = results.offset(offest).all()
            if limit:
                if offset is None:
                    offset = 0
                results = results.limit(limit).offset(offset).all()
            if with_secrets == True:
                for e in results:
                    if e.secrets:
                        response[e.id] = utils.merge_dictionary(e.body,
                                e.secrets)
                    else:
                        response[e.id] = e.body
                    response[e.id]['tenantId'] = e.tenant_id
            else:
                for e in results:
                    response[e.id] = e.body
                    response[e.id]['tenantId'] = e.tenant_id
            return response
        else:
            return {}

    def save_object(self, klass, id, body, secrets=None, tenant_id=None):
        """Clients that wish to save the body but do/did not have access to
        secrets will by default send in None for secrets. We must not have that
        overwrite the secrets. To clear the secrets for an object, a non-None
        dict needs to be passed in: ex. {}
        """
        if isinstance(body, ExtensibleDict):
            body = body.__dict__()
        assert isinstance(body, dict), "dict required by sqlalchemy backend"

        #object locking logic
        results = None
        tries = 0
        lock_timestamp = time.time() 
        while tries < DEFAULT_RETRIES:
            #try to get the lock
            updated = Session.query(klass).filter_by(
                id=id, 
                locked=0
            ).update({'locked': lock_timestamp})
            Session.commit()

            if updated > 0:
                #get the object that we just locked
                results = Session.query(klass).filter_by(id=id, 
                    locked=lock_timestamp)
                assert results.count() > 0, ("There was a fatal error. The"
                    "object %s with id %s could not be locked!") % (klass, id)
                break
            else:
                existing_object = Session.query(klass).filter_by(id=id).first()
                if not existing_object:
                    #this is a new object
                    break

                elif (lock_timestamp - existing_object.locked) >= \
                    DEFAULT_STALE_LOCK_TIMEOUT:

                    #the lock is stale, remove it
                    stale_lock_object = \
                        Session.query(klass).filter_by(
                            id=id, 
                            locked=existing_object.locked
                        ).update({'locked' : lock_timestamp})
                    Session.commit()

                    results = Session.query(klass).filter_by(id=id)

                    if stale_lock_object:
                        print "stale break"
                        #updated the stale lock
                        break

                if (tries + 1) == DEFAULT_TIMEOUT:
                    raise DatabaseTimeoutException("Attempted to query the "
                "   database the maximum amount of retries.")
                time.sleep(DEFAULT_TIMEOUT)
                tries += 1

        if results and results.count() > 0:
            e = results.first()
            e.locked = 0
            
            #merge the results
            saved_body = deepcopy(e.body)
            collate(saved_body, body)
            e.body = saved_body

            if tenant_id:
                e.tenant_id = tenant_id
            elif "tenantId" in body:
                e.tenant_id = body.get("tenantId")

            assert tenant_id or e.tenant_id, "tenantId must be specified"                

            if secrets is not None:
                if not secrets:
                    LOG.warning("Clearing secrets for %s:%s" % (klass.__name__,
                            id))
                    # TODO: to catch bugs. We can remove when we're comfortable
                    raise Exception("CLEARING CREDS! Why?!!!!")
                else:
                    if not e.secrets:
                        e.secrets = {}
                    new_secrets = deepcopy(e.secrets)
                    collate(new_secrets, secrets, extend_lists=False)
                    e.secrets = new_secrets
        else:
            assert tenant_id or 'tenantId' in body, \
                "tenantId must be specified"
            #new item
            e = klass(id=id, body=body, tenant_id=tenant_id,
                    secrets=secrets, locked=0)

        Session.add(e)
        Session.commit()
        return body

def merge(old, new):
   collate(new_secrets, secrets, extend_lists=False)
   return new_secrets
   