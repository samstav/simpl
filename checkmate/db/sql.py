import json
import os

from sqlalchemy import Column, Integer, String, Text, PickleType
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from checkmate.db.common import *

#__all__ = ['Base', 'Environment']
 
CONNECTION_STRING = os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')
if CONNECTION_STRING == 'sqlite://':
    engine = create_engine(CONNECTION_STRING, echo=True,
                connect_args={'check_same_thread': False},
                poolclass=StaticPool)
else:
    engine = create_engine(CONNECTION_STRING, echo=True)

Base = declarative_base(bind=engine)
Session = scoped_session(sessionmaker(engine))


class TextPickleType(PickleType):
    """Type that can be set to dict and stored as Text"""
    impl = Text


class Environment(Base):
    __tablename__ = 'environments'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    body = Column(TextPickleType(pickler=json))


class Deployment(Base):
    __tablename__ = 'deployments'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    id = Column(String(32), index=True, unique=True)
    body = Column(TextPickleType(pickler=json))


Base.metadata.create_all(engine)

class Driver(DbBase):
    def dump(self):
        response = {}
        response['environments'] = self.get_environments()
        response['deployments'] = self.get_deployments()
        return response

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

    def save_environment(self, id, body):
        results = Session.query(Environment).filter_by(id=id)
        if results and results.count() > 0:
            e = results.first()
            e.body = body
        else:
            e = Environment(id=id, body=body)
        Session.add(e)
        Session.commit()
        return body


    def get_deployment(self, id):
        results = Session.query(Deployment).filter_by(id=id)
        print dir(results)
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

    def save_deployment(self, id, body):
        results = Session.query(Deployment).filter_by(id=id)
        if results and results.count() > 0:
            e = results.first()
            e.body = body
        else:
            e = Deployment(id=id, body=body)
        Session.add(e)
        Session.commit()
        return body
