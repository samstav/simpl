# pylint: disable=C0302
# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""The Deployment class, the Resource class and functions
for dealing with same.
"""
import collections
import copy
import logging
import os
import urlparse

import bottle
import morpheus
import simplefsm as fsm
from simplefsm import exceptions as fsmexc

from checkmate import blueprints
from checkmate.common import schema
from checkmate import constraints as cm_constraints
from checkmate import db
from checkmate import environment as cm_env
from checkmate import exceptions
from checkmate import functions
from checkmate import inputs as cm_inputs
from checkmate import keys
from checkmate import resource as cm_res
from checkmate import utils


LOG = logging.getLogger(__name__)
DB = db.get_driver()
SIMULATOR_DB = db.get_driver(connection_string=os.environ.get(
    'CHECKMATE_SIMULATOR_CONNECTION_STRING',
    os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')))
OPERATION_DEPLOYMENT_STATUS_MAP = {
    'BUILD': {'initial': 'PLANNED', 'final': 'UP', 'error': 'FAILED'},
    'DELETE': {'final': 'DELETED', 'error': 'FAILED'},
    'SCALE UP': {'initial': 'UP', 'final': 'UP', 'error': 'ALERT'},
    'SCALE DOWN': {'initial': 'UP', 'final': 'UP', 'error': 'ALERT'},
    'TAKE OFFLINE': {'initial': 'UP', 'final': 'UP', 'error': 'ALERT'},
    'BRING ONLINE': {'initial': 'UP', 'final': 'UP', 'error': 'ALERT'},
}


def validate_blueprint_options(deployment):
    """Validate blueprints options.

    - Check that blueprint options marked 'required' are supplied.
    - Check that url-type options are valid

    Raise error if not
    """
    blueprint = deployment['blueprint']
    if 'options' in blueprint:
        for key, option in blueprint['options'].iteritems():
            check_option_required(key, option, deployment)
            check_option_url(key, option, deployment)


def check_option_url(key, option, deployment):
    """Check that if an option is a URL, then its cert info is consistent."""

    inputs = deployment.get('inputs', {})
    bp_inputs = inputs.get('blueprint', {})

    if option.get('type') == 'url':
        value = bp_inputs.get(key)
        if isinstance(value, dict):
            if 'private_key' in value and 'certificate' not in value:
                msg = ("If a private key is supplied for '%s', then a "
                       "certificate is also required" % key)
                raise exceptions.CheckmateValidationException(
                    msg, friendly_message=msg)
            if 'certificate' in value and 'private_key' not in value:
                msg = ("If a certificate is supplied for '%s', then a private "
                       "key is also required" % key)
                raise exceptions.CheckmateValidationException(
                    msg, friendly_message=msg)
            if 'intermediate_key' in value and (
                    'private_key' not in value or
                    'certificate' not in value):
                msg = ("If an intermediate key is supplied for '%s', then a "
                       "certificate and private key are also required" % key)
                raise exceptions.CheckmateValidationException(
                    msg, friendly_message=msg)


def check_option_required(key, option, deployment):
    """Check that if an option is required, then it has a value."""
    inputs = deployment.get('inputs', {})
    bp_inputs = inputs.get('blueprint', {})
    if 'default' in option:
        return True
    if 'required' not in option:
        return True
    required = option['required']
    if isinstance(required, dict):
        required = functions.evaluate(
            required,
            options=deployment.get('blueprint', {}).get('options'),
            services=deployment.get('blueprint', {}).get('services'),
            resources=deployment.get('resources'),
            inputs=inputs
        )
    if required:
        if key not in bp_inputs:
            raise exceptions.CheckmateValidationException(
                "Required blueprint input '%s' not supplied" % key)


def validate_input_constraints(deployment):
    """Check that inputs meet the option constraint criteria

    Raise error if not
    """
    blueprint = deployment['blueprint']
    if 'options' in blueprint:
        options = blueprint['options']
        inputs = deployment.get('inputs', {})
        bp_inputs = inputs.get('blueprint', {})
        services = deployment.get('blueprint', {}).get('services')
        resources = deployment.get('resources')
        for key, option in options.iteritems():
            constraints = option.get('constraints')
            if constraints:
                value = bp_inputs.get(key, option.get('default'))

                # Handle special defaults
                if utils.is_evaluable(value):
                    value = utils.evaluate(value[1:])

                if value is None:
                    continue  # don't validate null inputs

                for entry in constraints:
                    parsed = functions.parse(
                        entry,
                        options=options,
                        services=services,
                        resources=resources,
                        inputs=inputs)
                    constraint = cm_constraints.Constraint.from_constraint(
                        parsed)
                    if not constraint.test(cm_inputs.Input(value)):
                        msg = ("The input for option '%s' did not pass "
                               "validation. The value was '%s'. The "
                               "validation rule was %s" %
                               (key,
                                value if option.get('type') != 'password'
                                else '*******',
                                constraint.message))
                        raise exceptions.CheckmateValidationException(msg)


def get_os_env_keys():
    """Get keys if they are set in the os_environment."""
    dkeys = {}
    if ('CHECKMATE_PUBLIC_KEY' in os.environ and
            os.path.exists(os.path.expanduser(
                os.environ['CHECKMATE_PUBLIC_KEY']))):
        try:
            path = os.path.expanduser(os.environ['CHECKMATE_PUBLIC_KEY'])
            with file(path, 'r') as f_input:
                key = f_input.read()
            if utils.is_ssh_key(key):
                dkeys['checkmate'] = {'public_key_ssh': key,
                                      'public_key_path': path}
            else:
                dkeys['checkmate'] = {'public_key': key,
                                      'public_key_path': path}
        except IOError as (errno, strerror):
            LOG.error("I/O error reading public key from CHECKMATE_PUBLIC_KEY="
                      "'%s' environment variable (%s): %s",
                      os.environ['CHECKMATE_PUBLIC_KEY'], errno, strerror)
        except StandardError as exc:
            LOG.error("Error reading public key from CHECKMATE_PUBLIC_KEY="
                      "'%s' environment variable: %s",
                      os.environ['CHECKMATE_PUBLIC_KEY'], exc)
    return dkeys


def get_client_keys(inputs):
    """Get/generate client-supplied or requested keys keys

    Inputs can supply a 'client' public key to be added to all servers or
    specify a command to generate the keys.
    """
    results = {}
    # pylint: disable=E1101
    if 'client_public_key' in inputs:
        if utils.is_ssh_key(inputs['client_public_key']):
            bottle.abort(406, "ssh public key must be in "
                         "client_public_key_ssh field, not client_public_key. "
                         "client_public_key must be in PEM format.")
        results['client'] = {'public_key': inputs['client_public_key']}

    if 'client_public_key_ssh' in inputs:
        if not utils.is_ssh_key(inputs['client_public_key_ssh']):
            bottle.abort(406, "client_public_key_ssh input is not a valid "
                         "ssh public key string: %s"
                         % inputs['client_public_key_ssh'])
        results['client'] = {'public_key_ssh': inputs['client_public_key_ssh']}
    # pylint: enable=E1101
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


class Deployment(morpheus.MorpheusDict):
    """A checkmate deployment.

    Acts like a dict. Includes validation, setting logic and other useful
    methods.
    Holds the Environment and providers during the processing of a deployment
    and creation of a workflow
    """
    __schema__ = [
        'id', 'name', 'blueprint', 'environment', 'inputs', 'display-outputs',
        'resources', 'workflow', 'status', 'created', 'tenantId', 'operation',
        'error-messages', 'live', 'plan', 'operations-history', 'created-by',
        'secrets',
        'meta-data',  # Used to store, display miscellaneous data on the
                      #deployment
        'check-limit-results', 'check-access-results',
        'includes',  # used to place YAML-referenced parts but then removed
    ]

    FSM_TRANSITIONS = {
        'NEW': {'PLANNED', 'FAILED', 'DELETED'},
        'PLANNED': {'UP', 'FAILED', 'DELETED'},
        'UP': {'ALERT', 'UNREACHABLE', 'DOWN', 'DELETED'},
        'FAILED': {'DELETED', 'PLANNED'},
        'ALERT': {'DELETED', 'UP'},
        'UNREACHABLE': {'DOWN', 'UP', 'ALERT'},
        'DOWN': {'UP', 'DELETED'},
        'DELETED': {}
    }

    legacy_statuses = {  # TODO(any): remove these when old data is clean
        "BUILD": 'UP',
        "CONFIGURE": 'UP',
        "ACTIVE": 'UP',
        'ERROR': 'FAILED',
        'DELETING': 'UP',
        'LAUNCHED': 'UP',
    }

    def __init__(self, *args, **kwargs):
        super(Deployment, self).__init__(*args, **kwargs)
        self._settings = None
        self._environment = None
        self.fsm = fsm.SimpleFSM({
            'initial': None,
            'transitions': self.FSM_TRANSITIONS
        })

        if 'status' not in self:
            self['status'] = 'NEW'
        elif self['status'] in self.legacy_statuses:
            self['status'] = self.legacy_statuses[self['status']]
        else:
            try:
                self.fsm.change_to(self['status'])
            except fsmexc.InvalidStateError as error:
                raise exceptions.CheckmateValidationException(str(error))

        if 'created' not in self:
            self['created'] = utils.get_time_string()

    def __setitem__(self, key, value):
        if key == 'status':
            if value in self.legacy_statuses:
                value = self.legacy_statuses[value]
            if value != self.fsm.current:
                try:
                    LOG.info("Tenant: %s - Deployment %s going from %s to %s",
                             self.get('tenantId'), self.get('id'),
                             self.get('status'), value)
                    self.fsm.change_to(value)
                except fsmexc.InvalidStateError as error:
                    raise exceptions.CheckmateBadState(str(error))
        super(Deployment, self).__setitem__(key, value)

    @classmethod
    def inspect(cls, obj, fail_fast=False):
        errors = super(Deployment, cls).inspect(obj)
        if 'id' in obj:
            error = db.any_id_problems(obj['id'])
            if error:
                errors.append(error)
        errors.extend(schema.validate_inputs(obj))
        if 'blueprint' in obj:
            if not blueprints.Blueprint.is_supported_syntax(obj['blueprint']):
                errors.extend(blueprints.Blueprint.inspect(obj['blueprint']))
        return errors

    def get_resources_for_service(self, service_name):
        """Gets all the non deleted resources for the given service name

        :param service_name: The name of the service
        :return: Dict of resources for the given service
        """
        instances = self['plan']['services'][service_name]['component'][
            'instances']
        resources = self.get_non_deleted_resources()
        non_deleted_resources = {}
        for resource_key in instances:
            if resource_key in resources:
                non_deleted_resources.update(
                    {resource_key: resources[resource_key]})
        return non_deleted_resources

    def get_statuses(self, context):
        """Get all statuses from a given context.

        Loops through all the resources and gets the latest status. Based on
        the resource status calculates the status of the deployment and
        operation
        :param context:
        :return:
        """
        resources = {}
        env = self.environment()

        for key, resource in self.get('resources', {}).items():
            if key.isdigit() and 'provider' in resource:
                provider = env.get_provider(resource['provider'])
                context['resource_key'] = key
                result = provider.get_resource_status(context, self.get('id'),
                                                      resource, key)
                if result:
                    resources.update({key: result['instance:%s' % key]})
        # If instance is 'DELETED' or 'ERROR', so is anything hosted on it
        for key, resource in self.get('resources', {}).items():
            if (key.isdigit() and 'hosted_on' in resource and
                    resource['hosted_on'] in resources and
                    resources[resource['hosted_on']]['status'] in
                    ['DELETED', 'ERROR']):
                resources.update({
                    key: {
                        'status': resources[resource['hosted_on']]['status']}
                })

        statuses = self._calc_dep_and_op_statuses(resources)
        statuses.update({'resources': resources})
        return statuses

    def _calc_dep_and_op_statuses(self, resources):
        """Determine deployment and operation status from resources statuses

        :param resources:
        :return:
        """
        statuses = []
        deployment_status = self['status']
        operation = self.get('operation', {})
        operation_status = operation.get('status')
        all_tasks_complete = (
            operation.get('tasks', 0) == operation.get('complete', 0))

        for value in resources.values():
            statuses.append(value['status'])

        if statuses:
            if all(status == 'DELETED' for status in statuses):
                deployment_status = 'DELETED'
                operation_status = 'COMPLETE'
            elif (all(status == 'ACTIVE' for status in statuses) and
                    all_tasks_complete):
                deployment_status = 'UP'
                operation_status = 'COMPLETE'
            elif all(status == 'NEW' for status in statuses):
                deployment_status = 'PLANNED'
                operation_status = 'NEW'
            # elif any(status == 'DELETED' for status in statuses):
            #     deployment_status = "ALERT"
            #     operation_status = 'ABORTED'

        return {'status': deployment_status,
                'operation': {'status': operation_status}}

    def environment(self):
        """Initialize environment from Deployment."""
        if self._environment is None:
            entity = self.get('environment')
            if entity:
                self._environment = cm_env.Environment(entity)
            else:
                return cm_env.Environment({})
        return self._environment

    def inputs(self):
        """Return inputs of deployment."""
        return self.get('inputs', {})

    def settings(self):
        """Returns (inits if does not exist) a reference to the deployment
        settings

        Note: this is to be used instead of the old context object
        """
        try:
            if self._settings is not None:
                return self._settings
        except AttributeError:
            pass

        results = {}

        #TODO(any): make this smarter
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
        except StandardError:
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
                    provider_key=None, relation=None, default=None):
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
        if not name:
            raise exceptions.CheckmateValidationException(
                "setting() was called with a blank value. Check your map "
                "file for bad calls to 'setting'"
            )
        if relation:
            result = self._get_svc_relation_attribute(name, service_name,
                                                      relation)
            if result is not None:
                LOG.debug(
                    "Setting '%s' matched in _get_svc_relation_attribute", name
                )
                return result
        if service_name:
            result = (self._get_input_service_override(name, service_name,
                      resource_type=resource_type))
            if result is not None:
                LOG.debug(
                    "Setting '%s' matched in _get_input_service_override", name
                )
                return result

            result = self._check_services_constraints(name, service_name)
            if result is not None:
                LOG.debug("Setting '%s' matched in "
                          "_check_services_constraints", name)
                return result

        if provider_key:
            result = (self._get_input_provider_option(name, provider_key,
                      resource_type=resource_type))
            if result is not None:
                LOG.debug(
                    "Setting '%s' matched in _get_input_provider_option", name
                )
                return result

        result = (self._check_resources_constraints(name,
                  service_name=service_name, resource_type=resource_type))
        if result is not None:
            LOG.debug("Setting '%s' matched in "
                      "_check_resources_constraints", name)
            return result

        result = (self._check_options_constraints(name,
                  service_name=service_name, resource_type=resource_type))
        if result is not None:
            LOG.debug("Setting '%s' matched in "
                      "_check_options_constraints", name)
            return result

        result = self._get_input_simple(name)
        if result is not None:
            LOG.debug("Setting '%s' matched in _get_input_simple", name)
            return result

        result = self._get_input_global(name)
        if result is not None:
            LOG.debug("Setting '%s' matched in _get_input_global", name)
            return result

        result = (self._get_env_provider_constraint(name, provider_key,
                  resource_type=resource_type))
        if result is not None:
            LOG.debug("Setting '%s' matched in "
                      "_get_env_provider_constraint", name)
            return result

        result = (self._get_env_provider_constraint(name, 'common',
                  resource_type=resource_type))
        if result is not None:
            LOG.debug("Setting '%s' matched 'common' setting in "
                      "_get_env_provider_constraint", name)
            return result

        result = self._get_resource_setting(name)
        if result is not None:
            LOG.debug("Setting '%s' matched in _get_resource_setting", name)
            return result

        result = self._get_setting_value(name)
        if result is not None:
            LOG.debug("Setting '%s' matched in _get_setting_value", name)
            return result

        LOG.debug("Setting '%s' unmatched with resource_type=%s, service=%s, "
                  "provider_key=%s and returning default '%s'", name,
                  resource_type, service_name, provider_key, default)
        return default

    def _get_resource_setting(self, name):
        """Get a value from resources with support for paths."""
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
        """Read a setting that constrains a static resource by path name

        The name must be resources/:resource_key/:setting
        """
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
                            if result is not None:
                                LOG.debug("Found setting '%s' from constraint."
                                          " %s=%s", path, key, result)
                                return result
        return default

    def _get_setting_value(self, name):
        """Get a value from the deployment hierarchy with support for paths."""
        if name:
            node = self
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
        """Get a setting directly under inputs."""
        inputs = self.inputs()
        if name in inputs:
            result = inputs[name]
            LOG.debug("Found setting '%s' in inputs. %s=%s",
                      name, name, result)
            return result

    def _get_input_simple(self, name):
        """Get a setting directly from inputs/blueprint."""
        inputs = self.inputs()
        if 'blueprint' in inputs:
            blueprint_inputs = inputs['blueprint']
            # Direct, simple entry
            if name in blueprint_inputs:
                result = blueprint_inputs[name]
                LOG.debug("Found setting '%s' in inputs/blueprint. %s=%s",
                          name, name, result)
                return result

    def _check_options_constraints(self, name, service_name=None,
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
                        if self.constraint_applies(constraint, name,
                                                   service_name=service_name,
                                                   resource_type=resource_type
                                                   ):
                            result = self._apply_constraint(name, constraint,
                                                            option=option,
                                                            option_key=key)
                            if result is not None:
                                LOG.debug("Found setting '%s' from constraint."
                                          " %s=%s", name, name, result)
                                return result

    def _check_resources_constraints(self, name, service_name=None,
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
                        if self.constraint_applies(constraint, name,
                                                   service_name=service_name,
                                                   resource_type=resource_type
                                                   ):
                            instance = self['resources'][key]['instance']
                            result = self._apply_constraint(name, constraint,
                                                            resource=instance)
                            if result is not None:
                                LOG.debug("Found setting '%s' from constraint "
                                          "in blueprint resource '%s'. %s=%s",
                                          name, key, name, result)
                                return result

    def _get_svc_relation_attribute(self, name, service_name, relation_to):
        """Get a setting implied through a blueprint service attribute

        :param name: the name of the setting
        :param service_name: the name of the service being evaluated
        :param relation_to: the name of the service ot which the service_name
        is related
        """
        blueprint = self['blueprint']
        if 'services' in blueprint:
            services = blueprint['services']
            service = services.get(service_name, None)
            if service:
                if 'relations' in service:
                    relations = service['relations']
                    for relation_key, relation in relations.iteritems():
                        if (relation_key == relation_to or
                                relation.get('service', None) == relation_to):
                            attributes = relation.get('attributes', None)
                            if attributes:
                                for attrib_key, attribute \
                                        in attributes.iteritems():
                                    if attrib_key == name:
                                        LOG.debug(
                                            "Found setting '%s' as a service "
                                            "attribute in service '%s'. %s=%s",
                                            name, service_name,
                                            name, attribute)
                                        return attribute

    def _check_services_constraints(self, name, service_name):
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
                                      "constraint in service '%s'. %s=%s",
                                      name, service_name, name, result)
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
                                              "in service '%s'. %s=%s", name,
                                              service_name, name, result)
                                    return result

    @staticmethod
    def parse_constraints(constraints):
        """Ensure constraint syntax is valid

        If it is key/values, convert it to a list.
        If the list has key/values, convert them to the expected format with
        setting, service, etc...

        """
        constraint_list = []
        if isinstance(constraints, list):
            constraint_list = constraints
        elif isinstance(constraints, dict):
            LOG.warning("Constraints not a list: %s", constraints)
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

    @staticmethod
    def constraint_applies(constraint, name, resource_type=None,
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
        LOG.debug("Constraint '%s' for '%s' applied to '%s/%s'",
                  constraint, name, service_name or '*', resource_type or '*')
        return True

    def _apply_constraint(self, name, constraint, option=None, resource=None,
                          option_key=None):
        """Returns the value of the option applying any constraint definitions

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
            if value is None and option and 'default' in option:
                value = option.get('default')
                LOG.debug("Default setting '%s' obtained from constraint "
                          "in blueprint input '%s': default=%s",
                          name, option_key, value)

        # objectify the value it if it is a typed option

        if option and 'type' in option and not resource:
            value = self._objectify(option, value)

        # If the constraint has an attribute specified, get that attribute

        if 'attribute' in constraint:
            attribute = constraint['attribute']

            if value is not None:
                result = None
                if isinstance(value, cm_inputs.Input):
                    if hasattr(value, attribute):
                        result = getattr(value, attribute)
                elif isinstance(value, collections.Mapping):
                    if attribute in value:
                        result = value[attribute]
                else:
                    error_message = "Could not read attribute '%s' while " \
                                    "obtaining option '%s' since value is " \
                                    "of type %s" % (attribute, name,
                                                    type(value).__name__)
                    raise exceptions.CheckmateException(
                        error_message,
                        friendly_message=exceptions.BLUEPRINT_ERROR)
                if result is not None:
                    LOG.debug("Found setting '%s' from constraint. %s=%s",
                              name, option_key or name, result)
                    return result

        if value is not None:
            LOG.debug("Found setting '%s' from constraint in blueprint input "
                      "'%s'. %s=%s", name, option_key, option_key, value)
            return value

    @staticmethod
    def _objectify(option, value):
        """Parse option based on type into an object of that type."""
        if 'type' not in option:
            return value
        if option['type'] == 'url':
            result = cm_inputs.Input(value)
            if isinstance(value, basestring):
                result.parse_url()
            return result
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
                        LOG.debug("Found setting '%s' as service setting "
                                  "in blueprint/services/%s/%s'. %s=%s", name,
                                  service_name, resource_type, name, result)
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
                        LOG.debug("Found setting '%s' as provider setting in "
                                  "blueprint/providers/%s/%s'. %s=%s", name,
                                  provider_key, resource_type, name, result)
                        return result

    def _get_env_provider_constraint(self, name, provider_key,
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
                              "the environment for provider '%s'. %s=%s",
                              name, provider_key, name, result)
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
            LOG.debug("Identifying component '%s' for service '%s'",
                      service_component, service_name)
            assert not isinstance(service_component, list)  # deprecated syntax
            component = self.environment().find_component(service_component,
                                                          context)
            if not component:
                error_message = ("Could not resolve component '%s'" %
                                 service_component)
                raise exceptions.CheckmateException(
                    error_message, friendly_message=exceptions.BLUEPRINT_ERROR)
            LOG.debug("Component '%s' identified as '%s' for service '%s'",
                      service_component, component['id'], service_name)
            results[service_name] = component
        return results

    def _constrained_to_one(self, service_name):
        """Return true if a service is constrained to 1, false otherwise.

        Example:

        blueprint:
          [...]
          services:
            [...]
            master:
              [...]
              constraints:
              - count: 1
              [...]
        """
        blueprint_resource = self['blueprint']['services'][service_name]
        if 'constraints' in blueprint_resource:
            for constraint in blueprint_resource['constraints']:
                if 'count' in constraint:
                    if constraint['count'] == 1:
                        return True
        return False

    @staticmethod
    def parse_source_uri(uri):
        """Parses the URI format of source

        :param uri: string uri based on display-output sources
        :returns: dict
        """
        try:
            parts = urlparse.urlparse(uri)
        except AttributeError:
            # probably a scalar
            parts = urlparse.urlparse('')

        result = {
            'scheme': parts.scheme,
            'netloc': parts.netloc,
            'path': parts.path.strip('/'),
            'query': parts.query,
            'fragment': parts.fragment,
        }
        if parts.scheme in ['options', 'resources', 'services']:
            result['path'] = os.path.join(parts.netloc.strip('/'),
                                          parts.path.strip('/')).strip('/')
        return result

    def evaluator(self, parsed_url, **kwargs):
        """given a parsed source URI, evaluate and return the value."""
        if parsed_url['scheme'] == 'options':
            return self.get_setting(parsed_url['netloc'])
        elif parsed_url['scheme'] == 'resources':
            return utils.read_path(self, 'resources/%s' % parsed_url['path'])
        elif parsed_url['scheme'] == 'services':
            return utils.read_path(kwargs['services'], parsed_url['path'])
        else:
            raise exceptions.CheckmateValidationException(
                "display-output scheme not supported: %s" %
                parsed_url['scheme']
            )
        return None

    def find_display_output_definitions(self):
        """Finds all display-output definitions."""
        result = {}
        if 'blueprint' not in self:
            return result
        # Get explicitly defined display-outputs
        result.update(self['blueprint'].get('display-outputs', {}))

        # Get options marked as outputs
        options = self['blueprint'].get('options') or {}
        marked = {
            k: {
                'type': o.get('type'),
                'source': 'options://%s' % k,
            }
            for (k, o) in options.items()
            if o.get('display-output') is True
        }
        if marked:
            result.update(marked)

        # Find definitions in services
        if 'services' in self['blueprint']:
            for key, service in self['blueprint']['services'].items():
                if 'display-outputs' not in service:
                    continue
                for do_key, output in service['display-outputs'].items():
                    if 'source' not in output:
                        raise exceptions.CheckmateValidationException(
                            "display-output without a source: %s" % do_key)
                    definition = copy.deepcopy(output)
                    # Target output to this service
                    definition['source'] = 'services://%s/%s' % (key,
                                                                 output
                                                                 ['source'])
                    result[do_key] = definition

        for value in result.values():
            # Mark password types as secrets unless already marked by author
            if value.get('type') == 'password':
                if 'is-secret' not in value:
                    value['is-secret'] = True

        return result

    def calculate_outputs(self):
        """Parse display-outputs definitions and generate display-outputs."""
        definitions = self.find_display_output_definitions()
        results = {}
        if not definitions:
            return results
        services = self.calculate_services()
        for name, definition in definitions.items():
            entry = {}
            if 'type' in definition:
                entry['type'] = definition['type']
            if definition.get('is-secret', False) is True:
                entry['is-secret'] = True
                entry['status'] = 'GENERATING'
                results[name] = entry
            try:
                parsed = Deployment.parse_source_uri(definition['source'])
                value = self.evaluator(parsed, services=services)
                if value is not None:
                    entry['value'] = value
                    results[name] = entry
                    if definition.get('is-secret', False) is True:
                        entry['status'] = 'AVAILABLE'
            except (KeyError, AttributeError) as exc:
                LOG.debug("Error in display-output: %s in %s", exc, name)
            if 'extra-sources' in definition:
                for key, source in definition['extra-sources'].items():
                    try:
                        parsed = Deployment.parse_source_uri(source)
                        value = self.evaluator(parsed, services=services)
                        if value is not None:
                            if 'extra-info' not in entry:
                                entry['extra-info'] = {}
                            entry['extra-info'][key] = value
                    except (KeyError, AttributeError) as exc:
                        LOG.debug("Error in extra-sources: %s in %s", exc, key)

        return results

    def calculate_services(self):
        """Generates list of services with interfaces and output data."""
        services = {}

        # Populate services key in deployment
        service_definitions = utils.read_path(self, 'blueprint/services') or {}
        for key, _ in service_definitions.iteritems():
            services[key] = {}
            # Write resource list for each service
            resources = self.get('resources') or {}
            resource_list = [index for index, r in resources.items()
                             if 'service' in r and r['service'] == key]
            services[key]['resources'] = resource_list
            # Find primary resource
            if resource_list:
                primary = resource_list[0]  # default
                for index, resource in resources.iteritems():
                    if index not in resource_list:
                        continue
                    if 'hosts' in resource:
                        continue
                    primary = resource
                    break
            else:
                primary = None
            # Write interfaces for each service
            if primary:
                instance = primary.get('instance') or {}
                interfaces = instance.get('interfaces')
                if interfaces:
                    utils.write_path(services[key], 'interfaces', interfaces)
        return services

    def create_resource_template(self, index, definition, service_name,
                                 context):
        """Create a new resource dict to add to the deployment

        :param index: the index of the resource within its service (ex. web2)
        :param definition: the component definition coming from the Plan
        :param context: RequestContext (auth token, etc) for catalog calls

        :returns: a validated dict of the resource ready to add to deployment
        """

        # Call provider to give us a resource template
        provider_key = definition['provider-key']
        provider = self.environment().get_provider(provider_key)
        component = provider.get_component(context, definition['id'])
        # TODO(any): Provider key can be used from withing the provider class.
        # But if we do that then the planning mixin will start reading data
        # from the child class
        LOG.debug("Getting resource templates for %s: %s", provider_key,
                  component)
        resources = provider.generate_template(
            self,
            component.get('is'),
            service_name,
            context,
            index,
            provider.key,
            definition
        )
        for resource in resources:
            resource.setdefault('component', definition['id'])
            resource.setdefault('status', "NEW")
            resource.setdefault('desired-state', {})
            cm_res.Resource.validate(resource)
        return resources

    def on_postback(self, contents, target=None):
        """Called to merge in all deployment and operation data in one

        Validates and assigns contents data to target

        :param contents: dict -- the new data to write
        :param target: dict -- optional for writing to other than this
                       deployment
        """
        if target is None:
            target = self

        if not isinstance(contents, dict):
            raise exceptions.CheckmateException(
                "Postback value was not a dictionary")
        status = contents.get('status')
        if status and not target.fsm.permitted(status):
            contents.pop('status')

        allowed = ['resources', 'operation', 'status']
        updated = {key: contents[key] for key in allowed if key in contents}
        if updated != contents:
            raise NotImplementedError("Valid postback keys include resources, "
                                      "operation and status only")

        LOG.debug("Merging postback data for deployment")
        utils.merge_dictionary(target, updated)

    def on_resource_postback(self, contents, target=None):
        """Called to merge in contents when a postback with new resource data
        is received.

        Translates values to canonical names. Iterates to one level of depth to
        handle postbacks that write to instance key

        :param contents: dict -- the new data to write
        :param target: dict -- optional for writing to other than this
                       deployment
        """
        if contents:
            if not isinstance(contents, dict):
                raise exceptions.CheckmateException(
                    "Postback value was not a dictionary")

            if target is None:
                target = self
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
                        raise exceptions.CheckmateException(
                            "Postback value for instance '%s' was not a "
                            "dictionary" % resource_id)
                    if not value:
                        LOG.warn("Deployment %s resource postback for resource"
                                 " %s was empty!", self.get('id'), resource_id)
                        continue
                    # Canonicalize it
                    value = schema.translate_dict(value)
                    # Only apply instance
                    if 'instance' in value:
                        value = value['instance']

                    # Merge it in (to target if supplied)
                    data = {
                        'resources': {
                            str(resource_id): {
                                'instance': value,
                            }
                        }
                    }
                    resource = self['resources'][resource_id]
                    if 'instance' not in resource:
                        resource['instance'] = {}
                    LOG.debug("Merging postback data for resource %s: %s",
                              resource_id, value, extra=dict(data=resource))
                    utils.merge_dictionary(target, data)

                elif key.startswith('connection:'):
                    # TODO(any): deprecate this (or handle it better)
                    # I don't think this is being used. [ZNS 2013-04-22]
                    # New partial resource_postback logic would skip this
                    # and not have it get saved
                    LOG.error("Connection was recieved in a resource_postback "
                              "and the logic for that code path is slated for "
                              "deprecation (or a refresh) '%s'=%s", key, value)
                    # Find the connection
                    connection_id = key.split(':')[1]
                    connection = self['connections'][connection_id]
                    if not connection:
                        raise IndexError("Connection %s not found" %
                                         connection_id)
                    # Check the value
                    if not isinstance(value, dict):
                        raise exceptions.CheckmateException(
                            "Postback value for connection '%s' was not a "
                            "dictionary" % connection_id)
                    # Canonicalize it
                    value = schema.translate_dict(value)
                    # Merge it in
                    LOG.debug("Merging postback data for connection %s: %s",
                              connection_id, value,
                              extra=dict(data=connection))
                    utils.merge_dictionary(connection, value)
                elif key == 'resources':
                    LOG.debug("Merging postback resources: %s", value.keys(),
                              extra=dict(data=value))
                    # Canonicalize it
                    value = {'resources': schema.translate_dict(value)}
                    # Merge it in
                    utils.merge_dictionary(target, value)
                else:
                    if isinstance(value, dict):
                        value = schema.translate_dict(value)
                    else:
                        value = schema.translate(value)
                    raise NotImplementedError("Global post-back values not "
                                              "yet supported: %s" % key)

    def get_new_and_planned_resources(self):
        """Return resources with statuses of NEW and PLANNED."""
        planned_resources = {}
        for resource_key, resource_value in self.get(
                "resources", {}).iteritems():
            if resource_value.get("status", None) in ("PLANNED", "NEW"):
                planned_resources.update({resource_key: resource_value})
        return planned_resources

    def get_non_deleted_resources(self):
        """Return resources with status not equal to DELETED."""
        resources = {}
        for resource_key, resource_value in self.get(
                "resources", {}).iteritems():
            if resource_value.get("status") != "DELETED":
                resources.update({resource_key: resource_value})
        return resources

    def get_indexed_resources(self):
        """Return a set of indexed resources."""
        indexed_resources = {}
        for resource_key, resource_value in self.get(
                "resources", {}).iteritems():
            if resource_key.isdigit():
                indexed_resources.update({resource_key: resource_value})
        return indexed_resources


def update_deployment_status(deployment_id, new_status, driver=None):
    """Update the status of the specified deployment."""
    if utils.is_simulation(deployment_id):
        driver = SIMULATOR_DB
    if not driver:
        driver = DB

    delta = {}
    if new_status:
        delta['status'] = new_status
    if delta:
        driver.save_deployment(deployment_id, delta, partial=True)


def get_status(deployment_id):
    """Gets the deployment status by deployment id.

    Protects against invalid types and key errors.
    """
    deployment = DB.get_deployment(deployment_id)
    if hasattr(deployment, '__getitem__'):
        return deployment.get('status')
