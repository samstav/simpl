'''
REST API for Checkmate server
'''
import logging

# pylint: disable=W0611,W0402
from bottle import get, request, response

import checkmate
from checkmate import environments  # loads /providers too
from checkmate import workflows
from checkmate import utils

LOG = logging.getLogger(__name__)

__version_string__ = None


#
# Status and System Information
#
@get('/version')
def get_api_version():
    """ Return api version information """
    global __version_string__
    if not __version_string__:
        __version_string__ = checkmate.version()
    LOG.debug('GET /version called and reported version %s',
              __version_string__)
    return utils.write_body({"version": __version_string__}, request, response)
