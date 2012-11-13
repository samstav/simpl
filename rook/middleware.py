import httplib
import json
import logging
import os

from urlparse import urlparse

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
# pylint: disable=E0611
from bottle import get, post, request, response, abort, \
        static_file, HTTPError, route
import webob
import webob.dec

LOG = logging.getLogger(__name__)


from rook.db import get_driver
from checkmate.utils import HANDLERS, RESOURCES, STATIC, write_body, \
        read_body, support_only, with_tenant, to_json, to_yaml, \
        get_time_string, import_class


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
        STATIC.extend(['static', 'favicon.ico', 'apple-touch-icon.png',
                'authproxy', 'marketing', '', 'images', 'ui', None,
                'feedback'])
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
        # We need Environment to load providers for the provider proxy calls
        # Side effect: Loads db and routes
        from checkmate.environments import Environment

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

        @get('/')
        @get('/ui/<path:path>')
        #TODO: remove application/json and fix angular to call partials with
        #  text/html
        @support_only(['text/html', 'text/css', 'text/javascript',
                       'application/json'])  # Angular calls template in json
        def ui(path=None):
            """Expose new javascript UI"""
            root = os.path.join(os.path.dirname(__file__), 'static', 'ui')
            if path and path.startswith('/js/'):
                root = os.path.join(os.path.dirname(__file__), 'static', 'ui',
                                    'js')
            if not path or not os.path.exists(os.path.join(root, path)):
                return static_file("index.html", root=root)
            if path.endswith('.css'):
                return static_file(path, root=root, mimetype='text/css')
            elif path.endswith('.html'):
                if 'partials' in path.split('/'):
                    return static_file(path, root=root)
                else:
                    return static_file("index.html", root=root)
            return static_file(path, root=root)

        @get('/static/<path:path>')
        #TODO: remove application/json and fix angular to call partials with
        #  text/html
        @support_only(['text/html', 'text/css', 'text/javascript', 'image/*',
                       'application/json'])  # Angular calls template in json
        def static(path):
            """Expose static files (images, css, javascript, etc...)"""
            root = os.path.join(os.path.dirname(__file__), 'static')
            # Ensure correct mimetype
            mimetype = 'auto'
            if path.endswith('.css'):  # bottle does not write this for css
                mimetype = 'text/css'
            httpResponse = static_file(path, root=root, mimetype=mimetype)
            if self.with_simulator and \
                    path.endswith('deployment-new.html') and \
                    isinstance(httpResponse.output, file):
                httpResponse.output = httpResponse.output.read().replace(
                        "<!-- SIMULATE BUTTON PLACEHOLDER - do not change "
                        "this comment, used for substitution!! -->",
                        '<button ng-click="simulate()" class="btn" '
                        'ng-disabled="!auth.loggedIn">Simulate It</button>'
                        '<button ng-click="preview()" class="btn" '
                        'ng-disabled="!auth.loggedIn">Preview It</button>')
            return httpResponse

        @get('/images/<path:path>')  # for RackspaceCalculator
        def images(path):
            """Expose image files"""
            root = os.path.join(os.path.dirname(__file__), 'static',
                    'RackspaceCalculator', 'images')
            return static_file(path, root=root)

        @get('/marketing/<path:path>')
        @support_only(['text/html', 'text/css', 'text/javascript'])
        def home(path):
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

        @route('/providers/<provider_id>/proxy/<path:path>')
        @with_tenant
        def provider_proxy(provider_id, tenant_id=None, path=None):
            vendor = None
            if "." in provider_id:
                vendor = provider_id.split(".")[0]
                provider_id = provider_id.split(".")[1]
            environment = Environment(dict(providers={provider_id:
                    dict(vendor=vendor)}))
            try:
                provider = environment.get_provider(provider_id)
            except KeyError:
                abort(404, "Invalid provider: %s" % provider_id)
            results = provider.proxy(path, request, tenant_id=tenant_id)

            return write_body(results, request, response)

        @post('/feedback')
        @support_only(['application/json'])
        def feedback():
            """Accepts feedback from UI"""
            feedback = read_body(request)
            if not feedback or 'feedback' not in feedback:
                abort(406, "Expecting a 'feedback' body in the request")
            token = request.get_header('X-Auth-Token')
            if token:
                feedback['feedback']['token'] = token
            feedback['feedback']['received'] = get_time_string()
            self.feedback_db.save_feedback(feedback)
            return write_body(feedback, request, response)

    def __call__(self, e, h):
        """Detect unauthenticated calls and redirect them to root.
        This gets processed before the bottle routes"""
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
