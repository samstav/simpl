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
    data = request.body
    if not data:
        abort(400, 'No data received')
    content_type = request.get_header('Content-type', 'application/json')
    if content_type == 'application/x-yaml':
        entity = yaml.safe_load(data)
        if 'deployment' in entity:
            entity = entity['deployment']
    elif content_type == 'application/json':
        entity = json.loads(data)
    else:
        return HTTPError(status=415, output="Unsupported Media Type")

    if not entity.has_key('id'):
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return HTTPError(code=406, output=any_id_problems(entity['id']))

    db['deployments'][str(entity['id'])] = entity
    #TODO: testing
    entity['feedback'] = execute(str(entity['id']))
    entity['feedback']['Note'] = "A copy of what was sent to stockton FYI"
    entity['async_task_id'] = entity['feedback']['async_task_id']

    # Write files out to disk so we have them as simple text files
    jfile = open(os.path.join(ACTUAL_DATA_PATH, 'deployments', '%s.%s' %
                         (entity['id'], 'json')), 'w')
    json.dump(entity, jfile, indent=4)
    jfile.close()
    yfile = open(os.path.join(ACTUAL_DATA_PATH, 'deployments', '%s.%s' %
                         (entity['id'], 'yaml')), 'w')
    yaml.dump(entity, yfile, default_flow_style=False)
    yfile.close()


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
    entity = db['deployments'].get(str(id))
    if not entity:
        abort(404, 'No deployment with id %s' % id)

    results = 'Unknown status'
    if 'async_task_id' in entity:
        async_call = app_or_default().AsyncResult(entity['async_task_id'])
        async_call.state   # refresh state
        if async_call.ready():
            results = async_call.info
        elif isinstance(async_call.info, BaseException):
            results = "Error: %s" % async_call.info
        elif async_call.info and len(async_call.info):
            results = async_call.info

    return output_content(results, request, response, wrapper='result')


@get('/favicon.ico')
def favicon():
    """Without this, browsers keep getting a 404 and perceive slow response"""
    return static_file('favicon.ico', root=os.path.dirname(__file__))



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
    deployment = db['deployments'].get(str(id))
    if not deployment:
        abort(404, 'No deployment with id %s' % id)
    inputs = deployment.get('inputs', [])

    stockton_deployment = {
        'id': str(random.randint(1000, 10000)),
        'username': os.environ['STOCKTON_USERNAME'],
        'apikey': os.environ['STOCKTON_APIKEY'],
        'region': os.environ['STOCKTON_REGION'],
        'files': {}
    }
    print "Deployment ID: %s" % deployment['id']
    
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
    
    # Make the async call!
    hostname = 'orchestrator-test-%s.%s' % (stockton_deployment['id'],
                             inputs.get('domain',
                                        os.environ.get('STOCKTON_TEST_DOMAIN',
                                                       'mydomain.com')))
    if 'resources' not in deployment:
        deployment['resources'] = {}
    deployment['resources'][0] = {'dns-name': hostname, 'instance-id': None}
 
    async_call = checkmate.orchestrator.distribute_create_simple_server.delay(
            stockton_deployment, hostname, files=stockton_deployment['files'])
    stockton_deployment['async_task_id'] = async_call.task_id
    return stockton_deployment


if __name__ == '__main__':
    run(host='localhost', port=8080, reloader=True)
