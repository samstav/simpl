import copy
import logging
import os

from checkmate import keys
from checkmate.classes import ExtensibleDict
from checkmate.exceptions import CheckmateException,\
    CheckmateValidationException
from checkmate.middleware import RequestContext
from checkmate.providers import ProviderBase
from checkmate import utils
from checkmate.deployment import verify_required_blueprint_options_supplied,\
    Resource, verify_inputs_against_constraints
from celery.canvas import group
import eventlet

LOG = logging.getLogger(__name__)


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
        verify_inputs_against_constraints(deployment)

    def plan(self, context):
        """Perform plan analysis. Returns a reference to planned resources"""
        LOG.info("Planning deployment '%s'", self.deployment['id'])
        # Fill the list of services
        service_names = self.deployment['blueprint'].get('services', {}).keys()
        self['services'] = {name: {'component': {}} for name in service_names}

        # Perform analysis steps
        self.evaluate_defaults()
        self.resolve_components(context)
        self.resolve_relations()
        self.resolve_remaining_requirements(context)
        self.resolve_recursive_requirements(context, history=[])
        self.add_resources(self.deployment, context)
        self.connect_resources()
        self.add_static_resources(self.deployment, context)

        LOG.debug("ANALYSIS\n%s", utils.dict_to_yaml(self._data))
        LOG.debug("RESOURCES\n%s", utils.dict_to_yaml(self.resources))
        return self.resources

    def _providers_to_verify(self):
        providers = []
        names = ['load-balancer', 'nova', 'database', 'dns']
        for name, provider in self.environment.providers.iteritems():
            if not names:
                break
            if name in names:
                providers.append(provider)
                names.remove(name)
        return providers

    def verify_limits(self, context):
        # TODO: Run these asynchronously using eventlet
        results = []
        providers = self._providers_to_verify()
        for provider in providers:
            pile.spawn(provider.verify_limits, context, self.resources)
        results = []
        for result in pile:
            if result:
                results.extend(result)
        return results

    def verify_access(self, context):
        # TODO: Run these asynchronously using eventlet
        results = []
        providers = self._providers_to_verify()
        for provider in providers:
            pile.spawn(provider.verify_access, context, self.resources)
        results = []
        for result in pile:
            if result:
                results.extend(result)
        return results

    def plan_delete(self, context):
        """
        Collect delete resource tasks from the deployment

        :param context: a RequestContext
        :return: a celery.canvas.group of the delete tasks
        """
        assert isinstance(context, RequestContext)
        del_tasks = []
        dep_id = self.deployment.get("id")
        for res_key, resource in self.deployment.get("resources",
                                                     {}).iteritems():
            prov_key = resource.get('provider')
            if not prov_key:
                LOG.warn("Deployment %s resource %s does not specify a "
                         "provider", dep_id, res_key)
                continue
            provider = self.environment.get_provider(resource.get("provider"))
            if not provider:
                LOG.warn("Deployment %s resource %s has an unknown provider:"
                         " %s", dep_id, res_key, resource.get("provider"))
                continue
            new_tasks = provider.delete_resource_tasks(context, dep_id,
                                                       resource, res_key)
            if new_tasks:
                del_tasks.append(new_tasks)
        if not del_tasks:
            LOG.warn("No delete resource tasks for deployment %s", dep_id)
        return del_tasks

    def evaluate_defaults(self):
        """

        Evaluate option defaults

        Replaces defaults if they are a function with a final value so that the
        defaults are not evaluated once per workflow or once per component.

        """
        for key, option in self.blueprint.get('options', {}).iteritems():
            if 'default' in option:
                default = option['default']
                if (isinstance(default, basestring,) and
                        default.startswith('=generate')):
                    option['default'] = utils.evaluate(default[1:])

    def add_resources(self, deployment, context):
        """
        This is a container for the origninal plan() function. It contains
        code that is not yet fully refactored. This will go away over time.
        """
        blueprint = self.blueprint
        environment = self.environment
        resources = self.resources
        services = blueprint.get('services', {})

        # counter we increment and use as a new resource key
        self.resource_index = 0

        #
        # Prepare resources and connections to create
        #
        LOG.debug("Add resources")
        for service_name, service in services.iteritems():
            LOG.debug("  For service '%s'" % service_name)
            service_analysis = self['services'][service_name]
            definition = service_analysis['component']

            # Get main component for this service
            provider_key = definition['provider-key']
            provider = environment.get_provider(provider_key)
            component = provider.get_component(context, definition['id'])
            resource_type = component.get('is')
            count = deployment.get_setting('count',
                                           provider_key=provider_key,
                                           resource_type=resource_type,
                                           service_name=service_name,
                                           default=1)

            #TODO: shouldn't this live in the provider?
            default_domain = os.environ.get('CHECKMATE_DOMAIN',
                                            'checkmate.local')
            domain = deployment.get_setting('domain',
                                            provider_key=provider_key,
                                            resource_type=resource_type,
                                            service_name=service_name,
                                            default=default_domain)

            # Create as many as we have been asked to create
            for service_index in range(1, count + 1):
                # Create the main resource template
                resource = deployment.create_resource_template(service_index,
                                                               definition,
                                                               service_name,
                                                               domain, context)
                resource['status'] = 'PLANNED'
                # Add it to resources
                self.add_resource(resource, definition)

                # Add host and other requirements that exist in this service
                extra_components = service_analysis.get('extra-components', {})
                for key, extra_def in extra_components.iteritems():
                    LOG.debug("    Processing extra component '%s' for '%s'" %
                              (key, service_name))
                    extra_resource = deployment.create_resource_template(
                        service_index,
                        extra_def,
                        service_name, domain,
                        context)
                    self.add_resource(extra_resource, extra_def)

                    # Connnect extra components

                    if key in definition.get('host-keys', []):
                        # connect hosts
                        connections = definition.get('connections', {})
                        if key not in connections:
                            continue
                        connection = connections[key]
                        if connection.get('relation') == 'reference':
                            continue
                        if connection['direction'] == 'inbound':
                            continue
                        self.connect_instances(resource, extra_resource,
                                               connection, key)

    def connect_resources(self):
        # Add connections
        LOG.debug("Connect resources")
        for service_name, service_plan in self['services'].iteritems():
            # Do main component
            definition = service_plan['component']
            for index in definition.get('instances', []):
                self.connect_resource(self.resources[index], definition)
            # Do extra components
            extras = service_plan.get('extra-components')
            if extras:
                for definition in extras.values():
                    for index in definition.get('instances', []):
                        self.connect_resource(self.resources[index],
                                              definition)
        #Write resources and connections to deployment
        if self.connections:
            self.resources['connections'] = self.connections

    def add_static_resources(self, deployment, context):
        blueprint = self.blueprint
        environment = self.environment
        resources = self.resources
        services = blueprint.get('services', {})

        # Generate static resources
        LOG.debug("Prepare static resources")
        for key, resource in blueprint.get('resources', {}).iteritems():
            component = environment.find_component(resource, context)
            if component:
                provider = component.provider
                #TODO: shouldn't this live in the provider?
                default_domain = os.environ.get('CHECKMATE_DOMAIN',
                                                'checkmate.local')
                domain = deployment.get_setting('domain',
                                                provider_key=provider.key,
                                                resource_type=resource['type'],
                                                default=default_domain)

                name = "shared%s.%s" % (key, domain)

                # Call provider to give us a resource template
                result = (provider.generate_template(deployment,
                          resource['type'], None, context, name=name))
                result['component'] = component['id']
            else:
                # TODO: These should come from a provider (ex. AD, LDAP, PKI,
                # etc...)
                if resource['type'] == 'user':
                    # Fall-back to local loader
                    instance = {}
                    result = dict(type='user', instance=instance)
                    if 'name' not in resource:
                        instance['name'] = \
                            deployment._get_setting_by_resource_path(
                                "resources/%s/name" % key, 'admin')
                        if not instance['name']:
                            raise CheckmateException("Name must be specified "
                                                     "for the '%s' user "
                                                     "resource" % key)
                    else:
                        instance['name'] = resource['name']
                    if 'password' not in resource:
                        instance['password'] = \
                            deployment._get_setting_by_resource_path(
                                "resources/%s/password" % key)
                        if not instance['password']:
                            instance['password'] = utils.evaluate(
                                "generate_password()")
                    else:
                        instance['password'] = resource['password']
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
                            public_key_ssh = keys.get_ssh_public_key(
                                private_key)
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

    def add_resource(self, resource, definition):
        """Add a resource to the list of resources to be created"""
        resource['index'] = str(self.resource_index)
        self.resource_index += 1
        LOG.debug("  Adding a '%s' resource with resource key '%s'" % (
                  resource.get('type'), resource['index']))
        self.resources[resource['index']] = resource
        if 'instances' not in definition:
            definition['instances'] = []
        definition['instances'].append(resource['index'])

    def connect_resource(self, resource, definition):
        """

        Add 'relations' key to a resource based on the connection information
        in the plan to connect it to all other resources

        :param resource: the resource to connect
        :param definition: the definition of the resource from the plan

        """
        for key, connection in definition.get('connections', {}).iteritems():
            if (connection.get('relation', 'reference') == 'host'
                    and connection['direction'] == 'inbound'):
                continue  # we don't write host relation on host

            target_service = self['services'][connection['service']]
            if 'extra-key' in connection:
                extra_key = connection['extra-key']
                target_def = target_service['extra-components'][extra_key]
            else:
                target_def = target_service['component']
            for target_index in target_def.get('instances', []):
                target = self.resources[target_index]
                self.connect_instances(resource, target, connection, key)

            #TODO: this is just copied in for legacy compatibility
            if (connection['direction'] == 'outbound'
                    and 'extra-key' not in connection):
                rel_key = key  # connection['name']
                if rel_key not in self.connections:
                    con_def = {'interface': connection['interface']}
                    self.connections[rel_key] = con_def

    def connect_instances(self, resource, target, connection, connection_key):
        """Connect two resources based on the provided connection definition"""
        relation_type = connection.get('relation', 'reference')
        if relation_type == 'host':
            write_key = 'host'
        else:
            write_key = '%s-%s' % (connection_key, target['index'])
        result = {
            'interface': connection['interface'],
            'state': 'planned',
            'name': connection_key,
            'relation': relation_type
        }
        if connection['direction'] == 'inbound':
            result['source'] = target['index']
        elif connection['direction'] == 'outbound':
            result['target'] = target['index']
            result['requires-key'] = connection['requires-key']

        #FIXME: remove v0.2 feature
        if 'attribute' in connection:
            LOG.warning("Using v0.2 feature")
            result['attribute'] = connection['attribute']
        #END v0.2 feature

        if 'relation-key' in connection:
            result['relation-key'] = connection['relation-key']

        # Validate

        if 'relations' in resource and write_key in resource['relations']:
            if resource['relations'][write_key] != result:
                LOG.debug("Relation '%s' already exists")
                return
            else:
                CheckmateException("Conflicting relation named '%s' exists in "
                                   "service '%s'" % (write_key,
                                   target['service']))

        # Write relation

        if 'relations' not in resource:
            resource['relations'] = {}
        relations = resource['relations']
        if relation_type == 'host':
            if resource.get('hosted_on') not in [None, target['index']]:
                raise CheckmateException("Resource '%s' is already set to be "
                                         "hosted on '%s'. Cannot change host "
                                         "to '%s'" % (resource['index'],
                                         resource['hosted_on'], target['index']
                                         ))

            resource['hosted_on'] = target['index']
            if 'hosts' in target:
                if resource['index'] not in target['hosts']:
                    target['hosts'].append(resource['index'])
            else:
                target['hosts'] = [resource['index']]
        relations[write_key] = result

    def resolve_components(self, context):
        """

        Identify needed components and resolve them to provider components

        :param context: the call context. Component catalog may depend on
                current context

        """
        LOG.debug("Analyzing service components")
        services = self.deployment['blueprint'].get('services', {})
        for service_name, service in services.iteritems():
            definition = service['component']
            LOG.debug("Identifying component '%s' for service '%s'" % (
                      definition, service_name))
            component = self.identify_component(definition, context)
            LOG.debug("Component '%s' identified as '%s' for service '%s'" % (
                      definition, component['id'], service_name))
            self['services'][service_name]['component'] = component

    def resolve_relations(self):
        """

        Identifies source and target provides/requires keys for all relations

        Assumes that find_components() has already run and identified all the
        components in the deployment. If not, this will effectively be a noop

        """
        LOG.debug("Analyzing relations")
        services = self.deployment['blueprint'].get('services', {})
        for service_name, service in services.iteritems():
            if 'relations' not in service:
                continue
            for key, relation in service['relations'].iteritems():
                rel_key, rel = self._format_relation(key, relation,
                                                     service_name)
                if rel['service'] not in services:
                    msg = ("Cannot find service '%s' for '%s' to connect to "
                           "in deployment %s" % (rel['service'], service_name,
                           self.deployment['id']))
                    LOG.info(msg)
                    raise CheckmateValidationException(msg)

                source = self['services'][service_name]['component']
                requires_match = self._find_requires_key(rel, source)
                if not requires_match:
                    LOG.warning("Bypassing validation for v0.2 compatibility")
                    continue  # FIXME: This is here for v0.2 features only
                    raise CheckmateValidationException("Could not identify "
                                                       "source for relation "
                                                       "'%s'" % rel_key)

                LOG.debug("  Matched relation '%s' to requirement '%s'" % (
                          rel_key, requires_match))
                target = self['services'][rel['service']]['component']
                requirement = source['requires'][requires_match]
                if 'satisfied-by' not in requirement:
                    self._satisfy_requirement(requirement, rel_key, target,
                                              rel['service'], name=rel_key,
                                              relation_key=rel_key)
                    provides_match = requirement['satisfied-by'][
                        'provides-key']
                    #FIXME: part of v0.2 features to be removed
                    if 'attribute' in relation:
                        LOG.warning("Using v0.2 feature")
                        requirement['satisfied-by']['attribute'] = \
                            relation['attribute']
                else:
                    provides_match = self._find_provides_key(rel, target)

                # Connect the two components (write connection info in each)

                source_def = self['services'][service_name]['component']
                source_map = {
                    'component': source_def,
                    'service': service_name,
                    'endpoint': requires_match,
                }
                target_map = {
                    'component': target,
                    'service': rel['service'],
                    'endpoint': provides_match,
                }
                relation_type = rel.get('relation', 'reference')
                attribute = rel.get('attribute')  # FIXME: v0.2 feature
                self.connect(source_map, target_map, rel['interface'],
                             rel_key, relation_type=relation_type,
                             relation_key=key, attribute=attribute)

        LOG.debug("All relations successfully matched with target services")

    def connect(self, source, target, interface, connection_key,
                relation_type='reference', relation_key=None, attribute=None):
        """

        Connect two components by adding the connection information to them

        :param source: a map of the source 'component', 'service' name, and
                       'endpoint, as shown below
        :param target: a dict of the target 'component', 'service' name, and
                       'endpoint' as shown below
        :param interface: the interface used as the protocol of the connection
        :param connection_key: the name of the connection
        :param relation_type: 'reference' or 'host'
        :param relation_key: if this is coming from an explicit relation, as
                             opposed to a requirement being satisfied.
        :param attribute: for v0.2 compatibility

        Format of source and target dicts:
        {
            'component': dict of the component,
            'service': string of the service name
            'extra-key': key of the component if it is an extra component
            'endpoint': the key of the 'requires' or 'provides' entry
        }

        Write connection like this:
        {key}:
            direction: 'inbound' | 'outbound'
            interface: ...
            requires-key: from the source
            provides-key: from the target
            relation: 'reference' | 'host'
            relation-key: if the connection was created by a relation
            service: the service at the other end if this is between services
            extra-key: key of component if it is an extra component
            attribute: if needed by v0.2 connection


        """

        # Write to source connections

        if 'connections' not in source['component']:
            source['component']['connections'] = {}
        connections = source['component']['connections']
        if connection_key not in connections:
            info = {
                'direction': 'outbound',
                'service': target['service'],
                'provides-key': target['endpoint'],
                'interface': interface,
                'requires-key': source['endpoint'],
                'relation': relation_type,
            }
            if relation_key:
                info['relation-key'] = relation_key
            if 'extra-key' in target:
                info['extra-key'] = target['extra-key']
            if attribute:
                info['attribute'] = attribute

            connections[connection_key] = info

        # Write to target connections

        if 'connections' not in target['component']:
            target['component']['connections'] = {}
        connections = target['component']['connections']
        if connection_key not in connections:
            info = {
                'direction': 'inbound',
                'service': source['service'],
                'interface': interface,
                'provides-key': target['endpoint'],
                'relation': relation_type,
            }
            if relation_key:
                info['relation-key'] = relation_key
            if 'extra-key' in source:
                info['extra-key'] = source['extra-key']
            connections[connection_key] = info

    def resolve_remaining_requirements(self, context):
        """

        Resolves all requirements by finding and loading appropriate components

        Requirements that have been already resolved by an explicit relation
        are left alone. This is expected to be run after relations are resolved
        in order to fullfill any remaining requirements.

        Any additional components are added under a service's
        `extra-components` key using the requirement's key.

        """
        LOG.debug("Analyzing requirements")
        services = self['services']
        for service_name, service in services.iteritems():
            requirements = service['component']['requires']
            for key, requirement in requirements.iteritems():
                # Skip if already matched
                if 'satisfied-by' in requirement:
                    continue

                # Get definition
                definition = copy.copy(requirement)
                relation = definition.pop('relation', 'reference')

                # Identify the component
                LOG.debug("Identifying component '%s' to satisfy requirement "
                          "'%s' in service '%s'" % (definition, key,
                          service_name))
                component = self.identify_component(definition, context)
                if not component:
                    raise CheckmateException("Could not resolve component '%s'"
                                             % definition)
                LOG.debug("Component '%s' identified as '%s'  to satisfy "
                          "requirement '%s' for service '%s'" % (definition,
                          component['id'], key, service_name))

                # Add it to the 'extra-components' list in the service
                if 'extra-components' not in service:
                    service['extra-components'] = {}
                service['extra-components'][key] = component

                # Remember which resources are host resources

                if relation == "host":
                    if 'host-keys' not in service['component']:
                        service['component']['host-keys'] = []
                    service['component']['host-keys'].append(key)

                self._satisfy_requirement(requirement, key, component,
                                          service_name)

                # Connect the two components (write connection info in each)
                provides_match = self._find_provides_key(requirement,
                                                         component)
                source_map = {
                    'component': service['component'],
                    'service': service_name,
                    'endpoint': key,
                }
                target_map = {
                    'component': component,
                    'service': service_name,
                    'endpoint': provides_match,
                    'extra-key': key,
                }
                self.connect(source_map, target_map, requirement['interface'],
                             key, relation_type=relation)

    def resolve_recursive_requirements(self, context, history):
        """

        Goes through extra-component and resolves any of their requirements

        Loops recursively until all requirements are met. Detects cyclic Loops
        by keeping track of requirements met.

        """
        LOG.debug("Analyzing additional requirements")
        stack = []
        services = self['services']
        for service_name, service in services.iteritems():
            if 'extra-components' not in service:
                continue
            for component_key, component in service['extra-components']\
                    .iteritems():
                requirements = component['requires']
                for key, requirement in requirements.iteritems():
                    # Skip if already matched
                    if 'satisfied-by' in requirement:
                        continue
                    stack.append((service_name, component_key, key))

        for service_name, component_key, requirement_key in stack:
            service = services[service_name]
            component = service['extra-components'][component_key]
            requirement = component['requires'][requirement_key]

            # Get definition
            definition = copy.copy(requirement)
            relation = definition.pop('relation', 'reference')

            # Identify the component
            LOG.debug("Identifying component '%s' to satisfy requirement "
                      "'%s' in service '%s' for extra component '%s'",
                      definition, requirement_key, service_name,
                      component_key)
            found = self.identify_component(definition, context)
            if not found:
                raise CheckmateException("Could not resolve component '%s'"
                                         % definition)
            LOG.debug("Component '%s' identified as '%s'  to satisfy "
                      "requirement '%s' for service '%s' for extra component "
                      "'%s'", definition, found['id'], requirement_key,
                      service_name, component_key)

            signature = (service_name, found['id'])
            if signature in history:
                msg = ("Dependency loop detected while resolving requirements "
                       "for service '%s'. The component '%s' has been "
                       "encountered already" % signature)
                LOG.debug(msg, extra={'data': self})
                raise CheckmateException(msg)
            history.append(signature)
            # Add it to the 'extra-components' list in the service
            service['extra-components'][requirement_key] = found

            self._satisfy_requirement(requirement, requirement_key, found,
                                      service_name)

            # Connect the two components (write connection info in each)
            source_map = {
                'component': component,
                'service': service_name,
                'endpoint': requirement_key,
                'extra-key': component_key,
            }
            provides_key = requirement['satisfied-by']['provides-key']
            target_map = {
                'component': found,
                'service': service_name,
                'endpoint': provides_key,
                'extra-key': requirement_key,
            }
            self.connect(source_map, target_map, requirement['interface'],
                         requirement_key, relation_type=relation)
        if stack:
            self.resolve_recursive_requirements(context, history)

    def _satisfy_requirement(self, requirement, requirement_key, component,
                             component_service, relation_key=None, name=None):
        """

        Mark requirement as satisfied by component

        Format is:
            satisfied-by:
              service: the name of the service the requirement is met by
              component: the component ID that satisfies the requirement
              provides-key: the 'provides' key that meets the requirement
              name: the name to use for the relation
              relation-key: optional key of a relation if one was used as a
                            hint to identify this relationship

        """
        # Identify the matching interface
        provides_match = self._find_provides_key(requirement, component)
        if not provides_match:
            raise CheckmateValidationException("Could not identify target for "
                                               "requirement '%s'" %
                                               requirement_key)
        info = {
            'service': component_service,
            'component': component['id'],
            'provides-key': provides_match,
            'name': name or relation_key or requirement_key,
        }
        if relation_key:
            info['relation-key'] = relation_key
        requirement['satisfied-by'] = info

    def identify_component(self, definition, context):
        """Identifies a component based on blueprint-type keys"""
        assert not isinstance(definition, list)  # deprecated syntax
        found = self.environment.find_component(definition, context)
        if not found:
            raise CheckmateException("Could not resolve component '%s'"
                                     % definition)
        component = {}
        component['id'] = found['id']
        provider = found.provider
        component['provider-key'] = provider.key
        component['provider'] = "%s.%s" % (provider.vendor, provider.name)
        component['provides'] = found.provides or {}
        component['requires'] = found.requires or {}
        return component

    @staticmethod
    def _format_relation(key, value, service):
        """

        Parses relation and returns expanded relation as key and map tuple

        A Relation's syntax is one of:
        1 - service: interface
        2 - key:
              map (or set of keys and values)
        3 - host: interface (a special case of #1 where 'host' is a keyword)

        If #1 or #3 are passed in, they are converted to the format of #2

        :param key: the key of the relation or first value of a key/value pair
        :param value: the value after the key
        :param service: the name of the current service being evaluated

        :returns: key, value as formatted by #2

        The key returned also handles relationship naming optimized for user
        readability. COnnections between services are named 'from-to',
        connections generated by a named relation are named per the relation
        name, and other relations are named service:interface.

        """
        final_key = key
        final_map = {}
        if isinstance(value, dict):
            # Format #2
            final_key = key
            final_map = value
        else:
            if key == 'host':
                # Format #3
                final_key = '%s:%s' % (key, value)
                final_map['relation'] = 'host'
                # host will be created in current service
                final_map['service'] = service
                final_map['interface'] = value
            else:
                # Format #1
                final_key = '%s-%s' % (service, key)
                final_map['service'] = key
                final_map['interface'] = value
            LOG.debug("  _format_relation translated (%s, %s) to (%s, %s)" % (
                      key, value, final_key, final_map))
        # FIXME: this is for v0.2 only
        if 'service' not in final_map:
            LOG.warning("Skipping validation for v0.2 compatibility")
            final_map['service'] = service

        if 'service' not in final_map:  # post v0.2, let's raise this
            raise CheckmateException("No service specified for relation '%s'" %
                                     final_key)
        return final_key, final_map

    @staticmethod
    def _find_requires_key(relation, component):
        """

        Matches a requirement on the source component as the source of a
        relation

        Will not match a requirement that is already satisfied.

        :param relation: dict of the relation
        :param component: a dict of the component as parsed by the analyzer
        :returns: 'requires' key

        """
        backup = None
        for key, requirement in component.get('requires', {}).iteritems():
            if requirement['interface'] == relation['interface']:
                if 'satisfied-by' not in requirement:
                    return key
                else:
                    #FIXME: this is needed for v0.2 compatibility
                    # Use this key as a backup if we don't find one that is
                    # still unsatisfied
                    backup = key
        if backup:
            LOG.warning("Returning satisfied requirement for v0.2 "
                        "compatibility")
        return backup

    @staticmethod
    def _find_provides_key(relation, component):
        """

        Matches a provided interface on the target component as the target of a
        relation

        :param relation: dict of the relation
        :param component: a dict of the component as parsed by the analyzer
        :returns: 'provides' key

        """
        for key, provided in component.get('provides', {}).iteritems():
            if provided['interface'] == relation['interface']:
                return key
