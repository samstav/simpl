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
import sys
from time import sleep
import uuid
import webob
from webob.exc import HTTPNotFound
from celery.app import app_or_default

from checkmate import orchestrator
from checkmate.db import get_driver, any_id_problems, any_tenant_id_problems
from checkmate.deployments import plan
from checkmate import environments  # Load routes
from checkmate.workflows import create_workflow
from checkmate.utils import write_body, read_body

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

    from SpiffWorkflow.storage import DictionarySerializer
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
# Components
#
@get('/components')
@get('/<tenant_id>/components')
def get_components(tenant_id=None):
    return write_body(db.get_components(), request, response)


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

    results = db.save_component(entity['id'], entity)

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

    results = db.save_component(id, entity)

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
    return write_body(db.get_blueprints(), request, response)


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

    results = db.save_blueprint(entity['id'], entity)

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

    results = db.save_blueprint(id, entity)

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
    return write_body(db.get_deployments(), request, response)


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
@put('/<tenant_id>/deployments/<id>')
def put_deployment(id, tenant_id=None):
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
            elif service_name == 'loadbalancer':
                LOG.debug("    This is the LB!")
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
    resource_index = 0  # counter we use to increment as we create resources
    for service_name, service in blueprint['services'].iteritems():
        LOG.debug("Gather resources needed for service %s" % service_name)
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
            web_heads = inputs.get('wordpress:instance/count',
                    service['config']['settings'].get(
                            'wordpress:instance/count', int((rps + 49) / 50.)))

            if web_heads > 6:
                abort(406, "Blueprint does not support the required number of "
                        "web-heads: %s" % web_heads)
            domain = inputs.get('domain', os.environ.get('CHECKMATE_DOMAIN',
                                                           'mydomain.local'))
            if web_heads > 0:
                flavor = inputs.get('wordpress:instance/flavor',
                        service['config']['settings'].get(
                                'wordpress:instance/flavor',
                                service['config']['settings']
                                ['instance/flavor']['default']))
                image = inputs.get('wordpress:instance/os',
                        service['config']['settings'].get(
                                'wordpress:instance/os',
                                service['config']['settings']['instance/os']
                                ['default']))
                if image == 'Ubuntu 11.10':
                    image = 119  # TODO: call provider to make this translation
                for index in range(web_heads):
                    name = 'CMDEP%s-web%s.%s' % (deployment['id'][0:7], index + 1,
                            domain)
                    resources[str(resource_index)] = {'type': 'server',
                                                 'dns-name': name,
                                                 'flavor': flavor,
                                                 'image': image,
                                                 'instance-id': None}
                    if 'instances' not in service:
                        service['instances'] = []
                    instances = service['instances']
                    instances.append(str(resource_index))
                    LOG.debug("  Adding %s with id %s" % (resources[str(
                            resource_index)]['type'], resource_index))
                    resource_index += 1
            load_balancer = high_availability or web_heads > 1 or rps > 20
            if load_balancer == True:
                lb = [service for key, service in
                        deployment['blueprint']['services'].iteritems()
                        if service['config']['id'] == 'loadbalancer']
                if not lb:
                    raise Exception("%s tier calls for multiple webheads "
                            "but no loadbalancer is included in blueprint" %
                            service_name)
        elif service_name == 'database':
            flavor = inputs.get('database:instance/flavor',
                    service['config']['settings'].get(
                            'database:instance/flavor',
                            service['config']['settings']
                                    ['instance/flavor']['default']))

            domain = inputs.get('domain', os.environ.get(
                    'CHECKMATE_DOMAIN', 'mydomain.local'))

            name = 'CMDEP%s-db1.%s' % (deployment['id'][0:7], domain)
            resources[str(resource_index)] = {'type': 'database', 'dns-name': name,
                                         'flavor': flavor, 'instance-id': None}
            if 'instances' not in service:
                service['instances'] = []
            instances = service['instances']
            instances.append(str(resource_index))
            LOG.debug("  Adding %s with id %s" % (resources[str(
                    resource_index)]['type'], resource_index))
            resource_index += 1
        elif service_name == 'loadbalancer':
            name = 'CMDEP%s-lb1.%s' % (deployment['id'][0:7], domain)
            resources[str(resource_index)] = {'type': 'load-balancer',
                                               'dns-name': name,
                                               'instance-id': None}
            if 'instances' not in service:
                service['instances'] = []
            instances = service['instances']
            instances.append(str(resource_index))
            LOG.debug("  Adding %s with id %s" % (resources[str(
                    resource_index)]['type'], resource_index))
            resource_index += 1
        else:
            abort(406, "Unrecognized service type '%s'" % service_name)

    # Create connections between components
    wires = {}
    LOG.debug("Wiring tiers and resources")
    for relation in relations:
        # Find what's needed
        tier = deployment['blueprint']['services'][relation]
        resource_type = relations[relation].keys()[0]
        interface = tier['config']['requires'][resource_type]['interface']
        LOG.debug("  Looking for a provider for %s:%s for the %s tier" % (
                resource_type, interface, relation))
        instances = tier['instances']
        LOG.debug("    These instances need %s:%s: %s" % (resource_type,
                interface, instances))
        # Find who can provide it
        provider_tier_name = relations[relation].values()[0]
        provider_tier = deployment['blueprint']['services'][provider_tier_name]
        if resource_type not in provider_tier['config']['provides']:
            raise Exception("%s does not provide a %s resource, which is "
                    "needed by %s" % (provider_tier_name, resource_type,
                    relation))
        if provider_tier['config']['provides'][resource_type] != interface:
            raise Exception("'%s' provides %s:%s, but %s needs %s:%s" % (
                    provider_tier_name, resource_type,
                    provider_tier['config']['provides'][resource_type],
                    relation, resource_type, interface))
        providers = provider_tier['instances']
        LOG.debug("    These instances provide %s:%s: %s" % (resource_type,
                interface, providers))

        # Wire them up
        name = "%s-%s" % (relation, provider_tier_name)
        if name in wires:
            name = "%s-%s" % (name, len(wires))
        wires[name] = {}
        for instance in instances:
            if 'relations' not in resources[instance]:
                resources[instance]['relations'] = {}
            for provider in providers:
                if 'relations' not in resources[provider]:
                    resources[provider]['relations'] = {}
                resources[instance]['relations'][name] = {'state': 'new'}
                resources[provider]['relations'][name] = {'state': 'new'}
                LOG.debug("    New connection from %s:%s to %s:%s created: %s"
                        % (relation, instance, provider_tier_name, provider,
                        name))
    resources['connections'] = wires
    deployment['resources'] = resources

    wf = create_workflow(deployment)

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
