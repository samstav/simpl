"""Database drivers only used by the UI middleware. This will be moved out with
the UI component

"""
import json
import logging
import os

LOG = logging.getLogger(__name__)

try:
    import pymongo

    from sqlalchemy import Column, Integer, String, Text, PickleType
    from sqlalchemy.ext.declarative import declarative_base
    from sqlalchemy.pool import StaticPool
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker, scoped_session
except Exception as exc:
    LOG.exception(exc)

from rook.db.common import *
from rook.exceptions import RookDatabaseConnectionError
from checkmate.utils import merge_dictionary

__all__ = ['Base', 'Feedback']


CONNECTION_STRING = os.environ.get('ROOK_CONNECTION_STRING', os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://'))
_ENGINE = None
if CONNECTION_STRING == 'sqlite://':
    _ENGINE = create_engine(CONNECTION_STRING,
                connect_args={'check_same_thread': False},
                poolclass=StaticPool)
    message = ("The feedback driver is connected to an in-memory sqlite "
               "database. No feedback data will be persisted. To store your "
               "data, set the ROOK_CONNECTION_STRING environment "
               "variable to a valid sqlalchemy connection string")
    LOG.warning(message)
elif CONNECTION_STRING.startswith('sqlite'):
    _ENGINE = create_engine(CONNECTION_STRING)
    LOG.info("Connected to '%s'" % CONNECTION_STRING)


class MongoDriver(DbBase):
    """MongoDB Database Driver for Feedback Collection"""
    _connection = None

    def __init__(self, *args, **kwargs):
        """Initializes globals for this driver"""
        DbBase.__init__(self, *args, **kwargs)
        self.connection_string = os.environ.get('ROOK_CONNECTION_STRING',
                                                os.environ.get('CHECKMATE_CONNECTION_STRING',
                                                'mongodb://localhost'))
        # Temp hack for production
        parts = self.connection_string.split('/')
        if parts[-1] == 'checkmate':
            parts[-1] = "feedback"
        self.connection_string = '/'.join(parts)
        LOG.debug("Feedback connecting to: %s" % self.connection_string)

        self.db_name = 'feedback'
        self._database = None

    def database(self):
        """Connects to and returns mongodb database object"""
        if self._database is None:
            if self._connection is None:
                try:
                    self._connection = pymongo.Connection(
                            self.connection_string)
                except pymongo.errors.AutoReconnect as exc:
                    raise RookDatabaseConnectionError(exc.__str__())

            self._database = self._connection[self.db_name]
            LOG.info("Connected to mongodb on %s (database=%s)" %
                     (self.connection_string, self.db_name))
        return self._database

    def save_feedback(self, body):
        """Stores feedback provided from UI"""
        assert isinstance(body, dict), "dict required by backend"
        self.database()['feedback'].insert(body)
        body['id'] = str(body['_id'])
        del body['_id']
        return body


if _ENGINE:
    Base = declarative_base(bind=_ENGINE)
    Session = scoped_session(sessionmaker(_ENGINE))
else:
    Base = object

class TextPickleType(PickleType):
    """Type that can be set to dict and stored in the database as Text.
    This allows us to read and write the 'body' attribute as dicts"""
    impl = Text


class Feedback(Base):
    __tablename__ = 'feedback'
    dbid = Column(Integer, primary_key=True, autoincrement=True)
    body = Column(TextPickleType(pickler=json))


if _ENGINE:
    Base.metadata.create_all(_ENGINE)


class SqlDriver(DbBase):
    def save_feedback(self, body):
        """Stores client feedback from UI"""
        assert isinstance(body, dict), "dict required by sqlalchemy backend"
        e = Feedback(body=body)
        Session.add(e)
        Session.commit()
        return body
