#!/usr/bin/env python
from bottle import abort
import logging
import os

from checkmate.db import get_driver
from checkmate.workflows import create_workflow

LOG = logging.getLogger(__name__)
db = get_driver('checkmate.db.sql.Driver')


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
