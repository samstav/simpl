#!/usr/bin/env python
''' Module to initialize and run Checkmate server'''
import argparse
import json
import logging
import os
import string
import sys
import threading

# pylint: disable=W0611
import checkmate.common.tracer  # module runs on import

# pylint: disable=E0611
import bottle
from bottle import (
    app,
    run,
    request,
    response,
    HeaderDict,
    default_app,
    load,
)
from celery import Celery
import eventlet

from checkmate import blueprints
from checkmate import celeryconfig
from checkmate import db
from checkmate import deployments
from checkmate import middleware
from checkmate import utils
from checkmate.api.admin import Router as AdminRouter
from checkmate.common import config
from checkmate.common.gzip_middleware import Gzipper
from checkmate.exceptions import (
    CheckmateException,
    CheckmateNoMapping,
    CheckmateValidationException,
    CheckmateNoData,
    CheckmateDoesNotExist,
    CheckmateBadState,
    CheckmateDatabaseConnectionError,
)

LOG = logging.getLogger(__name__)
DRIVERS = {}
MANAGERS = {}
ROUTERS = {}
CONFIG = config.current()


# Check our configuration
def check_celery_config():
    '''Make sure a backend is configured.'''
    from celery import current_app
    try:
        if current_app.backend.__class__.__name__ not in ['DatabaseBackend',
                                                          'MongoBackend']:
            LOG.warning("Celery backend does not seem to be configured for a "
                        "database: %s", current_app.backend.__class__.__name__)
        if not current_app.conf.get("CELERY_RESULT_DBURI"):
            LOG.warning("ATTENTION!! CELERY_RESULT_DBURI not set.  Was the "
                        "checkmate environment loaded?")
    except StandardError:
        pass


DEFAULT_AUTH_ENDPOINTS = [{
    'middleware': 'checkmate.middleware.TokenAuthMiddleware',
    'default': True,
    'uri': 'https://identity.api.rackspacecloud.com/v2.0/tokens',
    'kwargs': {
        'protocol': 'Keystone',
        'realm': 'US Cloud',
        'priority': '1',
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
    '''Catch errors and output them in the correct format/media-type.'''
    output = {}
    accept = request.get_header("Accept") or ""
    if "application/x-yaml" in accept:
        error.headers = HeaderDict({"content-type": "application/x-yaml"})
        error.apply(response)
    else:  # default to JSON
        error.headers = HeaderDict({"content-type": "application/json"})
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
        output['message'] = error.exception.__str__()
    elif isinstance(error.exception, CheckmateException):
        error.output = error.exception.__str__()
    elif isinstance(error.exception, AssertionError):
        error.status = 400
        error.output = error.exception.__str__()
    else:
        # For other 500's, provide underlying cause
        if error.exception:
            output['message'] = error.exception.__str__()

    output['description'] = error.output
    output['code'] = error.status
    response.status = error.status
    return utils.write_body(dict(error=output), request, response)


def comma_separated_strs(value):
    '''Handles comma-separated arguments passed in command-line.'''
    return map(str, value.split(","))


def comma_separated_key_value_pairs(value):
    '''Handles comma-separated key/values passed in command-line.'''
    pairs = value.split(",")
    results = {}
    for pair in pairs:
        key, pair_value = pair.split('=')
        results[key] = pair_value
    return results


def config_statsd():
    '''Stores statsd config in checkmate.common.config.'''
    user_values = CONFIG.statsd.split(':')
    if (len(user_values) < 1 or len(user_values) > 2):
        raise CheckmateException('statsd config required in format '
                                 'server:port')
    elif len(user_values) == 1:
        CONFIG.STATSD_PORT = 8125
    else:
        CONFIG.STATSD_PORT = user_values[1]

    CONFIG.STATSD_HOST = user_values[0]


def argument_parser():
    '''Parses start-up arguments and returns namespace with config variables.
    '''

    parser = argparse.ArgumentParser()

    #
    # Positional arguments
    #
    if len(sys.argv) > 1 and sys.argv[1] == 'START':
        sys.argv.pop(1)
    parser.add_argument("address",
                        help="address and optional port to start server on "
                        "[address[:port]]",
                        nargs='?',
                        default="127.0.0.1:8080"
                        )

    #
    # Verbosity, debugging, and monitoring
    #
    parser.add_argument("--logconfig",
                        help="Optional logging configuration file")
    parser.add_argument("-d", "--debug",
                        action="store_true",
                        help="turn on additional debugging inspection and "
                        "output including full HTTP requests and responses. "
                        "Log output includes source file path and line "
                        "numbers."
                        )
    parser.add_argument("-v", "--verbose",
                        action="store_true",
                        help="turn up logging to DEBUG (default is INFO)"
                        )
    parser.add_argument("-q", "--quiet",
                        action="store_true",
                        help="turn down logging to WARN (default is INFO)"
                        )
    parser.add_argument("--newrelic",
                        action="store_true",
                        default=False,
                        help="enable newrelic monitoring (place newrelic.ini "
                        "in your directory"
                        )
    parser.add_argument("-t", "--trace-calls",
                        action="store_true",
                        default=False,
                        help="display call hierarchy and errors to stdout"
                        )
    parser.add_argument("--statsd",
                        help="enable statsd server with [address[:port]]",
                        )

    #
    # Optional Capabilities
    #
    parser.add_argument("-u", "--with-ui",
                        action="store_true",
                        default=False,
                        help="enable support for browsers and HTML templates"
                        )
    parser.add_argument("-s", "--with-simulator",
                        action="store_true",
                        default=False,
                        help="enable support for the deployment simulator"
                        )
    parser.add_argument("-a", "--with-admin",
                        action="store_true",
                        default=False,
                        help="enable /admin calls (authorized to admin users "
                        "only)"
                        )
    parser.add_argument("-e", "--eventlet",
                        action="store_true",
                        default=False,
                        help="use the eventlet server (recommended in "
                        "production)"
                        )

    #
    # Queue
    #
    parser.add_argument("--eager",
                        action="store_true",
                        default=False,
                        help="all celery (queue) tasks will be executed "
                        "in-process. Use this for debugging only. There is no "
                        "need to start a queue instance when running eager."
                        )
    parser.add_argument("--worker",
                        action="store_true",
                        default=False,
                        help="start the celery worker in-process as well"
                        )

    #
    # Blueprint handling (CrossCheck functionality)
    #
    parser.add_argument("--webhook",
                        action="store_true",
                        default=False,
                        help="Enable blueprints GitHub webhook responder"
                        )
    parser.add_argument("-g", "--github-api",
                        help="Root github API uri for the repository "
                        "containing blueprints. ex: "
                        "https://api.github.com/v3")
    parser.add_argument("-o", "--organization",
                        help="The github organization owning the blueprint "
                        "repositories",
                        default="Blueprints")
    parser.add_argument("-r", "--ref",
                        help="Branch/tag/reference denoting the version of "
                        "blueprints to use.",
                        default="master")
    parser.add_argument("--cache-dir",
                        help="cache directory")
    parser.add_argument("--preview-ref",
                        help="version of deployment templates for preview",
                        default=None)
    parser.add_argument("--preview-tenants",
                        help="preview tenant IDs",
                        type=comma_separated_strs,
                        default=None)
    parser.add_argument("--group-refs",
                        help="Auth Groups and refs to associate with them as "
                        "a comma-delimited list. Ex. "
                        "--group-refs tester=master,prod=stable",
                        type=comma_separated_key_value_pairs,
                        default=None)

    args = parser.parse_args()
    return args


def main_func():
    '''Start the server based on passed in arguments. Called by __main__.'''
    CONFIG.update(vars(argument_parser()))

    resources = ['version']
    anonymous_paths = ['version']

    # Init logging before we load the database, 3rd party, and 'noisy' modules
    utils.init_logging(CONFIG,
                       default_config="/etc/default/checkmate-svr-log.conf")
    global LOG  # pylint: disable=W0603
    LOG = logging.getLogger(__name__)  # reload
    if utils.get_debug_level(CONFIG) == logging.DEBUG:
        bottle.debug(True)

    if CONFIG.eventlet is True:
        eventlet.monkey_patch()

    if CONFIG.statsd:
        config_statsd()
    
    check_celery_config()

    # Register built-in providers
    from checkmate.providers import (
        rackspace,
        opscode,
    )
    rackspace.register()
    opscode.register()

    # Load routes from other modules
    LOG.info("Loading API")
    load("checkmate.api")

    # Build WSGI Chain:
    LOG.info("Loading Application")
    next_app = root_app = default_app()  # This is the main checkmate app
    root_app.error_handler = {
        500: error_formatter,
        400: error_formatter,
        401: error_formatter,
        404: error_formatter,
        405: error_formatter,
        406: error_formatter,
        415: error_formatter,
    }
    root_app.catchall = True

    DRIVERS['default'] = db.get_driver()
    DRIVERS['simulation'] = db.get_driver(
        connection_string=os.environ.get(
            'CHECKMATE_SIMULATOR_CONNECTION_STRING',
            os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')
        )
    )

    if CONFIG.webhook is True:
        if 'github' not in MANAGERS:
            MANAGERS['github'] = blueprints.GitHubManager(DRIVERS, CONFIG)
        ROUTERS['webhook'] = blueprints.WebhookRouter(
            root_app, MANAGERS['github']
        )
        anonymous_paths.append('webhook')
        resources.append('webhook')

    # Load Deployment Handlers
    MANAGERS['deployments'] = deployments.Manager(DRIVERS)
    ROUTERS['deployments'] = deployments.Router(
        root_app, MANAGERS['deployments']
    )
    resources.append('deployments')

    # Load Blueprint Handlers - choose between database or github cache
    if CONFIG.github_api:
        if 'github' not in MANAGERS:
            MANAGERS['github'] = blueprints.GitHubManager(DRIVERS, CONFIG)
        MANAGERS['blueprints'] = MANAGERS['github']
    else:
        MANAGERS['blueprints'] = blueprints.Manager(DRIVERS)
    ROUTERS['blueprints'] = blueprints.Router(
        root_app, MANAGERS['blueprints']
    )
    resources.append('blueprints')

    # Load admin routes if requested
    if CONFIG.with_admin is True:
        LOG.info("Loading Admin Endpoints")
        ROUTERS['admin'] = AdminRouter(root_app, MANAGERS['deployments'])
        resources.append('admin')

    next_app = middleware.AuthorizationMiddleware(
        next_app,
        anonymous_paths=anonymous_paths,
        admin_paths=['admin'],
    )
    endpoints = os.environ.get('CHECKMATE_AUTH_ENDPOINTS')
    if endpoints:
        endpoints = json.loads(endpoints)
    else:
        endpoints = DEFAULT_AUTH_ENDPOINTS
    next_app = middleware.AuthTokenRouterMiddleware(
        next_app,
        endpoints,
        anonymous_paths=anonymous_paths
    )

    next_app = middleware.TenantMiddleware(next_app, resources=resources)
    next_app = middleware.StripPathMiddleware(next_app)
    next_app = middleware.ExtensionsMiddleware(next_app)

    # Load Rook if requested (after Context as Rook depends on it)
    if CONFIG.with_ui is True:
        try:
            from rook.middleware import BrowserMiddleware
            next_app = BrowserMiddleware(next_app,
                                         proxy_endpoints=endpoints,
                                         with_simulator=CONFIG.with_simulator,
                                         with_admin=CONFIG.with_admin)
        except ImportError as exc:
            LOG.exception(exc)
            msg = ("Unable to load the UI (rook.middleware). Make sure rook "
                   "is installed or run without the --with-ui argument.")
            LOG.error(msg)
            print msg
            sys.exit(1)

    next_app = middleware.ContextMiddleware(next_app)

    # Load NewRelic inspection if requested
    if CONFIG.newrelic is True:
        try:
            import newrelic.agent
        except ImportError as exc:
            LOG.exception(exc)
            msg = ("The newrelic python agent could not be loaded. Make sure "
                   "it is installed or run without the --newrelic argument")
            LOG.error(msg)
            print msg
            sys.exit(1)
        newrelic.agent.initialize(os.path.normpath(os.path.join(
                                  os.path.dirname(__file__), os.path.pardir,
                                  'newrelic.ini')))  # optional param
        next_app = newrelic.agent.wsgi_application()(next_app)

    # Load request/response dumping if debugging enabled
    if CONFIG.debug is True:
        next_app = middleware.DebugMiddleware(next_app)
        LOG.debug("Routes: %s", ['%s %s' % (r.method, r.rule) for r in
                                 app().routes])

    next_app = Gzipper(next_app, compresslevel=8)

    worker = None
    if CONFIG.worker is True:
        celery = Celery(log=LOG, set_as_current=True)
        celery.config_from_object(celeryconfig)
        worker = celery.WorkController(pool_cls="solo")
        worker.disable_rate_limits = True
        worker.concurrency = 1
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

    # Pick up IP/port from last param (default is 127.0.0.1:8080)
    ip_address = '127.0.0.1'
    port = 8080
    if CONFIG.address:
        supplied = CONFIG.address
        if len([c for c in supplied if c in '%s:.' % string.digits]) == \
                len(supplied):
            if ':' in supplied:
                ip_address, port = supplied.split(':')
            else:
                ip_address = supplied

    # Select server (wsgiref by default. eventlet if requested)
    reloader = True
    server = 'wsgiref'
    if CONFIG.eventlet is True:
        server = 'eventlet'
        reloader = False  # assume eventlet is prod, so don't reload

    # Start listening. Enable reload by default to pick up file changes
    try:
        run(app=next_app, host=ip_address, port=port, reloader=reloader,
            server=server)
    except Exception as exc:
        print "Caught:", exc
    finally:
        try:
            if worker:
                worker.stop()
        except StandardError:
            pass


#
# Main function
#
if __name__ == '__main__':
    main_func()
