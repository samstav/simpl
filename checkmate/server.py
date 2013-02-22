#!/usr/bin/env python
""" Module to initialize and run Checkmate server"""
import os
import json
import logging
import string
import sys

import checkmate.common.tracer  # @UnusedImport # module runs on import

# pylint: disable=E0611
from bottle import app, run, request, response, HeaderDict, default_app, load


from checkmate.exceptions import (CheckmateException,
                                  CheckmateNoMapping,
                                  CheckmateValidationException,
                                  CheckmateNoData,
                                  CheckmateDoesNotExist,
                                  CheckmateBadState,
                                  CheckmateDatabaseConnectionError,
                                  )
from checkmate import middleware
from checkmate import utils

LOG = logging.getLogger(__name__)

# Check our configuration
from celery import current_app
try:
    if current_app.backend.__class__.__name__ not in ['DatabaseBackend',
                                                      'MongoBackend']:
        LOG.warning("Celery backend does not seem to be configured for a "
                    "database: %s" % current_app.backend.__class__.__name__)
    if not current_app.conf.get("CELERY_RESULT_DBURI"):
        LOG.warning("ATTENTION!! CELERY_RESULT_DBURI not set.  Was the "
                    "checkmate environment loaded?")
except:
    pass


DEFAULT_AUTH_ENDPOINTS = [{
                    'middleware': 'checkmate.middleware.TokenAuthMiddleware',
                    'default': True,
                    'uri': 'https://identity.api.rackspacecloud.com/v2.0/tokens',
                    'kwargs': {
                            'protocol': 'Keystone',
                            'realm': 'US Cloud',
                        },
                }, {
                    'middleware': 'checkmate.middleware.TokenAuthMiddleware',
                    'uri': 'https://lon.identity.api.rackspacecloud.com/v2.0/tokens',
                    'kwargs': {
                            'protocol': 'Keystone',
                            'realm': 'UK Cloud',
                        },
                }]


def error_formatter(error):
    """Catch errors and output them in the correct format/media-type"""
    output = {}
    accept = request.get_header("Accept")
    if "application/json" in accept:
        error.headers = HeaderDict({"content-type": "application/json"})
        error.apply(response)
    elif "application/x-yaml" in accept:
        error.headers = HeaderDict({"content-type": "application/x-yaml"})
        error.apply(response)

    if isinstance(error.exception, CheckmateNoMapping):
        error.status = 406
        error.output = error.exception.__str__()
    elif isinstance(error.exception, CheckmateDoesNotExist):
        error.status = 404
        error.output = error.exception.__str__()
    elif isinstance(error.exception, CheckmateValidationException):
        error.status = 400
        error.output = error.exception.__str__()
    elif isinstance(error.exception, CheckmateNoData):
        error.status = 400
        error.output = error.exception.__str__()
    elif isinstance(error.exception, CheckmateBadState):
        error.status = 409
        error.output = error.exception.__str__()
    elif isinstance(error.exception, CheckmateDatabaseConnectionError):
        error.status = 500
        error.output = "Database connection error on server."
        output['reason'] = error.exception.__str__()
    elif isinstance(error.exception, CheckmateException):
        error.output = error.exception.__str__()
    elif isinstance(error.exception, AssertionError):
        error.status = 400
        error.output = error.exception.__str__()
    else:
        # For other 500's, provide underlying cause
        if error.exception:
            output['reason'] = error.exception.__str__()

    output['description'] = error.output
    output['code'] = error.status
    response.status = error.status
    return utils.write_body(dict(error=output), request, response)

def list_filter(config):
    ''' Bottle custom filter that matches a comma 
        separated list of numbers. '''
    delimiter = config or ','
    regexp = r'\d+(%s\d)*' % re.escape(delimiter)

    def to_python(match):
        return map(int, match.split(delimiter))

    def to_url(numbers):
        return delimiter.join(map(str, numbers))

    return regexp, to_python, to_url    

def main_func():
    """ Start the server based on passed in arguments. Called by __main__ """

    # Init logging before we load the database, 3rd party, and 'noisy' modules
    utils.init_logging(default_config="/etc/default/checkmate-svr-log.conf")

    # Register built-in providers
    from checkmate.providers import rackspace, opscode
    rackspace.register()
    opscode.register()

    # Load routes from other modules
    LOG.info("Loading API")
    load("checkmate.api")

    # Load simulator if requested
    with_simulator = False
    if '--with-simulator' in sys.argv:
        load("checkmate.simulator")
        with_simulator = True

    # Load admin routes if requested
    with_admin = False
    if '--with-admin' in sys.argv:
        load("checkmate.admin")
        with_admin = True

    # Build WSGI Chain:
    LOG.info("Loading Application")
    next_app = default_app()  # This is the main checkmate app

    next_app.router.add_filter('list', list_filter) #registers custom filter

    next_app.error_handler = {500: error_formatter,
                              401: error_formatter,
                              404: error_formatter,
                              405: error_formatter,
                              406: error_formatter,
                              415: error_formatter,
                              }
    next_app.catchall = True
    next_app = middleware.AuthorizationMiddleware(next_app,
                                                  anonymous_paths=utils.STATIC)
    endpoints = os.environ.get('CHECKMATE_AUTH_ENDPOINTS')
    if endpoints:
        endpoints = json.loads(endpoints)
    else:
        endpoints = DEFAULT_AUTH_ENDPOINTS
    next_app = middleware.AuthTokenRouterMiddleware(next_app, endpoints,
                                                    anonymous_paths=utils.\
                                                            STATIC)

    # Load Rook if requested
    if '--with-ui' in sys.argv:
        try:
            from rook.middleware import BrowserMiddleware
            next_app = BrowserMiddleware(next_app, proxy_endpoints=endpoints,
                                         with_simulator=with_simulator,
                                         with_admin=with_admin)
        except ImportError as exc:
            LOG.exception(exc)
            LOG.warning("Unable to load UI middleware. Make sure rook is "
                        "installed.")
    next_app = middleware.TenantMiddleware(next_app)
    next_app = middleware.ContextMiddleware(next_app)
    next_app = middleware.StripPathMiddleware(next_app)
    next_app = middleware.ExtensionsMiddleware(next_app)

    # Load NewRelic inspection if requested
    if '--newrelic' in sys.argv:
        import newrelic.agent
        newrelic.agent.initialize(os.path.normpath(os.path.join(
                                  os.path.dirname(__file__), os.path.pardir,
                                  'newrelic.ini')))  # optional param
        next_app = newrelic.agent.wsgi_application()(next_app)

    # Load request/response dumping if debugging enabled
    if '--debug' in sys.argv:
        next_app = middleware.DebugMiddleware(next_app)
        LOG.debug("Routes: %s" % ['%s %s' % (r.method, r.rule) for r in
                                  app().routes])

    # Pick up IP/port from last param (default is 127.0.0.1:8080)
    ip = '127.0.0.1'
    port = 8080
    if len(sys.argv) > 0:
        supplied = sys.argv[-1]
        if len([c for c in supplied if c in '%s:.' % string.digits]) == \
                len(supplied):
            if ':' in supplied:
                ip, port = supplied.split(':')
            else:
                ip = supplied

    # Select server (wsgiref by default. eventlet if requested)
    server = 'wsgiref'
    if '--eventlet' in sys.argv:
        server = 'eventlet'

    # Start listening. Enable reload by default to pick up file changes
    run(app=next_app, host=ip, port=port, reloader=True, server=server)


#
# Main function
#
if __name__ == '__main__':
    main_func()
