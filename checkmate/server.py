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
import json
# pylint: disable=E0611
from bottle import route, get, post, run, request, response, abort, \
        HTTPError, static_file
import os
import uuid
import yaml

from celery.app import app_or_default
from checkmate import orchestrator

DEFAULT_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data')
ACTUAL_DATA_PATH = os.path.join(os.environ.get('CHECKMATE_DATA_PATH',
                                          DEFAULT_DATA_PATH))

# Set up database and load seed.yamnl file if it exists
db = {
        'components': {},
        'environments': {},
        'blueprints': {},
        'deployments': {},
    }

seed_file = os.path.join(ACTUAL_DATA_PATH, 'seed.yaml')
if os.path.exists(seed_file):
    stream = file(seed_file, 'r')
    seed = yaml.safe_load(stream)
    components = seed.pop('components', None)
    if components:
        db['components'] = components
    environment = seed.pop('environment', None)
    if environment:
        db['environments'][environment.get('id', '1')]= environment
    blueprint = seed.pop('blueprint', None)
    if blueprint:
        db['blueprints'][blueprint.get('id', '1')]= blueprint
    deployment = seed.pop('deployment', None)
    if deployment:
        db['deployments'][deployment.get('id', '1')] = deployment
    if seed:
        print "Unprocessed seed data: %s" % seed


def output_content(data, request, response, wrapper=None):
    """Write output with format based on accept header. json is default"""
    accept = request.get_header('Accept', ['application/json'])
    
    # YAML
    if 'application/x-yaml' in accept:
        response.add_header('content-type', 'application/x-yaml')
        if wrapper:
            return yaml.dump({wrapper: data}, default_flow_style=False)
        else:
            return yaml.dump(data, default_flow_style=False)
    
    #JSON (default)
    response.add_header('content-type', 'application/json')
    return json.dumps(data, indent=4)


def ensure_dirs(path):
    """ Make sure a directory exists (create if not there) """
    try:
        os.makedirs(path)
    except OSError:
        if os.path.isdir(path):
            # Looking good?
            pass
        else:
            # There was an error on creation, so make sure we know about it
            raise


ensure_dirs(os.path.join(ACTUAL_DATA_PATH, 'environments'))
ensure_dirs(os.path.join(ACTUAL_DATA_PATH, 'components'))
ensure_dirs(os.path.join(ACTUAL_DATA_PATH, 'blueprints'))
ensure_dirs(os.path.join(ACTUAL_DATA_PATH, 'deployments'))


def any_id_problems(id):
    """Validate the ID provided is safe and returns problems as a string.
    
    To use this, call it with an ID you want to validate. If the response is
    None, then the ID is good. Otherwise, the response is a string explaining
    the problem with the ID that you can use to return to the client"""
    allowed_start_chars = "abcdefghijklmnopqrstuvwxyz"\
                          "ABCDEFGHIJKLMNOPQRSTUVWXYZ"\
                          "0123456789"
    allowed_chars = allowed_start_chars + "-_.+~@"
    if id is None:
        return 'ID cannot be blank'
    if not isinstance(id, basestring):
        id = str(id)
    if 1 > len(id) > 128:
        return "ID cannot be 1 to 128 characters"
    if id[0] not in allowed_start_chars:
        return "Invalid start character '%s'. ID can start with any of '%s'" \
                % (id[0], allowed_start_chars)
    for c in id:
        if c not in allowed_chars:
            return "Invalid character '%s'. Allowed charaters are '%s'" % (c,
                                                                allowed_chars)
    return None

#
# Making life easy - calls that are handy but might not be in final API
#
@get('/')
def get_everything():
    return output_content(db, request, response)


#
# Environments
#
@get('/environments')
def get_environments():
    return output_content(db['environments'], request, response)


@post('/environments')
def post_environment():
    data = request.body
    if not data:
        abort(400, 'No data received')
    content_type = request.get_header('Content-type', 'application/json')
    if content_type == 'application/x-yaml':
        entity = yaml.load(data)
        if 'environment' in entity:
            entity = entity['environment']
    elif content_type == 'application/json':
        entity = json.loads(data)
    else:
        return HTTPError(status=415, output="Unsupported Media Type")

    if not entity.has_key('id'):
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return HTTPError(code=406, output=any_id_problems(entity['id']))

    db['environments'][str(entity['id'])] = entity
    jfile = open(os.path.join(ACTUAL_DATA_PATH, 'environments', '%s.%s' %
                         (entity['id'], 'json')), 'w')
    json.dump(entity, jfile, indent=4)
    jfile.close()
    yfile = open(os.path.join(ACTUAL_DATA_PATH, 'environments', '%s.%s' %
                         (entity['id'], 'yaml')), 'w')
    yaml.dump(entity, yfile, default_flow_style=False)
    yfile.close()

    return output_content(entity, request, response, wrapper='environment')


@get('/environments/:id')
def get_environment(id):
    entity = db['environments'].get(str(id))
    if not entity:
        abort(404, 'No environment with id %s' % id)
    return output_content(entity, request, response, wrapper='environment')

#
# Deployments
#
@route('/deployments', method='GET')
def get_deployments():
    return db['deployments']


@post('/deployments')
def post_deployment():
    # Load content from body (and resolve external references)
    data = request.body
    if not data:
        abort(400, 'No data received')
    content_type = request.get_header('Content-type', 'application/json')
    if content_type == 'application/x-yaml':
        entity = yaml.safe_load(yaml.emit(resolve_yaml_external_refs(data)))
        if 'deployment' in entity:
            entity = entity['deployment']
    elif content_type == 'application/json':
        entity = json.loads(data)
    else:
        return HTTPError(status=415, output="Unsupported Media Type")

    # Store deployment and validate and assign identifier
    if not entity.has_key('id'):
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return HTTPError(code=406, output=any_id_problems(entity['id']))
    entity['id'] = entity['id'] # make sure it is a string
    db['deployments'][entity['id']] = entity

    #Assess work to be done & resources to be created
    results = plan(entity['id'])
    
    #Trigger creation of resources
    results = execute(entity['id'])

    # Write files out to disk (our only persistence method for now)
    jfile = open(os.path.join(ACTUAL_DATA_PATH, 'deployments', '%s.%s' %
                         (entity['id'], 'json')), 'w')
    json.dump(entity, jfile, indent=4)
    jfile.close()
    yfile = open(os.path.join(ACTUAL_DATA_PATH, 'deployments', '%s.%s' %
                         (entity['id'], 'yaml')), 'w')
    yaml.dump(entity, yfile, default_flow_style=False)
    yfile.close()

    # Return response and new resource location
    response.add_header('Location', "/deployments/%s" % entity['id'])
    return output_content(entity, request, response, wrapper='deployment')


@get('/deployments/:id')
def get_deployment(id):
    entity = db['deployments'].get(str(id))
    if not entity:
        abort(404, 'No deployment with id %s' % id)
    return output_content(entity, request, response, wrapper='deployment')


@get('/deployments/:id/status')
def get_deployment_status(id):
    deployment = db['deployments'].get(id)
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

    return output_content(results, request, response, wrapper='results')


@get('/favicon.ico')
def favicon():
    """Without this, browsers keep getting a 404 and perceive slow response"""
    return static_file('favicon.ico', root=os.path.dirname(__file__))

def plan(id):
    """Process a new checkmate deployment and plan for execution.

    This creates placeholder tags that will be used for the actual creation
    of resources.

    :param id: checkmate deployment id
    """
    deployment = db['deployments'].get(id)
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


import copy
import os
import random
import sys
import time


def execute(id):
    """Process a checkmate deployment, translate it into a stockton deployment,
    and execute it
    :param id: checkmate deployment id
    """
    deployment = db['deployments'].get(id)
    if not deployment:
        abort(404, 'No deployment with id %s' % id)
    if 'resources' not in deployment:
        return {} # Nothing to do
    inputs = deployment.get('inputs', [])

    stockton_deployment = {
        'id': str(random.randint(1000, 10000)),
        'username': os.environ['STOCKTON_USERNAME'],
        'apikey': os.environ['STOCKTON_APIKEY'],
        'region': os.environ['STOCKTON_REGION'],
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

    print "Deployment ID: %s" % deployment['id']


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


@post('/parse')
def parse():
    """ For debugging only """
    data = request.body
    if not data:
        abort(400, 'No data received')
    content_type = request.get_header('Content-type', 'application/json')
    if content_type == 'application/x-yaml':
        return yaml.emit(resolve_yaml_external_refs(data))
    elif content_type == 'application/json':
        entity = json.loads(data)
    else:
        return HTTPError(status=415, output="Unsupported Media Type")


from yaml.events import AliasEvent, MappingStartEvent, ScalarEvent
from yaml.tokens import AliasToken, AnchorToken
def resolve_yaml_external_refs(document):
    """Parses YAML and resolves any external references"""
    anchors = []
    for event in yaml.parse(document):
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
    run(host='localhost', port=8080, reloader=True)
