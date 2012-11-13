import logging
import os

from checkmate import utils

DEFAULT_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data')
ACTUAL_DATA_PATH = os.path.join(os.environ.get('ROOK_DATA_PATH',
                                          os.environ.get('CHECKMATE_DATA_PATH',
                                          DEFAULT_DATA_PATH)))
from rook.db.base import DbBase as dbBaseClass
DbBase = dbBaseClass

LOG = logging.getLogger(__name__)
DB = None


def get_driver(name=None, reset=False):
    global DB
    if reset: #Forces a hard reset of global variable
        DB = None
    if DB is None:
        if not name:
            connection_string = os.environ.get('ROOK_CONNECTION_STRING',
                    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://'))
            if connection_string.startswith('mongodb://'):
                name = 'rook.db.mongodb.Driver'
            else:
                name = 'rook.db.sql.Driver'
        LOG.debug("Initializing database engine: %s" % name)
        driver = utils.import_class(name)
        DB = driver()
    return DB

