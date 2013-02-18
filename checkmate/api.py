""" Module to initialize the Checkmate REST API

REST API for Checkmate server

*****************************************************
*          This is still a VERY MESSY WIP           *
*****************************************************


Load these resources from their respective modules:
    /components:   juju charm-like definitions of services and components
    /environments: targets that can have resources deployed to them
    /blueprints:   *architect* definitions defining applications or solutions
    /deployments:  deployed resources (an instance of a blueprint deployed to
                   an environment)
    /workflows:    SpiffWorkflow workflows (persisted in database)

Special calls:
    POST /deployments/              This is where the meat of things gets done
                                    Triggers a celery task which can then be
                                    followed up on using deployments/:id/status
    GET  /deployments/:id/status    Check status of a deployment
    GET  /workflows/:id/status      Check status of a workflow
    GET  /workflows/:id/tasks/:id   Read a SpiffWorkflow Task
    POST /workflows/:id/tasks/:id   Partial update of a SpiffWorkflow Task
                                    Supports the following attributes: state,
                                    attributes, and internal_attributes
    GET  /workflows/:id/+execute    A browser-friendly way to run a workflow
    GET  /workflows/:id/tasks/:id/+reset   Reset a SpiffWorkflow Celery Task
    GET  /static/*                  Return files in /static folder
    PUT  /*/:id                     So you can edit/save objects without
                                    triggering actions (like a deployment).
                                    CAUTION: No locking or guarantees of
                                    atomicity across calls
Tools (added by this module):
    GET  /test/dump      Dumps the database
    POST /test/parse     Parses the body (use to test your yaml or json)
    POST /test/hack      Testing random stuff....
    GET  /test/async     Returns a streamed response (3 x 1 second intervals)

Notes:
    .yaml/.json extensions override Accept headers (except in /static/)
    Trailing slashes are ignored (ex. /blueprints/ == /blueprints)
"""
import logging

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
import checkmate
init_console_logging()
LOG = logging.getLogger(__name__)

from bottle import get, request, response

from checkmate.utils import write_body

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
    return write_body({"version": __version_string__}, request, response)
