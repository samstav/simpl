import logging
import os
import uuid

# pylint: disable=E0611
from bottle import get, post, request, response, route, abort
from celery.task import task
from SpiffWorkflow import Workflow, Task
from SpiffWorkflow.storage import DictionarySerializer

from checkmate import keys
from checkmate import orchestrator
from checkmate.classes import ExtensibleDict
from checkmate.common import schema
from checkmate.db import get_driver, any_id_problems
from checkmate.environments import Environment
from checkmate.exceptions import CheckmateException, CheckmateDoesNotExist, \
        CheckmateValidationException, CheckmateBadState
from checkmate.providers import ProviderBase
from checkmate.workflows import create_workflow_deploy
from checkmate.utils import write_body, read_body, extract_sensitive_data, \
        merge_dictionary, with_tenant, is_ssh_key, get_time_string

LOG = logging.getLogger(__name__)
db = get_driver()


def _content_to_deployment(bottle_request, deployment_id=None, tenant_id=None):
    """Receives request content and puts it in a deployment

    :param bottle_request: the bottlepy request object
    :param deployment_id: the expected/requested ID
    :param tenant_id: the tenant ID in the request

    """
    entity = read_body(bottle_request)
    if 'deployment' in entity:
        entity = entity['deployment']  # Unwrap if wrapped
    if 'id' not in entity:
        entity['id'] = deployment_id or uuid.uuid4().hex
    if any_id_problems(entity['id']):
        raise CheckmateValidationException(any_id_problems(entity['id']))
    deployment = Deployment(entity)  # Also validates syntax
    if 'includes' in deployment:
        del deployment['includes']
    if 'tenantId' in deployment and tenant_id:
        assert deployment['tenantId'] == tenant_id, ("tenantId must match "
                                                     "with current tenant ID")
    else:
        assert tenant_id, "Tenant ID must be specified in deployment "
        deployment['tenantId'] = tenant_id
    return deployment


def _save_deployment(deployment, deployment_id=None, tenant_id=None):
    """Sync ID and tenant and save deployment

    :returns: saved deployment
    """
    if not deployment_id:
        if 'id' not in deployment:
            deployment_id = uuid.uuid4().hex
            deployment['id'] = deployment_id
        else:
            deployment_id = deployment['id']
    else:
        if 'id' not in deployment:
            deployment['id'] = deployment_id
        else:
            assert deployment_id == deployment['id'], ("Deployment ID does "
                                                       "not match "
                                                       "deploymentId")
    if 'tenantId' in deployment:
        if tenant_id:
            assert deployment['tenantId'] == tenant_id, ("tenantId must match "
                                                     "with current tenant ID")
        else:
            tenant_id = deployment['tenantId']
    else:
        assert tenant_id, "Tenant ID must be specified in deployment"
        deployment['tenantId'] = tenant_id
    body, secrets = extract_sensitive_data(deployment)
    return db.save_deployment(deployment_id, body, secrets,
                              tenant_id=tenant_id)


def _create_deploy_workflow(deployment, context):
    workflow = create_workflow_deploy(deployment, context)
    serializer = DictionarySerializer()
    serialized_workflow = workflow.serialize(serializer)
    return serialized_workflow


def _deploy(deployment, context):
    """Deploys a deployment and returns the workflow"""
    if deployment.get('status') != 'PLANNED':
        raise CheckmateBadState("Deployment '%s' is in '%s' status and must "
                                "be in 'PLANNED' status to be deployed" %
                                (deployment['id'], deployment.get('status')))
    deployment_keys = generate_keys(deployment)
    workflow = _create_deploy_workflow(deployment, context)
    workflow['id'] = deployment['id']  #TODO: need to support multiple workflows
    deployment['workflow'] = workflow['id']
    deployment['status'] = "LAUNCHED"

    body, secrets = extract_sensitive_data(workflow)
    db.save_workflow(workflow['id'], body, secrets,
                     tenant_id=deployment['tenantId'])

    _save_deployment(deployment)

    return workflow


#
# Deployments
#
@get('/deployments')
@with_tenant
def get_deployments(tenant_id=None):
    return write_body(db.get_deployments(tenant_id=tenant_id), request,
            response)


@get('/deployments/count')
@with_tenant
def get_deployments_count(tenant_id=None):
    """
    Get the number of deployments. May limit response to include all
    deployments for a particular tenant and/or blueprint

    :param:tenant_id: the (optional) tenant
    """
    return write_body({"count": len(db.get_deployments(tenant_id=tenant_id))},
            request, response)


@get("/deployments/count/<blueprint_id>")
@with_tenant
def get_deployments_by_bp_count(blueprint_id, tenant_id=None):
    ret = {"count": 0}
    deployments = db.get_deployments(tenant_id=tenant_id)
    if not deployments:
        LOG.debug("No deployments")
    for dep_id, dep in deployments.items():
        if "blueprint" in dep:
            LOG.debug("Found blueprint {} in deployment {}".format(dep.get("blueprint"), dep_id))
            if (blueprint_id == dep["blueprint"]) or \
            ("id" in dep["blueprint"] and blueprint_id == dep["blueprint"]["id"]):
                ret["count"] += 1
        else:
            LOG.debug("No blueprint defined in deployment {}".format(dep_id))
    return write_body(ret, request, response)


@post('/deployments')
@with_tenant
def post_deployment(tenant_id=None):
    deployment = _content_to_deployment(request, tenant_id=tenant_id)
    oid = str(deployment['id'])
    _save_deployment(deployment, deployment_id=oid, tenant_id=tenant_id)
    # Return response (with new resource location in header)
    if tenant_id:
        response.add_header('Location', "/%s/deployments/%s" % (tenant_id,
                                                                oid))
    else:
        response.add_header('Location', "/deployments/%s" % oid)

    #Assess work to be done & resources to be created
    parsed_deployment = plan(deployment, request.context)

    # Create a 'new deployment' workflow
    workflow = _deploy(parsed_deployment, request.context)

    #Trigger the workflow in the queuing service
    async_task = execute(oid)
    LOG.debug("Triggered workflow (task='%s')" % async_task)

    return write_body(parsed_deployment, request, response)


@post('/deployments/+parse')
@with_tenant
def parse_deployment(tenant_id=None):
    """Parse a deployment and return the parsed response"""
    deployment = _content_to_deployment(request, tenant_id=tenant_id)
    results = plan(deployment, request.context)
    return write_body(results, request, response)


@post('/deployments/+preview')
@with_tenant
def preview_deployment(tenant_id=None):
    """Parse and preview a deployment and its workflow"""
    deployment = _content_to_deployment(request, tenant_id=tenant_id)
    results = plan(deployment, request.context)
    workflow = _create_deploy_workflow(results, request.context)
    results['workflow'] = workflow
    return write_body(results, request, response)


@route('/deployments/<oid>', method=['PUT'])
@with_tenant
def update_deployment(oid, tenant_id=None):
    """Store a deployment on this server"""
    deployment = _content_to_deployment(request, deployment_id=oid,
                                        tenant_id=tenant_id)
    results = _save_deployment(deployment, deployment_id=oid,
                               tenant_id=tenant_id)
    # Return response (with new resource location in header)
    if tenant_id:
        response.add_header('Location', "/%s/deployments/%s" % (tenant_id,
                                                                oid))
    else:
        response.add_header('Location', "/deployments/%s" % oid)
    return write_body(results, request, response)


@route('/deployments/<oid>/+plan', method=['POST', 'GET'])
@with_tenant
def plan_deployment(oid, tenant_id=None):
    """Plan a NEW deployment and save it as PLANNED"""
    if any_id_problems(oid):
        abort(406, any_id_problems(oid))
    entity = db.get_deployment(oid, with_secrets=True)
    if not entity:
        raise CheckmateDoesNotExist('No deployment with id %s' % oid)
    if entity.get('status', 'NEW') != 'NEW':
        raise CheckmateBadState("Deployment '%s' is in '%s' status and must "
                                "be in 'NEW' to be planned" %
                                (oid, entity.get('status')))
    deployment = Deployment(entity)  # Also validates syntax
    planned_deployment = plan(deployment, request.context)
    results = _save_deployment(planned_deployment, deployment_id=oid,
                               tenant_id=tenant_id)
    return write_body(results, request, response)


@route('/deployments/<oid>/+deploy', method=['POST', 'GET'])
@with_tenant
def deploy_deployment(oid, tenant_id=None):
    """Deploy a NEW or PLANNED deployment and save it as DEPLOYED"""
    if any_id_problems(oid):
        raise CheckmateValidationException(any_id_problems(oid))
    entity = db.get_deployment(oid, with_secrets=True)
    if not entity:
        CheckmateDoesNotExist('No deployment with id %s' % oid)
    deployment = Deployment(entity)  # Also validates syntax
    if entity.get('status', 'NEW') == 'NEW':
        deployment = plan(deployment, request.context)
    if entity.get('status') != 'PLANNED':
        raise CheckmateBadState("Deployment '%s' is in '%s' status and must "
                                "be in 'PLANNED' or 'NEW' status to be "
                                "deployed" % (oid, entity.get('status')))

    # Create a 'new deployment' workflow
    workflow = _deploy(deployment, request.context)

    #Trigger the workflow
    async_task = execute(oid)
    LOG.debug("Triggered workflow (task='%s')" % async_task)

    return write_body(deployment, request, response)


@get('/deployments/<oid>')
@with_tenant
def get_deployment(oid, tenant_id=None):
    if 'with_secrets' in request.query:  # TODO: verify admin-ness
        entity = db.get_deployment(oid, with_secrets=True)
    else:
        entity = db.get_deployment(oid)
    if not entity:
        raise CheckmateDoesNotExist('No deployment with id %s' % oid)
    return write_body(entity, request, response)


@get('/deployments/<oid>/status')
@with_tenant
def get_deployment_status(oid, tenant_id=None):
    deployment = db.get_deployment(oid)
    if not deployment:
        abort(404, 'No deployment with id %s' % oid)

    resources = deployment.get('resources', {})
    results = {}
    workflow_id = deployment.get('workflow')
    if workflow_id:
        workflow = db.get_workflow(workflow_id)
        serializer = DictionarySerializer()
        wf = Workflow.deserialize(serializer, workflow)
        for task in wf.get_tasks(state=Task.ANY_MASK):
            if 'resource' in task.task_spec.defines:
                resource_id = str(task.task_spec.defines['resource'])
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


def execute(oid, timeout=180, tenant_id=None):
    """Process a checkmate deployment workflow

    Executes and moves the workflow forward.
    Retrieves results (final or intermediate) and updates them into
    deployment.

    :param id: checkmate deployment id
    :returns: the async task
    """
    if any_id_problems(oid):
        abort(406, any_id_problems(oid))

    deployment = db.get_deployment(oid)
    if not deployment:
        abort(404, 'No deployment with id %s' % oid)

    result = orchestrator.run_workflow.delay(oid, timeout=900)
    return result


def plan(deployment, context):
    """Process a new checkmate deployment and plan for execution.

    This creates placeholder tags that will be used for the actual creation
    of resources.

    The logic is as follows:
    - find the blueprint in the deployment
    - get the components from the blueprint
    - identify dependencies (inputs/options and connections/relations)
    - build a list of resources to create
    - returns the parsed Deployment

    :param deployment: checkmate deployment instance (dict)
    """
    assert context.__class__.__name__ == 'RequestContext'
    assert deployment.get('status') == 'NEW'
    assert isinstance(deployment, Deployment)

    LOG.info("Planning deployment '%s'" % deployment['id'])
    # Find blueprint and environment. Without those, there's nothing to plan!
    blueprint = deployment.get('blueprint')
    if not blueprint:
        abort(406, "Blueprint not found. Nothing to do.")
    environment = deployment.environment()
    if not environment:
        abort(406, "Environment not found. Nowhere to deploy to.")
    services = blueprint.get('services', {})
    relations = {}

    # The following are hashes with resource_type as the hash:
    requirements = {}  # list of interfaces needed by component
    provided = {}  # list of interfaces provided by other components

    #
    # Analyze Dependencies
    #
    _verify_required_blueprint_options_supplied(deployment)

    # Load providers
    providers = environment.get_providers(context)

    #Identify component providers and get the resolved components
    components = deployment.get_components(context)

    # Collect all requirements from components
    for service_name, component in components.iteritems():
        LOG.debug("Analyzing component %s requirements and needs in service %s"
                % (component['id'], service_name))

        # Save list of interfaces provided by which service
        if 'provides' in component:
            for entry in component['provides']:
                resource_type, interface = entry.items()[0]
                if resource_type in provided:
                    provided[resource_type].append(interface)
                else:
                    provided[resource_type] = [interface]
        # Save list of what interfaces are required by each service
        if 'requires' in component:
            for entry in component['requires']:
                key, value = entry.items()[0]
                # Convert short form to long form before evaluating
                if not isinstance(value, dict):
                    value = {'interface': value}
                interface = value['interface']
                if interface in requirements:
                    requirements[interface].append(service_name)
                else:
                    requirements[interface] = [service_name]

    # Collect relations and verify service for relation exists
    LOG.debug("Analyzing relations")
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
    LOG.debug("All relations successfully matched with target services")

    #
    # Build needed resource list
    #
    resources = {}
    resource_index = 0  # counter we use to increment as we create resources
    for service_name, service in services.iteritems():
        LOG.debug("Gather resources needed for service '%s'" % service_name)
        service_components = components[service_name]
        if not isinstance(service_components, list):
            service_components = [service_components]
        for component in service_components:
            if 'is' in component:
                resource_type = component['is']
            else:
                resource_type = component['id']
                LOG.debug("Component '%s' has no type specified using the "
                        "'is' attribute so the id of the component is being "
                        "used as the type" % component['id'])

            # Check for hosting relationship
            host = None
            if 'requires' in component:
                for entry in component['requires']:
                    key, value = entry.items()[0]
                    # Skip short form not called host (reference relationship)
                    if not isinstance(value, dict):
                        if key != 'host':
                            continue
                        value = dict(interface=value, relation='host')
                    if value.get('relation', 'reference') == 'host':
                        LOG.debug("Host needed for %s" % component['id'])
                        host = key
                        host_type = key if key != 'host' else None
                        host_interface = value['interface']
                        host_provider = environment.select_provider(context,
                                resource=host_type, interface=host_interface)
                        found = host_provider.find_components(context,
                                resource=host_type, interface=host_interface)
                        if found:
                            if len(found) == 1:
                                host_component = found[0]
                                host_type = host_component['is']
                            else:
                                raise CheckmateException("More than one "
                                        "component offers '%s:%s' in provider "
                                        "%s: %s" % (host_type, host_interface,
                                        host_provider.key, ', '.join([c['id']
                                        for c in found])))
                        else:
                            raise CheckmateException("No components found "
                                        "that offer '%s:%s' in provider %s" % (
                                        host_type, host_interface,
                                        host_provider.key))
                        break

            provider = component.provider()
            if not provider:
                raise CheckmateException("No provider could be found for the "
                        "'%s' resource in component '%s'" % (resource_type,
                        component['id']))
            count = deployment.get_setting('count', provider_key=provider.key,
                    resource_type=resource_type, service_name=service_name,
                    default=1)

            def add_resource(provider, deployment, service, service_name,
                    index, domain, resource_type, component_id=None):
                # Generate a default name
                name = 'CM-%s-%s%s.%s' % (deployment['id'][0:7], service_name,
                        index, domain)
                # Call provider to give us a resource template
                resource = provider.generate_template(deployment,
                        resource_type, service_name, context, name=name)
                if component_id:
                    resource['component'] = component_id
                # Add it to resources
                resources[str(resource_index)] = resource
                resource['index'] = str(resource_index)
                # Link resource to service
                if 'instances' not in service:
                    service['instances'] = []
                instances = service['instances']
                instances.append(str(resource_index))
                LOG.debug("  Adding a %s resource with resource key %s" % (
                        resources[str(resource_index)]['type'],
                        resource_index))
                Resource.validate(resource)
                return resource

            domain = deployment.get_setting('domain',
                    provider_key=provider.key, resource_type=resource_type,
                    service_name=service_name,
                    default=os.environ.get('CHECKMATE_DOMAIN',
                                                   'checkmate.local'))
            for index in range(count):
                if host:
                    # Obtain resource to host this one on
                    LOG.debug("Creating %s resource to host %s/%s" % (
                            host_type, service_name, component['id']))
                    host_resource = add_resource(host_provider, deployment,
                            service, service_name, index + 1,
                            domain, host_type,
                            component_id=host_component['id'])
                    host_index = str(resource_index)
                    resource_index += 1

                resource = add_resource(provider, deployment, service,
                        service_name, index + 1, domain,
                        resource_type, component_id=component['id'])
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
                    # populate an array
                    if 'hosts' in host_resource:
                        host_resource['hosts'].append(str(resource_index - 1))
                    else:
                        host_resource['hosts'] = [str(resource_index - 1)]
                    LOG.debug("Created hosting relation from %s to %s:%s" % (
                            resource_index - 1, host_index, host_interface))

    # Create connections between components
    connections = {}
    LOG.debug("Wiring services and resources")
    for service_name, service_relations in relations.iteritems():
        LOG.debug("  For %s" % service_name)
        service = services[service_name]
        instances = service['instances']
        for name, relation in service_relations.iteritems():
            # Find what interface is needed
            target_interface = relation['interface']
            LOG.debug("  Looking for a provider supporting '%s' for the '%s' "
                    "service" % (target_interface, service_name))
            target_service_name = relation['service']
            target_service = services[target_service_name]

            # Verify target can provide requested interface
            target_components = components[target_service_name]
            if not isinstance(target_components, list):
                target_components = [target_components]
            target_component_ids = [c['id'] for c in target_components]
            found = []
            for component in target_components:
                provides = component.get('provides', [])
                for entry in provides:
                    if target_interface == entry.values()[0]:
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
            LOG.debug("    Instances %s need '%s' from the '%s' service"
                    % (instances, target_interface, target_service_name))

            # Get list of target instances
            target_instances = [i for i in target_service.get('instances', [])
                    if resources[i].get('component') in target_component_ids]
            LOG.debug("    Instances %s provide %s" % (target_instances,
                    target_interface))

            # Wire them up (create relation entries under resources)
            connection_name = "%s-%s" % (service_name, target_service_name)
            if connection_name in connections:
                connection_name = "%s-%s" % (connection_name, len(connections))
            connections[connection_name] = dict(
                    interface=relation['interface'])
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
                    LOG.debug("    New connection '%s' from %s:%s to %s:%s "
                            "created" % (connection_name, service_name,
                            source_instance, target_service_name,
                            target_instance))

    #Write resources and connections to deployment
    if connections:
        resources['connections'] = connections
    if resources:
        deployment['resources'] = resources

    deployment['status'] = 'PLANNED'
    LOG.info("Deployment '%s' planning complete and status changed to %s" %
            (deployment['id'], deployment['status']))
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
    dkeys = {}
    if ('CHECKMATE_PUBLIC_KEY' in os.environ and
            os.path.exists(os.path.expanduser(
                os.environ['CHECKMATE_PUBLIC_KEY']))):
        try:
            path = os.path.expanduser(os.environ['CHECKMATE_PUBLIC_KEY'])
            with file(path, 'r') as f:
                key = f.read()
            if is_ssh_key(key):
                dkeys['checkmate'] = {'public_key_ssh': key,
                        'public_key_path': path}
            else:
                dkeys['checkmate'] = {'public_key': key,
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
    return dkeys


def get_client_keys(inputs):
    """Get/generate client-supplied or requested keys keys

    Inputs can supply a 'client' public key to be added to all servers or
    specify a command to generate the keys.
    """
    results = {}
    if 'client_public_key' in inputs:
        if is_ssh_key(inputs['client_public_key']):
            abort(406, "ssh public key must be in client_public_key_ssh "
                  "field, not client_public_key. client_public_key must be in "
                  "PEM format.")
        results['client'] = {'public_key': inputs['client_public_key']}

    if 'client_public_key_ssh' in inputs:
        if not is_ssh_key(inputs['client_public_key_ssh']):
            abort(406, "client_public_key_ssh input is not a valid ssh public "
                    "key string: %s" % inputs['client_public_key_ssh'])
        results['client'] = {'public_key_ssh': inputs['client_public_key_ssh']}
    return results


def generate_keys(deployment):
    """Generates keys for the deployment.

    Generates:
        private_key
        public_key
        public_key_ssh
    """
    dkeys = deployment.get('resources', {}).get('keys', {})
    results = {}
    private_key = dkeys.get('private_key')
    if private_key is None:
        private, public = keys.generate_key_pair()
        results.update(dict(public_key=public['PEM'],
                public_key_ssh=public['ssh'], private_key=private['PEM']))
    else:
        # Private key was supplied, make sure we have or can get a public key
        if 'public_key' not in dkeys:
            results['public_key'] = keys.get_public_key(private_key)
        if 'public_key_ssh' not in results:
            public_key = keys.get_ssh_public_key(private_key)
            results['public_key_ssh'] = public_key

        results['private_key'] = private_key

    if results:
        if 'resources' not in deployment:
            deployment['resources'] = {}
        if 'keys' not in deployment['resources']:
            deployment['resources']['keys'] = {}
        deployment['resources']['keys'].update(results)

    return results


class Resource():
    def __init__(self, key, obj):
        Resource.validate(obj)
        self.key = key
        self.dict = obj

    @classmethod
    def validate(cls, obj):
        errors = schema.validate(obj, schema.RESOURCE_SCHEMA)
        if errors:
            raise CheckmateValidationException("Invalid resource: %s" %
                    '\n'.join(errors))

    def get_settings(self, deployment, context, provider):
        """Get all settings for this resource

        :param deployment: the dict of the deployment
        :param context: the current planning context
        :param provider: the instance of the provider (subclasses ProviderBase)
        """
        assert isinstance(provider, ProviderBase)
        component = provider.get_component(self.dict['component'])
        if not component:
            raise CheckmateException("Could not find component '%s' in "
                    "provider %s.%s's catalog" % (self.dict['component'],
                    provider.vendor, provider.name))


class Deployment(ExtensibleDict):
    """A checkmate deployment.

    Acts like a dict. Includes validation, setting logic and other useful
    methods.
    Holds the Environment and providers during the processing of a deployment
    and creation of a workflow
    """
    def __init__(self, *args, **kwargs):
        ExtensibleDict.__init__(self, *args, **kwargs)
        self._environment = None

        if 'status' not in self:
            self['status'] = 'NEW'
        if 'created' not in self:
            self['created'] = get_time_string()

    @classmethod
    def validate(cls, obj):
        errors = schema.validate(obj, schema.DEPLOYMENT_SCHEMA)
        errors.extend(schema.validate_inputs(obj))
        if errors:
            raise CheckmateValidationException("Invalid %s: %s" % (
                    cls.__name__, '\n'.join(errors)))

    def environment(self):
        if self._environment is None:
            entity = self.get('environment')
            if entity:
                self._environment = Environment(entity)
        return self._environment

    def inputs(self):
        return self.get('inputs', {})

    def settings(self):
        """Returns (inits if does not exist) a reference to the deployment
        settings

        Note: this is to be used instead of the old context object
        """
        if hasattr(self, '_settings'):
            return getattr(self, '_settings')

        results = {}

        #TODO: make this smarter
        try:
            creds = [p['credentials'][0] for key, p in
                            self['environment']['providers'].iteritems()
                            if key == 'common']
            if creds:
                creds = creds[0]
                results['username'] = creds['username']
                if 'apikey' in creds:
                    results['apikey'] = creds['apikey']
                if 'password' in creds:
                    results['password'] = creds['password']
            else:
                LOG.debug("No credentials supplied in environment/common/"
                        "credentials")
        except Exception as exc:
            LOG.debug("No credentials supplied in environment/common/"
                        "credentials")

        inputs = self.inputs()
        results['region'] = inputs.get('blueprint', {}).get('region')

        # Look in inputs:
        # Read in the public keys to be passed to newly created servers.
        os_keys = get_os_env_keys()

        all_keys = get_client_keys(inputs)
        if os_keys:
            all_keys.update(os_keys)
        deployment_keys = self.get('resources', {}).get('keys')
        if deployment_keys:
            all_keys['deployment'] = deployment_keys

        if not all_keys:
            LOG.warn("No keys supplied. Less secure password auth will be "
                    "used.")

        results['keys'] = all_keys

        results['domain'] = inputs.get('domain', os.environ.get(
                    'CHECKMATE_DOMAIN', 'checkmate.local'))
        self._settings = results
        return results

    def get_setting(self, name, resource_type=None,
                service_name=None, provider_key=None, default=None):
        """Find a value that an option was set to.

        Look in this order:
        - start with the deployment inputs where the paths are:
            inputs/blueprint
            inputs/providers/:provider
        - finally look at the component defaults

        :param name: the name of the setting
        :param service: the name of the service being evaluated
        :param resource_type: the type of the resource being evaluated (ex.
                compute, database)
        :param default: value to return if no match found
        """
        if service_name:
            result = self._get_input_service_override(name, service_name,
                    resource_type=resource_type)
            if result:
                return result

        if provider_key:
            result = self._get_input_provider_option(name, provider_key,
                    resource_type=resource_type)
            if result:
                return result

        result = self._get_input_blueprint_option_constraint(name,
                service_name=service_name, resource_type=resource_type)
        if result:
            return result

        result = self._get_input_simple(name)
        if result:
            return result

        result = self._get_input_global(name)
        if result:
            return result

        result = self._get_environment_setting(name, provider_key, service_name)
        if result:
            return result


        return default

    def _get_input_global(self, name):
        """Get a setting directly under inputs"""
        inputs = self.inputs()
        if name in inputs:
            result = inputs[name]
            LOG.debug("Found setting '%s' in inputs. %s=%s" %
                    (name, name, result))
            return result

    def _get_input_simple(self, name):
        """Get a setting directly from inputs/blueprint"""
        inputs = self.inputs()
        if 'blueprint' in inputs:
            blueprint_inputs = inputs['blueprint']
            # Direct, simple entry
            if name in blueprint_inputs:
                result = blueprint_inputs[name]
                LOG.debug("Found setting '%s' in inputs/blueprint. %s=%s" %
                        (name, name, result))
                return result

    def _get_input_blueprint_option_constraint(self, name, service_name=None,
            resource_type=None):
        """Get a setting implied through blueprint option constraint

        :param name: the name of the setting
        :param service_name: the name of the service being evaluated
        """
        blueprint = self['blueprint']
        if 'options' in blueprint:
            options = blueprint['options']
            for key, option in options.iteritems():
                if 'constrains' in option:  # the verb 'constrains' (not noun)
                    for constraint in option['constrains']:
                        if self.constraint_applies(constraint, name,
                                service_name=service_name,
                                resource_type=resource_type):
                            # Find in inputs or use default if available
                            result = self._get_input_simple(key)
                            if result:
                                LOG.debug("Found setting '%s' from constraint "
                                        "in blueprint input '%s'. %s=%s" % (
                                        name, key, name, result))
                                return result
                            if 'default' in option:
                                result = option['default']
                                LOG.debug("Default setting '%s' obtained from "
                                        "constraint in blueprint input '%s': "
                                        "default=%s" % (name, key, result))
                                return result

    def constraint_applies(self, constraint, name, resource_type=None,
                service_name=None):
        """Checks if a constraint applies

        :param constraint: the constraint dict
        :param name: the name of the setting
        :param resource_type: the resource type (ex. compute)
        :param service_name: the name of the service being evaluated
        """
        if 'resource_type' in constraint:
            if resource_type is None or \
                    constraint['resource_type'] != resource_type:
                return False
        if 'setting' in constraint:
            if constraint['setting'] != name:
                return False
        if 'service' in constraint:
            if service_name is None or constraint['service'] != service_name:
                return False
        LOG.debug("Constraint '%s' for '%s' applied to '%s/%s'" % (
                constraint, name, service_name, resource_type))
        return True

    def _get_input_service_override(self, name, service_name,
            resource_type=None):
        """Get a setting applied through a deployment setting on a service

        Params are ordered similar to how they appear in yaml/json::
            inputs/services/:id/:resource_type/:option-name

        :param service_name: the name of the service being evaluated
        :param resource_type: the resource type (ex. compute)
        :param name: the name of the setting
        """
        inputs = self.inputs()
        if 'services' in inputs:
            services = inputs['services']
            if service_name in services:
                service_object = services[service_name]
                if resource_type in service_object:
                    options = service_object[resource_type]
                    if name in options:
                        result = options[name]
                        LOG.debug("Found setting '%s' as service "
                                "setting in blueprint/services/%s/%s'. %s=%s"
                                % (name, service_name, resource_type, name,
                                result))
                        return result

    def _get_input_provider_option(self, name, provider_key,
            resource_type=None):
        """Get a setting applied through a deployment setting to a provider

        Params are ordered similar to how they appear in yaml/json::
            inputs/providers/:id/[:resource_type/]:option-name

        :param name: the name of the setting
        :param provider_key: the key of the provider in question
        :param resource_type: the resource type (ex. compute)
        """
        inputs = self.inputs()
        if 'providers' in inputs:
            providers = inputs['providers']
            if provider_key in providers:
                provider = providers[provider_key]
                if resource_type in provider:
                    options = provider[resource_type]
                    if options and name in options:
                        result = options[name]
                        LOG.debug("Found setting '%s' as provider "
                                "setting in blueprint/providers/%s/%s'. %s=%s"
                                % (name, provider_key, resource_type, name,
                                result))
                        return result

    def _get_environment_setting(self, name, provider_key, service_name):
        environment = self.environment()
        providers = environment.dict['providers']
        if provider_key in providers:
            settings = providers[provider_key]
            if service_name in settings:
                options = settings[service_name]
                for option in options:
                    if name in option:
                        result = option[name]
                        LOG.debug("Found setting '%s' in environment" % name)   
                        return result

    def get_components(self, context):
        """Collect all requirements from components

        :param context: the call context. Component catalog may depend on
                current context
        :returns: hash of service_name/Component
        """
        results = {}
        services = self['blueprint'].get('services', {})
        for service_name, service in services.iteritems():
            service_component = service['component']
            LOG.debug("Identifying component '%s' for service '%s'" % (
                    service_component, service_name))
            assert not isinstance(service_component, list)  # deprecated syntax
            component = self.environment().find_component(service_component,
                    context)
            if not component:
                raise CheckmateException("Could not resolve component '%s'"
                        % service_component)
            LOG.debug("Component '%s' identified as '%s' for service '%s'" % (
                    service_component, component['id'], service_name))
            results[service_name] = component
        return results

    def on_resource_postback(self, contents):
        """Called to merge in contents when a postback with new resource data
        is received.

        Translates values to canonical names. Iterates to one level of depth to
        handle postbacks that write to instance key"""
        if contents:
            if not isinstance(contents, dict):
                raise CheckmateException("Postback value was not a dictionary")

            # Find targets and merge in values appropriately
            for key, value in contents.iteritems():
                if key.startswith('instance:'):
                    # Find the resource
                    resource_id = key.split(':')[1]
                    resource = self['resources'][resource_id]
                    if not resource:
                        raise IndexError("Resource %s not found" % resource_id)
                    # Check the value
                    if not isinstance(value, dict):
                        raise CheckmateException("Postback value for instance "
                                "'%s' was not a dictionary" % resource_id)
                    # Canonicalize it
                    value = schema.translate_dict(value)
                    # Merge it in
                    if 'instance' not in resource:
                        resource['instance'] = {}
                    LOG.debug("Merging postback data for resource %s: %s" % (
                            resource_id, value), extra=dict(data=resource))
                    merge_dictionary(resource['instance'], value)

                elif key.startswith('connection:'):
                    # Find the connection
                    connection_id = key.split(':')[1]
                    connection = self['connections'][connection_id]
                    if not connection:
                        raise IndexError("Connection %s not found" %
                                connection_id)
                    # Check the value
                    if not isinstance(value, dict):
                        raise CheckmateException("Postback value for "
                                "connection '%s' was not a dictionary" %
                                connection_id)
                    # Canonicalize it
                    value = schema.translate_dict(value)
                    # Merge it in
                    LOG.debug("Merging postback data for connection %s: %s" % (
                            connection_id, value), extra=dict(data=connection))
                    merge_dictionary(connection, value)
                else:
                    if isinstance(value, dict):
                        value = schema.translate_dict(value)
                    else:
                        value = schema.translate(value)
                    raise NotImplementedError("Global post-back values not "
                            "yet supported: %s" % key)


@task
def resource_postback(deployment_id, contents):
    """Accepts back results from a remote call and updates the deployment with
    the result data for a specific resource.

    The data updated can be:
    - a value: usually not tied to a resource or relation
    - an instance value (with the instance id appended with a colon):]
        {'instance:0':
            {'field_name': value}
        }
    - an interface value (under interfaces/interface_name)
        {'instance:0':
            {'interfaces':
                {'mysql':
                    {'username': 'johnny', ...}
                }
            }
        }
    - a connection value (under connection\:name):
        {'connection:web-backend':
            {'interface': 'mysql',
            'field_name': value}
        }
        Note: connection 'interface' is always included.
        Note: connection:host always refers to the hosting connection if there

    The contents are a hash (dict) of all the above
    """
    deployment = db.get_deployment(deployment_id, with_secrets=True)
    if not deployment:
        raise IndexError("Deployment %s not found" % deployment_id)

    deployment = Deployment(deployment)
    deployment.on_resource_postback(contents)

    body, secrets = extract_sensitive_data(deployment)
    db.save_deployment(deployment_id, body, secrets)

    LOG.debug("Updated deployment %s with post-back" % deployment_id,
            extra=dict(data=contents))
