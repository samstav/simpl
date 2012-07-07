# pylint: disable=E0611
import logging
import os
import sys
import uuid

from bottle import get, post, put, request, response, abort
from celery.app import app_or_default
from SpiffWorkflow.storage import DictionarySerializer

from checkmate import orchestrator
from checkmate.db import get_driver, any_id_problems
from checkmate.environments import Environment
from checkmate.exceptions import CheckmateException
from checkmate.common import schema
from checkmate.workflows import create_workflow
from checkmate.utils import write_body, read_body, extract_sensitive_data,\
        merge_dictionary, with_tenant, is_ssh_key

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

    errors = schema.validate(deployment, schema.DEPLOYMENT_FIELDS)
    if errors:
        abort(406, "Invalid deployment: %s" % '\n'.join(errors))

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

    errors = schema.validate(deployment, schema.DEPLOYMENT_FIELDS)
    if errors:
        abort(406, "Invalid deployment: %s" % '\n'.join(errors))

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

    errors = schema.validate(deployment, schema.DEPLOYMENT_FIELDS)
    if errors:
        abort(406, "Invalid deployment: %s" % '\n'.join(errors))

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

    result = orchestrator.run_workflow.delay(id, timeout=900)
    return result


def plan(id):
    deployment = db.get_deployment(id, with_secrets=True)
    if not deployment:
        abort(404, "No deployment with id %s" % id)
    return plan_dict(deployment)


def plan_dict(deployment):
    """DEPRECATED: Process a new checkmate deployment, plan for execution,
    create a context, and create a workflow.

    This creates placeholder tags that will be used for the actual creation
    of resources.

    :returns: dict of parsed deployment and workflow
    :param deployment: checkmate deployment dict
    """
    parsed_deployment = plan(deployment)
    context = get_context(deployment)
    workflow = create_workflow(parsed_deployment, context)

    return {'deployment': parsed_deployment, 'workflow': workflow}


def get_context(deployment):
    """Create context with creds and keys"""
    #
    context = dict(id=deployment['id'])

    #TODO: make this smarter
    creds = [p['credentials'][0] for key, p in
                    deployment['environment']['providers'].iteritems()
                    if key == 'common']
    if creds:
        creds = creds[0]
        context['username'] = creds['username']
        if 'apikey' in creds:
            context['apikey'] = creds['apikey']
        if 'password' in creds:
            context['password'] = creds['password']
    else:
        LOG.debug("No credentials supplied in environment/common/credentials")

    inputs = deployment.get('inputs', {})
    context['region'] = inputs.get('blueprint', {}).get('region')

    # Look in inputs:
    # Read in the public keys to be passed to newly created servers.
    os_keys = get_os_env_keys()

    environment = deployment.get('environment')
    if not environment:
        abort(406, "Environment not found. Nowhere to deploy to.")
    environment = Environment(environment)

    keys = get_keys(inputs, environment)
    if os_keys:
        keys.update(os_keys)

    if not keys:
        LOG.warn("No keys supplied. Less secure password auth will be used.")

    context['keys'] = keys
    return context


def plan(deployment):
    """Process a new checkmate deployment and plan for execution.

    This creates placeholder tags that will be used for the actual creation
    of resources.

    The logic is as follows:
    - find the blueprint in the deployment
    - get the components from the blueprint
    - identify dependencies (inputs/options and connections/relations)
    - build a list of resources to create
    - returns the parsed deployment

    :param deployment: checkmate deployment dict
    """
    LOG.info("Planning deployment '%s'" % deployment['id'])
    # Find blueprint and environment. Without those, there's nothing to plan!
    blueprint = deployment.get('blueprint')
    if not blueprint:
        abort(406, "Blueprint not found. Nothing to do.")
    environment = deployment.get('environment')
    if not environment:
        abort(406, "Environment not found. Nowhere to deploy to.")
    environment = Environment(environment)
    inputs = deployment.get('inputs', {})
    services = blueprint.get('services', {})
    relations = {}

    # The following are hashes with resource_type as the hash:
    requirements = {}  # list of interfaces needed by component
    provided = {}  # list of interfaces provided by other components
    available = {}  # interfaces available from environment

    #
    # Analyze Dependencies
    #
    _verify_required_blueprint_options_supplied(deployment)

    # Load providers
    providers = environment.get_providers()
    # Get interfaces available from environment
    for provider in providers.values():
        LOG.debug("%s provides %s" % (provider.__class__, provider.provides()))
        for item in provider.provides():
            resource_type = item.keys()[0]
            interface = item.values()[0]
            entry = dict(provider=provider, resource=resource_type)
            if interface in available:
                available[interface].append(entry)
                LOG.warning("More than one provider for '%s': %s" % (
                        interface, available[interface]))
            else:
                available[interface] = [entry]

    # Collect all requirements from components
    for service_name, service in services.iteritems():
        LOG.debug("Analyzing service %s" % service_name)
        components = service['components']
        if not isinstance(components, list):
            components = [components]
        for component in components:
            LOG.debug("  Config for %s", component['id'])
            # Check that the environment can provide this component
            if 'is' in component:
                klass = component['is']
                found = False
                for l in available.values():
                    for e in l:
                        if e['resource'] == klass:
                            found = True
                            break
                if not found:
                    abort(406, "Environment does not provide '%s'" % klass)
            # Save list of interfaces provided by which service
            if 'provides' in component:
                for resource_type, interface in component['provides']\
                        .iteritems():
                    if resource_type in provided:
                        provided[resource_type].append(interface)
                    else:
                        provided[resource_type] = [interface]
            # Save list of what interfaces are required by each service
            if 'requires' in component:
                for key, value in component['requires'].iteritems():
                    # Convert short form to long form before evaluating
                    if not isinstance(value, dict):
                        value = {'interface': value}
                    interface = value['interface']
                    if interface in requirements:
                        requirements[interface].append(service_name)
                    else:
                        requirements[interface] = [service_name]

    # Quick check that at least each interface is provided
    for required_interface in requirements.keys():
        if required_interface not in provided.values() and required_interface \
                not in available:
            msg = "Cannot satisfy requirement '%s' in deployment %s" % (
                    required_interface, deployment['id'])
            LOG.info(msg)
            abort(406, msg)
        # TODO: check that interfaces match between requirement and provider

    # Collect relations and verify service for relation exists
    for service_name, service in services.iteritems():
        if 'relations' in service:
            # Check that they all connect to valid service
            # TODO: check interfaces also match
            for key, relation in service['relations'].iteritems():
                if isinstance(relation, dict):
                    target = relation['service']
                else:
                    target = key
                if target not in services:
                    msg = "Cannot find service '%s' for '%s' to connect to " \
                          "in deployment %s" % (target, service_name,
                          deployment['id'])
                    LOG.info(msg)
                    abort(406, msg)
            # Collect all of them (converting short syntax to long)
            expanded = {}
            for key, value in service['relations'].iteritems():
                if isinstance(value, dict):
                    expanded[key] = value
                else:
                    # Generate name and expand
                    relation_name = '%s-%s' % (service_name, key)
                    expanded_relation = {
                            'interface': value,
                            'service': key,
                            }
                    expanded[relation_name] = expanded_relation
            relations[service_name] = expanded

    #
    # Build needed resource list
    #
    domain = inputs.get('domain', os.environ.get('CHECKMATE_DOMAIN',
                                                   'mydomain.local'))
    resources = {}
    resource_index = 0  # counter we use to increment as we create resources
    for service_name, service in services.iteritems():
        LOG.debug("Gather resources needed for service %s" % service_name)
        components = service['components']
        if not isinstance(components, list):
            components = [components]
        for component in components:
            resource_type = component.get('is', component['id'])

            host = None
            if 'requires' in component:
                for key, value in component['requires'].iteritems():
                    # Skip short form which implies a reference relationship
                    if not isinstance(value, dict):
                        continue
                    if value.get('relation', 'reference') == 'host':
                        host = key
                        host_interface = value['interface']
                        break
            if host:
                host_provider = available[host_interface][0]['provider']
                host_type = available[host_interface][0]['resource']

            provider = environment.select_provider(resource=resource_type)
            count = provider.get_deployment_setting(deployment, 'count',
                    resource_type=resource_type, service=service_name) or 1

            def add_resource(provider, deployment, service, service_name,
                    index, domain, resource_type, component_id):
                # Generate a default name
                name = 'CM-%s-%s%s.%s' % (deployment['id'][0:7], service_name,
                        index, domain)
                # Call provider to give us a resource template
                resource = provider.generate_template(deployment,
                        resource_type, service_name, name=name)
                resource['component'] = component_id
                # Add it to resources
                resources[str(resource_index)] = resource
                # Link resource to service
                if 'instances' not in service:
                    service['instances'] = []
                instances = service['instances']
                instances.append(str(resource_index))
                LOG.debug("  Adding %s with id %s" % (resources[str(
                        resource_index)]['type'], resource_index))
                return resource

            for index in range(count):
                if host:
                    # Obtain resource to host this one on
                    host_resource = add_resource(host_provider, deployment,
                            service, service_name, index + 1, domain,
                            host_type, component['id'])
                    host_index = str(resource_index)
                    resource_index += 1
                resource = add_resource(provider, deployment, service,
                        service_name, index + 1, domain, resource_type,
                        component['id'])
                resource_index += 1
                if host:
                    # Fill in relations on hosted resource
                    resource['hosted_on'] = str(resource_index - 2)
                    relation = dict(interface=host_interface, state='planned',
                            relation='host', target=host_index)
                    if 'relations' not in resource:
                        resource['relations'] = dict(host=relation)
                    else:
                        if 'host' in resource['relations']:
                            CheckmateException("Conflicting relation named "
                                    "'host' exists in service '%s'" %
                                    service_name)
                        resource['relations']['host'] = relation

                    # Fill in relations on hosting resource
                    # no need to fill in a full relation for host, so just
                    # populate and array
                    if 'hosts' in host_resource:
                        host_resource['hosts'].append(str(resource_index - 1))
                    else:
                        host_resource['hosts'] = [str(resource_index - 1)]

    # Create connections between components
    connections = {}
    LOG.debug("Wiring services and resources")
    for service_name, service_relations in relations.iteritems():
        LOG.debug("    For %s" % service_name)
        service = services[service_name]
        instances = service['instances']
        for name, relation in service_relations.iteritems():
            # Find what interface is needed
            target_interface = relation['interface']
            LOG.debug("  Looking for a provider supporting %s for the %s "
                    "service" % (target_interface, service_name))
            target_service_name = relation['service']
            target_service = services[target_service_name]

            # Verify target can provide requested interface
            target_components = target_service['components']
            if not isinstance(target_components, list):
                target_components = [target_components]
            found = []
            for component in target_components:
                if target_interface in component.get('provides', {})\
                        .values():
                        found.append(component)
            if not found:
                raise CheckmateException("'%s' service does not provide a "
                        "resource with an interface of type '%s', which is "
                        "needed by the '%s' relationship to '%s'" % (
                        target_service_name, target_interface, name,
                        service_name))
            if len(found) > 1:
                raise CheckmateException("'%s' has more than one resource "
                        "that provides an interface of type '%s', which is "
                        "needed by the '%s' relationship to '%s'. This causes "
                        "ambiguity. Additional information is needed to "
                        "identify which component to connect" % (
                        target_service_name, target_interface, name,
                        service_name))

            # Get list of source instances
            source_instances = {index: resources[index] for index in
                                instances}
            LOG.debug("    These instances need '%s' from the '%s' service: %s"
                    % (target_interface, target_service_name,
                    source_instances))

            # Get list of target instances
            target_instances = target_service['instances']
            LOG.debug("    These instances provide %s: %s" % (target_interface,
                    target_instances))

            # Wire them up (create relation entries under resources)
            connection_name = "%s-%s" % (service_name, target_service_name)
            if connection_name in connections:
                connection_name = "%s-%s" % (connection_name, len(connections))
            connections[connection_name] = {}
            for source_instance in source_instances:
                if 'relations' not in resources[source_instance]:
                    resources[source_instance]['relations'] = {}
                for target_instance in target_instances:
                    if 'relations' not in resources[target_instance]:
                        resources[target_instance]['relations'] = {}
                    # Add forward relation (from source to target)
                    resources[source_instance]['relations'][connection_name] \
                            = dict(state='planned', target=target_instance,
                                interface=target_interface)
                    # Add relation to target showing incoming from source
                    resources[target_instance]['relations'][connection_name] \
                            = dict(state='planned', source=source_instance,
                                interface=target_interface)
                    LOG.debug("    New connection from %s:%s to %s:%s "
                            "created: %s" % (service_name, source_instance,
                            target_service_name, target_instance,
                            connection_name))

    #Write resources and connections to deployment
    if connections:
        resources['connections'] = connections
    if resources:
        deployment['resources'] = resources

    return deployment


def _verify_required_blueprint_options_supplied(deployment):
    """Check that blueprint options marked 'required' are supplied.

    Raise error if not
    """
    blueprint = deployment['blueprint']
    if 'options' in blueprint:
        inputs = deployment.get('inputs', {})
        bp_inputs = inputs.get('blueprint')
        for key, option in blueprint['options'].iteritems():
            if (not 'default' in option) and \
                    option.get('required') in ['true', True]:
                if key not in bp_inputs:
                    abort(406, "Required blueprint input '%s' not supplied" %
                            key)


def get_os_env_keys():
    """Get keys if they are set in the os_environment"""
    keys = {}
    if ('CHECKMATE_PUBLIC_KEY' in os.environ and
            os.path.exists(os.path.expanduser(
                os.environ['CHECKMATE_PUBLIC_KEY']))):
        try:
            path = os.path.expanduser(os.environ['CHECKMATE_PUBLIC_KEY'])
            with file(path, 'r') as f:
                key = f.read()
            if is_ssh_key(key):
                keys['checkmate'] = {'public_key_ssh': key,
                        'public_key_path': path}
            else:
                keys['checkmate'] = {'public_key': key,
                        'public_key_path': path}
        except IOError as (errno, strerror):
            LOG.error("I/O error reading public key from CHECKMATE_PUBLIC_KEY="
                    "'%s' environment variable (%s): %s" % (
                            os.environ['CHECKMATE_PUBLIC_KEY'], errno,
                                                                strerror))
        except StandardError as exc:
            LOG.error("Error reading public key from CHECKMATE_PUBLIC_KEY="
                    "'%s' environment variable: %s" % (
                            os.environ['CHECKMATE_PUBLIC_KEY'], exc))
    return keys


def get_keys(inputs, environment):
    """Get keys from inputs or generate them if they are not there.

    Inputs can supply a 'client' public key to be added to all servers.

    Inputs can also supply environment private/public key pairs. If not, then
    a pair is generated.
    """
    keys = {}
    # Get 'client' keys
    if 'client_public_key' in inputs:
        if is_ssh_key(inputs['client_public_key']):
            abort("ssh public key must be in public_key_ssh field, not "
                    "client_public_key. client_public_key must be in PEM "
                    "format.")
        keys['client'] = {'public_key': inputs['client_public_key']}

    if 'client_public_key_ssh' in inputs:
        if not is_ssh_key(inputs['client_public_key_ssh']):
            abort("client_public_key_ssh input is not a valid ssh public key "
                    "string.")
        keys['client'] = {'public_key_ssh': inputs['client_public_key_ssh']}

    # Get 'environment' keys
    private_key = inputs.get('environment_private_key')
    if private_key is None or private_key == '=generate()':
        private, public = environment.generate_key_pair()
        keys['environment'] = dict(public_key=public['PEM'],
                public_key_ssh=public['ssh'], private_key=private['PEM'])
        if private_key == '=generate()':
            inputs['environment_private_key'] = private['PEM']
    else:
        # Private key was supplied, make sure we have or can get a public key
        results = {}
        if 'environment_public_key' in inputs:
            results['public_key'] = inputs['environment_public_key']
        if 'environment_public_key_ssh' in inputs:
            results['public_key_ssh'] = inputs['environment_public_key_ssh']
        if 'environment_public_key_ssh' not in results:
            # Generate public ssh key
            public_key = environment.get_ssh_public_key(private_key)
            results['public_key_ssh'] = public_key

        results['private_key'] = private['PEM']
        keys['environment'] = results

    return keys
