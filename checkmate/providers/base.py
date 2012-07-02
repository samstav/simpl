import logging

from checkmate import utils

LOG = logging.getLogger(__name__)
PROVIDER_CLASSES = {}


class CheckmateProviderConflict(Exception):
    pass


class CheckmateInvalidProvider(Exception):
    pass


class ProviderBaseWorkflowMixIn():
    """The methods used by the workflow generation code

    This class is mixed in to the ProviderBase
    """
    def prep_environment(self, wfspec, deployment):
        """Add any tasks that are needed for an environment setup

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        :returns: a hash (dict) of relevant tasks. The hash keys are:
                'root': the root task in the sequence
                'final': the task that signifies readiness (work is done)
        """
        return {}

    def add_resource_tasks(self, resource, key, wfspec, deployment,
            context, wait_on=None):
        """Add tasks needed to create a resource (the resource would normally
            be what was generated in the generate_template call)

        :param wait_on: tasks to wait on before executing
        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        :returns: a hash (dict) of relevant tasks. The hash keys are:
                'root': the root task in the sequence
                'final': the task that signifies readiness (work is done)
        Note: the tasks also have defined properties that mark the resource
              impacted, the provider who owns the task, and the position or
              role of the task (ex. final, root, etc). This allows for other
              providers top look this task up and connect to it if needed
        """
        LOG.debug("%s.%s.add_resource_tasks called, but was not implemented" %
                (self.vendor, self.name))
        return {}

    def add_connection_tasks(self, resource, key, relation, relation_key,
            wfspec, deployment):
        """Add tasks needed to create a connection between rersources

        :param resource: the resource we are connecting from
        :param key: the ID of resource we are connecting from
        :param relation: the relation we are connecting
        :param relation_key: the ID of the relation
        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        :returns: a hash (dict) of relevant tasks. The hash keys are:
                'root': the root task in the sequence
                'final': the task that signifies readiness (work is done)
        Note: the tasks also have defined properties that mark the resource
              impacted, the provider who owns the task, and the position or
              role of the task (ex. final, root, etc). This allows for other
              providers top look this task up and connect to it if needed
        """
        LOG.debug("%s.%s.add_connection_tasks called, but was not "
                "implemented" % (self.vendor, self.name))
        return {}

    def find_tasks(self, wfspec, resource=None, provider=None, tag=None):
        """Find tasks in the workflow based on deployment data.

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        :param resource: the ID of the resource we are looking for
        :param provider: the key of the provider we are looking for
        :param tag: the tag for the task (root, final, create, etc..)
        """
        tasks = []
        for task in wfspec.task_specs.values():
            if (resource is None or task.get_property('resource') == resource)\
                    and (provider is None or task.get_property('provider') ==
                            provider) \
                    and (tag is None or tag in
                            (task.get_property('task_tags') or [])):
                tasks.append(task)
        if not tasks:
            LOG.debug("No tasks found in find_tasks for resource=%s, "
                    "provider=%s, tag=%s" % (resource, provider, tag))
        return tasks

    def add_wait_on_host_tasks(self, resource, wfspec, deployment, wait_on):
        """Add task to wait on host if this is hosted on another resource

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        """
        if 'hosted_on' in resource:
            host_key = resource['hosted_on']
            host_resource = deployment['resources'][host_key]
            host_final = self.find_tasks(wfspec, resource=host_key,
                    provider=host_resource['provider'], tag='final')
            if host_final:
                host_final = host_final[0]
                wait_on.append(host_final)
            return host_final


class ProviderBasePlanningMixIn():
    """The methods used by the deployment planning code

    This class is mixed in to the ProviderBase
    """
    def generate_template(self, deployment, resource_type, service, name=None):
        """Generate a resource dict to be embedded in a deployment"""
        result = dict(type=resource_type, provider=self.key)
        if not name:
            name = 'CM-%s-%s' % (deployment['id'][0:7], resource_type)
        if name:
            result['dns-name'] = name
        return result

    def get_deployment_setting(self, deployment, name, resource_type=None,
                service=None, default=None):
        """Find a value that an option was set to.

        Look in this order:
        - start with the deployment inputs where the paths are:
            inputs/blueprint
            inputs/providers/:provider
        - finally look at the component defaults

        :param deployment: the full deployment json
        :param name: the name of the setting
        :param service: the name of the service being evaluated
        :param resource_type: the type of the resource being evaluated (ex.
                compute, database)
        :param default: value to return if no match found
        """
        result = self._get_input_simple(deployment, name)
        if result:
            return result

        result = self._get_input_blueprint_option_constraint(deployment, name,
                service=service)
        if result:
            return result

        if service:
            result = self._get_input_service_override(deployment, service,
                    resource_type, name)
            if result:
                return result

        result = self._get_input_provider_option(deployment, name,
                resource_type=resource_type)
        if result:
            return result

        return default

    def _get_input_simple(self, deployment, name):
        """Get a setting directly from inputs/blueprint"""
        if 'inputs' in deployment:
            inputs = deployment['inputs']
            if 'blueprint' in inputs:
                blueprint_inputs = inputs['blueprint']
                # Direct, simple entry
                if name in blueprint_inputs:
                    result = blueprint_inputs[name]
                    LOG.debug("Found setting '%s' in inputs/blueprint: %s" %
                            (name, result))
                    return result

    def _get_input_blueprint_option_constraint(self, deployment, name,
            service=None):
        """Get a setting implied through blueprint option constraint

        :param deployment: the full deployment json
        :param name: the name of the setting
        :param service: the name of the service being evaluated
        """
        blueprint = deployment['blueprint']
        if 'options' in blueprint:
            options = blueprint['options']
            for key, option in options.iteritems():
                if 'constrains' in option:  # the verb 'constrains' (not noun)
                    for constraint in option['constrains']:
                        if self.constraint_applies(constraint, name,
                                service=service):
                            # Find in inputs or use default if available
                            result = self._get_input_simple(deployment, key)
                            if result:
                                LOG.debug("Found setting '%s' from constraint "
                                        "in blueprint input '%s': %s" % (name,
                                        key, result))
                                return result
                            if 'default' in option:
                                result = option['default']
                                LOG.debug("Found setting '%s' from constraint "
                                        "in blueprint input '%s': default=%s"
                                        % (name, key, result))
                                return result

    def _get_input_service_override(self, deployment, service, resource_type,
                name):
        """Get a setting applied through a deployment setting on a service

        Params are ordered similar to how they appear in yaml/json::
            inputs/services/:id/:resource_type/:option-name

        :param deployment: the full deployment json
        :param service: the name of the service being evaluated
        :param resource_type: the resource type (ex. compute)
        :param name: the name of the setting
        """
        if 'inputs' in deployment:
            inputs = deployment['inputs']
            if 'services' in inputs:
                services = inputs['services']
                if service in services:
                    service_object = services[service]
                    if resource_type in service_object:
                        options = service_object[resource_type]
                        if name in options:
                            result = options[name]
                            LOG.debug("Found setting '%s' as service "
                                    "setting in blueprint/services/%s/%s':"
                                    " %s" % (name, service, resource_type,
                                    result))
                            return result

    def _get_input_provider_option(self, deployment, name, resource_type=None):
        """Get a setting applied through a deployment setting to a provider

        Params are ordered similar to how they appear in yaml/json::
            inputs/providers/:id/[:resource_type/]:option-name

        :param deployment: the full deployment json
        :param name: the name of the setting
        :param resource_type: the resource type (ex. compute)
        """
        if 'inputs' in deployment:
            inputs = deployment['inputs']
            if 'providers' in inputs:
                providers = inputs['providers']
                if self.name in providers:
                    provider = providers[self.name]
                    if resource_type in provider:
                        options = provider[resource_type]
                        if name in options:
                            result = options[name]
                            LOG.debug("Found setting '%s' as provider "
                                    "setting in blueprint/providers/%s/%s':"
                                    " %s" % (name, self.name, resource_type,
                                    result))
                            return result

    def constraint_applies(self, constraint, name, service=None):
        """Checks if a constraint applies to this provider

        :param constrain: the constraint dict
        :param name: the name of the setting
        :param service: the name of the service being evaluated
        """
        if 'resource_type' in constraint:
            if constraint['resource_type'] not in self.provides():
                return False
        if 'setting' in constraint:
            if constraint['setting'] != name:
                return False
        if 'service' in constraint:
            if service is None or constraint['service'] != service:
                return False
        LOG.debug("Constraint '%s' for '%s' applied to provider '%s'" % (
                constraint, name, self.__class__.__name__))
        return True


class ProviderBase(ProviderBasePlanningMixIn, ProviderBaseWorkflowMixIn):
    """Base class the providers inherit from.

    It includes mixins for deployment planning and workflow generation
    """
    name = 'base'
    vendor = 'checkmate'

    def __init__(self, provider, key=None):
        """Initialize provider with :
        :param provider: a dict from thje environment
        :param key: optional key used for environment to mark which provider
                is
        """
        self.dict = provider
        self.key = key

    def provides(self):
        """Returns  a list of resources that this provider can provder"""
        return self.dict.get('provides', [])

    def get_catalog(self, context, type_filter=None):
        """Returns catalog (filterable by type) for this provider.

        Catalogs display the types of resources that can be created by this
        provider
        :param context: a RequestContext that has a security information
        :param type_filter: which type of resource to filter by
        :return_type: dict"""
        return {}


def register_providers(providers):
    """Add provider class to list of available providers"""
    for provider in providers:
        name = '%s.%s' % (provider.vendor, provider.name)
        if name in PROVIDER_CLASSES:
            raise CheckmateProviderConflict(name)
        PROVIDER_CLASSES[name] = provider


def get_provider_class(vendor, key):
    """Given a vendor name, and provider key, return the provider class"""
    name = "%s.%s" % (vendor, key)
    if name in PROVIDER_CLASSES:
        return PROVIDER_CLASSES[name]
    # Attempt instantiation by name
    class_name = "checkmate.providers.%s" % name.replace('-', '_')
    LOG.debug("Instantiating unregistered provider class: %s" % class_name)
    try:
        klass = utils.import_class(class_name)
        if klass:
            LOG.warning("Unregistered provider class loaded: %s" % class_name)
        return klass
    except StandardError as exc:
        LOG.exception(exc)
        raise CheckmateInvalidProvider("Unable to load provider '%s'" % name)
