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
            raise Exception(msg)
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
    def get_environment(self, id):
        results = Session.query(Environment).filter_by(id=id)
        if results and results.count() > 0:
            return results.first().body

    def get_environments(self):
        results = Session.query(Environment)
        if results and results.count() > 0:
            response = {}
            for e in results:
                response[e.id] = e.body
            return response
        else:
            return {}

    def save_environment(self, id, body, secrets=None, tenant_id=None):
        results = Session.query(Environment).filter_by(id=id)
        if results and results.count() > 0:
            e = results.first()
            e.body = body
            e.tenant_id = e.tenant_id
            e.secrets = secrets
        else:
            e = Environment(id=id, body=body, tenant_id=tenant_id,
                    secrets=secrets)
        Session.add(e)
        Session.commit()
        return body

    # DEPLOYMENTS
    def get_deployment(self, id):
        results = Session.query(Deployment).filter_by(id=id)
        if results and results.count() > 0:
            return results.first().body

    def get_deployments(self):
        results = Session.query(Deployment)
        if results and results.count() > 0:
            response = {}
            for e in results:
                response[e.id] = e.body
            return response
        else:
            return {}

    def save_deployment(self, id, body, secrets=None, tenant_id=None):
        results = Session.query(Deployment).filter_by(id=id)
        if results and results.count() > 0:
            e = results.first()
            e.body = body
            e.tenant_id = e.tenant_id
            e.secrets = secrets
        else:
            e = Deployment(id=id, body=body, tenant_id=tenant_id,
                    secrets=secrets)
        Session.add(e)
        Session.commit()
        return body

    #BLUEPRINTS
    def get_blueprint(self, id):
        results = Session.query(Blueprint).filter_by(id=id)
        if results and results.count() > 0:
            return results.first().body

    def get_blueprints(self):
        results = Session.query(Blueprint)
        if results and results.count() > 0:
            response = {}
            for e in results:
                response[e.id] = e.body
            return response
        else:
            return {}

    def save_blueprint(self, id, body, secrets=None, tenant_id=None):
        results = Session.query(Blueprint).filter_by(id=id)
        if results and results.count() > 0:
            e = results.first()
            e.body = body
            e.tenant_id = e.tenant_id
            e.secrets = secrets
        else:
            e = Blueprint(id=id, body=body, tenant_id=tenant_id,
                    secrets=secrets)
        Session.add(e)
        Session.commit()
        return body

    # COMPONENTS
    def get_component(self, id):
        results = Session.query(Component).filter_by(id=id)
        if results and results.count() > 0:
            return results.first().body

    def get_components(self):
        results = Session.query(Component)
        if results and results.count() > 0:
            response = {}
            for e in results:
                response[e.id] = e.body
            return response
        else:
            return {}

    def save_component(self, id, body, secrets=None, tenant_id=None):
        results = Session.query(Component).filter_by(id=id)
        if results and results.count() > 0:
            e = results.first()
            e.body = body
            e.tenant_id = e.tenant_id
            e.secrets = secrets
        else:
            e = Component(id=id, body=body, tenant_id=tenant_id,
                    secrets=secrets)
        Session.add(e)
        Session.commit()
        return e

    # WORKFLOWS
    def get_workflow(self, id):
        results = Session.query(Workflow).filter_by(id=id)
        if results and results.count() > 0:
            return results.first().body

    def get_workflows(self):
        results = Session.query(Workflow)
        if results and results.count() > 0:
            response = {}
            for e in results:
                response[e.id] = e.body
            return response
        else:
            return {}

    def save_workflow(self, id, body, secrets=None, tenant_id=None):
        assert isinstance(body, dict)  # Make sure we didn't pass in a workflow
        results = Session.query(Workflow).filter_by(id=id)
        if results and results.count() > 0:
            e = results.first()
            e.body = body
            e.tenant_id = e.tenant_id
            e.secrets = secrets
        else:
            e = Workflow(id=id, body=body, tenant_id=tenant_id,
                    secrets=secrets)
        Session.add(e)
        Session.commit()
        return body
