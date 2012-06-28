# pylint: disable=E0611
from bottle import get, post, put, request, response, abort
from celery.app import app_or_default
import logging
import os
from SpiffWorkflow.storage import DictionarySerializer
import sys
import uuid

from checkmate.db import get_driver, any_id_problems
from checkmate.environments import Environment
from checkmate import orchestrator
from checkmate.workflows import create_workflow
from checkmate.utils import write_body, read_body, extract_sensitive_data,\
        merge_dictionary, with_tenant
from checkmate import orchestrator

LOG = logging.getLogger(__name__)
db = get_driver('checkmate.db.sql.Driver')


#
# Deployments
#
@get('/deployments')
@with_tenant
def get_deployments(tenant_id=None):
    return write_body(db.get_deployments(tenant_id=tenant_id), request,
            response)


@post('/deployments')
@with_tenant
def post_deployment(tenant_id=None):
    entity = read_body(request)

    # Validate syntax
    errors = check_deployment(entity)
    if errors:
        abort(406, "\n".join(errors))

    if 'deployment' in entity:
        entity = entity['deployment']

    if 'id' not in entity:
        entity['id'] = uuid.uuid4().hex
    if any_id_problems(entity['id']):
        abort(406, any_id_problems(entity['id']))

    id = str(entity['id'])
    body, secrets = extract_sensitive_data(entity)
    db.save_deployment(id, body, secrets, tenant_id=tenant_id)

    # Return response (with new resource location in header)
    if tenant_id:
        response.add_header('Location', "/%s/deployments/%s" % (tenant_id, id))
    else:
        response.add_header('Location', "/deployments/%s" % id)

    #Assess work to be done & resources to be created
    results = plan(id)

    serializer = DictionarySerializer()
    workflow = results['workflow'].serialize(serializer)
    workflow['id'] = id
    deployment = results['deployment']
    deployment['workflow'] = id

    body, secrets = extract_sensitive_data(deployment)
    deployment = db.save_deployment(id, body, secrets, tenant_id=tenant_id)

    body, secrets = extract_sensitive_data(workflow)
    db.save_workflow(id, body, secrets, tenant_id=tenant_id)

    #Trigger the workflow
    async_task = execute(id)

    return write_body(deployment, request, response)


@post('/deployments/+parse')
@with_tenant
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
@with_tenant
def put_deployment(id, tenant_id=None):
    entity = read_body(request)
    if 'deployment' in entity:
        entity = entity['deployment']

    if any_id_problems(id):
        abort(406, any_id_problems(id))
    if 'id' not in entity:
        entity['id'] = str(id)

    body, secrets = extract_sensitive_data(entity)
    results = db.save_deployment(id, body, secrets, tenant_id=tenant_id)

    return write_body(results, request, response)


@get('/deployments/<id>')
@with_tenant
def get_deployment(id, tenant_id=None):
    if 'with_secrets' in request.query:  # TODO: verify admin-ness
        entity = db.get_deployment(id, with_secrets=True)
    else:
        entity = db.get_deployment(id)
    if not entity:
        abort(404, 'No deployment with id %s' % id)
    return write_body(entity, request, response)


@get('/deployments/<id>/status')
@with_tenant
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

    result = orchestrator.distribute_run_workflow.delay(id, timeout=900)
    return result


def plan(id):
    deployment = db.get_deployment(id, with_secrets=True)
    if not deployment:
        abort(404, "No deployment with id %s" % id)
    return plan_dict(deployment)


def plan_dict(deployment):
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
    inputs = deployment.get('inputs', {})
    blueprint = deployment.get('blueprint')
    if not blueprint:
        abort(406, "Blueprint not found. Nothing to do.")
    environment = deployment.get('environment')
    if not environment:
        abort(406, "Environment not found. Nowhere to deploy to.")
    environment = Environment(environment)

    #
    # Analyze Dependencies
    #
    relations = {}
    requirements = {}
    provided = {}  # From other components
    available = {}  # From environment
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
                for key, value in config['requires'].iteritems():
                    if key == 'host':
                        # Find host type (ex: host/instance=compute)
                        requirement_type = value['instance']
                    else:
                        requirement_type = key
                    if requirement_type in requirements:
                        requirements[requirement_type].append(service_name)
                    else:
                        requirements[requirement_type] = [service_name]
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
    # Add resources provided by environment
    providers = environment.get_providers()
    for provider in providers.values():
        LOG.debug("%s provides %s" % (provider.__class__, provider.provides()))
        for resource in provider.provides():
            if resource in available:
                available[resource].append(provider)
            else:
                available[resource] = [provider]

    # Check we have what we need (requirements are met)
    for requirement in requirements.keys():
        if requirement not in provided and requirement not in available:
            msg = "Cannot satisfy requirement '%s' in deployment %s" % (
                    requirement, deployment['id'])
            LOG.info(msg)
            abort(406, msg)
        # TODO: check that interfaces match between requirement and provider
    # Check we have what we need (we can resolve relations)
    for service_name in relations:
        for relation in relations[service_name]:
            if relations[service_name][relation] not in blueprint['services']:
                msg = "Cannot find '%s' for '%s' to connect to in " \
                      "deployment %s" % (relations[service_name][relation],
                      service_name, deployment['id'])
                LOG.info(msg)
                abort(406, msg)

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
                compute = environment.select_provider(resource='compute')

                for index in range(web_heads):
                    # Generate a default name
                    name = 'CMDEP%s-web%s.%s' % (deployment['id'][0:7],
                            index + 1, domain)
                    # Call provider to give us a resource template
                    resource = compute.generate_template(deployment,
                            service_name, service, name=name)
                    # Add it to resources
                    resources[str(resource_index)] = resource
                    # Link resource to tier
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
            database = environment.select_provider(resource='database')
            domain = inputs.get('domain', os.environ.get(
                    'CHECKMATE_DOMAIN', 'mydomain.local'))
            name = 'CMDEP%s-db1.%s' % (deployment['id'][0:7], domain)
            # Call provider to give us a resource template
            resource = database.generate_template(deployment, service_name,
                    service, name=name)
            resources[str(resource_index)] = resource
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
        endpoint_providers = provider_tier['instances']
        LOG.debug("    These instances provide %s:%s: %s" % (resource_type,
                interface, endpoint_providers))

        # Wire them up
        name = "%s-%s" % (relation, provider_tier_name)
        if name in wires:
            name = "%s-%s" % (name, len(wires))
        wires[name] = {}
        for instance in instances:
            if 'relations' not in resources[instance]:
                resources[instance]['relations'] = {}
            for endpoint_provider in endpoint_providers:
                if 'relations' not in resources[endpoint_provider]:
                    resources[endpoint_provider]['relations'] = {}
                resources[instance]['relations'][name] = {'state': 'new'}
                resources[endpoint_provider]['relations'][name] = {'state':
                        'new'}
                LOG.debug("    New connection from %s:%s to %s:%s created: %s"
                        % (relation, instance, provider_tier_name,
                                endpoint_provider, name))
    resources['connections'] = wires
    deployment['resources'] = resources

    wf = create_workflow(deployment)

    return {'deployment': deployment, 'workflow': wf}
def check_deployment(deployment):
    """Validates deployment (a combination of components, blueprints, deployments,
    and environments)

    This is a simple, initial atempt at validation"""
    errors = []
    roots = ['components', 'blueprint', 'environment', 'deployment']
    values = ['name', 'prefix', 'inputs', 'includes']
    if deployment:
        allowed = roots[:]
        allowed.extend(values)
        for key, value in deployment.iteritems():
            if key not in allowed:
                errors.append("'%s' not a valid value. Only %s allowed" % (key,
                        ', '.join(allowed)))
    return errors
