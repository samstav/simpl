'''Analyzes a Checkmate deployment and persists the analysis results'''
import copy
import logging
import string

import eventlet

from checkmate import keys
from checkmate import utils
from checkmate.classes import ExtensibleDict
from checkmate.deployment import (
    validate_blueprint_options,
    validate_input_constraints,
)
from checkmate.exceptions import (
    BLUEPRINT_ERROR,
    CheckmateException,
    CheckmateValidationException,
    CheckmateUserException,
)
from checkmate.resource import Resource

LOG = logging.getLogger(__name__)

# Used when parsing so keys don't have to be generated
PARSE_PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAoJ/A7ofO0KlB2KVvyhfFDuadBwCUrUYgB5ROSCYSsMVxNmQr
hiFcoMsj34k6MkihL/TUyGJTu0tGbLdgXaPZFZDNkb9odPomDOImcrHSAiYLBN04
Svoz/wldjYP5p8rdLqQYmOpSq4RiSJ2BCLSTJrrBJN+UQvisfB0cbLN8fqbvYHtc
Z9VN8W2raDhDXTSAIlTQphQwkJB/xXOqZfJsj/Zk3R9osJu9RzM30vFA+2xcahtj
gZBiUiP4dOKQkIGPOj+J+n10iU1Pn1PoQmWMIfzfx++J9oCWBOJc4yR9PC+xwco5
3LnqNVjqsldaYn09xwvzCq8lepnwjbie9Yc0twIDAQABAoIBAFwmqwpuMdH2eQdx
CmyYLH77AXXF+IZcZ/3RMQQli62M6QG6gFnog/rf8InLce7tSkR4Iyd/eehHLHUs
04WFfgLoW3fVp3kNFo1npYVBzWlcKBA3Vpd1aiVUWy7YW3/PXAvpKw93x8wNHFHq
wt+asZ2ToUGlX6r4fgSKswcOBkumUpZckwV6zpmz5mHdXfE1dh5LYm+tODSaGoqK
O9Q1pqGlC8JvIjtwwglCsqk3ZrXc3hwgyYdifpwx8BMb2rZa8dYON1SEH8PAjZyZ
6k0paUemF7YT78/o9AXbSMnfLud0js+hO6p/lIqXCMXERdbspLq8bcOI3kn/uTt0
g1PkDkECgYEAuKNp8tjtyC6zHE6ZlK4mHFT1Wlir4eufM/BLpABvqSDrz9tRQRZC
xc/qCuWpfdzSzRKDQZascNC4ly+bDtFXSH1m/pttCkTrgXocimozQPElfrugCtzL
xkbfOsn5ADQ+HFbL0JTiPMqp3Sc7hq18KVJ0a82/SoGukB4lU6KY1FcCgYEA3rRN
23eerP7kzK3y67oD9OrkV6Yzsn63aiB+/WmwJPkadseuIrzTqbCtmPDHkZIlblql
L+UFajnLi0ln518xMVFJ4tZuVs8INsl/5nXcSIc2vvkLWVqkc1649jOdcm6vBuIt
/QY2OrydnQY5IKFbnFH+8Sy6WpargLbyII5JZqECgYEAmfR4hWvoaUC3TGUlnlnP
oVQd+SVyvMBxUSeOisNqV8YBmqGvEOx05OhGqKtzNmWIyEIle+0dADypjja9vg9E
DkeyN551v1hUXvPpFGkVL5NjxlbATg5pQ30Y6bY7j7YADDU7YUKjmjkKhkMOWXAS
1YnRVYqLdJ7JZZYdXa14baUCgYEA0odcerZQOHYV0TA3zoPgra1IA1vIz1pfBWKG
6gT5UVpznAoUIh6jcWzmDwi/gGvKGtJyCh7UyaCtPJU+NkmU9WxFDr1rPYEl4LUH
xdNxVNcN9+byxZucjrvi2kvc8YqUx0sV8nXm2gvoa8KwSpp/Qf15poCEApMgueM4
bXJVDUECgYAn+ZU4aNdKW1eVKB8cRX13Y3oaP9k4XSKci/XjCc+KqPvnVkcbt+J1
OxK9cb/HUIOOJwaLKymrlxCddZjrrFwSGYdpHn19KM+nUlbgTSKOYEs32vuNbd/a
0tfYsyBZitpdG5/WkQnRrWeCiGFMbFbDfcS3t1+Pb5xial8A5EbySQ==
-----END RSA PRIVATE KEY-----"""

PARSE_PUBLIC_KEY = """"-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAoJ/A7ofO0KlB2KVvyhfF
DuadBwCUrUYgB5ROSCYSsMVxNmQrhiFcoMsj34k6MkihL/TUyGJTu0tGbLdgXaPZ
FZDNkb9odPomDOImcrHSAiYLBN04Svoz/wldjYP5p8rdLqQYmOpSq4RiSJ2BCLST
JrrBJN+UQvisfB0cbLN8fqbvYHtcZ9VN8W2raDhDXTSAIlTQphQwkJB/xXOqZfJs
j/Zk3R9osJu9RzM30vFA+2xcahtjgZBiUiP4dOKQkIGPOj+J+n10iU1Pn1PoQmWM
Ifzfx++J9oCWBOJc4yR9PC+xwco53LnqNVjqsldaYn09xwvzCq8lepnwjbie9Yc0
twIDAQAB\n-----END PUBLIC KEY-----"""

PARSE_PUBLIC_SHA = """ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCgn8Duh87QqUHYpW/K\
F8UO5p0HAJStRiAHlE5IJhKwxXE2ZCuGIVygyyPfiToySKEv9NTIYlO7S0Zst2Bdo9kVkM2Rv2h0+i\
YM4iZysdICJgsE3ThK+jP/CV2Ng/mnyt0upBiY6lKrhGJInYEItJMmusEk35RC+Kx8HRxss3x+pu9g\
e1xn1U3xbatoOENdNIAiVNCmFDCQkH/Fc6pl8myP9mTdH2iwm71HMzfS8UD7bFxqG2OBkGJSI/h04p\
CQgY86P4n6fXSJTU+fU+hCZYwh/N/H74n2gJYE4lzjJH08L7HByjncueo1WOqyV1pifT3HC/MKryV6\
mfCNuJ71hzS3"""


class Planner(ExtensibleDict):
    '''Analyzes a Checkmate deployment and persists the analysis results

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

    '''
    def __init__(self, deployment, parse_only=False, *args, **kwargs):
        '''

        :param parse_only: optimize for parsing. Uses dummy keys
        '''
        ExtensibleDict.__init__(self, *args, **kwargs)
        self.deployment = deployment
        self.resources = self.deployment.get('resources', {})
        self.connections = self.deployment.get('connections', {})
        self.parse_only = parse_only

        # Find blueprint and environment. Otherwise, there's nothing to plan!
        self.blueprint = self.deployment.get('blueprint')
        if not self.blueprint:
            raise CheckmateValidationException("Blueprint not found. Nothing "
                                               "to do.")
        self.environment = self.deployment.environment()
        if not self.environment:
            raise CheckmateValidationException("Environment not found. "
                                               "Nowhere to deploy to.")

    def plan_additional_nodes(self, context, service_name, count):
        '''
        This method would add 'count' number of resource nodes of
        service-type 'service_name' to a deployment that has already been
        PLANNED.

        :param context: Request context
        :param service_name: The service to add additional nodes for
        :param count: The number of nodes to add
        :return:
        '''
        LOG.info("Planning %s additional nodes for service %s in deployment "
                 "'%s'", count, service_name, self.deployment['id'])
        service_analysis = self['services'][service_name]
        definition = service_analysis['component']

        # Get main component for this service
        provider_key = definition['provider-key']

        seed = self._get_number_of_resources(provider_key, service_name) + 1
        for service_index in range(seed, seed + count):
            self.add_resource_for_service(context, service_name, service_index)
        self.connect_resources()
        return self.resources

    def plan(self, context):
        '''Perform plan analysis. Returns a reference to planned resources'''
        LOG.info("Planning deployment '%s'", self.deployment['id'])

        # Quick validations
        validate_blueprint_options(self.deployment)
        validate_input_constraints(self.deployment)

        # Fill the list of services
        service_names = self.deployment['blueprint'].get('services', {}).keys()
        self['services'] = {name: {'component': {}} for name in service_names}

        # Perform analysis steps
        self.evaluate_defaults()

        # FIXME: we need to figure a way to make this happen in the providers
        # Set region to pick up the right images
        if not context.region:
            region = self.deployment.get_setting('region')
            if region:
                context.region = region
        self.resolve_components(context)
        self.resolve_relations()
        self.resolve_remaining_requirements(context)
        self.resolve_recursive_requirements(context, history=[])
        self.add_resources(context)
        self.connect_resources()
        self.add_static_resources(self.deployment, context)

        LOG.debug("ANALYSIS\n%s", utils.dict_to_yaml(self._data))
        LOG.debug("RESOURCES\n%s", utils.dict_to_yaml(self.resources))
        return self.resources

    def _unique_providers(self):
        '''Returns a list of provider instances, one per provider type.'''
        providers = []
        names = []
        for name, provider in self.environment.providers.iteritems():
            if name not in names:
                providers.append(provider)
                names.append(name)
        return providers

    def verify_limits(self, context):
        '''Ensure provider resources can be allocated.

        Checks API limits against resources that will be spun up
        during deployment.

        :param context: a RequestContext
        :return: Returns a list of warning/error messages
        '''
        pile = eventlet.GreenPile()
        providers = self._unique_providers()
        for provider in providers:
            resources = utils.filter_resources(self.resources, provider.name)
            pile.spawn(provider.verify_limits, context, resources)
        results = []
        for result in pile:
            if result:
                results.extend(result)
        return results

    def verify_access(self, context):
        '''Ensure user has RBAC permissions to allocate provider resources.

        :param context: a RequestContext
        :return: Returns a list of warning/error messages
        '''
        pile = eventlet.GreenPile()
        providers = self._unique_providers()
        for provider in providers:
            pile.spawn(provider.verify_access, context)
        results = []
        for result in pile:
            if result:
                results.append(result)
        return results

    def evaluate_defaults(self):
        '''

        Evaluate option defaults

        Replaces defaults if they are a function with a final value so that the
        defaults are not evaluated once per workflow or once per component.

        '''
        for _, option in self.blueprint.get('options', {}).iteritems():
            if 'default' in option:
                default = option['default']
                if (isinstance(default, basestring,) and
                        default.startswith('=generate')):
                    option['default'] = utils.evaluate(default[1:])

    def add_resources(self, context):
        '''
        This is a container for the original plan() function. It contains
        code that is not yet fully refactored. This will go away over time.
        '''
        blueprint = self.blueprint
        environment = self.environment
        services = blueprint.get('services', {})

        # Prepare resources and connections to create
        LOG.debug("Add resources")
        for service_name, _ in services.iteritems():
            LOG.debug("  For service '%s'", service_name)
            service_analysis = self['services'][service_name]
            definition = service_analysis['component']

            # Get main component for this service
            provider_key = definition['provider-key']
            provider = environment.get_provider(provider_key)
            component = provider.get_component(context, definition['id'])
            resource_type = component.get('is')
            count = self.deployment.get_setting('count',
                                                provider_key=provider_key,
                                                resource_type=resource_type,
                                                service_name=service_name,
                                                default=1)

            # Create as many as we have been asked to create
            for service_index in range(1, count + 1):
                # Create the main resource template
                self.add_resource_for_service(context, service_name,
                                              service_index)

    def add_resource_for_service(self, context, service_name, service_index):
        '''
        Adds a new 'resource' block to the deployment, based on the
        service name
        :param service_name: Name of the service
        :param context: Request context
        :param service_index:
        :return:
        '''
        LOG.debug("  For service '%s'", service_name)
        service_analysis = self['services'][service_name]
        definition = service_analysis['component']

        # Create as many as we have been asked to create
            # Create the main resource template
        resources = self.deployment.create_resource_template(service_index,
                                                             definition,
                                                             service_name,
                                                             context)
        for resource in resources:
            resource['status'] = 'PLANNED'
            # Add it to resources
            self.add_resource(resource, definition, service_name)

            # Add host and other requirements that exist in the service
            extra_components = service_analysis.get(
                'extra-components', {})
            for key, extra_def in extra_components.iteritems():
                LOG.debug("    Processing extra component '%s' for "
                          "'%s'", key, service_name)
                extra_resources = self.deployment.create_resource_template(
                    service_index,
                    extra_def,
                    service_name,
                    context)
                for extra_resource in extra_resources:
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
                        self.connect_instances(resource,
                                               extra_resource,
                                               connection, key)

    def connect_resources(self):
        '''Wire up resource connections within a Plan'''
        # Add connections
        LOG.debug("Connect resources")
        for _, service_plan in self['services'].iteritems():
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
        '''Generate static resources and add them to resources collection'''
        blueprint = self.blueprint
        environment = self.environment
        resources = self.resources

        # Generate static resources
        LOG.debug("Prepare static resources")
        for key, resource in blueprint.get('resources', {}).iteritems():
            component = environment.find_component(resource, context)
            if component:
                provider = component.provider
                # Call provider to give us a resource template
                results = (provider.generate_template(deployment,
                                                      resource['type'], None,
                                                      context, 1, provider.key,
                                                      None))
                for result in results:
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
                            error_message = "Name must be specified " \
                                           "for the '%s' user " \
                                           "resource" % key
                            raise CheckmateUserException(
                                error_message, utils.get_class_name(
                                    CheckmateException), BLUEPRINT_ERROR, '')
                    else:
                        instance['name'] = resource['name']
                    if 'password' not in resource:
                        instance['password'] = \
                            deployment._get_setting_by_resource_path(
                                "resources/%s/password" % key)
                        if not instance['password']:
                            instance['password'] = utils.generate_password(
                                starts_with=string.letters,
                                valid_chars=''.join([
                                    string.letters,
                                    string.digits
                                ])
                            )
                    else:
                        instance['password'] = resource['password']
                elif resource['type'] == 'key-pair':
                    # Fall-back to local loader
                    instance = {}
                    private_key = resource.get('private_key')
                    if private_key is None:
                        # Generate and store all key types
                        if self.parse_only:
                            private = {
                                'PEM': PARSE_PRIVATE_KEY
                            }
                            public = {
                                'PEM': PARSE_PUBLIC_KEY,
                                "ssh": PARSE_PRIVATE_KEY,
                            }
                        else:
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
                    error_message = "Could not find provider for the " \
                                   "'%s' resource" % key
                    raise CheckmateUserException(error_message,
                                                 utils.get_class_name(
                                                     CheckmateException),
                                                 BLUEPRINT_ERROR, '')
                    # Add it to resources
            resources[str(key)] = result
            result['index'] = str(key)
            LOG.debug("  Adding a %s resource with resource key %s",
                      resources[str(key)]['type'],
                      key)
            Resource.validate(result)

    def add_resource(self, resource, definition, service_name=None):
        '''Add a resource to the list of resources to be created'''
        resource['index'] = self._get_next_resource_index()

        LOG.debug("  Adding a '%s' resource with resource key '%s'",
                  resource.get('type'), resource['index'])
        self.resources[resource['index']] = resource
        if 'instances' not in definition:
            definition['instances'] = []
        definition['instances'].append(resource['index'])

        #TODO: Refactor this
        if service_name:
            interface = self.blueprint["services"][service_name][
                "component"].get("interface")
            if interface == 'vip':
                connections = definition["connections"]
                connections[connections.keys()[int(resource['index'])]][
                    "outbound-from"] = resource['index']

    def connect_resource(self, resource, definition):
        '''

        Add 'relations' key to a resource based on the connection information
        in the plan to connect it to all other resources

        :param resource: the resource to connect
        :param definition: the definition of the resource from the plan

        '''
        for key, connection in definition.get('connections', {}).iteritems():
            if connection.get('outbound-from') and connection.get(
                    'outbound-from') != resource['index']:
                continue
            if (connection.get('relation', 'reference') == 'host' and
                    connection['direction'] == 'inbound'):
                continue  # we don't write host relation on host

            target_service = self['services'][connection['service']]
            if 'extra-key' in connection:
                extra_key = connection['extra-key']
                target_def = target_service['extra-components'][extra_key]
            else:
                target_def = target_service['component']
            if (target_def["connections"].get(resource["service"]) and
                    target_def["connections"][resource["service"]].get(
                    "outbound-from")):
                instances = target_def["connections"][
                    resource["service"]]["outbound-from"]
            else:
                instances = target_def.get('instances', [])
            for target_index in instances:
                target = self.resources[target_index]

                self.connect_instances(resource, target, connection, key)

                #TODO: this is just copied in for legacy compatibility
            if (connection['direction'] == 'outbound' and
                    'extra-key' not in connection):
                rel_key = key  # connection['name']
                if rel_key not in self.connections:
                    con_def = {'interface': connection['interface']}
                    self.connections[rel_key] = con_def

    @staticmethod
    def connect_instances(resource, target, connection, connection_key):
        '''Connect two resources based on the provided connection definition'''
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
                LOG.debug("Relation '%s' already exists",
                          resource['relations'][write_key])
                return
            else:
                LOG.debug("Conflicting relation named '%s' exists in service "
                          "'%s'" % (write_key, target['service']))
                return

        # Write relation

        if 'relations' not in resource:
            resource['relations'] = {}
        relations = resource['relations']
        if relation_type == 'host':
            if resource.get('hosted_on') not in [None, target['index']]:
                error_message = ("Resource '%s' is already set to be hosted on "
                                 "'%s'. Cannot change host to '%s'" %
                                (resource['index'], resource['hosted_on'],
                                 target['index']))
                raise CheckmateUserException(error_message,
                                             utils.get_class_name(
                                                 CheckmateException),
                                             BLUEPRINT_ERROR, '')

            resource['hosted_on'] = target['index']
            if 'hosts' in target:
                if resource['index'] not in target['hosts']:
                    target['hosts'].append(resource['index'])
            else:
                target['hosts'] = [resource['index']]
        relations[write_key] = result

    def resolve_components(self, context):
        '''

        Identify needed components and resolve them to provider components

        :param context: the call context. Component catalog may depend on
                current context

        '''
        LOG.debug("Analyzing service components")
        services = self.deployment['blueprint'].get('services', {})
        for service_name, service in services.iteritems():
            definition = service['component']
            LOG.debug("Identifying component '%s' for service '%s'",
                      definition, service_name)
            component = self.identify_component(definition, context)
            LOG.debug("Component '%s' identified as '%s' for service '%s'",
                      definition, component['id'], service_name)
            self['services'][service_name]['component'] = component

    def resolve_relations(self):
        '''

        Identifies source and target provides/requires keys for all relations

        Assumes that find_components() has already run and identified all the
        components in the deployment. If not, this will effectively be a noop

        '''
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

                LOG.debug("  Matched relation '%s' to requirement '%s'",
                          rel_key, requires_match)
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

    @staticmethod
    def connect(source, target, interface, connection_key,
                relation_type='reference', relation_key=None, attribute=None):
        '''

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


        '''

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
        '''

        Resolves all requirements by finding and loading appropriate components

        Requirements that have been already resolved by an explicit relation
        are left alone. This is expected to be run after relations are resolved
        in order to fullfill any remaining requirements.

        Any additional components are added under a service's
        `extra-components` key using the requirement's key.

        '''
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
                          "'%s' in service '%s'", definition, key,
                          service_name)
                component = self.identify_component(definition, context)
                if not component:
                    error_message = "Could not resolve component '%s'" % definition
                    raise CheckmateUserException(error_message,
                                                 utils.get_class_name(
                                                     CheckmateException),
                                                 BLUEPRINT_ERROR, '')
                LOG.debug("Component '%s' identified as '%s'  to satisfy "
                          "requirement '%s' for service '%s'", definition,
                          component['id'], key, service_name)

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
        '''

        Goes through extra-component and resolves any of their requirements

        Loops recursively until all requirements are met. Detects cyclic Loops
        by keeping track of requirements met.

        '''
        LOG.debug("Analyzing additional requirements")
        stack = []
        services = self['services']
        for service_name, service in services.iteritems():
            if 'extra-components' not in service:
                continue
            for component_key, component in (
                    service['extra-components'].iteritems()):
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
                error_message = "Could not resolve component '%s'" % definition
                raise CheckmateUserException(error_message,
                                             utils.get_class_name(
                                                 CheckmateException),
                                             BLUEPRINT_ERROR, "")
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
                raise CheckmateUserException(msg, utils.get_class_name(
                    CheckmateException), BLUEPRINT_ERROR, '')
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

    def _get_next_resource_index(self):
        '''
        Calculates the next resource index based on the current resources
        :return:
        '''
        return (str(len([res for res in self.resources.keys()
                         if res.isdigit()])))

    def _get_number_of_resources(self, provider_key, service_name):
        '''
        Gets the number of resources for a specific service and provider
        :param provider_key:
        :param service_name:
        :return:
        '''
        count = 0
        for key, resource in self.resources.iteritems():
            if (resource.get("service") == service_name and resource.get(
                    "provider") == provider_key):
                count += 1
        return count

    def _satisfy_requirement(self, requirement, requirement_key, component,
                             component_service, relation_key=None, name=None):
        '''

        Mark requirement as satisfied by component

        Format is:
            satisfied-by:
              service: the name of the service the requirement is met by
              component: the component ID that satisfies the requirement
              provides-key: the 'provides' key that meets the requirement
              name: the name to use for the relation
              relation-key: optional key of a relation if one was used as a
                            hint to identify this relationship

        '''
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
        '''Identifies a component based on blueprint-type keys'''
        assert not isinstance(definition, list)  # deprecated syntax
        found = self.environment.find_component(definition, context)
        if not found:
            error_message = "Could not resolve component '%s'" % definition
            raise CheckmateUserException(error_message,utils.get_class_name(
                CheckmateException), BLUEPRINT_ERROR, '')
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
        '''

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

        '''
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
            LOG.debug("  _format_relation translated (%s, %s) to (%s, %s)",
                      key, value, final_key, final_map)
        # FIXME: this is for v0.2 only
        if 'service' not in final_map:
            LOG.warning("Skipping validation for v0.2 compatibility")
            final_map['service'] = service

        if 'service' not in final_map:  # post v0.2, let's raise this
            error_message = "No service specified for relation '%s'" % final_key
            raise CheckmateUserException(error_message, utils.get_class_name(
                CheckmateException),BLUEPRINT_ERROR, '')
        return final_key, final_map

    @staticmethod
    def _find_requires_key(relation, component):
        '''

        Matches a requirement on the source component as the source of a
        relation

        Will not match a requirement that is already satisfied.

        :param relation: dict of the relation
        :param component: a dict of the component as parsed by the analyzer
        :returns: 'requires' key

        '''
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
        '''

        Matches a provided interface on the target component as the target of a
        relation

        :param relation: dict of the relation
        :param component: a dict of the component as parsed by the analyzer
        :returns: 'provides' key

        '''
        for key, provided in component.get('provides', {}).iteritems():
            if provided['interface'] == relation['interface']:
                return key
