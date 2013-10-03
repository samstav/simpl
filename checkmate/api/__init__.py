'''
REST API for Checkmate server
'''
import os
import logging

# pylint: disable=W0611,W0402
import bottle

import checkmate
from checkmate import environments  # loads /providers too
from checkmate import workflows
from checkmate import utils

LOG = logging.getLogger(__name__)

__version_string__ = None


#
# Status and System Information
#
@bottle.get('/version')
def get_api_version():
    """ Return api version information """
    accept = bottle.request.get_header('Accept', ['application/json'])
    if 'application/vnd.sun.wadl+xml' in accept:
        return bottle.static_file('application.wadl',
                                  root=os.path.dirname(__file__),
                                  mimetype='application/vnd.sun.wadl+xml')

    global __version_string__
    if not __version_string__:
        __version_string__ = checkmate.version()
    LOG.debug('GET /version called and reported version %s',
              __version_string__)
    results = {
        "version": __version_string__,
        "wadl": "./version.wadl",
    }
    return utils.write_body(results, bottle.request, bottle.response)
