#!/usr/bin/env python
""" Module to initialize and run Checkmate server"""
import json
import os
import logging
import string
import sys

import checkmate.common.tracer  # @UnusedImport # module runs on import

# pylint: disable=E0611
from bottle import app, run, request, response, error, HeaderDict, \
    default_app, load


from checkmate.exceptions import CheckmateException, CheckmateNoMapping, \
    CheckmateValidationException, CheckmateNoData, CheckmateDoesNotExist, \
    CheckmateBadState, CheckmateDatabaseConnectionError
from checkmate import middleware
from checkmate.utils import STATIC, write_body

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
    return write_body(dict(error=output), request, response)


#if __name__ == '__main__':
def main_func():

    # Init logging before we load the database, 3rd party, and 'noisy' modules
    from checkmate.utils import init_logging
    init_logging(default_config="/etc/default/checkmate-svr-log.conf")

    # Register built-in providers
    from checkmate.providers import rackspace, opscode
    rackspace.register()
    opscode.register()

    # Load routes from other modules
    LOG.info("Loading API")
    load("checkmate.api")
    with_simulator = False
    if '--with-simulator' in sys.argv:
        load("checkmate.simulator")
        with_simulator = True

    # Build WSGI Chain:
    LOG.info("Loading Application")
    next_app = default_app()  # This is the main checkmate app
    next_app.error_handler = {500: error_formatter,
                              401: error_formatter,
                              404: error_formatter,
                              405: error_formatter,
                              406: error_formatter,
                              415: error_formatter,
                              }
    next_app.catchall = True
    next_app = middleware.AuthorizationMiddleware(next_app,
                                                  anonymous_paths=STATIC)
    #next = middleware.PAMAuthMiddleware(next, all_admins=True)
    endpoints = ['https://identity.api.rackspacecloud.com/v2.0/tokens',
                 'https://lon.identity.api.rackspacecloud.com/v2.0/tokens']
    next_app = (middleware.AuthTokenRouterMiddleware(next_app, endpoints,
                default='https://identity.api.rackspacecloud.com/v2.0/tokens',
                anonymous_paths=STATIC))
    """
    if '--with-ui' in sys.argv:
        # With a UI, we use basic auth and route that to cloud auth.
        domains = {
                'UK': {
                        'protocol': 'keystone',
                        'endpoint':
                                'https://lon.identity.api.rackspacecloud.com/'
                                'v2.0/tokens',
                    },
                'US': {
                        'protocol': 'keystone',
                        'endpoint': 'https://identity.api.rackspacecloud.com/'
                        'v2.0/tokens',
                    },
            }
        next = middleware.BasicAuthMultiCloudMiddleware(next, domains=domains)
    """
    if '--with-ui' in sys.argv:
        try:
            from rook.middleware import BrowserMiddleware
            next_app = BrowserMiddleware(next_app, proxy_endpoints=endpoints,
                                         with_simulator=with_simulator)
        except ImportError as exc:
            LOG.exception(exc)
            LOG.warning("Not loading UI middleware. Make sure rook is "
                        "installed.")
    next_app = middleware.TenantMiddleware(next_app)
    next_app = middleware.ContextMiddleware(next_app)
    next_app = middleware.StripPathMiddleware(next_app)
    next_app = middleware.ExtensionsMiddleware(next_app)
    #next_app = middleware.CatchAll404(next_app)
    if '--newrelic' in sys.argv:
        import newrelic.agent
        newrelic.agent.initialize(os.path.normpath(os.path.join(
                                  os.path.dirname(__file__), os.path.pardir,
                                  'newrelic.ini')))  # optional param
        next_app = newrelic.agent.wsgi_application()(next_app)
    if '--debug' in sys.argv:
        next_app = middleware.DebugMiddleware(next_app)
        LOG.debug("Routes: %s" % ['%s %s' % (r.method, r.rule) for r in
                                  app().routes])

    # Pick up IP/port from last param
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
    server = 'wsgiref'
    if '--eventlet' in sys.argv:
        server = 'eventlet'
    run(app=next_app, host=ip, port=port, reloader=True, server=server)


#
# Main function
#
if __name__ == '__main__':
    main_func()
