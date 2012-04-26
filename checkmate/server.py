#!/usr/bin/env python
""" REST API for CheckMate

*****************************************************
*          This is STILL VERY MESSY WIP             *
*****************************************************
 

Implements these resources:
    /components:   juju charm-like definitions of services and components
    /environments: targets that can have resources deployed to them
    /blueprints:   *architect* definitions defining applications or solutions
    /deployments:  deployed resources (an instance of a blueprint deployed to
                   an environment)

These are stored in:
    ./data/components/ 
    ./data/environments/
    ./data/blueprints
    ./data/deployments
    Note::
        Master is a .shelve file, but .yaml and .json copies also exist.
        seed.yaml is the default start-up file and is loaded if present.
        The data is loaded from ./data unless the environment variable
            CHECKMATE_DATA_PATH is set.
"""
import copy
import json
# pylint: disable=E0611
from bottle import route, get, post, put, delete, run, request, response, \
        abort, HTTPError, static_file
import os
import random
import sys
import time
import uuid
import yaml
from yaml.events import AliasEvent, MappingStartEvent, ScalarEvent
from yaml.tokens import AliasToken, AnchorToken
from celery.app import app_or_default

from checkmate import orchestrator
from checkmate.db import get_driver, any_id_problems

db = get_driver('checkmate.db.sql.Driver')


#
# Making life easy - calls that are handy but might not be in final API
#
@get('/')
def get_everything():
    return write_body(db.dump(), request, response)


@post('/parse')
def parse():
    """ For debugging only """
    return read_body(request)


@get('/favicon.ico')
def favicon():
    """Without this, browsers keep getting a 404 and perceive slow response"""
    return static_file('favicon.ico', root=os.path.dirname(__file__))


#
# Environments
#
@get('/environments')
def get_environments():
    return write_body(db.get_environments(), request, response)


@post('/environments')
def post_environment():
    entity = read_body(request)
    if 'environment' in entity:
        entity = entity['environment']

    if not entity.has_key('id'):
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return HTTPError(code=406, output=any_id_problems(entity['id']))

    results = db.save_environment(entity['id'], entity)

    return write_body(results, request, response, wrapper='environment')


@put('/environments/{id}')
def put_environment(id):
    entity = read_body(request)
    if 'environment' in entity:
        entity = entity['environment']

    if any_id_problems(id):
        return HTTPError(code=406, output=any_id_problems(entity['id']))
    if not entity.has_key('id'):
        entity['id'] = str(id)

    results = db.save_environment(entity['id'], entity)

    return write_body(results, request, response, wrapper='environment')


@get('/environments/:id')
def get_environment(id):
    entity = db.get_environment(id)
    if not entity:
        abort(404, 'No environment with id %s' % id)
    return write_body(entity, request, response, wrapper='environment')


#
# Components
#
@get('/components')
def get_components():
    return write_body(db.get_components(), request, response)


@post('/components')
def post_component():
    entity = read_body(request)
    if 'component' in entity:
        entity = entity['component']

    if not entity.has_key('id'):
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return HTTPError(code=406, output=any_id_problems(entity['id']))

    results = db.save_component(entity['id'], entity)

    return write_body(results, request, response, wrapper='component')


@put('/components/{id}')
def put_component(id):
    entity = read_body(request)
    if 'component' in entity:
        entity = entity['component']

    if any_id_problems(id):
        return HTTPError(code=406, output=any_id_problems(entity['id']))
    if not entity.has_key('id'):
        entity['id'] = str(id)

    results = db.save_component(entity['id'], entity)

    return write_body(results, request, response, wrapper='component')


@get('/components/:id')
def get_component(id):
    entity = db.get_component(id)
    if not entity:
        abort(404, 'No component with id %s' % id)
    return write_body(entity, request, response, wrapper='component')


#
# Blueprints
#
@get('/blueprints')
def get_blueprints():
    return write_body(db.get_blueprints(), request, response)


@post('/blueprints')
def post_blueprint():
    entity = read_body(request)
    if 'blueprint' in entity:
        entity = entity['blueprint']

    if not entity.has_key('id'):
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return HTTPError(code=406, output=any_id_problems(entity['id']))

    results = db.save_blueprint(entity['id'], entity)

    return write_body(results, request, response, wrapper='blueprint')


@put('/blueprints/{id}')
def put_blueprint(id):
    entity = read_body(request)
    if 'blueprint' in entity:
        entity = entity['blueprint']

    if any_id_problems(id):
        return HTTPError(code=406, output=any_id_problems(entity['id']))
    if not entity.has_key('id'):
        entity['id'] = str(id)

    results = db.save_blueprint(entity['id'], entity)

    return write_body(results, request, response, wrapper='blueprint')


@get('/blueprints/:id')
def get_blueprint(id):
    entity = db.get_blueprint(id)
    if not entity:
        abort(404, 'No blueprint with id %s' % id)
    return write_body(entity, request, response, wrapper='blueprint')

#
# Deployments
#
@route('/deployments', method='GET')
def get_deployments():
    return db.getdeployments()


@post('/deployments')
def post_deployment():
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if not entity.has_key('id'):
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return HTTPError(code=406, output=any_id_problems(entity['id']))
    id = str(entity['id'])
    results = db.save_deployment(id, entity)

    #Assess work to be done & resources to be created
    results = plan(id)
    results = db.save_deployment(id, results)

    #Trigger creation of resources
    results = execute(id)
    results = db.save_deployment(id, results)

    # Return response and new resource location
    response.add_header('Location', "/deployments/%s" % id)
    return write_body(results, request, response, wrapper='deployment')


@put('/deployments/{id}')
def put_deployment(id):
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if any_id_problems(id):
        return HTTPError(code=406, output=any_id_problems(entity['id']))
    if not entity.has_key('id'):
        entity['id'] = str(id)

    results = db.save_deployment(entity['id'], entity)

    return write_body(results, request, response, wrapper='deployment')


@get('/deployments/:id')
def get_deployment(id):
    entity = db.get_deployment(id)
    if not entity:
        abort(404, 'No deployment with id %s' % id)
    return write_body(entity, request, response, wrapper='deployment')


@get('/deployments/:id/status')
def get_deployment_status(id):
    deployment = db.get_deployment(id)
    if not deployment:
        abort(404, 'No deployment with id %s' % id)

    resources = deployment.get('resources', [])
    results = {}
    for key in resources:
        resource = resources[key]
        if 'async_task_id' in resource:
            async_call = app_or_default().AsyncResult(
                    resource['async_task_id'])
            async_call.state   # refresh state
            if async_call.ready():
                result = async_call.info
            elif isinstance(async_call.info, BaseException):
                result = "Error: %s" % async_call.info
            elif async_call.info and len(async_call.info):
                result = async_call.info
            else:
                result = 'Error: No celery data available on %s' %\
                        resource['async_task_id']
            results[key] = result

    return write_body(results, request, response, wrapper='results')


def plan(id):
    """Process a new checkmate deployment and plan for execution.

    This creates placeholder tags that will be used for the actual creation
    of resources.

    :param id: checkmate deployment id
    """
    deployment = db.get_deployment(id)
    if not deployment:
        abort(404, 'No deployment with id %s' % id)
    inputs = deployment.get('inputs', [])
    
    #TODO: now hard-coded to this logic:
    # <20 requests => 1 server, running mysql & web
    # 21-200 requests => 1 mysql, mod 50 web servers
    # if ha selected, use min 1 sql, 2 web, and 1 lb
    # More than 4 web heads not supported
    high_availability = False
    if 'high-availability' in inputs:
        if inputs['high-availability'] in [True, 'true', 'True', '1', 'TRUE']:
            high_availability = True
    rps = 1 # requests per second
    if 'requests-per-second' in inputs:
        rps = int(inputs['requests-per-second'])
    
    dedicated_mysql = high_availability or rps > 20
    web_heads = int((rps+49)/50.)
    load_balancer = high_availability or web_heads > 1 or rps > 20

    if web_heads > 4:
        raise HTTPError(406, output="Blueprint does not support the "
                        "required number of web-heads: %s" % web_heads)
    deployment['resources'] = {}
    domain = inputs.get('domain', os.environ.get('STOCKTON_TEST_DOMAIN',
                                                       'mydomain.local'))
    resource_index = 0
    if web_heads > 0:
        for index in range(web_heads):
            name = 'CMDEP-%s-web%s.%s' % (deployment['id'], index + 1, domain)
            deployment['resources'][resource_index] = {'type': 'server',
                                                       'dns-name': name,
                                                       'instance-id': None}
            resource_index += 1
    if dedicated_mysql == True:
            name = 'CMDEP-%s-db1.%s' % (deployment['id'], domain)
            deployment['resources'][resource_index] = {'type': 'server',
                                                       'dns-name': name,
                                                       'instance-id': None}
            resource_index += 1
    if load_balancer == True:
            name = 'CMDEP-%s-lb1.%s' % (deployment['id'], domain)
            deployment['resources'][resource_index] = {'type': 'load-balancer',
                                                       'dns-name': name,
                                                       'instance-id': None}
            resource_index += 1
    return deployment


def execute(id):
    """Process a checkmate deployment, translate it into a stockton deployment,
    and execute it
    :param id: checkmate deployment id
    """
    deployment = db.get_deployment(id)
    if not deployment:
        abort(404, 'No deployment with id %s' % id)
    if 'resources' not in deployment:
        return {} # Nothing to do
    inputs = deployment.get('inputs', [])

    #TODO: make this smarter
    creds = [p['credentials'][0] for p in deployment['environment']['providers'] if p.has_key('common')][0]

    stockton_deployment = {
        'id': deployment['id'],
        'username': creds['username'],
        'apikey': creds['apikey'],
        'region': inputs['region'],
        'files': {}
    }

    # Read in the public key, this can be passed to newly created servers.
    if 'public_key' in inputs:
        stockton_deployment['files']['/root/.ssh/authorized_keys'] = \
                        inputs['public_key']
    else:
        if (os.environ.has_key('STOCKTON_PUBLIC_KEY') and  
                os.path.exists(os.path.expanduser(
                    os.environ['STOCKTON_PUBLIC_KEY']))):
            try:
                f = open(os.path.expanduser(os.environ['STOCKTON_PUBLIC_KEY']))
                stockton_deployment['public_key'] = f.read()
                stockton_deployment['files']['/root/.ssh/authorized_keys'] = \
                        stockton_deployment['public_key']
                f.close()
            except IOError as (errno, strerror):
                sys.exit("I/O error reading public key (%s): %s" % (errno,
                                                                    strerror))
            except:
                sys.exit('Cannot read public key.')

    import stockton  # init and ensure we end up using the same celery instance
    import checkmate.orchestrator

    # Let's make sure we are talking to the stockton celery
    #TODO: fix this when we have better celery/stockton configuration
    from celery import current_app
    assert current_app.backend.__class__.__name__ == 'DatabaseBackend'
    assert 'python-stockton' in current_app.backend.dburi.split('/')
    
    # Make the async calls
    for key in deployment['resources']:
        resource = deployment['resources'][key]
        if resource.get('type') == 'server':
            hostname = resource['dns-name']
            async_call = checkmate.orchestrator.\
                         distribute_create_simple_server.delay(
                                stockton_deployment, hostname,
                                files=stockton_deployment['files'])
            resource['async_task_id'] = async_call.task_id
    return deployment


def read_body(request):
    data = request.body
    if not data:
        abort(400, 'No data received')
    content_type = request.get_header('Content-type', 'application/json')
    if content_type == 'application/x-yaml':
        return yaml.safe_load(yaml.emit(resolve_yaml_external_refs(data),
                         Dumper=yaml.SafeDumper))
    elif content_type == 'application/json':
        return json.loads(data)
    else:
        return HTTPError(status=415, output="Unsupported Media Type")


def write_body(data, request, response, wrapper=None):
    """Write output with format based on accept header. json is default"""
    accept = request.get_header('Accept', ['application/json'])
    
    # YAML
    if 'application/x-yaml' in accept:
        response.add_header('content-type', 'application/x-yaml')
        if wrapper:
            return yaml.safe_dump({wrapper: data}, default_flow_style=False)
        else:
            return yaml.safe_dump(data, default_flow_style=False)
    
    #JSON (default)
    response.add_header('content-type', 'application/json')
    return json.dumps(data, indent=4)


def resolve_yaml_external_refs(document):
    """Parses YAML and resolves any external references"""
    anchors = []
    for event in yaml.parse(document, Loader=yaml.SafeLoader):
        if isinstance(event, AliasEvent):
            if event.anchor not in anchors:
                # Swap out local reference for external reference
                new_ref = u'checkmate-reference://%s' % event.anchor
                event = ScalarEvent(anchor=None, tag=None,
                                    implicit=(True, False), value=new_ref)
        if hasattr(event, 'anchor') and event.anchor:
            anchors.append(event.anchor)

        yield event


if __name__ == '__main__':
    run(host='127.0.0.1', port=8080, reloader=True)
