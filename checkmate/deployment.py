import collections
import copy
import logging
import os
from urlparse import urlparse

from checkmate import keys
from checkmate.classes import ExtensibleDict
from checkmate.common import schema
from checkmate.db import get_driver
from checkmate.environments import Environment
from checkmate.exceptions import (CheckmateException,
                                  CheckmateValidationException)
from checkmate.providers import ProviderBase
from checkmate.utils import (merge_dictionary, get_time_string, is_ssh_key)
from bottle import abort

LOG = logging.getLogger(__name__)
DB = get_driver()


def verify_required_blueprint_options_supplied(deployment):
    """Check that blueprint options marked 'required' are supplied.

    Raise error if not
    """
    blueprint = deployment['blueprint']
    if 'options' in blueprint:
        inputs = deployment.get('inputs', {})
        bp_inputs = inputs.get('blueprint', {})
        for key, option in blueprint['options'].iteritems():
            if (not 'default' in option) and \
                    option.get('required') in ['true', True]:
                if key not in bp_inputs:
                    raise CheckmateValidationException("Required blueprint "
                            "input '%s' not supplied" % key)


def get_os_env_keys():
    """Get keys if they are set in the os_environment"""
    dkeys = {}
    if ('CHECKMATE_PUBLIC_KEY' in os.environ and
            os.path.exists(os.path.expanduser(
                os.environ['CHECKMATE_PUBLIC_KEY']))):
        try:
            path = os.path.expanduser(os.environ['CHECKMATE_PUBLIC_KEY'])
            with file(path, 'r') as fi:
                key = fi.read()
            if is_ssh_key(key):
                dkeys['checkmate'] = {'public_key_ssh': key,
                                      'public_key_path': path}
            else:
                dkeys['checkmate'] = {'public_key': key,
                                      'public_key_path': path}
        except IOError as(errno, strerror):
            LOG.error("I/O error reading public key from CHECKMATE_PUBLIC_KEY="
                      "'%s' environment variable (%s): %s" % (
                      os.environ['CHECKMATE_PUBLIC_KEY'], errno, strerror))
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
    """Generates keys for the deployment and stores them as a resource.

    Generates:
        private_key
        public_key
        public_key_ssh

    If a private_key exists, it will be used to generate the public keys
    """
    if 'resources' not in deployment:
        deployment['resources'] = {}
    if 'deployment-keys' not in deployment['resources']:
        deployment['resources']['deployment-keys'] = dict(type='key-pair')
    elif 'type' not in deployment['resources']['deployment-keys']:
        deployment['resources']['deployment-keys']['type'] = 'key-pair'
    if 'instance' not in deployment['resources']['deployment-keys']:
        deployment['resources']['deployment-keys']['instance'] = {}

    dep_keys = deployment['resources']['deployment-keys']['instance']
    private_key = dep_keys.get('private_key')
    if private_key is None:
        # Generate and store all key types
        private, public = keys.generate_key_pair()
        dep_keys['public_key'] = public['PEM']
        dep_keys['public_key_ssh'] = public['ssh']
        dep_keys['private_key'] = private['PEM']
    else:
        # Private key was supplied, make sure we have or can get a public key
        if 'public_key' not in dep_keys:
            dep_keys['public_key'] = keys.get_public_key(private_key)
        if 'public_key_ssh' not in dep_keys:
            public_key = keys.get_ssh_public_key(private_key)
            dep_keys['public_key_ssh'] = public_key

    # Make sure next call to settings() will get a fresh copy of the keys
    if hasattr(deployment, '_settings'):
        delattr(deployment, '_settings')

    return copy.copy(dep_keys)


class Resource():
    def __init__(self, key, obj):
        Resource.validate(obj)
        self.key = key
        self.dict = obj

    @classmethod
    def validate(cls, obj):
        """Validate Schema"""
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
            raise (CheckmateException("Could not find component '%s' in "
                   "provider %s.%s's catalog" % (self.dict['component'],
                   provider.vendor, provider.name)))


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
        """ Validate Schema """
        errors = schema.validate(obj, schema.DEPLOYMENT_SCHEMA)
        errors.extend(schema.validate_inputs(obj))
        if errors:
            raise (CheckmateValidationException("Invalid %s: %s" % (
                   cls.__name__, '\n'.join(errors))))

    def environment(self):
        """ Initialize environment from Deployment """
        if self._environment is None:
            entity = self.get('environment')
            if entity:
                self._environment = Environment(entity)
            else:
                return Environment({})
        return self._environment

    def inputs(self):
        """ return inputs of deployment """
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
        deployment_keys = (self.get('resources', {}).get(
                           'deployment-keys', {}).get('instance'))
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

    def get_setting(self, name, resource_type=None, service_name=None,
                    provider_key=None, default=None):
        """Find a value that an option was set to.

        Look in this order:
        - start with the deployment inputs where the paths are:
            inputs/blueprint
            inputs/providers/:provider
            etc
        - global inputs
        - environment settings (generated at planning time)
        - resources (generated during deployment)
        - finally look at the component defaults

        :param name: the name of the setting
        :param service: the name of the service being evaluated
        :param resource_type: the type of the resource being evaluated (ex.
                compute, database)
        :param default: value to return if no match found
        """
        result = None
        if service_name:
            result = (self._get_input_service_override(name, service_name,
                      resource_type=resource_type))
            if result:
                LOG.debug("Setting '%s' matched in _get_input_service_override"
                          % name)
                return result

            result = self._get_constrained_svc_cmp_setting(name, service_name)
            if result:
                LOG.debug("Setting '%s' matched in "
                          "_get_constrained_svc_cmp_setting" % name)
                return result

        if provider_key:
            result = (self._get_input_provider_option(name, provider_key,
                      resource_type=resource_type))
            if result:
                LOG.debug("Setting '%s' matched in _get_input_provider_option"
                          % name)
                return result

        result = (self._get_constrained_static_resource_setting(name,
                  service_name=service_name, resource_type=resource_type))
        if result:
            LOG.debug("Setting '%s' matched in "
                          "_get_constrained_static_resource_setting" % name)
            return result

        result = (self._get_input_blueprint_option_constraint(name,
                  service_name=service_name, resource_type=resource_type))
        if result:
            LOG.debug("Setting '%s' matched in "
                          "_get_input_blueprint_option_constraint" % name)
            return result

        result = self._get_input_simple(name)
        if result:
            LOG.debug("Setting '%s' matched in _get_input_simple" % name)
            return result

        result = self._get_input_global(name)
        if result:
            LOG.debug("Setting '%s' matched in _get_input_global" % name)
            return result

        result = (self._get_environment_provider_constraint(name, provider_key,
                  resource_type=resource_type))
        if result:
            LOG.debug("Setting '%s' matched in "
                      "_get_environment_provider_constraint" % name)
            return result

        result = (self._get_environment_provider_constraint(name, 'common',
                  resource_type=resource_type))
        if result:
            LOG.debug("Setting '%s' matched 'common' setting in "
                      "_get_environment_provider_constraint" % name)
            return result

        result = self._get_resource_setting(name)
        if result:
            LOG.debug("Setting '%s' matched in _get_resource_setting" % name)
            return result

        result = self._get_setting_value(name)
        if result:
            LOG.debug("Setting '%s' matched in _get_setting_value" % name)
            return result

        LOG.debug("Setting '%s' unmatched with resource_type=%s, service=%s, "
                  "provider_key=%s and returning default '%s'" % (name,
                  resource_type, service_name, provider_key, default))
        return default

    def _get_resource_setting(self, name):
        """Get a value from resources with support for paths"""
        if name:
            node = self.get("resources", {})
            for key in name.split("/"):
                if key in node:
                    try:
                        node = node[key]
                    except TypeError:
                        return None
                else:
                    return None
            return node

    def _get_setting_by_resource_path(self, path, default=None):
        """Read a setting that constrains a static resource using the name of
        the setting as a path.
        The name must be resources/:resource_key/:setting"""
        #FIXME: we need to confirm if we want this as part of the DSL
        blueprint = self['blueprint']
        if 'options' in blueprint:
            options = blueprint['options']
            for key, option in options.iteritems():
                if 'constrains' in option:
                    constraints = self.parse_constraints(option['constrains'])
                    for constraint in constraints:
                        if self.constraint_applies(constraint, path):
                            result = self._apply_constraint(path, constraint,
                                                            option=option,
                                                            option_key=key)
                            if result:
                                LOG.debug("Found setting '%s' from constraint."
                                          " %s=%s" % (path, key, result))
                                return result
        return default

    def _get_setting_value(self, name):
        """Get a value from the deployment hierarchy with support for paths"""
        if name:
            node = self._data
            for key in name.split("/"):
                if key in node:
                    try:
                        node = node[key]
                    except TypeError:
                        return None
                else:
                    return None
            return node

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
        :param resource_type: the resource type to match the constraint with
        """
        blueprint = self['blueprint']
        if 'options' in blueprint:
            options = blueprint['options']
            for key, option in options.iteritems():
                if 'constrains' in option:  # the verb 'constrains' (not noun)
                    constraints = self.parse_constraints(option['constrains'])
                    for constraint in constraints:
                        if (self.constraint_applies(constraint, name,
                            service_name=service_name,
                            resource_type=resource_type)):
                            result = self._apply_constraint(name, constraint,
                                                            option=option,
                                                            option_key=key)
                            if result:
                                LOG.debug("Found setting '%s' from constraint."
                                          " %s=%s" % (name, name, result))
                                return result

    def _get_constrained_static_resource_setting(self, name, service_name=None,
                                                 resource_type=None):
        """Get a setting implied through a static resource constraint

        :param name: the name of the setting
        :param service_name: the name of the service being evaluated
        :param resource_type: the type of the resource being evaluated
        """
        blueprint = self['blueprint']
        if 'resources' in blueprint:
            resources = blueprint['resources']
            for key, resource in resources.iteritems():
                if 'constrains' in resource:
                    constraints = resource['constrains']
                    constraints = self.parse_constraints(constraints)
                    for constraint in constraints:
                        if (self.constraint_applies(constraint, name,
                            service_name=service_name,
                            resource_type=resource_type)):
                            instance = self['resources'][key]['instance']
                            result = self._apply_constraint(name, constraint,
                                                            resource=instance)
                            if result:
                                LOG.debug("Found setting '%s' from constraint "
                                          "in blueprint resource '%s'. %s=%s" %
                                          (name, key, name, result))
                                return result

    def _get_constrained_svc_cmp_setting(self, name, service_name):
        """Get a setting implied through a blueprint service constraint

        :param name: the name of the setting
        :param service_name: the name of the service being evaluated
        """
        blueprint = self['blueprint']
        if 'services' in blueprint:
            services = blueprint['services']
            service = services.get(service_name, None)
            if service is not None:
                # Check constraints under service
                if 'constraints' in service:
                    constraints = service['constraints']
                    constraints = self.parse_constraints(constraints)
                    for constraint in constraints:
                        if name == constraint['setting']:
                            result = self._apply_constraint(name, constraint)
                            LOG.debug("Found setting '%s' as a service "
                                      "constraint in service '%s'. %s=%s"
                                      % (name, service_name, name, result))
                            return result
                # Check constraints under component
                if 'component' in service:
                    if service['component'] is not None:
                        if 'constraints' in service['component']:
                            constraints = service['component']['constraints']
                            constraints = self.parse_constraints(constraints)
                            for constraint in constraints:
                                if name == constraint['setting']:
                                    result = self._apply_constraint(name,
                                                                    constraint)
                                    LOG.debug("Found setting '%s' as a "
                                              "service comoponent constraint "
                                              "in service '%s'. %s=%s" % (name,
                                              service_name, name, result))
                                    return result

    @staticmethod
    def parse_constraints(constraints):
        """

        Ensure constraint syntax is valid

        If it is key/values, convert it to a list.
        If the list has key/values, convert them to the expected format with
        setting, service, etc...

        """
        constraint_list = []
        if isinstance(constraints, list):
            constraint_list = constraints
        elif isinstance(constraints, dict):
            LOG.warning("Constraints not a list: %s" % constraints)
            for key, value in constraints.iteritems():
                constraint_list.append({'setting': key,
                                        'value': value})
        parsed = []
        for constraint in constraint_list:
            if len(constraint) == 1 and constraint.keys()[0] != 'setting':
                # it's one key/value pair which is not 'setting':path
                # Convert setting:value to full constraint syntax
                parsed.append({'setting': constraint.keys()[0],
                               'value': constraint.values()[0]})
            else:
                parsed.append(constraint)

        return parsed

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
        if 'resource' in constraint:
            if resource_type is None or \
                    constraint['resource'] != resource_type:
                return False
        LOG.debug("Constraint '%s' for '%s' applied to '%s/%s'" % (
                  constraint, name, service_name or '*', resource_type or '*'))
        return True

    def _apply_constraint(self, name, constraint, option=None, resource=None,
                          option_key=None):
        """

        Returns the value to of the option applying any constraint definitions

        :param name: the name of the option we are seeking
        :param constraint: the dict of any constraint used to find the option
        :param option: the option being evaluated
        :param resource: the resource the constraint is applied to
        :param option_key: the key of the option the constraint is coming from

        """

        # Return the value if it is explicitely assigned in the constraint

        if 'value' in constraint:
            return constraint['value']

        # Find the value

        value = None
        if resource:
            # use the resource as the value if the constraint has a resource
            value = resource
        else:
            if option_key:
                value = self._get_input_simple(option_key)
            if (not value) and option and 'default' in option:
                value = option.get('default')
                LOG.debug("Default setting '%s' obtained from constraint "
                          "in blueprint input '%s': default=%s" % (
                            name, option_key, value))

        # objectify the value it if it is a typed option

        if option and 'type' in option and not resource:
            value = self._objectify(option, value)

        # If the constraint has an attribute specified, get that attribute

        if 'attribute' in constraint:
            attribute = constraint['attribute']

            if value:
                if not isinstance(value, collections.Mapping):
                    raise CheckmateException("Could not read attribute '%s' "
                                             "while obtaining option '%s' "
                                             "since value is of type %s" % (
                                             attribute, name,
                                             type(value).__name__))
                if attribute in value:
                    result = value[attribute]
                if result:
                    LOG.debug("Found setting '%s' from constraint. %s=%s" % (
                              name, option_key or name, result))
                    return result

        if value:
            LOG.debug("Found setting '%s' from constraint in blueprint "
                      "input '%s'. %s=%s" % (name, option_key, option_key,
                      value))
            return value

    def _objectify(self, option, value):
        """Parse option based on type into an object of that type"""
        if 'type' not in option:
            return value
        if option['type'] == 'url':
            parts = urlparse(value)
            return {
                    'scheme': parts.scheme,
                    'protocol': parts.scheme,
                    'netloc': parts.netloc,
                    'hostname': parts.hostname,
                    'port': parts.port,
                    'username': parts.username,
                    'password': parts.password,
                    'path': parts.path.strip('/'),
                    'query': parts.query,
                    'fragment': parts.fragment,
                   }
        else:
            return value

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
                provider = providers[provider_key] or {}
                if resource_type in provider:
                    options = provider[resource_type]
                    if options and name in options:
                        result = options[name]
                        LOG.debug("Found setting '%s' as provider "
                                  "setting in blueprint/providers/%s/%s'."
                                  " %s=%s" % (name, provider_key,
                                  resource_type, name, result))
                        return result

    def _get_environment_provider_constraint(self, name, provider_key,
                                             resource_type=None):
        """Get a setting applied through a provider constraint in the
        environment

        :param name: the name of the setting
        :param provider_key: the key of the provider in question
        :param resource_type: the resource type (ex. compute)
        """
        environment = self.environment()
        providers = environment.dict['providers']
        if provider_key in providers:
            provider = providers[provider_key] or {}
            constraints = provider.get('constraints', [])
            assert isinstance(constraints, list), ("constraints need to be a "
                                                   "list or array")
            constraints = self.parse_constraints(constraints)
            for constraint in constraints:
                if self.constraint_applies(constraint, name,
                                           resource_type=resource_type):
                    result = self._apply_constraint(name, constraint)
                    LOG.debug("Found setting '%s' as a provider constraint in "
                              "the environment for provider '%s'. %s=%s"
                              % (name, provider_key, name, result))
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

    def create_resource_template(self, index, definition, service_name, domain,
                                 context):
        """Create a new resource dict to add to the deployment

        :param index: the index of the resource within its service (ex. web2)
        :param definition: the component definition coming from the Plan
        :param domain: the DNS domain to use for resource names
        :param context: RequestContext (auth token, etc) for catalog calls

        :returns: a validated dict of the resource ready to add to deployment
        """
        # Generate a default name
        name = 'CM-%s-%s%s.%s' % (self['id'][0:7], service_name, index, domain)
        # Call provider to give us a resource template
        provider_key = definition['provider-key']
        provider = self.environment().get_provider(provider_key)
        component = provider.get_component(context, definition['id'])
        resource = provider.generate_template(self, component.get('is'),
                                              service_name, context, name=name)
        resource['component'] = definition['id']
        resource['status'] = "NEW"
        Resource.validate(resource)
        return resource

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
                        raise (CheckmateException("Postback value for "
                               "instance '%s' was not a dictionary"
                               % resource_id))
                    # Canonicalize it
                    print "before canon: %s" % value
                    value = schema.translate_dict(value)
                    print "after canon: %s" % value
                    # Only apply instance
                    if 'instance' in value:
                        value = value['instance']
                        print "isnt in value: %" % value
                    # Merge it in
                    if 'instance' not in resource:
                        resource['instance'] = {}
                    LOG.debug("Merging postback data for resource %s: %s" % (
                              resource_id, value), extra=dict(data=resource))
                    print "pre merge: %s" % resource['instance']
                    merge_dictionary(resource['instance'], value)
                    print "post merge: %s" % resource['instance']

                elif key.startswith('connection:'):
                    # Find the connection
                    connection_id = key.split(':')[1]
                    connection = self['connections'][connection_id]
                    if not connection:
                        raise IndexError("Connection %s not found" %
                                         connection_id)
                    # Check the value
                    if not isinstance(value, dict):
                        raise (CheckmateException("Postback value for "
                               "connection '%s' was not a dictionary" %
                               connection_id))
                    # Canonicalize it
                    value = schema.translate_dict(value)
                    # Merge it in
                    LOG.debug("Merging postback data for connection %s: %s" % (
                              connection_id, value),
                              extra=dict(data=connection))
                    merge_dictionary(connection, value)
                else:
                    if isinstance(value, dict):
                        value = schema.translate_dict(value)
                    else:
                        value = schema.translate(value)
                    raise (NotImplementedError("Global post-back values not "
                           "yet supported: %s" % key))
