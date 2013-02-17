import httplib
import json
import logging
import os
from socket import gaierror
from urlparse import urlparse

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
# pylint: disable=E0611
from bottle import get, post, request, response, abort, route, \
        static_file, HTTPError
import webob
import webob.dec

import rook

LOG = logging.getLogger(__name__)


from rook.db import get_driver
from checkmate.utils import HANDLERS, RESOURCES, STATIC, write_body, \
        read_body, support_only, \
        get_time_string, import_class

__version_string__ = None


class BrowserMiddleware(object):
    """Adds support for browser interaction and HTML content

    Adds these paths:
        /favicon.ico - returns Checkmate icon
        /authproxy for Ajax clients to authenticate (to address CORS)
        /static to serve static files
        /images to serve static files for add-ons like RackspaceCalculator

    Handles text/html requests as follows:
        - authenticated: render using bottle routes and text/html HANDLER
        - unauthenticated to anonymous route: use normal bottle route
        - unauthenticated to resource route: render root UI so client can auth
    """

    def __init__(self, app, proxy_endpoints=None, with_simulator=False):
        self.app = app
        STATIC.extend(['favicon.ico', 'apple-touch-icon.png', 'js', 'libs',
                       'css', 'img', 'authproxy', 'marketing', '', None,
                       'feedback', 'partials', 'githubproxy', 'rookversion'])
        HANDLERS['application/vnd.github.v3.raw'] = write_raw
        self.proxy_endpoints = proxy_endpoints
        self.with_simulator = with_simulator
        connection_string = os.environ.get('CHECKMATE_CONNECTION_STRING',
                'sqlite://')
        if connection_string.startswith('mongodb://'):
            driver_name = 'rook.db.feedback.MongoDriver'
        else:
            driver_name = 'rook.db.feedback.SqlDriver'
        driver = import_class(driver_name)
        self.feedback_db = driver()

        # Add static routes
        @get('/favicon.ico')
        def favicon():
            """Without this, browsers keep getting a 404 and users perceive
            slow response """
            return static_file('favicon.ico',
                    root=os.path.join(os.path.dirname(__file__), 'static'))

        @get('/apple-touch-icon.png')
        def apple_touch():
            """For iOS devices"""
            return static_file('apple-touch-icon.png',
                    root=os.path.join(os.path.dirname(__file__), 'static'))

        @get('/rookversion')
        def get_rook_version():
            """ Return api version information """
            global __version_string__
            if not __version_string__:
                __version_string__ = rook.version()
            return write_body({"version": __version_string__},
                              request, response)

        @get('/images/<path:path>')  # for RackspaceCalculator
        def images(path):
            """Expose image files"""
            root = os.path.join(os.path.dirname(__file__), 'static',
                    'RackspaceCalculator', 'images')
            return static_file(path, root=root)

        @get('/marketing/<path:path>')
        @support_only(['text/html', 'text/css', 'text/javascript'])
        def marketing(path):
            return static_file(path,
                    root=os.path.join(os.path.dirname(__file__), 'static',
                        'marketing'))

        @post('/authproxy')
        @support_only(['application/json', 'application/x-yaml'])
        def authproxy():
            """Proxy Auth Requests

            The Ajax client cannot talk to auth because of CORS. This function
            allows it to authenticate through this server.
            """
            auth = read_body(request)
            if not auth:
                abort(406, "Expecting a body in the request")
            source = request.get_header('X-Auth-Source')
            if not source:
                abort(401, "X-Auth-Source header not supplied. The header is "
                        "required and must point to a valid and permitted "
                        "auth endpoint.")
            if source not in self.proxy_endpoints:
                abort(401, "Auth endpoint not permitted: %s" % source)

            url = urlparse(source)
            if url.scheme == 'https':
                http_class = httplib.HTTPSConnection
                port = url.port or 443
            else:
                http_class = httplib.HTTPConnection
                port = url.port or 80
            host = url.hostname

            http = http_class(host, port)
            headers = {
                'Content-type': 'application/json',
                'Accept': 'application/json',
                }
            # TODO: implement some caching to not overload auth
            try:
                LOG.debug('Proxy authenticating to %s' % source)
                http.request('POST', url.path, body=json.dumps(auth),
                        headers=headers)
                resp = http.getresponse()
                body = resp.read()
            except Exception, e:
                LOG.error('HTTP connection exception: %s' % e)
                raise HTTPError(401, output='Unable to communicate with '
                        'keystone server')
            finally:
                http.close()

            if resp.status != 200:
                LOG.debug('Invalid authentication: %s' % resp.reason)
                raise HTTPError(401, output=resp.reason)

            try:
                content = json.loads(body)
            except ValueError:
                msg = 'Keystone did not return json-encoded body'
                LOG.debug(msg)
                raise HTTPError(401, output=msg)

            return write_body(content, request, response)

        @get('/githubproxy/<path:path>')
        @support_only(['application/json',
                       'application/vnd.github.v3.raw'])
        def githubproxy(path=None):
            """Proxy Github Requests

            The Ajax client cannot talk to remote github servers because of
            CORS. This function proxies these calls through this server.

            The target server URL should be passed in through the
            X-Target-Url header.
            """
            source = request.get_header('X-Target-Url')
            if not source:
                abort(406, "X-Target-Url header not supplied. The header is "
                        "required and must point to a valid and permitted "
                        "git endpoint.")

            url = urlparse(source)
            if url.scheme == 'https':
                http_class = httplib.HTTPSConnection
                port = url.port or 443
            else:
                http_class = httplib.HTTPConnection
                port = url.port or 80
            host = url.hostname

            http = http_class(host, port)
            headers = {
                'Accept': request.get_header('Accept', ['application/json']),
                }
            body = None
            try:
                LOG.debug('Proxying github call to %s' % source)
                http.request('GET', '/%s' % path, headers=headers)
                resp = http.getresponse()
                body = resp.read()
            except gaierror, e:
                LOG.error('HTTP connection exception: %s' % e)
                raise HTTPError(500, output="Unable to communicate with "
                        "github server: %s" % source)
            except Exception, e:
                LOG.error("HTTP connection exception of type '%s': %s" % (
                          e.__class__.__name__, e))
                raise HTTPError(401, output="Unable to communicate with "
                                "github server")
            finally:
                http.close()

            if resp.status != 200:
                LOG.debug('Invalid github call: %s' % resp.reason)
                raise HTTPError(resp.status, output=resp.reason)

            if 'application/json' in resp.getheader('Content-type'):
                try:
                    content = json.loads(body)
                except ValueError:
                    msg = 'Github did not return json-encoded body'
                    LOG.debug(msg)
                    raise HTTPError(resp.status, output=msg)
            else:
                content = body

            return write_body(content, request, response)


        @route('/feedback', method=['POST', 'OPTIONS'])
        @support_only(['application/json'])
        def feedback():
            """Accepts feedback from UI"""
            if request.method == 'OPTIONS':
                origin = request.get_header('origin', 'http://noaccess')
                u = urlparse(origin)
                if (u.netloc in ['localhost:8080', 'checkmate.rackspace.com',
                                 'checkmate.rackspace.net'] or
                    u.netloc.endswith('chkmate.rackspace.net:8080')):
                    response.add_header('Access-Control-Allow-Origin', origin)
                    response.add_header('Access-Control-Allow-Methods',
                                        'POST, OPTIONS')
                    response.add_header('Access-Control-Allow-Headers',
                                        'Origin, Accept, Content-Type, '
                                        'X-Requested-With, X-CSRF-Token')
                return write_body({}, request, response)
            feedback = read_body(request)
            if not feedback or 'feedback' not in feedback:
                abort(406, "Expecting a 'feedback' body in the request")
            token = request.get_header('X-Auth-Token')
            if token:
                feedback['feedback']['token'] = token
            feedback['feedback']['received'] = get_time_string()
            self.feedback_db.save_feedback(feedback)
            return write_body(feedback, request, response)

        @get('/')
        @get('/<path:path>')
        #TODO: remove application/json and fix angular to call partials with
        #  text/html
        @support_only(['text/html', 'text/css', 'text/javascript', 'image/*',
                       'application/json'])  # Angular calls template in json
        def static(path=None):
            """Expose UI"""
            root = os.path.join(os.path.dirname(__file__), 'static')
            # Ensure correct mimetype (bottle does not handle css)
            mimetype = 'auto'
            if path and path.endswith('.css'):  # bottle does not write this for css
                mimetype = 'text/css'
            return static_file(path or '/index.html', root=root, mimetype=mimetype)

    def __call__(self, e, h):
        """Detect unauthenticated calls and redirect them to root.
        This gets processed before the bottle routes"""
        h = self.start_response_callback(h)
        if 'text/html' in webob.Request(e).accept or \
                e['PATH_INFO'].endswith('.html'):  # Angular requests json
            if e['PATH_INFO'] not in [None, "", "/", "/authproxy"]:
                path_parts = e['PATH_INFO'].split('/')
                if path_parts[1] in STATIC:
                    # Not a tenant call. Bypass auth and return static content
                    LOG.debug("Browser middleware stripping creds")
                    if 'HTTP_X_AUTH_TOKEN' in e:
                        del e['HTTP_X_AUTH_TOKEN']
                    if 'HTTP_X_AUTH_SOURCE' in e:
                        del e['HTTP_X_AUTH_SOURCE']
                elif path_parts[1] in RESOURCES:
                    # If not ajax call, entered in browser address bar
                    # then return client app
                    context = request.context
                    if (not context.authenticated) and \
                            e.get('HTTP_X_REQUESTED_WITH') != 'XMLHttpRequest':
                        e['PATH_INFO'] = "/"  # return client app
        return self.app(e, h)

    def start_response_callback(self, start_response):
        """Intercepts upstream start_response and adds our headers"""
        def callback(status, headers, exc_info=None):
            # Add our headers to response
            if self.with_simulator:
                headers.append(("X-Simulator-Enabled", "True"))
            # Call upstream start_response
            start_response(status, headers, exc_info)
        return callback


def write_raw(data, request, response):
    """Write output in raw format"""
    response.set_header('content-type', 'application/vnd.github.v3.raw')
    return data
