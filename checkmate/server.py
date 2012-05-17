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

import json
# pylint: disable=E0611
from bottle import app, get, post, put, delete, run, request, \
        response, abort, static_file
import os
import logging
from SpiffWorkflow.storage import DictionarySerializer
import sys
from time import sleep
import uuid
import webob
from webob.exc import HTTPNotFound
from celery.app import app_or_default


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

from checkmate import orchestrator
from checkmate.db import get_driver, any_id_problems, any_tenant_id_problems
from checkmate.deployments import plan, plan_dict
from checkmate import environments  # Load routes
from checkmate import simulator  # Load routes
from checkmate.workflows import create_workflow
from checkmate.utils import write_body, read_body

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
    return write_body('go to workflows', request, response)


#
# Components
#
@get('/components')
@get('/<tenant_id>/components')
def get_components(tenant_id=None):
    return write_body(db.get_components(tenant_id=tenant_id), request,
            response)


@post('/components')
@post('/<tenant_id>/components')
def post_component(tenant_id=None):
    entity = read_body(request)
    if 'component' in entity:
        entity = entity['component']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    results = db.save_component(entity['id'], entity, tenant_id=tenant_id)

    return write_body(results, request, response)


@put('/components/<id>')
@put('/<tenant_id>/components/<id>')
def put_component(id, tenant_id=None):
    entity = read_body(request)
    if 'component' in entity:
        entity = entity['component']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_component(id, entity, tenant_id=tenant_id)

    return write_body(results, request, response)


@get('/components/<id>')
@get('/<tenant_id>/components/<id>')
def get_component(id, tenant_id=None):
    entity = db.get_component(id)
    if not entity:
        abort(404, 'No component with id %s' % id)
    return write_body(entity, request, response)


#
# Blueprints
#
@get('/blueprints')
@get('/<tenant_id>/blueprints')
def get_blueprints(tenant_id=None):
    return write_body(db.get_blueprints(tenant_id=tenant_id), request,
            response)


@post('/blueprints')
@post('/<tenant_id>/blueprints')
def post_blueprint(tenant_id=None):
    entity = read_body(request)
    if 'blueprint' in entity:
        entity = entity['blueprint']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    results = db.save_blueprint(entity['id'], entity, tenant_id=tenant_id)

    return write_body(results, request, response)


@put('/blueprints/<id>')
@put('/<tenant_id>/blueprints/<id>')
def put_blueprint(id, tenant_id=None):
    entity = read_body(request)
    if 'blueprint' in entity:
        entity = entity['blueprint']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_blueprint(id, entity, tenant_id=tenant_id)

    return write_body(results, request, response)


@get('/blueprints/<id>')
@get('/<tenant_id>/blueprints/<id>')
def get_blueprint(id, tenant_id=None):
    entity = db.get_blueprint(id)
    if not entity:
        abort(404, 'No blueprint with id %s' % id)
    return write_body(entity, request, response)


#
# Deployments
#
@get('/deployments')
@get('/<tenant_id>/deployments')
def get_deployments(tenant_id=None):
    return write_body(db.get_deployments(tenant_id=tenant_id), request,
            response)


@post('/deployments')
@post('/<tenant_id>/deployments')
def post_deployment(tenant_id=None):
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))
    id = str(entity['id'])
    results = db.save_deployment(id, entity, tenant_id=tenant_id)

    response.add_header('Location', "/deployments/%s" % id)

    #Assess work to be done & resources to be created
    results = plan(id)

    serializer = DictionarySerializer()
    workflow = results['workflow'].serialize(serializer)
    workflow['id'] = id
    deployment = results['deployment']
    deployment['workflow'] = id

    deployment = db.save_deployment(id, deployment, tenant_id=tenant_id)
    db.save_workflow(id, workflow, tenant_id=tenant_id)

    #Trigger the workflow
    async_task = execute(id)

    # Return response (with new resource location in header)
    return write_body(deployment, request, response)


@post('/deployments/+parse')
@post('/<tenant_id>/deployments/+parse')
def parse_deployment():
    """ Use this to preview a request """
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    results = plan_dict(entity)

    serializer = DictionarySerializer()
    workflow = results['workflow'].serialize(serializer)
    results['workflow'] = workflow

    return write_body(results, request, response)


@put('/deployments/<id>')
@put('/<tenant_id>/deployments/<id>')
def put_deployment(id, tenant_id=None):
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_deployment(id, entity, tenant_id=tenant_id)

    return write_body(results, request, response)


@get('/deployments/<id>')
@get('/<tenant_id>/deployments/<id>')
def get_deployment(id, tenant_id=None):
    entity = db.get_deployment(id)
    if not entity:
        abort(404, 'No deployment with id %s' % id)
    return write_body(entity, request, response)


@get('/deployments/<id>/status')
@get('/<tenant_id>/deployments/<id>/status')
def get_deployment_status(id, tenant_id=None):
    deployment = db.get_deployment(id)
    if not deployment:
        abort(404, 'No deployment with id %s' % id)

    resources = deployment.get('resources', {})
    results = {}
    workflow_id = deployment.get('workflow')
    if workflow_id:
        workflow = db.get_workflow(workflow_id)
        serializer = DictionarySerializer()
        wf = Workflow.deserialize(serializer, workflow)
        for task in wf.get_tasks(state=Task.ANY_MASK):
            if 'Resource' in task.task_spec.defines:
                resource_id = str(task.task_spec.defines['Resource'])
                resource = resources.get(resource_id, None)
                if resource:
                    result = {}
                    result['state'] = task.get_state_name()
                    error = task.get_attribute('error', None)
                    if error is not None:  # Show empty strings too
                        result['error'] = error
                    result['output'] = {key: task.attributes[key] for key
                            in task.attributes if key not in['deployment',
                            'token', 'error']}
                    if 'tasks' not in resource:
                        resource['tasks'] = {}
                    resource['tasks'][task.get_name()] = result
            else:
                result = {}
                result['state'] = task.get_state_name()
                error = task.get_attribute('error', None)
                if error is not None:  # Show empty strings too
                    result['error'] = error
                if 'tasks' not in results:
                    results['tasks'] = {}
                results['tasks'][task.get_name()] = result

    results['resources'] = resources

    return write_body(results, request, response)


def execute(id, timeout=180, tenant_id=None):
    """Process a checkmate deployment workflow

    Executes and moves the workflow forward.
    Retrieves results (final or intermediate) and updates them into
    deployment.

    :param id: checkmate deployment id
    :returns: the async task
    """
    if any_id_problems(id):
        abort(406, any_id_problems(id))

    deployment = db.get_deployment(id)
    if not deployment:
        abort(404, 'No deployment with id %s' % id)

    result = orchestrator.distribute_run_workflow.delay(id)
    return result


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
            if tenant in ['deployments', 'workflows', 'static', 'blueprints',
                    'environments', 'components', 'test']:
                pass  # route with bottle / Admin
            else:
                errors = any_tenant_id_problems(tenant)
                if errors:
                    return HTTPNotFound(errors)(e, h)
                rewrite = "/%s" % '/'.join(path_parts[2:])
                LOG.debug("Rewriting tenant %s from '%s' to '%s'" % (
                        tenant, e['PATH_INFO'], rewrite))
                e['HTTP_X_TENANT_ID'] = tenant
                e['PATH_INFO'] = rewrite

        return self.app(e, h)


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
    root_app = app()
    no_path = StripPathMiddleware(root_app)
    no_ext = ExtensionsMiddleware(no_path)
    tenant = no_ext  # TenantMiddleware(no_ext)
    run(app=tenant, host='127.0.0.1', port=8080, reloader=True,
            server='wsgiref')
