import logging
import os

from checkmate import utils

DEFAULT_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data')
ACTUAL_DATA_PATH = os.path.join(os.environ.get('CHECKMATE_DATA_PATH',
                                          DEFAULT_DATA_PATH))
from checkmate.db.base import DbBase as dbBaseClass
DbBase = dbBaseClass

LOG = logging.getLogger(__name__)
DB = None


def any_id_problems(id):
    """Validates the ID provided is safe and returns problems as a string.

    To use this, call it with an ID you want to validate. If the response is
    None, then the ID is good. Otherwise, the response is a string explaining
    the problem with the ID that you can use to return to the client"""
    allowed_start_chars = "abcdefghijklmnopqrstuvwxyz"\
                          "ABCDEFGHIJKLMNOPQRSTUVWXYZ"\
                          "0123456789"
    allowed_chars = allowed_start_chars + "-_.+~@"
    if id is None:
        return 'ID cannot be blank'
    if not isinstance(id, basestring):
        id = str(id)
    if 1 > len(id) > 32:
        return "ID must be 1 to 32 characters"
    if id[0] not in allowed_start_chars:
        return "Invalid start character '%s'. ID can start with any of '%s'" \
                % (id[0], allowed_start_chars)
    for c in id:
        if c not in allowed_chars:
            return "Invalid character '%s'. Allowed charaters are '%s'" % (c,
                                                                allowed_chars)
    return None


def get_driver(name=None, reset=False):
    global DB
    if reset: #Forces a hard reset of global variable
        DB = None
    print "DB: %s" % DB
    print "name: %s" % name
    if DB is None:
        if not name:
            print "conn_string in common: %s" % os.environ.get('CHECKMATE_CONNECTION_STRING')
            connection_string = os.environ.get('CHECKMATE_CONNECTION_STRING',
                    'sqlite://')
            if connection_string.startswith('mongodb://'):
                name = 'checkmate.db.mongodb.Driver'
            else:
                name = 'checkmate.db.sql.Driver'
        LOG.debug("Initializing database engine: %s" % name)
        driver = utils.import_class(name)
        DB = driver()
    return DB


def any_tenant_id_problems(id):
    """Validates the tenant provided is safe and returns problems as a string.

    To use this, call it with a tenant ID you want to validate. If the response
    is None, then the ID is good. Otherwise, the response is a string
    explaining the problem with the ID that you can use to return to the
    client"""
    allowed_start_chars = "abcdefghijklmnopqrstuvwxyz"\
                          "ABCDEFGHIJKLMNOPQRSTUVWXYZ"\
                          "0123456789"
    allowed_chars = allowed_start_chars + "-_.+~@()[]*&^=%$#!<>"
    if id is None:
        return 'Tenant ID cannot be blank'
    if not isinstance(id, basestring):
        id = str(id)
    if 0 > len(id) > 255:
        return "Tenant ID must be 1 to 255 characters"
    if id[0] not in allowed_start_chars:
        return "Invalid start character '%s'. Tenant ID can start with any "\
                "of '%s'" % (id[0], allowed_start_chars)
    for c in id:
        if c not in allowed_chars:
            return "Invalid character '%s' in Tenant ID. Allowed charaters "\
                    "are '%s'" % (c, allowed_chars)
    return None
