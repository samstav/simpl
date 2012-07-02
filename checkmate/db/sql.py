import json
import logging
import os

from sqlalchemy import Column, Integer, String, Text, PickleType
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

try:
    # pylint: disable=E0611
    from migrate.versioning import exceptions as versioning_exceptions
except ImportError:
    from migrate import exceptions as versioning_exceptions

from checkmate.db import migration
from checkmate.db.common import *
from checkmate.exceptions import CheckmateDatabaseMigrationError
from checkmate.utils import merge_dictionary


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
    repo_path = migration.get_migrate_repo_path()

    try:
        repo_version = migration.get_repo_version(repo_path)
        db_version = migration.get_db_version(_ENGINE, repo_path)

        if repo_version != db_version:
            msg = ("Database (%s) is not up to date (current=%s, "
                "latest=%s); run `repository/manage.py upgrade "
                "'sqlite:///../../data/db.sqlite' repository` or '"
                "override your migrate version manually (see docs)" %
                (CONNECTION_STRING, db_version, repo_version))
            LOG.warning(msg)
            raise CheckmateDatabaseMigrationError(msg)
    except versioning_exceptions.DatabaseNotControlledError:
        msg = ("Database (%s) is not version controlled; "
                "run `repository/manage.py version_control "
                "'sqlite:///../../data/db.sqlite' repository` or "
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
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


class Deployment(Base):
    __tablename__ = 'deployments'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


class Blueprint(Base):
    __tablename__ = 'blueprints'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


class Component(Base):
    __tablename__ = 'components'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    tenant_id = Column(String(255), index=True)
    secrets = Column(TextPickleType(pickler=json))
    body = Column(TextPickleType(pickler=json))


class Workflow(Base):
    __tablename__ = 'workflows'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
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

    def get_deployments(self, tenant_id=None, with_secrets=None):
        return self.get_objects(Deployment, tenant_id, with_secrets)

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

    def get_workflows(self, tenant_id=None, with_secrets=None):
        return self.get_objects(Workflow, tenant_id, with_secrets)

    def save_workflow(self, id, body, secrets=None, tenant_id=None):
        return self.save_object(Workflow, id, body, secrets, tenant_id)

    # GENERIC
    def get_object(self, klass, id, with_secrets=None):
        results = Session.query(klass).filter_by(id=id)
        if results and results.count() > 0:
            if with_secrets == True:
                first = results.first()
                if first.secrets:
                    return merge_dictionary(first.body, first.secrets)
                else:
                    return first.body
            else:
                return results.first().body

    def get_objects(self, klass, tenant_id=None, with_secrets=None):
        results = Session.query(klass)
        if tenant_id:
            results = results.filter_by(tenant_id=tenant_id)
        if results and results.count() > 0:
            response = {}
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
        assert isinstance(body, dict)  # Make sure we passed in a dict
        results = Session.query(klass).filter_by(id=id)
        if results and results.count() > 0:
            e = results.first()
            e.body = body
            if tenant_id:
                e.tenant_id = tenant_id
            if secrets is not None:
                if not secrets:
                    LOG.warning("Clearing secrets for %s:%s" % (klass.__name__,
                            id))
                    raise Exception("CLEARING CREDS! Why?!!!!")
                e.secrets = secrets
        else:
            e = klass(id=id, body=body, tenant_id=tenant_id,
                    secrets=secrets)
        Session.add(e)
        Session.commit()
        return body
