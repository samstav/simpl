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

from jinja2 import Template
from jinja2 import BaseLoader, TemplateNotFound, Environment
import json
# pylint: disable=E0611
from bottle import app, get, post, put, delete, run, request, \
        response, abort, static_file
import os
import logging
import pystache
import sys
from time import sleep
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
from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.storage import DictionarySerializer

from checkmate import orchestrator
from checkmate.db import get_driver, any_id_problems


db = get_driver('checkmate.db.sql.Driver')

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


#
# Making life easy - calls that are handy but will not be in final API
#


@get('/test/dump')
def get_everything():
    return write_body(db.dump(), request, response)


@post('/test/parse')
def parse():
    """ For debugging only """
    return read_body(request)


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

    db.save_deployment(entity['id'], entity)
    results = plan(entity['id'])

    serializer = DictionarySerializer()
    workflow = results['workflow'].serialize(serializer)
    results['workflow'] = workflow

    return write_body(results, request, response)


@get('/test/async')
def async():
    """Test async responses"""
    response.set_header('content-type', "application/json")
    response.set_header('Location', "uri://something")
    return afunc()


def afunc():
    yield '{'
    sleep(1)
    for i in range(3):
        yield '"%i": "Counting",' % i
        sleep(1)
    yield '"Done": 3}'


#
# Static files & browser support
#
@get('/favicon.ico')
def favicon():
    """Without this, browsers keep getting a 404 and perceive slow response more than 80"""
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
        abort(406, any_id_problems(entity['id']))

    results = db.save_environment(entity['id'], entity)

    return write_body(results, request, response)


@put('/environments/<id>')
def put_environment(id):
    entity = read_body(request)
    if 'environment' in entity:
        entity = entity['environment']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_environment(id, entity)

    return write_body(results, request, response)


@get('/environments/<id>')
def get_environment(id):
    entity = db.get_environment(id)
    if not entity:
        abort(404, 'No environment with id %s' % id)
    return write_body(entity, request, response)


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
        abort(406, any_id_problems(entity['id']))

    results = db.save_component(entity['id'], entity)

    return write_body(results, request, response)


@put('/components/<id>')
def put_component(id):
    entity = read_body(request)
    if 'component' in entity:
        entity = entity['component']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_component(id, entity)

    return write_body(results, request, response)


@get('/components/<id>')
def get_component(id):
    entity = db.get_component(id)
    if not entity:
        abort(404, 'No component with id %s' % id)
    return write_body(entity, request, response)


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
        abort(406, any_id_problems(entity['id']))

    results = db.save_blueprint(entity['id'], entity)

    return write_body(results, request, response)


@put('/blueprints/<id>')
def put_blueprint(id):
    entity = read_body(request)
    if 'blueprint' in entity:
        entity = entity['blueprint']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_blueprint(id, entity)

    return write_body(results, request, response)


@get('/blueprints/<id>')
def get_blueprint(id):
    entity = db.get_blueprint(id)
    if not entity:
        abort(404, 'No blueprint with id %s' % id)
    return write_body(entity, request, response)


#
# Workflows
#
@get('/workflows')
def get_workflows():
    return write_body(db.get_workflows(), request, response)


@post('/workflows')
def add_workflow():
    entity = read_body(request)
    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    results = db.save_workflow(entity['id'], entity)

    return write_body(results, request, response)


@post('/workflows/<id>')
@put('/workflows/<id>')
def save_workflow(id):
    entity = read_body(request)

    if 'workflow' in entity and isinstance(entity['workflow'], dict):
        entity = entity['workflow']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_workflow(id, entity)

    return write_body(results, request, response)


@get('/workflows/<id>')
def get_workflow(id):
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    if 'id' not in entity:
        entity['id'] = str(id)
    return write_body(entity, request, response)


@get('/workflows/<id>/status')
def get_workflow_status(id):
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)
    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)
    return write_body(get_SpiffWorkflow_status(wf), request, response)


@get('/workflows/<id>/+execute')
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

    #Synchronous call
    orchestrator.distribute_run_workflow(id, timeout=10)
    entity = db.get_workflow(id)
    return write_body(entity, request, response)


def get_SpiffWorkflow_status(workflow):
    """
    Returns the subtree as a string for debugging.

    :param workflow: a SpiffWorkflow Workflow
    @rtype:  dict
    @return: The debug information.
    """
    def get_task_status(task, output):
        """Recursively fills task data into dict"""
        my_dict = {}
        my_dict['id'] = task.id
        my_dict['threadId'] = task.thread_id
        my_dict['state'] = task.get_state_name()
        output[task.get_name()] = my_dict
        for child in task.children:
            get_task_status(child, my_dict)

    result = {}
    task = workflow.task_tree
    get_task_status(task, result)
    return result


@get('/workflows/<id>/tasks/<task_id:int>/+reset')
def reset_workflow_task(id, task_id):
    """Reset a Celery workflow task and retry it

    Checks if task is a celery task in waiting state.
    Resets parent to READY and task to FUTURE.
    Removes existing celery task ID.

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """

    workflow = db.get_workflow(id)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, workflow)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    if task.task_spec.__class__.__name__ != 'Celery':
        abort(406, "You can only reset Celery tasks. This is a '%s' task" %
            task.task_spec.__class__.__name__)

    if task.state != Task.WAITING:
        abort(406, "You can only reset WAITING tasks. This task is in '%s'" %
            task.get_state_name())

    if 'task_id' in task.internal_attributes:
        del task.internal_attributes['task_id']
    if 'error' in task.attributes:
        del task.attributes['error']
    task._state = Task.FUTURE
    task.parent._state = Task.READY

    serializer = DictionarySerializer()
    results = db.save_workflow(id, wf.serialize(serializer))

    return write_body(results, request, response)


@get('/workflows/<id>/tasks/<task_id:int>')
def get_workflow_task(id, task_id):
    """Get a workflow task

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = id  # so we know which workflow it came from
    return write_body(data, request, response)


@post('/workflows/<id>/tasks/<task_id:int>')
def post_workflow_task(id, task_id):
    """Update a workflow task

    Attributes that can be updated are:
    - attributes
    - state
    - internal_attributes

    :param id: checkmate workflow id
    :param task_id: checkmate workflow task id
    """
    entity = read_body(request)

    workflow = db.get_workflow(id)
    if not workflow:
        abort(404, 'No workflow with id %s' % id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, workflow)

    task = wf.get_task(task_id)
    if not task:
        abort(404, 'No task with id %s' % task_id)

    if 'attributes' in entity:
        if not isinstance(entity['attributes'], dict):
            abort(406, "'attribues' must be a dict")
        task.attributes = entity['attributes']

    if 'internal_attributes' in entity:
        if not isinstance(entity['internal_attributes'], dict):
            abort(406, "'internal_attribues' must be a dict")
        task.internal_attributes = entity['internal_attributes']

    if 'state' in entity:
        if not isinstance(entity['state'], (int, long)):
            abort(406, "'state' must be an int")
        task._state = entity['state']

    serializer = DictionarySerializer()
    db.save_workflow(id, wf.serialize(serializer))
    task = wf.get_task(task_id)
    results = serializer._serialize_task(task, skip_children=True)
    results['workflow_id'] = id
    return write_body(results, request, response)


@get('/workflows/<id>/tasks/<task_id:int>/+execute')
def execute_workflow(id, task_id):
    """Process a checkmate deployment workflow task

    :param id: checkmate workflow id
    :param task_id: task id
    """
    entity = db.get_workflow(id)
    if not entity:
        abort(404, 'No workflow with id %s' % id)

    #Synchronous call
    orchestrator.distribute_run_one_task(id, task_id, timeout=10)
    entity = db.get_workflow(id)

    serializer = DictionarySerializer()
    wf = Workflow.deserialize(serializer, entity)

    task = wf.get_task(task_id)
    data = serializer._serialize_task(task, skip_children=True)
    data['workflow_id'] = id  # so we know which workflow it came from
    return write_body(data, request, response)


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
        abort(406, any_id_problems(entity['id']))
    id = str(entity['id'])
    results = db.save_deployment(id, entity)

    response.add_header('Location', "/deployments/%s" % id)

    #Assess work to be done & resources to be created
    results = plan(id)

    serializer = DictionarySerializer()
    workflow = results['workflow'].serialize(serializer)
    workflow['id'] = id
    deployment = results['deployment']
    deployment['workflow'] = id

    deployment = db.save_deployment(id, deployment)  # updated by plan()
    db.save_workflow(id, workflow)

    #Trigger the workflow
    async_task = execute(id)

    # Return response (with new resource location in header)
    return write_body(deployment, request, response)


@put('/deployments/<id>')
def put_deployment(id):
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    results = db.save_deployment(id, entity)

    return write_body(results, request, response)


@get('/deployments/<id>')
def get_deployment(id):
    entity = db.get_deployment(id)
    if not entity:
        abort(404, 'No deployment with id %s' % id)
    return write_body(entity, request, response)


@get('/deployments/<id>/status')
def get_deployment_status(id):
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
    - return the workflow

    :param id: checkmate deployment id
    """
    deployment = db.get_deployment(id)
    if not deployment:
        abort(404, "No deployment with id %s" % id)
    inputs = deployment.get('inputs', [])
    blueprint = deployment.get('blueprint')
    if not blueprint:
        abort(406, "Blueprint not found. Nothing to do.")
    environment = deployment.get('environment')
    if not environment:
        abort(406, "Environment not found. Nowhere to deploy to.")

    #
    # Analyze Dependencies
    #
    relations = {}
    requirements = {}
    provided = {}
    options = {}
    for service_name, service in blueprint['services'].iteritems():
        LOG.debug("Analyzing service %s" % service_name)
        if 'relations' in service:
            relations[service_name] = service['relations']
        config = service.get('config')
        if config:
            klass = config['id']
            LOG.debug("  Config for %s", klass)
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
                            abort(406, "Input required: %s" % key)
                    if key in options:
                        options[key].append(service_name)
                    else:
                        options[key] = [service_name]
            if service_name == 'wordpress':
                LOG.debug("    This is wordpress!")
            elif service_name == 'database':
                LOG.debug("    This is the DB!")
            else:
                abort(406, "Unrecognized component type '%s'" % klass)
    # Check we have what we need (requirements are met)
    for requirement in requirements.keys():
        if requirement not in provided:
            abort(406, "Cannot satisfy requirement '%s'" % requirement)
        # TODO: check that interfaces match between requirement and provider
    # Check we have what we need (we can resolve relations)
    for service_name in relations:
        for relation in relations[service_name]:
            if relations[service_name][relation] not in blueprint['services']:
                abort(406, "Cannot find '%s' for '%s' to connect to" %
                        (relations[service_name][relation], service_name))

    #
    # Build needed resource list
    #
    resources = {}
    resource_index = 0
    for service_name, service in blueprint['services'].iteritems():
        LOG.debug("Expanding service %s" % service_name)
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
                abort(406, "Blueprint does not support the required number of "
                        "web-heads: %s" % web_heads)
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
                    name = 'CMDEP%s-web%s.%s' % (deployment['id'][0:7], index + 1,
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
            # TODO: unHACK! Hard coding instead of using resources...
            load_balancer = high_availability or web_heads > 1 or rps > 20
            if load_balancer == True:
                    name = 'CMDEP%s-lb1.%s' % (deployment['id'][0:7], domain)
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

            name = 'CMDEP%s-db1.%s' % (deployment['id'][0:7], domain)
            resources[resource_index] = {'type': 'database', 'dns-name': name,
                                         'flavor': flavor, 'instance-id': None}
            if 'machines' not in service:
                service['machines'] = []
            machines = service['machines']
            machines.append(resource_index)
            resource_index += 1
        else:
            abort(406, "Unrecognized service type '%s'" % service_name)
    deployment['resources'] = resources

    #
    # Create Workflow
    #

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

    keys = []
    # Read in the public keys to be passed to newly created servers.
    if 'public_key' in inputs:
        key.append(inputs['public_key'])
    if ('CHECKMATE_PUBLIC_KEY' in os.environ and
            os.path.exists(os.path.expanduser(
                os.environ['CHECKMATE_PUBLIC_KEY']))):
        try:
            f = open(os.path.expanduser(os.environ['CHECKMATE_PUBLIC_KEY']))
            keys.append(f.read())
            f.close()
        except IOError as (errno, strerror):
            LOG.error("I/O error reading public key from CHECKMATE_PUBLIC_KEY="
                    "'%s' environment variable (%s): %s" % (
                            os.environ['CHECKMATE_PUBLIC_KEY'], errno,
                                                                strerror))
        except StandardException as exc:
            LOG.error("Error reading public key from CHECKMATE_PUBLIC_KEY="
                    "'%s' environment variable: %s" % (
                            os.environ['CHECKMATE_PUBLIC_KEY'], exc))
    if ('STOCKTON_PUBLIC_KEY' in os.environ and
            os.path.exists(os.path.expanduser(
                os.environ['STOCKTON_PUBLIC_KEY']))):
        try:
            f = open(os.path.expanduser(os.environ['STOCKTON_PUBLIC_KEY']))
            keys.append(f.read())
            f.close()
        except IOError as (errno, strerror):
            LOG.error("I/O error reading public key from STOCKTON_PUBLIC_KEY="
                    "'%s' environment variable (%s): %s" % (
                            os.environ['STOCKTON_PUBLIC_KEY'], errno,
                                                                strerror))
        except StandardException as exc:
            LOG.error("Error reading public key from STOCKTON_PUBLIC_KEY="
                    "'%s' environment variable: %s" % (
                            os.environ['STOCKTON_PUBLIC_KEY'], exc))
    if keys:
        stockton_deployment['files']['/root/.ssh/authorized_keys'] = \
                "\n".join(keys)
    else:
        LOG.warn("No public keys detected. Less secure password auth will be "
                "used.")

    # Create the tasks that make the async calls
    for key in deployment['resources']:
        resource = deployment['resources'][key]
        hostname = resource.get('dns-name')
        if resource.get('type') == 'server':
            # Third task takes the 'deployment' attribute and creates a server
            create_server_task = Celery(wfspec, 'Create Server:%s' % key,
                               'stockton.server.distribute_create',
                               call_args=[Attrib('deployment'), hostname],
                               api_object=None,
                               image=resource.get('image', 119),
                               flavor=resource.get('flavor', 1),
                               files=stockton_deployment['files'],
                               ip_address_type='public',
                               defines={"Resource": key})
            write_token.connect(create_server_task)

            # Then register in Chef
            register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                               'stockton.chefserver.distribute_register_node',
                               call_args=[Attrib('deployment'), hostname,
                                    ['wordpress-web']],
                               defines={"Resource": key})
            write_token.connect(register_node_task)

            ssh_wait_task = Celery(wfspec, 'Wait for Server:%s' % key,
                               'stockton.ssh.ssh_up',
                                call_args=[Attrib('deployment'), Attrib('ip'),
                                    'root'],
                                password=Attrib('password'),
                                identity_file=os.environ.get(
                                    'CHECKMATE_PRIVATE_KEY', '~/.ssh/id_rsa'),
                               defines={"Resource": key})
            create_server_task.connect(ssh_wait_task)

            bootstrap_task = Celery(wfspec, 'Bootstrap Server:%s' % key,
                               'stockton.chefserver.distribute_bootstrap',
                                call_args=[Attrib('deployment'), hostname,
                                Attrib('ip')],
                                password=Attrib('password'),
                                identity_file=os.environ.get(
                                    'CHECKMATE_PRIVATE_KEY', '~/.ssh/id_rsa'),
                                roles=['wordpress-web'],
                                run_roles=['build'])
            ssh_wait_task.connect(bootstrap_task)

        elif resource.get('type') == 'load-balancer':
            # Third task takes the 'deployment' attribute and creates a lb
            create_lb_task = Celery(wfspec, 'Create LB:%s' % key,
                               'stockton.lb.distribute_create_loadbalancer',
                               call_args=[Attrib('deployment'), hostname,
                                    'PUBLIC', 'HTTP', 80],
                               dns=True,
                               defines={"Resource": key})
            write_token.connect(create_lb_task)
        elif resource.get('type') == 'database':
            # Third task takes the 'deployment' attribute and creates a server
            create_db_task = Celery(wfspec, 'Create DB:%s' % key,
                               'stockton.db.distribute_create_instance',
                               call_args=[Attrib('deployment'), hostname, 1,
                                        resource.get('flavor', 1),
                                        [{'name': 'db1'}],
                                        'MyDBUser',
                                        'password'],
                               update_chef=True,
                               defines={"Resource": key})
            write_token.connect(create_db_task)
        elif resource.get('type') == 'dns':
            # TODO: NOT TESTED YET
            create_dns_task = Celery(wfspec, 'Create DNS Record' % key,
                               'stockton.dns.distribute_create_record',
                               call_args=[Attrib('deployment'),
                               inputs.get('domain', 'localhost'), hostname,
                               'A', Attrib('vip')],
                               defines={"Resource": key})
        else:
            pass

    # Create an instance of the workflow spec
    wf = Workflow(wfspec)
    #Pass in the initial deployemnt dict (task 3 is the Auth task)
    wf.get_task(3).set_attribute(deployment=stockton_deployment)

    return {'deployment': deployment, 'workflow': wf}


def execute(id, timeout=180):
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


def read_body(request):
    """Reads request body, taking into consideration the content-type, and
    return it as a dict"""
    data = request.body
    if not data:
        abort(400, 'No data received')
    content_type = request.get_header('Content-type', 'application/json')
    if content_type == 'application/x-yaml':
        return yaml.safe_load(yaml.emit(resolve_yaml_external_refs(data),
                         Dumper=yaml.SafeDumper))
    elif content_type == 'application/json':
        return json.load(data)
    elif content_type == 'application/x-www-form-urlencoded':
        obj = request.forms.object
        if obj:
            result = json.loads(obj)
            if result:
                return result
        abort(406, "Unable to parse content. Form POSTs only support objects "
                "in the 'object' field")
    else:
        abort(415, "Unsupported Media Type: %s" % content_type)


def write_body(data, request, response):
    """Write output with format based on accept header. json is default"""
    accept = request.get_header('Accept', ['application/json'])

    # YAML
    if 'application/x-yaml' in accept:
        response.add_header('content-type', 'application/x-yaml')
        return yaml.safe_dump(data, default_flow_style=False)

    # HTML
    if 'text/html' in accept:
        response.add_header('content-type', 'text/html')

        name = get_template_name_from_path(request.path)

        class MyLoader(BaseLoader):
            def __init__(self, path):
                self.path = path

            def get_source(self, environment, template):
                path = os.path.join(self.path, template)
                if not os.path.exists(path):
                    raise TemplateNotFound(template)
                mtime = os.path.getmtime(path)
                with file(path) as f:
                    source = f.read().decode('utf-8')
                return source, path, lambda: mtime == os.path.getmtime(path)
        env = Environment(loader=MyLoader(os.path.join(os.path.dirname(
            __file__), 'static')))
        env.json = json
        try:
            template = env.get_template("%s.template" % name)
            return template.render(data=data, source=json.dumps(data,
                    indent=2))
        except StandardError as exc:
            LOG.error(exc)
            try:
                template = env.get_template("default.template")
                return template.render(data=data, source=json.dumps(data,
                        indent=2))
            except StandardError as exc2:
                LOG.error(exc2)
                pass  # fall back to JSON

    #JSON (default)
    response.set_header('content-type', 'application/json')
    return json.dumps(data, indent=4)


def get_template_name_from_path(path):
    """ Returns template name fro request path"""
    parts = path.split('/')
    # IDs are 2nd or 3rd: /[type]/[id]/[type2|action]/[id2]/action
    if len(parts) >= 4:
        name = "%s.%s" % (parts[1][0:-1], parts[3][0:-1])
    elif len(parts) == 2:
        name = "%s" % parts[1]
    elif len(parts) == 3:
        name = "%s" % parts[1][0:-1]  # strip s
    else:
        name = 'default'
    return name


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
    """Catch-all unmatched paths (so we know we got teh request, but didn't
       match it)"""
    abort(404, "Path '%s' not recognized" % path)


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
    run(app=no_ext, host='127.0.0.1', port=8080, reloader=True,
            server='wsgiref')
