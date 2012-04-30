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
from bottle import app, get, post, put, delete, run, request, \
        response, abort, static_file
import os
import sys
import time
import uuid
import webob
import yaml
from yaml.events import AliasEvent, MappingStartEvent, ScalarEvent
from yaml.tokens import AliasToken, AnchorToken
from celery.app import app_or_default
try:
    from SpiffWorkflow.specs import WorkflowSpec, Celery, Transform
except ImportError:
    #TODO(zns): remove this when Spiff incorporates the code in it
    print "Get SpiffWorkflow with the Celery spec in it from here: "\
            "https://github.com/ziadsawalha/SpiffWorkflow/tree/celery"
    raise
from SpiffWorkflow import Workflow #, Task
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.storage import DictionarySerializer

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
    """Without this, browsers keep getting a 404 and perceive slow response more than 80"""
    return static_file('favicon.ico',
            root=os.path.join(os.path.dirname(__file__), 'static'))


@post('/hack')
def hack():
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return abort(406, any_id_problems(entity['id']))

    results = db.save_deployment(entity['id'], entity)
    results = plan(entity['id'])

    return write_body(results, request, response, wrapper='deployment')


@get('/static/<path:path>')
def wire(path):
    """Expose static files"""
    return static_file(path,
            root=os.path.join(os.path.dirname(__file__), 'static'))


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

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return abort(406, any_id_problems(entity['id']))

    results = db.save_environment(entity['id'], entity)

    return write_body(results, request, response, wrapper='environment')


@put('/environments/<id>')
def put_environment(id):
    entity = read_body(request)
    if 'environment' in entity:
        entity = entity['environment']

    if any_id_problems(id):
        return abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_environment(id, entity)

    return write_body(results, request, response, wrapper='environment')


@get('/environments/<id>')
def get_environment(id):
    entity = db.get_environment(id)
    if not entity:
        abort(404, 'No environment with id %s' % id)
    return write_body(entity, request, response, wrapper='environment')


@delete('/environments/<id>')
def delete_environments():
    entity = db.get_environment(id)
    if not entity:
        abort(404, 'No environment with id %s' % id)
    return write_body(db.get_environments(), request, response)


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

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return abort(406, any_id_problems(entity['id']))

    results = db.save_component(entity['id'], entity)

    return write_body(results, request, response, wrapper='component')


@put('/components/<id>')
def put_component(id):
    entity = read_body(request)
    if 'component' in entity:
        entity = entity['component']

    if any_id_problems(id):
        return abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_component(id, entity)

    return write_body(results, request, response, wrapper='component')


@get('/components/<id>')
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

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return abort(406, any_id_problems(entity['id']))

    results = db.save_blueprint(entity['id'], entity)

    return write_body(results, request, response, wrapper='blueprint')


@put('/blueprints/<id>')
def put_blueprint(id):
    entity = read_body(request)
    if 'blueprint' in entity:
        entity = entity['blueprint']

    if any_id_problems(id):
        return abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_blueprint(id, entity)

    return write_body(results, request, response, wrapper='blueprint')


@get('/blueprints/<id>')
def get_blueprint(id):
    entity = db.get_blueprint(id)
    if not entity:
        abort(404, 'No blueprint with id %s' % id)
    return write_body(entity, request, response, wrapper='blueprint')


#
# Workflows
#
@get('/workflows')
def get_workflows():
    return write_body(db.get_workflows(), request, response)


@post('/workflows')
def post_workflow():
    entity = read_body(request)
    if 'workflow' in entity:
        entity = entity['workflow']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return abort(406, any_id_problems(entity['id']))

    results = db.save_workflow(entity['id'], entity)

    return write_body(results, request, response, wrapper='workflow')


@put('/workflows/<id>')
def put_workflow(id):
    entity = read_body(request)
    if 'workflow' in entity:
        entity = entity['workflow']

    if any_id_problems(id):
        return abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_workflow(id, entity)

    return write_body(results, request, response, wrapper='workflow')


@get('/workflows/<id>')
def get_workflow(id):
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    return write_body(entity, request, response, wrapper='workflow')


@get('/workflows/<id>/status')
def get_workflow_status(id):
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)
    return write_body({'dump': wf.get_dump()}, request, response,
            wrapper='workflow')


@post('/workflows/<id>/+execute')
def execute_workflow(id):
    """Process a checkmate deployment workflow

    Executes and moves the workflow forward.
    Retrieves results (final or intermediate) and updates them into
    deployment.

    :param id: checkmate workflow id
    """
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)

    from checkmate.orchestrator import run_workflow
    wf = run_workflow(id)
    return write_body({'dump': wf.get_dump()}, request, response)


#
# Deployments
#
@get('/deployments')
def get_deployments():
    return write_body(db.get_deployments(), request, response)


@post('/deployments')
def post_deployment():
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        return abort(406, any_id_problems(entity['id']))
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


@put('/deployments/<id>')
def put_deployment(id):
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if any_id_problems(id):
        return abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_deployment(id, entity)

    return write_body(results, request, response, wrapper='deployment')


@get('/deployments/<id>')
def get_deployment(id):
    entity = db.get_deployment(id)
    if not entity:
        abort(404, 'No deployment with id %s' % id)
    return write_body(entity, request, response, wrapper='deployment')


@get('/deployments/<id>/status')
def get_deployment_status(id):
    deployment = db.get_deployment(id)
    if not deployment:
        abort(404, 'No deployment with id %s' % id)

    workflow_id = deployment.get('workflow')
    if workflow_id:
        workflow = db.get_workflow(workflow_id)


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

    The logic is as follows:
    - find the blueprint in the deployment
    - get the components from the blueprint
    - identify dependencies (inputs/options and connections/relations)
    - build a list of resources to create
    - build a workflow based on resources and dependencies

    :param id: checkmate deployment id
    """
    deployment = db.get_deployment(id)
    print "D http://localhost:8080/deployments/%s" % id
    if not deployment:
        abort(404, 'No deployment with id %s' % id)
    inputs = deployment.get('inputs', [])
    blueprint = deployment.get('blueprint')
    if not blueprint:
        return abort(406, 'Blueprint not found. Nothing to do.')
    environment = deployment.get('environment')
    if not environment:
        return abort(406, 'Environment not found. Nowhere to deploy to.')
    print json.dumps(blueprint, sort_keys=True, indent=4)
    relations = {}
    requirements = {}
    provided = {}
    options = {}
    for service_name, service in blueprint['services'].iteritems():
        print "Analyzing service", service_name
        if 'relations' in service:
            relations[service_name] = service['relations']
        config = service.get('config')
        if config:
            klass = config['id']
            print "  Config for", klass
            if 'provides' in config:
                for key in config['provides']:
                    if key in provided:
                        provided[key].append(service_name)
                    else:
                        provided[key] = [service_name]
            if 'requires' in config:
                for key in config['requires']:
                    if key in requirements:
                        requirements[key].append(service_name)
                    else:
                        requirements[key] = [service_name]
            if 'options' in config:
                for key, option in config['options'].iteritems():
                    if not 'default' in option:
                        if key not in inputs:
                            return abort(406, "Input required: %s" % key)
                    if key in options:
                        options[key].append(service_name)
                    else:
                        options[key] = [service_name]
            if service_name == 'wordpress':
                print "    This is wordpress!"
            elif service_name == 'database':
                print "    This is the DB!"
            else:
                return abort(406, "Unrecognized component type '%s'" % klass)
    # Check we have what we need (requirements are met)
    for requirement in requirements.keys():
        if requirement not in provided:
            return abort(406, "Cannot satisfy requirement '%s'" % requirement)
        # TODO: check that interfaces match between requirement and provider
    # Check we have what we need (we can resolve relations)
    for service_name in relations:
        for relation in relations[service_name]:
            if relations[service_name][relation] not in blueprint['services']:
                return abort(406, "Cannot find '%s' for '%s' to connect to" %
                        (relations[service_name][relation], service_name))
    # Expand resource list
    resources = {}
    resource_index = 0
    for service_name, service in blueprint['services'].iteritems():
        print "Expanding service", service_name
        if service_name == 'wordpress':
            #TODO: now hard-coded to this logic:
            # <20 requests => 1 server, running mysql & web
            # 21-200 requests => 1 mysql, mod 50 web servers
            # if ha selected, use min 1 sql, 2 web, and 1 lb
            # More than 4 web heads not supported
            high_availability = False
            if 'high-availability' in inputs:
                if inputs['high-availability'] in [True, 'true', 'True', '1',
                        'TRUE']:
                    high_availability = True
            rps = 1  # requests per second
            if 'requests-per-second' in inputs:
                rps = int(inputs['requests-per-second'])
            web_heads = inputs.get('wordpress:machine/count',
                    service['config']['settings'].get(
                            'wordpress:machine/count', int((rps + 49) / 50.)))

            if web_heads > 6:
                raise abort(406, "Blueprint does not support the required "
                            "number of web-heads: %s" % web_heads)
            domain = inputs.get('domain', os.environ.get('CHECKMATE_DOMAIN',
                                                           'mydomain.local'))
            if web_heads > 0:
                flavor = inputs.get('wordpress:machine/flavor',
                        service['config']['settings'].get(
                                'wordpress:machine/flavor',
                                service['config']['settings']
                                ['machine/flavor']['default']))
                image = inputs.get('wordpress:machine/os',
                        service['config']['settings'].get(
                                'wordpress:machine/os',
                                service['config']['settings']['machine/os']
                                ['default']))
                if image == 'Ubuntu 11.10':
                    image = 119  # TODO: call provider to make this translation
                for index in range(web_heads):
                    name = 'CMDEP-%s-web%s.%s' % (deployment['id'], index + 1,
                            domain)
                    resources[resource_index] = {'type': 'server',
                                                 'dns-name': name,
                                                 'flavor': flavor,
                                                 'image': image,
                                                 'instance-id': None}
                    if 'machines' not in service:
                        service['machines'] = []
                    machines = service['machines']
                    machines.append(resource_index)
                    resource_index += 1
            # More HACKs! Hard coding instead of using resources...
            load_balancer = high_availability or web_heads > 1 or rps > 20
            if load_balancer == True:
                    name = 'CMDEP-%s-lb1.%s' % (deployment['id'], domain)
                    resources[resource_index] = {'type': 'load-balancer',
                                                       'dns-name': name,
                                                       'instance-id': None}
                    resource_index += 1
        elif service_name == 'database':
            flavor = inputs.get('database:machine/flavor',
                    service['config']['settings'].get(
                            'database:machine/flavor',
                            service['config']['settings']
                                    ['machine/flavor']['default']))

            domain = inputs.get('domain', os.environ.get(
                    'CHECKMATE_DOMAIN', 'mydomain.local'))

            name = 'CMDEP-%s-db1.%s' % (deployment['id'], domain)
            resources[resource_index] = {'type': 'database', 'dns-name': name,
                                         'flavor': flavor, 'instance-id': None}
            if 'machines' not in service:
                service['machines'] = []
            machines = service['machines']
            machines.append(resource_index)
            resource_index += 1
        else:
            return abort(406, "Unrecognized service type '%s'" % service_name)
    deployment['resources'] = resources


    from celery.app import app_or_default
    from celery.result import AsyncResult
    from celery.task import task
    from checkmate import orchestrator

    # Build a workflow spec (the spec is the design of the workflow)
    wfspec = WorkflowSpec(name="%s Workflow" % blueprint['name'])

    # First task will read 'deployment' attribute and send it to Stockton
    auth_task = Celery(wfspec, 'Authenticate',
                       'stockton.auth.distribute_get_token',
                       call_args=[Attrib('deployment')], result_key='token')
    wfspec.start.connect(auth_task)

    # Second task will take output from first task (the 'token') and write it
    # into the 'deployment' dict to be available to future tasks
    write_token = Transform(wfspec, "Write Token to Deployment", transforms=[
            "my_task.attributes['deployment']['authtoken']"\
            "=my_task.attributes['token']"])
    auth_task.connect(write_token)

    stockton_deployment = {'files': {}}
    # Create an instance of the workflow spec
    wf = Workflow(wfspec)
    #Pass in the initial deployemnt dict (task 3 is the Auth task)
    wf.get_task(3).set_attribute(deployment=deployment)

    # Make the async calls
    for key in deployment['resources']:
        resource = deployment['resources'][key]
        if resource.get('type') == 'server':
            hostname = resource['dns-name']
            # Third task takes the 'deployment' attribute and creates a server
            create_server_task = Celery(wfspec, 'Create Server:%s' % key,
                               'stockton.server.distribute_create',
                               call_args=[Attrib('deployment'), hostname],
                               api_object=None,
                               image=resource.get('image', 119),
                               flavor=resource.get('flavor', 1),
                               files=stockton_deployment['files'],
                               ip_address_type='public')
            write_token.connect(create_server_task)
        elif resource.get('type') == 'loadbalancer':

            # Third task takes the 'deployment' attribute and creates a lb
            create_lb_task = Celery(wfspec, 'Create LB:%s' % key,
                               'stockton.lb.distribute_create',
                               call_args=[hostname, 'PUBLIC', 'HTTP', 80],
                               dns=True)
            write_token.connect(create_lb_task)
        elif resource.get('type') == 'database':
            # Third task takes the 'deployment' attribute and creates a server
            create_db_task = Celery(wfspec, 'Create DB:%s' % key,
                               'stockton.db.distribute_create',
                               call_args=[hostname, 1,
                                        resource.get('flavor', 1),
                                        'dbs?',
                                        'username',
                                        'password'],
                               update_chef=False)
            write_token.connect(create_db_task)
        else:
            pass

    serializer = DictionarySerializer()
    db.save_workflow(deployment['id'], wf.serialize(serializer))

    deployment['workflow'] = deployment['id']

    return deployment


def execute(id):
    """Process a checkmate deployment workflow

    Executes and moves the workflow forward.
    Retrieves results (final or intermediate) and updates them into
    deployment.

    :param id: checkmate deployment id
    """
    deployment = db.get_deployment(id)
    if not deployment:
        abort(404, 'No deployment with id %s' % id)
    if 'resources' not in deployment:
        return {}  # Nothing to do
    inputs = deployment.get('inputs', [])

    #TODO: make this smarter
    creds = [p['credentials'][0] for p in
            deployment['environment']['providers'] if 'common' in p][0]


def execute_old(id):
    """Process a checkmate deployment, translate it into a stockton deployment,
    and execute it
    :param id: checkmate deployment id
    """
    deployment = db.get_deployment(id)
    if not deployment:
        abort(404, 'No deployment with id %s' % id)
    if 'resources' not in deployment:
        return {}  # Nothing to do
    inputs = deployment.get('inputs', [])

    #TODO: make this smarter
    creds = [p['credentials'][0] for p in
            deployment['environment']['providers'] if 'common' in p][0]

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
        if ('STOCKTON_PUBLIC_KEY' in os.environ and
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
        return abort(415, "Unsupported Media Type: %s" % content_type)


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


# Keep this at end
@get('<path:path>')
def extensions(path):
    """Catch-all unmatched paths (so we know we got this)"""
    return abort(404, "Path '%s' not recognized" % path)


class StripPathMiddleware(object):
    """Strips exta / at end of path"""
    def __init__(self, app):
        self.app = app

    def __call__(self, e, h):
        e['PATH_INFO'] = e['PATH_INFO'].rstrip('/')
        return self.app(e, h)


class ExtensionsMiddleware(object):
    """ Converts .json and .yaml extensions to accept headers"""
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
        return self.app(e, h)


if __name__ == '__main__':
    root_app = app()
    no_path = StripPathMiddleware(root_app)
    no_ext = ExtensionsMiddleware(no_path)
    run(app=no_ext, host='127.0.0.1', port=8080, reloader=True)
