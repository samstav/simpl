import copy
import logging
import os

from checkmate.deployment import (Deployment, Resource,
                                  verify_required_blueprint_options_supplied)
from checkmate import keys
from checkmate.classes import ExtensibleDict
from checkmate.common import schema
from checkmate.db import get_driver
from checkmate.environments import Environment
from checkmate.exceptions import CheckmateException,\
    CheckmateValidationException
from checkmate.providers import ProviderBase
from checkmate.utils import extract_sensitive_data, \
    merge_dictionary, is_ssh_key, get_time_string, dict_to_yaml
from bottle import abort

LOG = logging.getLogger(__name__)
DB = get_driver()


class Plan(ExtensibleDict):
    """Analyzes a Checkmate deployment and persists the analysis results

    This class will do the following:
    - identify which components the blueprint calls for
    - figure out how to connect the components based on relations and
      requirements
    - save decisions such as which provider and which component were selected,
      how requirements were met, how relations were resolved

    The data is stored in this structure:
    ```
    services:
      {service}:
        component:
          id: {component_id}:
          provider: {key}
          requires:
            {key}:
              satisfied-by:
                ...
          provides:
            key:
              ...
          connections:
            {key}:
              target | source: {service}
    ```

    Each `requires` entry gets a `satisfied-by` entry.

    Services can also have an `extra-components` map with additional components
    loaded to meet requirements within the service.

    Usage:

    Instantiate the class with a deployment and context, then call plan(),
    which will return all planned resources.

    The class behaves like a dict and will contain the analysis results.
    The resources attribute will contain the planned resources as well.

    """

    def __init__(self, deployment, *args, **kwargs):
        ExtensibleDict.__init__(self, *args, **kwargs)

        self.deployment = deployment
        self.resources = {}
        self.connections = {}

        # Find blueprint and environment. Otherwise, there's nothing to plan!
        self.blueprint = deployment.get('blueprint')
        if not self.blueprint:
            raise CheckmateValidationException("Blueprint not found. Nothing "
                                               "to do.")
        self.environment = self.deployment.environment()
        if not self.environment:
            raise CheckmateValidationException("Environment not found. "
                                               "Nowhere to deploy to.")

        # Quick validations
        verify_required_blueprint_options_supplied(deployment)

    def plan(self, context):
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

        # Should use self. reference throughout, but done this way to
        # limit changes to ported code.
        deployment = self.deployment
        resources = self.resources
        connections = self.connections
        blueprint = self.blueprint
        environment = self.environment

        assert deployment.get('status') == 'NEW'
        assert isinstance(deployment, Deployment)

        LOG.info("Planning (legacy) deployment '%s'" % deployment['id'])
        # Find blueprint and environment. Without those, there's nothing to plan!
        if not blueprint:
            abort(406, "Blueprint not found. Nothing to do.")
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
        verify_required_blueprint_options_supplied(deployment)

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
                        if 'service' in relation:
                            target = relation['service']
                        else:
                            target = service_name
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
                            host_provider = (environment.select_provider(context,
                                             resource=host_type,
                                             interface=host_interface))
                            if not host_provider:
                                raise (CheckmateException("No provider found for "
                                       "%s:%s to host %s" % (host_type or '*',
                                       host_interface or '*', component['id'])))
                            found = (host_provider.find_components(context,
                                     resource=host_type, interface=host_interface))
                            if found:
                                if len(found) == 1:
                                    host_component = found[0]
                                    host_type = host_component['is']
                                else:
                                    raise (CheckmateException("More than one "
                                           "component offers '%s:%s' in provider "
                                           "%s: %s" % (host_type or '*',
                                           host_interface, host_provider.key,
                                           ', '.join([c['id'] for c in found]))))
                            else:
                                raise (CheckmateException("No components found "
                                       "that offer '%s:%s' in provider %s" % (
                                       host_type or '*', host_interface,
                                       host_provider.key)))
                            break

                provider = component.provider
                if not provider:
                    raise CheckmateException("No provider could be found for the "
                                             "'%s' resource in component '%s'" %
                                             (resource_type, component['id']))
                count = (deployment.get_setting('count', provider_key=provider.key,
                         resource_type=resource_type, service_name=service_name,
                         default=1))

                def add_resource(provider, deployment, service, service_name,
                                 index, domain, resource_type, component_id=None):
                    """ Add a new resource to Deployment """
                    # Generate a default name
                    name = 'CM-%s-%s%s.%s' % (deployment['id'][0:7], service_name,
                                              index, domain)
                    # Call provider to give us a resource template
                    resource = (provider.generate_template(deployment,
                                resource_type, service_name, context, name=name))
                    if component_id:
                        resource['component'] = component_id
                    # Add it to resources
                    resources[str(resource_index)] = resource
                    resource['index'] = str(resource_index)
                    LOG.debug("  Adding a %s resource with resource key %s" % (
                              resources[str(resource_index)]['type'],
                              resource_index))
                    Resource.validate(resource)
                    return resource

                domain = (deployment.get_setting('domain',
                          provider_key=provider.key, resource_type=resource_type,
                          service_name=service_name,
                          default=os.environ.get('CHECKMATE_DOMAIN',
                                                 'checkmate.local')))
                for index in range(count):
                    if host:
                        # Obtain resource to host this one on
                        LOG.debug("Creating %s resource to host %s/%s" % (
                                  host_type, service_name, component['id']))
                        host_resource = (add_resource(host_provider, deployment,
                                         service, service_name, index + 1,
                                         domain, host_type,
                                         component_id=host_component['id']))
                        host_index = str(resource_index)
                        resource_index += 1

                    resource = (add_resource(provider, deployment, service,
                                service_name, index + 1, domain,
                                resource_type, component_id=component['id']))
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
                                                   "'host' exists in service "
                                                   "'%s'" % service_name)
                            # wire up any information the component wants to get
                            #from its host
                            for relation in resource['relations'].values():
                                if ((relation.get('interface', '') == 'host' and
                                    'service' not in relation)):
                                        relation['target'] = host_index
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
        LOG.debug("Wiring services and resources")
        for service_name, service_relations in relations.iteritems():
            LOG.debug("  For %s" % service_name)
            service = services[service_name]
            for name, relation in service_relations.iteritems():
                # Find what interface is needed
                target_interface = relation['interface']
                LOG.debug("  Looking for a provider supporting '%s' for the '%s' "
                          "service" % (target_interface, service_name))
                if 'service' in relation:
                    target_service_name = relation['service']
                else:
                    target_service_name = service_name
                # Verify target can provide requested interface
                target_components = components[target_service_name]
                if not isinstance(target_components, list):
                    target_components = [target_components]
                target_component_ids = [c['id'] for c in target_components]
                found = []
                for component in target_components:
                    if target_interface == 'host':
                        if 'host' in [k for d in component.get('requires', [])
                                      for k in d.keys()]:
                            found.append(component)
                        else:
                            raise CheckmateException("%s service does not require "
                                                     "a host and cannot satisfy "
                                                     "relation %s of service %s" %
                                                     (target_service_name, name,
                                                      service_name))
                    else:
                        provides = component.get('provides', [])
                        for entry in provides:
                            if target_interface == entry.values()[0]:
                                found.append(component)
                if not found:
                    raise (CheckmateException("'%s' service does not provide a "
                           "resource with an interface of type '%s', which is "
                           "needed by the '%s' relationship to '%s'" % (
                           target_service_name, target_interface, name,
                           service_name)))
                if target_interface != 'host' and len(found) > 1:
                    raise (CheckmateException("'%s' has more than one resource "
                           "that provides an interface of type '%s', which is "
                           "needed by the '%s' relationship to '%s'. This causes "
                           "ambiguity. Additional information is needed to "
                           "identify which component to connect" % (
                           target_service_name, target_interface, name,
                           service_name)))

                # Get hash of source instances (exclude the hosts unless its
                # specifically requested)
                source_instances = {index: resource
                                    for index, resource in resources.iteritems()
                                    if resource['service'] == service_name and
                                    'hosts' not in resource}
                LOG.debug("    Instances %s need '%s' from the '%s' service"
                          % (source_instances.keys(), target_interface,
                          target_service_name))

                # Get list of target instances
                if target_interface == 'host':
                    target_instances = [
                        resource['hosted_on'] for index, resource in
                        resources.iteritems()
                        if resource['service'] == target_service_name
                        and resource.get('component') in target_component_ids]
                else:
                    target_instances = [
                        index for index, resource in resources.iteritems()
                        if resource['service'] == target_service_name
                        and resource.get('component') in target_component_ids]
                LOG.debug("    Instances %s provide %s" % (target_instances,
                          target_interface))

                # Wire them up (create relation entries under resources)
                connections[name] = dict(interface=relation['interface'])
                if 'host' == target_interface and "service" not in relation:
                    # relation is from component to its host
                    for source_instance, resource in source_instances.iteritems():
                        target_instance = resource['hosted_on']
                        if 'relations' not in resource:
                            resource['relations'] = {}
                        resource['relations'][name] = \
                            dict(state='planned', target=target_instance,
                                 interface=target_interface, name=name)
                        if 'relations' not in resources[target_instance]:
                            resources[target_instance]['relations'] = {}
                        resources[target_instance]['relations'][name] = \
                            dict(state='planned', source=source_instance,
                                 interface=target_interface, name=name)
                        if 'attribute' in relation:
                            resources[source_instance]['relations'][name]\
                                .update({'attribute': relation['attribute']})
                            resources[target_instance]['relations'][name]\
                                .update({'attribute': relation['attribute']})
                else:
                    for source_instance in source_instances:
                        if 'relations' not in resources[source_instance]:
                            resources[source_instance]['relations'] = {}
                        source_relation = '-'.join([name, source_instance])
                        for target_instance in target_instances:
                            target_relation = '-'.join([name, target_instance])
                            if 'relations' not in resources[target_instance]:
                                resources[target_instance]['relations'] = {}
                            # Add forward relation (from source to target)
                            srcrels = resources[source_instance]['relations']
                            srcrels[target_relation] \
                                = dict(state='planned', target=target_instance,
                                       interface=target_interface, name=name)
                            # Add relation to target showing incoming from source
                            trgrels = resources[target_instance]['relations']
                            trgrels[source_relation] \
                                = dict(state='planned', source=source_instance,
                                       interface=target_interface, name=name)
                            if 'attribute' in relation:
                                srcrels[target_relation]. \
                                    update({'attribute': relation['attribute']})
                                trgrels[source_relation]. \
                                    update({'attribute': relation['attribute']})
                            LOG.debug("  New connection '%s' from %s:%s to %s:%s "
                                      "created" % (name, service_name,
                                      source_instance, target_service_name,
                                      target_instance))

        # Generate static resources
        for key, resource in blueprint.get('resources', {}).iteritems():
            component = environment.find_component(resource, context)
            if component:
                # Generate a default name
                name = 'CM-%s-shared%s.%s' % (deployment['id'][0:7], key, domain)
                # Call provider to give us a resource template
                result = (provider.generate_template(deployment,
                          resource['type'], None, context, name=name))
                result['component'] = component['id']
            else:
                if resource['type'] == 'user':
                    # Fall-back to local loader
                    instance = {}
                    result = dict(type='user', instance=instance)
                    if 'name' not in resource:
                        instance['name'] = \
                            deployment._get_setting_by_resource_path("resources/%s"
                                                                     "/name" % key,
                                                                     'admin')
                        if not instance['name']:
                            raise CheckmateException("Name must be specified for "
                                                     "the '%s' user resource" %
                                                     key)
                    else:
                        instance['name'] = resource['name']
                    if 'password' not in resource:
                        instance['password'] = \
                            deployment._get_setting_by_resource_path("resources/%s"
                                                                     "/password" %
                                                                     key)
                        if not instance['password']:
                            instance['password'] = (ProviderBase({}).evaluate(
                                                    "generate_password()"))
                    else:
                        instance['password'] = resource['password']
                    instance['hash'] = keys.hash_SHA512(instance['password'])
                elif resource['type'] == 'key-pair':
                    # Fall-back to local loader
                    instance = {}
                    private_key = resource.get('private_key')
                    if private_key is None:
                        # Generate and store all key types
                        private, public = keys.generate_key_pair()
                        instance['public_key'] = public['PEM']
                        instance['public_key_ssh'] = public['ssh']
                        instance['private_key'] = private['PEM']
                    else:
                        # Private key was supplied
                        instance['private_key'] = private_key
                        #make sure we have or can get a public key
                        if 'public_key' in resource:
                            public_key = resource['public_key']
                        else:
                            public_key = keys.get_public_key(private_key)
                        instance['public_key'] = public_key
                        if 'public_key_ssh' in resource:
                            public_key_ssh = resource['public_key_ssh']
                        else:
                            public_key_ssh = keys.get_ssh_public_key(private_key)
                        instance['public_key_ssh'] = public_key_ssh
                    if 'instance' in resource:
                        instance = resource['instance']
                    result = dict(type='key-pair', instance=instance)
                else:
                    raise CheckmateException("Could not find provider for the "
                                             "'%s' resource" % key)
            # Add it to resources
            resources[str(key)] = result
            result['index'] = str(key)
            LOG.debug("  Adding a %s resource with resource key %s" % (
                      resources[str(key)]['type'],
                      key))
            Resource.validate(result)

        #Write resources and connections to deployment
        if connections:
            resources['connections'] = connections
        if resources:
            deployment['resources'] = resources
        # Link resources to services
        for index, resource in resources.iteritems():
            if index not in ['connections', 'keys'] and 'service' in resource:
                service = blueprint['services'][resource['service']]
                if 'instances' not in service:
                    service['instances'] = []
                service['instances'].append(str(index))

        deployment['status'] = 'PLANNED'
        LOG.info("Deployment '%s' planning complete and status changed to %s" %
                (deployment['id'], deployment['status']))
        LOG.debug("ANALYSIS\n%s", dict_to_yaml(self._data))
        LOG.debug("RESOURCES\n%s", dict_to_yaml(self.resources))

        return resources
