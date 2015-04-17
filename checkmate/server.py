#!/usr/bin/env python
# pylint: disable=E1101

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

"""Module to initialize and run Checkmate server.

Note: To support running with a wsgiref server with auto reloading and also
full eventlet support, we need to handle eventlet up front. If we are using
eventlet, then we'll monkey_patch ASAP. If not, then we won't monkey_patch at
all as that breaks reloading.
"""

from __future__ import print_function

# start tracer - pylint/flakes friendly
# NOTE: this will load checklmate which wil monkeypatch if eventlet is
#       requested. We also load this ASAP so we can trace as much code as
#       possible. So position is important.  KEEP THIS FIRST
__import__('checkmate.common.tracer')

import httplib
import json
import logging
import operator
import os
import sys

import bottle  # noqa
import celery  # noqa
import eventlet
from eventlet import debug
from eventlet.green import threading
import webob

import checkmate
from checkmate import admin
from checkmate import blueprints
from checkmate import celeryconfig
from checkmate.common import config
from checkmate.common import eventlet_backdoor
from checkmate.common.git import middleware as git_middleware
from checkmate.common import gzip_middleware
from checkmate.common import threadlocal
from checkmate import db
from checkmate import deployments
from checkmate import exceptions as cmexc
from checkmate import middleware
from checkmate.middleware import cors
from checkmate.middleware import keystone
from checkmate.middleware import tenant
from checkmate import resources as deployment_resources
from checkmate import stacks
from checkmate import utils
from checkmate import workflows

CONFIG = config.current()
LOG = logging.getLogger(__name__)
DRIVERS = {}
MANAGERS = {}
ROUTERS = {}


# Check our configuration
def check_celery_config():
    """Make sure a backend is configured."""
    try:
        backend = celery.current_app.backend.__class__.__name__
        if backend not in ['DatabaseBackend', 'MongoBackend', 'RedisBackend']:
            LOG.warning("Celery backend does not seem to be configured for a "
                        "database: %s", backend)
        if not celery.current_app.conf.get("CELERY_RESULT_BACKEND"):
            LOG.warning("ATTENTION!! CELERY_RESULT_BACKEND not set.  Was the "
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


def error_formatter(exception):
    """Format exception into http error messages.

    We return all errors formatted according to requested format. We default to
    json if we don't recognize or support the content.

    :param error:

    :returns: dict where content is:

        error:             - this is the wrapper for the returned error object
            code:          - the HTTP error code (ex. 404)
            description:   - the plain english, user-friendly description. Use
                             this to to surface a UI/CLI. non-technical message
    """
    output = {}

    if isinstance(exception, cmexc.CheckmateException):
        output['code'] = 400
        output['description'] = exception.friendly_message
    elif isinstance(exception, AssertionError):
        output['code'] = 400
        output['description'] = str(exception)
        LOG.error(exception)
    elif isinstance(exception, bottle.HTTPError):
        output['code'] = exception.status_code
        output['description'] = exception.message or exception.body
        LOG.error(exception)
    elif exception:
        output['code'] = 500
        output['description'] = cmexc.UNEXPECTED_ERROR

    return output


def bottle_error_formatter(bottle_error):
    """Format error for bottle.

    We return all errors formatted according to requested format. We default to
    json if we don't recognize or support the content.

    :param error:

    :returns: dict where content is:

        error:             - this is the wrapper for the returned error object
            code:          - the HTTP error code (ex. 404)
            message:       - the HTTP error code message (ex. Not Found)
            description:   - the plain english, user-friendly description. Use
                             this to to surface a UI/CLI. non-technical message
            reason:        - (optional) any additional technical information to
                             help a technical user help troubleshooting
    """
    output = error_formatter(bottle_error.exception)
    if 'description' not in output:
        if bottle_error.status_code == 404:
            output['description'] = bottle_error.body
        else:
            output['description'] = cmexc.UNEXPECTED_ERROR
    bottle_error.output = output['description']

    if 'code' in output and output['code'] != bottle_error.status_code:
        bottle_error._status_code = output['code']

    accept = bottle.request.get_header("Accept") or ""
    if "application/x-yaml" in accept:
        bottle_error.headers.update({"content-type": "application/x-yaml"})
    else:  # default to JSON
        bottle_error.headers.update({"content-type": "application/json"})

    output['message'] = httplib.responses[bottle_error.status_code]

    bottle_error.apply(bottle.response)
    return utils.write_body({'error': output}, bottle.request, bottle.response)


class FormatExceptionMiddleware(object):

    """Format outgoing exceptions.

    Uses and is compatible-with bottle exception formatting.

    - Handle Bottle Exceptions (even when catchall=False).
    - Handle CheckmateExceptions.
    - Handle other exceptions.
    - Fail-safe to a generic error (UNEXPECTED_ERROR)
    """

    def __init__(self, app, conf):
        self.app = app
        self.config = conf

    def __call__(self, environ, start_response):
        """Catch exceptions and format them based on config."""
        try:
            return self.app(environ, start_response)
        except bottle.HTTPError as exc:
            LOG.debug("Formatting a bottle exception.",
                      exc_info=exc)
            exc_info = sys.exc_info()
            exc.traceback = exc_info[1]
            start_response(exc.status_line, exc.headerlist)
            return [bottle_error_formatter(exc.exception)]
        except cmexc.CheckmateException as exc:
            LOG.debug("Formatting a Checkmate exception.",
                      exc_info=exc)
            exc_info = sys.exc_info()
            bottle_exc = bottle.HTTPError(
                status=exc.http_status, body=exc.friendly_message,
                exception=exc, traceback=exc_info[2])
            response = bottle_error_formatter(bottle_exc)
            start_response(bottle_exc.status_line, bottle_exc.headerlist)
            return [response]
        except Exception as exc:
            LOG.debug("Formatting a standard, unexpected exception.",
                      exc_info=exc)
            exc_info = sys.exc_info()
            bottle_exc = bottle.HTTPError(
                status=500, body=cmexc.UNEXPECTED_ERROR, exception=exc,
                traceback=exc_info[2])
            response = bottle_error_formatter(bottle_exc)
            # For other errors, log underlying cause
            req = webob.Request(environ)
            errmsg = "%s - %s" % (bottle_exc.status_code,
                                  utils.pytb_lastline(exc))
            context = {
                'request': "%s %s" % (req.method, req.path_url),
                'user': threadlocal.get_context().get('username'),
                'query': req.query_string,
            }
            LOG.critical(errmsg, context=context, exc_info=exc_info)
            start_response(bottle_exc.status_line, bottle_exc.headerlist)
            return [response]


def main():
    """Start the server based on passed in arguments. Called by __main__."""
    checkmate.print_banner('')
    config.preconfigure()
    if (CONFIG.bottle_reloader and not CONFIG.eventlet
            and not os.environ.get('BOTTLE_CHILD')):
        # bottle spawns 2 processes when in reloader mode
        print("Starting bottle autoreloader...")
        LOG.setLevel(logging.ERROR)
    resources = ['version']
    anonymous_paths = ['^[/]?version']
    if CONFIG.webhook:
        resources.append('webhooks')
        anonymous_paths.append('^[/]?webhooks')

    if CONFIG.debug:
        bottle.debug(True)

    if CONFIG.eventlet is True:
        LOG.warn(">>> Loading multi-threaded eventlet server <<<")
        if not CONFIG.quiet:
            print("You've loaded Checkmate as a multi-threaded server "
                  "with non-blocking HTTP io.")
        eventlet.monkey_patch()
    else:
        LOG.warn(">>> Loading single-threaded dev server <<<")
        if not CONFIG.quiet:
            if CONFIG.bottle_reloader:
                msg = (
                    "You've loaded Checkmate as a single-threaded WSGIRef "
                    "server. The advantage is that it will autoreload when "
                    "you edit any files. However, it will block when "
                    "performing background operations or responding to "
                    "requests. To run a multi-threaded server start "
                    "Checkmate with the '--eventlet' switch.")
            else:
                msg = (
                    "You've loaded Checkmate as a single-threaded WSGIRef "
                    "server. It will block when performing background "
                    "operations or responding to requests. To run a multi-"
                    "threaded server start Checkmate with the '--eventlet' "
                    "switch.")

    check_celery_config()

    # Register built-in providers
    LOG.info("Loading checkmate providers")
    provider_path = '%s/providers' % (checkmate.__path__[0])
    # import all providers in providers dir
    for prvder in os.walk(provider_path).next()[1]:
        try:
            LOG.info("Registering provider %s", prvder)
            provider = __import__("checkmate.providers.%s" % (prvder),
                                  globals(), locals(), ['object'], -1)
            getattr(provider, 'register')()
        except ImportError as exc:
            LOG.error("Failed to load %s provider", prvder)
            LOG.exception(exc)
        except AttributeError as exc:
            LOG.error("%s has no register method", prvder)
            LOG.exception(exc)

    # Build WSGI Chain:
    next_app = root_app = bottle.default_app()  # the main checkmate app
    root_app.error_handler = {
        500: bottle_error_formatter,
        400: bottle_error_formatter,
        401: bottle_error_formatter,
        404: bottle_error_formatter,
        405: bottle_error_formatter,
        406: bottle_error_formatter,
        415: bottle_error_formatter,
    }
    # disable catchall to prevent bottle from setting error.traceback to
    # format_exc(). We need an intact traceback to use for airbrake. We also
    # use the traceback in FormatExceptionMiddleware.
    root_app.catchall = False

    # Load routes from other modules
    LOG.info("Loading Checkmate API")
    bottle.load("checkmate.api")

    DRIVERS['default'] = db.get_driver()
    DRIVERS['simulation'] = db.get_driver(
        connection_string=os.environ.get(
            'CHECKMATE_SIMULATOR_CONNECTION_STRING',
            os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')
        )
    )

    if CONFIG.webhook is True:
        if 'github' not in MANAGERS:
            MANAGERS['github'] = blueprints.GitHubManager(CONFIG)
        ROUTERS['webhook'] = blueprints.WebhookRouter(
            root_app, MANAGERS['github']
        )
        anonymous_paths.append('webhook')
        resources.append('webhook')

    # Load Deployment Handlers
    MANAGERS['deployments'] = deployments.Manager()
    ROUTERS['deployments'] = deployments.Router(
        root_app, MANAGERS['deployments']
    )
    resources.append('deployments')

    # Load Workflow Handlers
    MANAGERS['workflows'] = workflows.Manager()
    ROUTERS['workflows'] = workflows.Router(
        root_app, MANAGERS['workflows'], MANAGERS['deployments']
    )
    resources.append('workflows')

    # Load Blueprint Handlers - choose between database or github cache
    MANAGERS['blueprints'] = blueprints.Manager(db.get_driver())
    MANAGERS['blueprint-cache'] = MANAGERS['blueprints']
    if CONFIG.github_api:
        if 'github' not in MANAGERS:
            MANAGERS['github'] = blueprints.GitHubManager(CONFIG)
        MANAGERS['blueprint-cache'] = MANAGERS['github']

    # Load anonymous blueprint manager, resource and anonymous path allowance.
    MANAGERS['anonymous-blueprints'] = None
    # We need to load the anonymous path and resource here otherwise it
    # believes "anonymous" is a tenant id and hits identity with it.
    resources.append('anonymous')
    anonymous_paths.append('^[/]?anonymous')
    if not CONFIG.without_anonymous:
        LOG.debug("Adding anonymous Github Manager")
        MANAGERS['anonymous-blueprints'] = \
            blueprints.github.AnonymousGitHubManager(CONFIG)
        ROUTERS['anonymous-blueprints'] = blueprints.AnonymousRouter(
            root_app, MANAGERS['anonymous-blueprints']
        )

    ROUTERS['blueprints'] = blueprints.Router(
        root_app, MANAGERS['blueprints'],
        cache_manager=MANAGERS['blueprint-cache'],
    )
    resources.append('blueprints')

    # Load Stack Handlers
    MANAGERS['stacks'] = stacks.Manager()
    ROUTERS['stacks'] = stacks.Router(
        root_app, MANAGERS['stacks']
    )
    resources.append('stacks')

    # Load Resources Handlers
    MANAGERS['resources'] = deployment_resources.Manager()
    ROUTERS['resources'] = deployment_resources.Router(
        root_app, MANAGERS['resources']
    )
    resources.append('resources')

    # Load admin routes if requested
    if CONFIG.with_admin is True:
        LOG.info("Loading Admin API")
        MANAGERS['tenants'] = admin.TenantManager()
        if CONFIG.github_api and 'github' not in MANAGERS:
            MANAGERS['github'] = blueprints.GitHubManager(CONFIG)
        ROUTERS['admin'] = admin.Router(
            root_app, MANAGERS['deployments'], MANAGERS['tenants'],
            blueprints_manager=MANAGERS.get('github'),
            blueprints_local_manager=MANAGERS['blueprints'])
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
    next_app = keystone.AuthTokenRouterMiddleware(
        next_app,
        endpoints,
        anonymous_paths=anonymous_paths
    )

    next_app = middleware.GitHubTokenMiddleware(next_app)
    next_app = tenant.TenantMiddleware(next_app, resources=resources)
    next_app = middleware.StripPathMiddleware(next_app)
    next_app = middleware.ExtensionsMiddleware(next_app)

    # Load Rook if requested (after Context as Rook depends on it)
    if CONFIG.with_ui is True:
        try:
            from rook import middleware as rook_middleware
            next_app = rook_middleware.BrowserMiddleware(
                next_app,
                CONFIG,
                proxy_endpoints=endpoints,
                with_simulator=CONFIG.with_simulator,
                with_admin=CONFIG.with_admin
            )
        except ImportError as exc:
            LOG.exception(exc)
            msg = ("Unable to load the UI (rook.middleware). Make sure rook "
                   "is installed or run without the --with-ui argument.")
            LOG.error(msg)
            print(msg)
            sys.exit(1)

    # Load Git if requested
    if CONFIG.with_git is True:
        root_path = os.environ.get("CHECKMATE_CHEF_LOCAL_PATH",
                                   "/var/local/checkmate/deployments")
        next_app = git_middleware.GitMiddleware(next_app, root_path)

    next_app = middleware.ContextMiddleware(next_app)

    # Load NewRelic inspection if requested
    if CONFIG.newrelic is True:
        try:
            # pylint: disable=F0401
            import newrelic.agent
            # pylint: enable=F0401
        except ImportError as exc:
            LOG.exception(exc)
            msg = ("The newrelic python agent could not be loaded. Make sure "
                   "it is installed or run without the --newrelic argument")
            LOG.error(msg)
            print(msg)
            sys.exit(1)
        LOG.info("Loading NewRelic agent")
        newrelic.agent.initialize(
            os.path.normpath(os.path.join(os.path.dirname(__file__),
                                          os.path.pardir,
                                          'newrelic.ini')))  # optional param
        next_app = newrelic.agent.wsgi_application()(next_app)

    # Load request/response dumping if debugging enabled
    if CONFIG.debug is True:
        next_app = middleware.DebugMiddleware(next_app)
    if not CONFIG.quiet:
        routes = [(r.method, r.rule) for r in bottle.app().routes]
        routes = sorted(routes, key=operator.itemgetter(1))
        print("Routes:\n" + "\n".join(
            ["    {: <6} {}".format(method, rule)
             for method, rule in routes]))

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
        reloader=CONFIG.bottle_reloader,
    )
    if CONFIG.eventlet is True:
        if CONFIG.bottle_reloader:
            LOG.warning("Bottle reloader not available with eventlet server.")
        kwargs['server'] = EventletSSLServer
        kwargs['reloader'] = False  # reload fails in bottle with eventlet
        kwargs['backlog'] = 100
        kwargs['log'] = EventletLogFilter
        eventlet_backdoor.initialize_if_enabled()
        from eventlet import wsgi  # noqa
        eventlet.wsgi.MAX_HEADER_LINE = 32768  # to accept x-catalog
    else:
        if CONFIG.access_log:
            print("--access-log only works with --eventlet")
            sys.exit(1)

    if kwargs['reloader']:
        LOG.warning("Bottle auto-reloader is on. The main process will not "
                    "start a server, but spawn a new child process using "
                    "the same command line arguments used to start the main "
                    "process. All module-level code is executed at least "
                    "twice! Be careful.")

    # Add CORS Headers
    etc_headers = (
        'X-API-version',
        'X-Auth-Source',
        'X-Auth-Token',
        'X-Proxy',
        'WWW-Authenticate')

    next_app = cors.CORSMiddleware(
        next_app,
        allowed_headers=(cors.CORSMiddleware.default_headers +
                         etc_headers),
        allowed_hostnames=CONFIG.cors_hosts or ['localhost', '127.0.0.1'],
        allowed_netlocs=CONFIG.cors_netlocs or [
            'checkmate.rax.io',
            'staging-checkmate.rax.io',
        ]
    )
    next_app = FormatExceptionMiddleware(next_app, CONFIG)

    # Start listening. Enable reload by default to pick up file changes
    try:
        bottle.run(app=next_app, host=ip_address, port=port, **kwargs)
    except StandardError as exc:
        print("Unexpected Exception Caught:", exc)
        sys.exit(1)
    finally:
        try:
            if worker:
                worker.stop()
            print("Shutdown complete...")
        except StandardError:
            print("Unexpected error shutting down worker:", exc)


class EventletSSLServer(bottle.ServerAdapter):

    """Eventlet SSL-Capable Bottle Server Adapter.

    * `backlog` adjust the eventlet backlog parameter which is the maximum
      number of queued connections. Should be at least 1; the maximum
      value is system-dependent.
    * `family`: (default is 2) socket family, optional. See socket
      documentation for available families.
    * `**kwargs`: directly map to python's ssl.wrap_socket arguments from
      https://docs.python.org/2/library/ssl.html#ssl.wrap_socket and
      wsgi.server arguments from
      http://eventlet.net/doc/modules/wsgi.html#wsgi-wsgi-server

    To create a self-signed key and start the eventlet server using SSL::

      openssl genrsa -des3 -out server.orig.key 2048
      openssl rsa -in server.orig.key -out test.key
      openssl req -new -key test.key -out server.csr
      openssl x509 -req -days 365 -in server.csr -signkey test.key -out \
      test.crt

      bottle.run(server='eventlet', keyfile='test.key', certfile='test.crt')
    """

    def get_socket(self):
        from eventlet import listen, wrap_ssl

        # Separate out socket.listen arguments
        socket_args = {}
        for arg in ('backlog', 'family'):
            try:
                socket_args[arg] = self.options.pop(arg)
            except KeyError:
                pass
        # Separate out wrap_ssl arguments
        ssl_args = {}
        for arg in ('keyfile', 'certfile', 'server_side', 'cert_reqs',
                    'ssl_version', 'ca_certs', 'do_handshake_on_connect',
                    'suppress_ragged_eofs', 'ciphers'):
            try:
                ssl_args[arg] = self.options.pop(arg)
            except KeyError:
                pass
        address = (self.host, self.port)
        try:
            sock = listen(address, **socket_args)
        except TypeError:
            # Fallback, if we have old version of eventlet
            sock = listen(address)
        if ssl_args:
            sock = wrap_ssl(sock, **ssl_args)
        return sock

    def run(self, handler):
        from eventlet import wsgi, patcher
        if not patcher.is_monkey_patched(os):
            msg = "Bottle requires eventlet.monkey_patch() (before import)"
            raise RuntimeError(msg)

        # Separate out wsgi.server arguments
        wsgi_args = {}
        for arg in ('log', 'environ', 'max_size', 'max_http_version',
                    'protocol', 'server_event', 'minimum_chunk_size',
                    'log_x_forwarded_for', 'custom_pool', 'keepalive',
                    'log_output', 'log_format', 'url_length_limit', 'debug',
                    'socket_timeout', 'capitalize_response_headers'):
            try:
                wsgi_args[arg] = self.options.pop(arg)
            except KeyError:
                pass
        if 'log_output' not in wsgi_args:
            wsgi_args['log_output'] = not self.quiet

        sock = self.options.pop('shared_socket', None) or self.get_socket()
        wsgi.server(sock, handler, **wsgi_args)

    def __repr__(self):
        return self.__class__.__name__


class EventletLogFilter(object):

    """Receives eventlet log.write() calls and routes them."""

    @staticmethod
    def write(text):
        """Write to appropriate target."""
        if text:
            if text[0] in '(w':
                # write thread and wsgi messages to debug only
                LOG.debug(text[:-1])
                return
            if CONFIG.access_log:
                CONFIG.access_log.write(text)
            LOG.info(text[:-1])


def run_with_profiling():
    """Start srver with yappi profiling and eventlet blocking detection on."""
    LOG.warn("Profiling and blocking detection enabled")
    debug.hub_blocking_detection(state=True)
    # pylint: disable=F0401
    import yappi
    try:
        yappi.start(True)
        main()
    finally:
        yappi.stop()
        stats = yappi.get_stats(sort_type=yappi.SORTTYPE_TSUB, limit=20)
        print("tsub   ttot   count  function")
        for stat in stats.func_stats:
            print(str(stat[3]).ljust(6), str(stat[2]).ljust(6),
                  str(stat[1]).ljust(6), stat[0])


#
# Main function
#
if __name__ == '__main__':
    if False:  # enable this for profiling and blocking detection
        run_with_profiling()
    else:
        main()
