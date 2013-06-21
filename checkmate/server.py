#!/usr/bin/env python
''' Module to initialize and run Checkmate server'''
import json
import logging
import os
import sys

# pylint: disable=W0611
import checkmate.common.tracer  # module runs on import

# pylint: disable=E0611
import bottle
from bottle import request
from bottle import response
import celery
import eventlet
from eventlet import debug
from eventlet.green import threading
from eventlet import wsgi

from checkmate.api import admin
from checkmate import git_middleware
from checkmate import blueprints
from checkmate import celeryconfig
from checkmate.common import config
from checkmate.common import eventlet_backdoor
from checkmate.common import gzip_middleware
from checkmate import db
from checkmate import deployments
from checkmate.exceptions import (
    CheckmateException,
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
DRIVERS = {}
MANAGERS = {}
ROUTERS = {}
CONFIG = config.current()


# Check our configuration
def check_celery_config():
    '''Make sure a backend is configured.'''
    try:
        backend = celery.current_app.backend.__class__.__name__
        if backend not in ['DatabaseBackend', 'MongoBackend']:
            LOG.warning("Celery backend does not seem to be configured for a "
                        "database: %s", backend)
        if not celery.current_app.conf.get("CELERY_RESULT_DBURI"):
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
        error.headers = bottle.HeaderDict(
            {"content-type": "application/x-yaml"})
        error.apply(response)
    else:  # default to JSON
        error.headers = bottle.HeaderDict({"content-type": "application/json"})
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


def main():
    '''Start the server based on passed in arguments. Called by __main__.'''
    CONFIG.initialize()
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
    bottle.load("checkmate.api")

    # Build WSGI Chain:
    LOG.info("Loading Application")
    next_app = root_app = bottle.default_app()  # the main checkmate app
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
        ROUTERS['admin'] = admin.Router(root_app, MANAGERS['deployments'])
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

    # Load Git if requested
    if CONFIG.with_git is True:
        next_app = git_middleware.GitMiddleware(next_app)

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
        LOG.debug("Routes: %s", ['\n%s %s' % (r.method, r.rule) for r in
                                 bottle.app().routes])

    next_app = gzip_middleware.Gzipper(next_app, compresslevel=8)

    worker = None
    if CONFIG.worker is True:
        celery_app = celery.Celery(log=LOG, set_as_current=True)
        celery_app.config_from_object(celeryconfig)
        worker = celery_app.WorkController(pool_cls="solo")
        worker.disable_rate_limits = True
        worker.concurrency = 1
        worker_thread = threading.Thread(target=worker.start)
        worker_thread.start()

    # Pick up IP/port from last param (default is 127.0.0.1:8080)
    ip_address = '127.0.0.1'
    port = 8080
    if CONFIG.address:
        supplied = CONFIG.address
        if supplied and all((c for c in supplied if c in '0123456789:.')):
            if ':' in supplied:
                ip_address, port = supplied.split(':')
            else:
                ip_address = supplied

    # Select server (wsgiref by default. eventlet if requested)
    kwargs = dict(
        server='wsgiref',
        quiet=CONFIG.quiet,
        reloader=True,
    )
    if CONFIG.eventlet is True:
        kwargs['server'] = CustomEventletServer
        kwargs['reloader'] = False  # assume eventlet is prod, so don't reload
        kwargs['backlog'] = 100
        kwargs['log'] = CONFIG.access_log
        eventlet_backdoor.initialize_if_enabled()
    else:
        if CONFIG.access_log:
            print "--access-log only works with --eventlet"
            sys.exit(1)

    # Start listening. Enable reload by default to pick up file changes
    try:
        bottle.run(app=next_app, host=ip_address, port=port, **kwargs)
    except StandardError as exc:
        print "Caught Exception:", exc
    finally:
        try:
            if worker:
                worker.stop()
        except StandardError:
            pass


class CustomEventletServer(bottle.ServerAdapter):
    '''Handles added backlog.'''
    def run(self, handler):
        try:
            socket_args = {}
            for arg in ['backlog', 'family']:
                if arg in self.options:
                    socket_args[arg] = self.options.pop(arg)
            if 'log_output' not in self.options:
                self.options['log_output'] = (not self.quiet)
            socket = eventlet.listen((self.host, self.port), **socket_args)
            wsgi.server(socket, handler, **self.options)
        except TypeError:
            # Fallback, if we have old version of eventlet
            wsgi.server(eventlet.listen((self.host, self.port)), handler)


#
# Main function
#
if __name__ == '__main__':
    if False:  # enable this for profiling and blocking detection
        LOG.warn("Profiling and blocking detection enabled")
        debug.hub_blocking_detection(state=True)
        import yappi
        try:
            yappi.start(True)
            main()
        finally:
            yappi.stop()
            stats = yappi.get_stats(sort_type=yappi.SORTTYPE_TSUB, limit=20)
            print "tsub   ttot   count  function"
            for stat in stats.func_stats:
                print str(stat[3]).ljust(6), stat[2].ljust(6), \
                    stat[1].ljust(6), stat[0]
    else:
        main()
