# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Common Exceptions and functions for database drivers."""

import logging
import os

from checkmate.db.base import DbBase as dbBaseClass
from checkmate import utils

DEFAULT_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data')
ACTUAL_DATA_PATH = os.path.join(os.environ.get('CHECKMATE_DATA_PATH',
                                               DEFAULT_DATA_PATH))
DbBase = dbBaseClass

LOG = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 1
DEFAULT_RETRIES = 5
# amount of time before a lock can be force deleted
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

    """Timeout or Retry value exceeded while trying to access the database."""


class ObjectLockedError(Exception):

    """Trying to access a database resource with an invalid key."""


class InvalidKeyError(Exception):

    """Specified key is invalid."""


def get_driver(name=None, reset=False, connection_string=None, api_id=None):
    """Get Shared Driver Instance.

    :param name: the class of the driver to load
    :param reset: whether to reset the driver before returning it
    :param connection_string: the URI connection string (ex. sqlite:// or
                              mongodb://localhost)

    Asking for a driver by name only will use the connection string defined in
    the environment (or a localhost, in-memory default)

    Resetting will reconnect the database (for in-momory databases this could
    also reset all data)
    """
    if api_id and utils.is_simulation(api_id) and \
            (connection_string is None and name is None):
        connection_string = os.environ.get(
            'CHECKMATE_SIMULATOR_CONNECTION_STRING')

    if not connection_string:
        environ_conn_string = os.environ.get('CHECKMATE_CONNECTION_STRING')
        if environ_conn_string:
            connection_string = environ_conn_string
        elif name:
            connection_string = DRIVERS_AVAILABLE[name][
                'default_connection_string']
        else:
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


def get_lock_db_driver():
    """Get the driver for connecting to the lock db."""
    return get_driver(connection_string=os.environ.get(
        'CHECKMATE_LOCK_CONNECTION_STRING'))


def any_id_problems(api_id):
    """Validate the ID provided is safe and returns problems as a string.

    To use this, call it with an ID you want to validate. If the response is
    None, then the ID is good. Otherwise, the response is a string explaining
    the problem with the ID that you can use to return to the client
    """
    allowed_start_chars = "abcdefghijklmnopqrstuvwxyz"\
                          "ABCDEFGHIJKLMNOPQRSTUVWXYZ"\
                          "0123456789"
    allowed_chars = allowed_start_chars + "-_.+~@"
    if not api_id:
        return 'ID cannot be blank'
    if not isinstance(api_id, basestring):
        return "ID must be a string, not an %s" % type(api_id).__name__
    if not (1 <= len(api_id) <= 32):
        return "ID must be 1 to 32 characters"
    if api_id[0] not in allowed_start_chars:
        return ("Invalid start character '%s'. ID can start with any of '%s'" %
                (api_id[0], allowed_start_chars))
    for char in api_id:
        if char not in allowed_chars:
            return ("Invalid character '%s'. Allowed characters are '%s'" %
                    (char, allowed_chars))
    return None


def any_tenant_id_problems(api_id):
    """Validate the tenant provided is safe and returns problems as a string.

    To use this, call it with a tenant ID you want to validate. If the response
    is None, then the ID is good. Otherwise, the response is a string
    explaining the problem with the ID that you can use to return to the
    client
    """
    allowed_start_chars = "abcdefghijklmnopqrstuvwxyz"\
                          "ABCDEFGHIJKLMNOPQRSTUVWXYZ"\
                          "0123456789"
    allowed_chars = allowed_start_chars + "-_.+~@()[]*&^=%$#!<>"
    if not api_id:
        return 'Tenant ID cannot be blank'
    if not isinstance(api_id, basestring):
        api_id = str(api_id)
    if not (1 <= len(api_id) <= 255):
        return "Tenant ID must be 1 to 255 characters"
    if api_id[0] not in allowed_start_chars:
        return ("Invalid start character '%s'. Tenant ID can start with any "
                "of '%s'" % (api_id[0], allowed_start_chars))
    for char in api_id:
        if char not in allowed_chars:
            return ("Invalid character '%s' in Tenant ID. Allowed charaters "
                    "are '%s'" % (char, allowed_chars))
    return None
