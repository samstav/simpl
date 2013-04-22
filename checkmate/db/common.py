import logging
import os

from checkmate import utils
from checkmate.exceptions import CheckmateException

DEFAULT_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data')
ACTUAL_DATA_PATH = os.path.join(os.environ.get('CHECKMATE_DATA_PATH',
                                               DEFAULT_DATA_PATH))

from checkmate.db.base import DbBase as dbBaseClass
DbBase = dbBaseClass

LOG = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 1
DEFAULT_RETRIES = 5
#amount of time before a lock can be force deleted
DEFAULT_STALE_LOCK_TIMEOUT = 10

DRIVER_INSTANCES = {}  # stored by connection string
DRIVERS_AVAILABLE = {
    'checkmate.db.sql.Driver': {
        'default_connection_string': 'sqlite://',
    },
    'checkmate.db.mongodb.Driver': {
        'default_connection_string': 'mongodb://localhost',
    },
}


class DatabaseTimeoutException(Exception):
    pass


class ObjectLockedError(Exception):
    pass


class InvalidKeyError(Exception):
    pass


def get_driver(name=None, reset=False, connection_string=None):
    '''Get Shared Driver Instance

    :param name: the class of the driver to load
    :param reset: whether to reset the driver before returning it
    :param connection_string: the URI connection string (ex. sqlite:// or
                              mongodb://localhost)

    Asking for a driver by name only will use the connection string defined in
    the environment (or a localhost, in-memory default)

    Resetting will reconnect the database (for in-momory databases this could
    also reset all data)
    '''
    if connection_string and not name:
        if connection_string.startswith('mongodb://'):
            name = 'checkmate.db.mongodb.Driver'
        else:
            name = 'checkmate.db.sql.Driver'

    if not connection_string:
        connection_string = os.environ.get('CHECKMATE_CONNECTION_STRING')
        if name and not connection_string:
            connection_string = DRIVERS_AVAILABLE[name][
                'default_connection_string']

    if not connection_string:
        connection_string = "sqlite://"

    if connection_string and not name:
        if connection_string.startswith('mongodb://'):
            name = 'checkmate.db.mongodb.Driver'
        else:
            name = 'checkmate.db.sql.Driver'

    if reset is False and connection_string in DRIVER_INSTANCES:
        driver = DRIVER_INSTANCES[connection_string]
    else:
        LOG.debug("Initializing database driver: %s", name)
        driver_class = utils.import_class(name)
        driver = driver_class(connection_string=connection_string)
        DRIVER_INSTANCES[connection_string] = driver

    return driver


def any_id_problems(api_id):
    """Validates the ID provided is safe and returns problems as a string.

    To use this, call it with an ID you want to validate. If the response is
    None, then the ID is good. Otherwise, the response is a string explaining
    the problem with the ID that you can use to return to the client"""
    allowed_start_chars = "abcdefghijklmnopqrstuvwxyz"\
                          "ABCDEFGHIJKLMNOPQRSTUVWXYZ"\
                          "0123456789"
    allowed_chars = allowed_start_chars + "-_.+~@"
    if api_id is None:
        return 'ID cannot be blank'
    if not isinstance(api_id, basestring):
        api_id = str(api_id)
    if 1 > len(api_id) > 32:
        return "ID must be 1 to 32 characters"
    if api_id[0] not in allowed_start_chars:
        return ("Invalid start character '%s'. ID can start with any of '%s'" %
                (api_id[0], allowed_start_chars))
    for char in api_id:
        if char not in allowed_chars:
            return ("Invalid character '%s'. Allowed charaters are '%s'" %
                    (char, allowed_chars))
    return None


def any_tenant_id_problems(api_id):
    """Validates the tenant provided is safe and returns problems as a string.

    To use this, call it with a tenant ID you want to validate. If the response
    is None, then the ID is good. Otherwise, the response is a string
    explaining the problem with the ID that you can use to return to the
    client"""
    allowed_start_chars = "abcdefghijklmnopqrstuvwxyz"\
                          "ABCDEFGHIJKLMNOPQRSTUVWXYZ"\
                          "0123456789"
    allowed_chars = allowed_start_chars + "-_.+~@()[]*&^=%$#!<>"
    if api_id is None:
        return 'Tenant ID cannot be blank'
    if not isinstance(api_id, basestring):
        api_id = str(api_id)
    if 0 > len(api_id) > 255:
        return "Tenant ID must be 1 to 255 characters"
    if api_id[0] not in allowed_start_chars:
        return ("Invalid start character '%s'. Tenant ID can start with any "
                "of '%s'" % (api_id[0], allowed_start_chars))
    for char in api_id:
        if char not in allowed_chars:
            return ("Invalid character '%s' in Tenant ID. Allowed charaters "
                    "are '%s'" % (char, allowed_chars))
    return None
