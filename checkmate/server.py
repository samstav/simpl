#!/usr/bin/env python
""" REST API for CheckMate

*****************************************************
*          This is still a VERY MESSY WIP           *
*****************************************************


Implements these resources:
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
    GET  /static/*                  Return files in /static folder
    PUT  /*/:id                     So you can edit/save objects without
                                    triggering actions (like a deployment).
                                    CAUTION: No locking or guarantees of
                                    atomicity across calls
Tools:
    GET  /test/dump      Dumps the database
    POST /test/parse     Parses the body (use to test your yaml or json)
    POST /test/hack      Testing random stuff....
    GET  /test/async     Returns a streamed response (3 x 1 second intervals)
    GET  /workflows/:id/tasks/:id/+reset   Reset a SpiffWorkflow Celery Task

Notes:
    .yaml/.json extensions override Accept headers (except in /static/)
    Trailing slashes are ignored (ex. /blueprints/ == /blueprints)
"""

import base64
# pylint: disable=E0611
from bottle import app, get, post, run, request, response, abort, static_file
import os
import logging
import pam
from time import sleep
import uuid
import webob
from webob.exc import HTTPNotFound, HTTPUnauthorized


# define a Handler which writes INFO messages or higher to the sys.stderr
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
# tell the handler to use this format
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger().addHandler(console)
logging.getLogger().setLevel(logging.DEBUG)
LOG = logging.getLogger(__name__)

from checkmate.db import get_driver, any_id_problems, any_tenant_id_problems

# Load routes
from checkmate import simulator
from checkmate import blueprints, components, deployments, environments

from checkmate.utils import *

db = get_driver('checkmate.db.sql.Driver')


#
# Making life easy - calls that are handy but will not be in final API
#


@get('/test/dump')
def get_everything():
    return write_body(db.dump(), request, response)


@post('/test/parse')
def parse():
    """ For debugging only """
    return write_body(read_body(request), request, response)


@post('/test/hack')
def hack():
    """ Use it to test random stuff """
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    return write_body(entity, request, response)


@get('/test/async')
def async():
    """Test async responses"""
    response.set_header('content-type', "application/json")
    response.set_header('Location', "uri://something")

    def afunc():
        yield ('{"Note": "To watch this in real-time, run: curl '\
                'http://localhost:8080/test/async -N -v",')
        sleep(1)
        for i in range(3):
            yield '"%i": "Counting",' % i
            sleep(1)
        yield '"Done": 3}'
    return afunc()


@get('/status/celery')
def get_celery_worker_status():
    """ Checking on celery """
    ERROR_KEY = "ERROR"
    try:
        from celery.task.control import inspect
        insp = inspect()
        d = insp.stats()
        if not d:
            d = {ERROR_KEY: 'No running Celery workers were found.'}
    except IOError as e:
        from errno import errorcode
        msg = "Error connecting to the backend: " + str(e)
        if len(e.args) > 0 and errorcode.get(e.args[0]) == 'ECONNREFUSED':
            msg += ' Check that the RabbitMQ server is running.'
        d = {ERROR_KEY: msg}
    except ImportError as e:
        d = {ERROR_KEY: str(e)}
    return write_body(d, request, response)


#
# Static files & browser support
#
@get('/favicon.ico')
def favicon():
    """Without this, browsers keep getting a 404 and perceive slow response """
    return static_file('favicon.ico',
            root=os.path.join(os.path.dirname(__file__), 'static'))


@get('/static/<path:path>')
def wire(path):
    """Expose static files"""
    return static_file(path,
            root=os.path.join(os.path.dirname(__file__), 'static'))


@get('/')
def root():
    return write_body('Welcome to the CheckMate Administration Interface',
            request, response)


# Keep this at end
@get('<path:path>')
def extensions(path):
    """Catch-all unmatched paths (so we know we got teh request, but didn't
       match it)"""
    abort(404, "Path '%s' not recognized" % path)


class TenantMiddleware(object):
    """Strips /tenant/ from path, puts it in header, does authn+z"""
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        # Clear headers is supplied
        if 'HTTP_X_TENANT_ID' in e:
            LOG.warn("Possible spoofing attempt. Got request with tenant "
                    "header supplied %s" % e['HTTP_X_TENANT_ID'])
            del e['HTTP_X_TENANT_ID']
        if e['PATH_INFO'] in [None, "", "/"]:
            pass  # route with bottle / Admin
        else:
            path_parts = e['PATH_INFO'].split('/')
            tenant = path_parts[1]
            if tenant in RESOURCES:
                pass  # route with bottle / Admin
            else:
                errors = any_tenant_id_problems(tenant)
                if errors:
                    return HTTPNotFound(errors)(e, h)
                rewrite = "/%s" % '/'.join(path_parts[2:])
                LOG.debug("TODO: Tenant %s rewrite from '%s' "
                        "to '%s'" % (tenant, e['PATH_INFO'], rewrite))
                e['HTTP_X_TENANT_ID'] = tenant
                # TODO: e['PATH_INFO'] = rewrite

        return self.app(e, h)


class AuthMiddleware(object):
    """ First stab at an Authentication module.

    ****************************************
    NOTE: THIS IS NOT PROVIDING SECURITY YET
    ****************************************

    - Allows all calls to /static/
    - Allows all calls with a tenant_id
    - ALlows all calls with X-Auth-Token header
    - Authenticates all other calls to PAM
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        tenant = e.get('HTTP_X_TENANT_ID', None)
        if tenant:
            # Allow all tenant calls
            return self.app(e, h)
        else:
            path_parts = e['PATH_INFO'].split('/')
            root = path_parts[1]
            if root in ['static', 'test']:
                # Allow test and static calls
                return self.app(e, h)

            # Authenticate admin calls to PAM
            if 'HTTP_AUTHORIZATION' in e:
                auth = e['HTTP_AUTHORIZATION'].split()
                if len(auth) == 2:
                    if auth[0].lower() == "basic":
                        uname, passwd = base64.b64decode(auth[1]).split(':')
                        # TODO: implement some caching
                        if pam.authenticate(uname, passwd, service='login'):
                            return self.app(e, h)
            # Authenticate calls with X-Auth-Token to the X-Auth-Source service
            if 'HTTP_X_AUTH_TOKEN' in e:
                service = e.get('HTTP_X_AUTH_TOKEN',
                    'https://identity.api.rackspacecloud.com/v2.0')
                auth = e['HTTP_X_AUTH_TOKEN']
                # TODO: implement auth & some caching to not overload auth
                if auth:
                    return self.app(e, h)
        return HTTPUnauthorized(None, [('WWW-Authenticate',
                'Basic realm="CheckMate PAM Module"')])(e, h)


class StripPathMiddleware(object):
    """Strips extra / at end of path"""
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        e['PATH_INFO'] = e['PATH_INFO'].rstrip('/')
        return self.app(e, h)


class ExtensionsMiddleware(object):
    """ Converts extensions to accept headers: yaml, json, html"""
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        if e['PATH_INFO'].startswith('/static/'):
            pass  # staic files have fixed extensions
        elif e['PATH_INFO'].endswith('.json'):
            webob.Request(e).accept = 'application/json'
            e['PATH_INFO'] = e['PATH_INFO'][0:-5]
        elif e['PATH_INFO'].endswith('.yaml'):
            webob.Request(e).accept = 'application/x-yaml'
            e['PATH_INFO'] = e['PATH_INFO'][0:-5]
        elif e['PATH_INFO'].endswith('.html'):
            webob.Request(e).accept = 'text/html'
            e['PATH_INFO'] = e['PATH_INFO'][0:-5]
        return self.app(e, h)


if __name__ == '__main__':
    LOG.setLevel(logging.DEBUG)
    # Build WSGI Chain:
    # Tenant->Auth->Extension to Content Type->Path Normalizer
    root_app = app()
    no_path = StripPathMiddleware(root_app)
    no_ext = ExtensionsMiddleware(no_path)
    auth = AuthMiddleware(no_ext)
    tenant = TenantMiddleware(auth)
    run(app=tenant, host='127.0.0.1', port=8080, reloader=True,
            server='wsgiref')
