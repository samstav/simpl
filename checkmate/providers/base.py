import logging

from checkmate import utils
from checkmate.common import schema
from checkmate.components import Component
from checkmate.exceptions import CheckmateValidationException

LOG = logging.getLogger(__name__)
PROVIDER_CLASSES = {}


class CheckmateProviderConflict(Exception):
    pass


class CheckmateInvalidProvider(Exception):
    pass


class ProviderBaseWorkflowMixIn():
    """The methods used by the workflow generation code (i.e. they need a
    workflow to work on)

    This class is mixed in to the ProviderBase
    """
    def prep_environment(self, wfspec, deployment, context):
        """Add any tasks that are needed for an environment setup

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        :returns: a hash (dict) of relevant tasks. The hash keys are:
                'root': the root task in the sequence
                'final': the task that signifies readiness (work is done)
        """
        LOG.debug("%s.%s.prep_environment called, but was not implemented" %
                (self.vendor, self.name))

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

    def add_connection_tasks(self, resource, key, relation, relation_key,
            wfspec, deployment, context):
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

    def find_tasks(self, wfspec, **kwargs):
        """Find tasks in the workflow with matching properties.

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        :param kwargs: properties to match (all must match)

        Note: 'tag' is a special case where the tag only needs to exist in
              the task_tags property. To match all tags, match against the
              'task_tags' property

        Example kwargs:
            relation: the ID of the relation we are looking for
            resource: the ID of the resource we are looking for
            provider: the key of the provider we are looking for
            tag: the tag for the task (root, final, create, etc..)
        """
        tasks = []
        for task in wfspec.task_specs.values():
            match = True
            if kwargs:
                for key, value in kwargs.iteritems():
                    if key == 'tag':
                        if value is not None and value not in\
                                (task.get_property('task_tags', []) or []):
                            match = False
                            break
                    elif value is not None and task.get_property(key) != value:
                        match = False
                        break

                    # Don't match if the task is ted toa relation and no
                    # relation key was provided
                    if 'relation' not in kwargs and \
                            task.get_property('relation'):
                        match = False
                        break
            if match:
                tasks.append(task)
        if not tasks:
            LOG.debug("No tasks found in find_tasks for %s" % ', '.join(
                    ['%s=%s' % (k, v) for k, v in kwargs.iteritems() or {}]))
        return tasks

    def get_host_ready_tasks(self, resource, wfspec, deployment):
        """Get tasks to wait on host if this is hosted on another resource

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        """
        if 'hosted_on' in resource:
            host_key = resource['hosted_on']
            host_resource = deployment['resources'][host_key]
            host_final = self.find_tasks(wfspec, resource=host_key,
                    provider=host_resource['provider'], tag='final')
            return host_final

    def get_hosting_relation_final_tasks(self, wfspec, resource_key):
        """Get tasks to wait on for completion of hosting relationship

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        """
        relation_final = self.find_tasks(wfspec, resource=resource_key,
                                         relation='host',
                                         provider=self.key,
                                         tag=['final'])
        return relation_final


class ProviderBasePlanningMixIn():
    """The methods used by the deployment planning code (i.e. they need a
    deployment to work on)

    This class is mixed in to the ProviderBase
    """
    def generate_template(self, deployment, resource_type, service, context,
            name=None):
        """Generate a resource dict to be embedded in a deployment"""
        result = dict(type=resource_type, provider=self.key, instance={})
        if not name:
            name = 'CM-%s-%s' % (deployment['id'][0:7], resource_type)
        if name:
            result['dns-name'] = name
        return result


class ProviderBase(ProviderBasePlanningMixIn, ProviderBaseWorkflowMixIn):
    """Base class the providers inherit from.

    It includes mixins for deployment planning and workflow generation. The
    calls ion this base class operate on the provider (they don't need a
    deployment or workflow)
    """
    name = 'base'
    vendor = 'checkmate'

    def __init__(self, provider, key=None):
        """Initialize provider

        :param provider: an initialization dict (usually from the environment)
            includes:
                catalog
                vendor
                provides (overrides provider settings)

        :param key: optional key used for environment to mark which provider
                this is
        """
        if provider:
            has_valid_data = False
            for k in provider.keys():
                if k in ['provides', 'catalog', 'vendor']:
                    has_valid_data = True
                    break
            if not has_valid_data:
                raise CheckmateInvalidProvider("Invalid provider "
                        "initialization data: %s" % provider)
        if 'catalog' in provider:
            self.validate_catalog(provider['catalog'])
        self._dict = provider or {}
        self.key = key or "%s.%s" % (self.vendor, self.name)
        if 'vendor' in provider and provider['vendor'] != self.vendor:
            LOG.debug("Vendor value being overwridden for %s to %s" % (
                    self.key, provider['vendor']))

    def provides(self, resource_type=None, interface=None):
        """Returns a list of resources that this provider can provide or
        validates that a specific type of resource or interface is provided.

        :param resource_type: a string used to filter the list returned by
                resource type
        :param interface: a string used to filter the list returned by
                the interface
        :returns: list of resource_type:interface hashes
        Usage:
            for item in provider.provides():
                ...
        or
            if provider.provides(resources_type='database'):
                print "We have databases!"
        """
        results = self._dict.get('provides', [])
        filtered = []
        for entry in results:
            item_type, item_interface = entry.items()[0]
            if (resource_type is None or resource_type == item_type) and\
                    (interface is None or interface == item_interface):
                filtered.append(entry)

        return filtered

    def get_catalog(self, context, type_filter=None):
        """Returns catalog (filterable by type) for this provider.

        Catalogs display the types of resources that can be created by this
        provider
        :param context: a RequestContext that has a security information
        :param type_filter: which type of resource to filter by
        :return_type: dict"""
        if 'catalog' in self._dict:
            return self._dict['catalog']
        return {}

    def validate_catalog(self, catalog):
        errors = schema.validate_catalog(catalog)
        if errors:
            raise CheckmateValidationException("Invalid catalog: %s" %
                    '\n'.join(errors))

    def get_component(self, context, id):
        """Get component by ID. Default implementation gets full catalog and
        searches for ID. Override with a more efficient implementation in your
        provider code."""
        LOG.debug("Default get_component implementation being used for '%s'. "
                "Override with more efficient implementation." % self.key)
        catalog = self.get_catalog(context)
        for key, value in catalog.iteritems():
            if key == 'lists':
                continue
            if id in value:
                return Component(value[id], id=id, provider=self)

    def find_components(self, context, **kwargs):
        """Finds the components that matches the supplied key/value arguments
        returns: list of matching components

        Note: resource type is usually called 'type' in serialized objects, but
              called resource_type in much of the code. Combine the two params.
        """
        component_id = kwargs.pop('id', None)
        resource_type = kwargs.pop('resource_type', kwargs.pop('type', None))
        interface = kwargs.pop('interface', None)
        kwargs.pop('version', None)  # noise reduction
        if kwargs:
            LOG.debug("Extra kwargs: %s" % kwargs)

        if component_id:
            component = self.get_component(context, component_id)
            if component:
                LOG.debug("Found component by id: %s" % component_id)
                return [Component(component, id=component_id, provider=self)]

        LOG.debug("Searching for component %s:%s in provider '%s'" % (
                resource_type, interface, self.key))
        catalog = self.get_catalog(context, type_filter=resource_type)
        matches = []
        # Loop through catalog
        for key, components in catalog.iteritems():
            if key == 'lists':
                continue  # ignore lists, we are looking for components
            for id, component in components.iteritems():
                provides = component.get('provides', [])
                for entry in provides:
                    ptype, pinterface = entry.items()[0]
                    if interface and interface != pinterface:
                        continue  # Interface specified and does not match
                    if resource_type and resource_type != ptype:
                        continue  # Type specified and does not match
                    LOG.debug("'%s' matches in provider '%s' and provides %s" %
                            (id, self.key, provides))
                    matches.append(Component(component, id=id, provider=self))
        return matches


def register_providers(providers):
    """Add provider classes to list of available providers"""
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
