#!/usr/bin/env python
""" Module to initialize and run Checkmate server"""
import json
import os
import logging
import string
import sys

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
# pylint: disable=E0611
from bottle import app, run, request, response, error, HeaderDict, \
        default_app, load

LOG = logging.getLogger(__name__)

from checkmate.exceptions import CheckmateException, CheckmateNoMapping
from checkmate import middleware
from checkmate.utils import STATIC


@error(code=500)
def custom_500(error):
    """Catch 500 errors that originate from a CheckmateExcption and output the
    Checkmate error information (more useful than a blind 500)"""
    accept = request.get_header("Accept")
    if "application/json" in accept:
        error.headers = HeaderDict({"content-type": "application/json"})
        error.apply(response)
    elif "application/x-yaml" in accept:
        error.headers = HeaderDict({"content-type": "application/x-yaml"})
        error.apply(response)
        #error.set_header = lambda s, h, v: LOG.debug(s)
    if isinstance(error.exception, CheckmateNoMapping):
        error.status = '406 Bad Request'
        error.output = error.exception.__str__()
    elif isinstance(error.exception, CheckmateException):
        error.status = '406 Bad Request'
        error.output = json.dumps(error.exception.__str__())

    return error.output #write_body(error, request, response)


#if __name__ == '__main__':
def main_func():
    # Load routes from other modules
    LOG.info("Loading API")
    load("checkmate.api")

    # Register built-in providers
    from checkmate.providers import rackspace, opscode

    # Build WSGI Chain:
    LOG.info("Loading Application")
    next_app = default_app()  # This is the main checkmate app
    app.error_handler = {500: custom_500}
    next_app.catch_all = True  # Handle errors ourselves so we can format them
    next_app = middleware.ExceptionMiddleware(next_app)
    next_app = middleware.AuthorizationMiddleware(next_app, anonymous_paths=STATIC)
    #next = middleware.PAMAuthMiddleware(next, all_admins=True)
    endpoints = ['https://identity.api.rackspacecloud.com/v2.0/tokens',
            'https://lon.identity.api.rackspacecloud.com/v2.0/tokens']
    next_app = middleware.AuthTokenRouterMiddleware(next_app, endpoints,
            default='https://identity.api.rackspacecloud.com/v2.0/tokens')
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
        next_app = middleware.BrowserMiddleware(next_app, proxy_endpoints=endpoints)
    next_app = middleware.TenantMiddleware(next_app)
    next_app = middleware.ContextMiddleware(next_app)
    next_app = middleware.StripPathMiddleware(next_app)
    next_app = middleware.ExtensionsMiddleware(next_app)
    next_app = middleware.CatchAll404(next_app)
    if '--newrelic' in sys.argv:
        import newrelic.agent
        newrelic.agent.initialize(os.path.normpath(os.path.join(
                os.path.dirname(__file__), os.path.pardir,
                'newrelic.ini')))  # optional param ->, 'staging')
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
