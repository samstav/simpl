'''Base Classes and functions for Providers'''
import functools
import logging

import celery
from celery import exceptions as celery_exceptions

from checkmate.common import schema
from checkmate import component as cmcomp
from checkmate import exceptions
from checkmate import middleware
from checkmate.providers.provider_base_planning_mixin import \
    ProviderBasePlanningMixIn
from checkmate import utils

LOG = logging.getLogger(__name__)
PROVIDER_CLASSES = {}


class CheckmateProviderConflict(Exception):
    '''Exception Class for Provider Conflicts.'''
    pass


class CheckmateInvalidProvider(Exception):
    '''Exception Class for Invalid Provider.'''
    pass


# pylint: disable=W0232
class ProviderBaseWorkflowMixIn(object):
    '''The methods used by the workflow generation code (i.e. they need a
    workflow to work on)

    This class is mixed in to the ProviderBase
    '''

    # pylint: disable=W0613,R0913
    def prep_environment(self, wfspec, deployment, context):
        '''Add any tasks that are needed for an environment setup

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        :returns: a hash (dict) of relevant tasks. The hash keys are:
                'root': the root task in the sequence
                'final': the task that signifies readiness (work is done)
        '''
        LOG.debug("%s.%s.prep_environment called, but was not implemented",
                  self.vendor, self.name)

    # pylint: disable=W0613,R0913
    def add_resource_tasks(self, resource, key, wfspec, deployment,
                           context, wait_on=None):
        '''Add tasks needed to create a resource (the resource would normally
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
        '''
        LOG.debug("%s.%s.add_resource_tasks called, but was not implemented",
                  self.vendor, self.name)

    def _add_resource_tasks_helper(self, resource, key, wfspec, deployment,
                                   context, wait_on):
        '''Common algoprithm for all providers. Gets service_name, finds
        component, and adds any hosting wait tasks.
        '''
        if wait_on is None:
            wait_on = []
        # 1 - Wait on host to be ready
        # Find final task(s) of 'host' relationship
        tasks = self.get_host_relation_final_tasks(wfspec, key)
        if not tasks:
            # If no relation tasks, make sure host is ready
            tasks = self.get_host_ready_tasks(resource, wfspec, deployment)
        if tasks:
            wait_on.extend(tasks)

        # Get component
        component_id = resource['component']
        component = self.get_component(context, component_id)
        if not component:
            raise exceptions.CheckmateNoMapping("Component '%s' not found" %
                                                component_id)

        # Get service
        service_name = resource['service']
        if not service_name:
            error_message = "Service not found for resource %s" % key
            raise exceptions.CheckmateUserException(
                error_message, utils.get_class_name(
                    exceptions.CheckmateException), exceptions.BLUEPRINT_ERROR,
                '')
        return wait_on, service_name, component

    def add_delete_connection_tasks(self, wf_spec, context,
                                    deployment, source_resource,
                                    target_resource):
        '''Add tasks needed to delete a connection between resources

        :param wf_spec: Workflow Spec
        :param context: Context
        :param deployment: Deployment
        :param source_resource:
        :param target_resource:
        :return:
        '''
        LOG.debug("%s.%s.add_delete_connection_tasks called, "
                  "but was not implemented", self.vendor, self.name)
        pass

    # pylint: disable=R0913
    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        '''Add tasks needed to create a connection between rersources

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
        '''
        LOG.debug("%s.%s.add_connection_tasks called, "
                  "but was not implemented", self.vendor, self.name)

    def get_host_ready_tasks(self, resource, wfspec, deployment):
        '''Get tasks to wait on host if this is hosted on another resource

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        '''
        if 'hosted_on' in resource:
            host_key = resource['hosted_on']
            host_resource = deployment['resources'][host_key]
            host_final = wfspec.find_task_specs(
                resource=host_key, provider=host_resource['provider'],
                tag='final')
            return host_final

    def get_host_relation_final_tasks(self, wfspec, resource_key):
        '''Get tasks to wait on for completion of hosting relationship

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        '''
        relation_final = wfspec.find_task_specs(resource=resource_key,
                                                relation='host',
                                                provider=self.key,
                                                tag=['final'])
        return relation_final

    def get_relation_final_tasks(self, wfspec, resource):
        '''Get all 'final' tasks  for relations where this resource is a source

        :param wfspec: the SpiffWorkflow WorkflowSpec we are building
        :param resource: the resource dict from the deployment
        '''
        tasks = []
        for key, relation in resource.get('relations', {}).iteritems():
            if 'target' in relation:
                relation_final = wfspec.find_task_specs(
                    resource=resource['index'], relation=key, tag=['final'])
                if relation_final:
                    tasks.extend(relation_final)
        return tasks

    def get_host_complete_task(self, wfspec, resource):
        '''Get the task tagged as 'complete' (if any) for the resource's
        host.
        '''
        tasks = wfspec.find_task_specs(
            resource=resource.get('hosted_on', None), tag='complete')
        if tasks:  # should only be one
            return tasks[0]


class ProviderBase(ProviderBasePlanningMixIn, ProviderBaseWorkflowMixIn):
    '''Base class the providers inherit from.

    It includes mixins for deployment planning and workflow generation. The
    calls ion this base class operate on the provider (they don't need a
    deployment or workflow)
    '''
    name = 'base'
    vendor = 'checkmate'

    def __init__(self, provider, key=None):
        '''Initialize provider

        :param provider: an initialization dict (usually from the environment)
            includes:
                catalog
                vendor
                provides (overrides provider settings)

        :param key: optional key used for environment to mark which provider
                this is
        '''
        self.key = key or "%s.%s" % (self.vendor, self.name)
        if 'vendor' in provider and provider['vendor'] != self.vendor:
            LOG.debug("Vendor value being overwridden "
                      "for %s to %s", self.key, provider['vendor'])
        if provider:
            has_valid_data = False
            for k in provider.keys():
                if k in ['provides', 'catalog', 'vendor', 'endpoint']:
                    has_valid_data = True
                    break
            if not has_valid_data:
                raise CheckmateInvalidProvider("Invalid provider "
                                               "initialization data: %s" %
                                               provider)
        if 'catalog' in provider:
            self.validate_catalog(provider['catalog'])
            LOG.debug("Initializing provider %s with catalog", self.key,
                      extra=dict(data=provider['catalog']))
        self._dict = provider or {}

    def provides(self, context, resource_type=None, interface=None):
        '''Returns a list of resources that this provider can provide or
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
        '''
        results = []
        if 'provides' in self._dict:
            results = self._dict['provides']
        else:
            data = self.get_catalog(context)
            if data:
                for key, type_category in data.iteritems():
                    if key == 'lists':
                        continue
                    if key == 'current_region':
                        continue
                    for _, component in type_category.iteritems():
                        if 'provides' in component:
                            for entry in component['provides']:
                                if entry not in results:
                                    results.append(entry)
            self._dict['provides'] = results  # cache this

        filtered = []
        for entry in results:
            item_type, item_interface = entry.items()[0]
            if (resource_type is None or resource_type == item_type) and\
                    (interface is None or interface == item_interface):
                filtered.append(entry)
        return filtered

    # pylint: disable=W0613
    def get_catalog(self, context, type_filter=None):
        '''Returns catalog (filterable by type) for this provider.

        Catalogs display the types of resources that can be created by this
        provider
        :param context: a RequestContext that has a security information
        :param type_filter: which type of resource to filter by
        :return_type: dict
        '''
        result = {}
        if 'catalog' in self._dict:
            catalog = self._dict['catalog']
            if type_filter and type_filter in catalog:
                result = {type_filter: catalog[type_filter]}
            else:
                result = self._dict['catalog']
        return result

    @staticmethod
    def validate_catalog(catalog):
        '''Catalog Validation.'''
        errors = schema.validate_catalog(catalog)
        if errors:
            raise exceptions.CheckmateValidationException(
                "Invalid catalog: %s" % '\n'.join(errors))

    def get_component(self, context, component_id):
        '''Get component by ID. Default implementation gets full catalog and
        searches for ID. Override with a more efficient implementation in your
        provider code.
        '''
        LOG.debug("Default get_component implementation being used for '%s'. "
                  "Override with more efficient implementation.", self.key)
        catalog = self.get_catalog(context)
        for key, value in catalog.iteritems():
            if key == 'lists':
                continue
            if key == 'current_region':
                continue
            if component_id in value:
                result = value[component_id]
                if 'is' not in result:
                    result['is'] = key
                return cmcomp.Component(result, id=component_id, provider=self)

    def find_components(self, context, **kwargs):
        '''Finds the components that matches the supplied key/value arguments
        returns: list of matching components

        Note: resource type is usually called 'type' in serialized objects, but
              called resource_type in much of the code. Combine the two params.
        '''
        component_id = kwargs.pop('id', None)
        resource_type = kwargs.pop('resource_type', kwargs.pop('type',
                                   kwargs.pop('resource', None)))
        interface = kwargs.pop('interface', None)
        role = kwargs.pop('role', None)
        kwargs.pop('version', None)      # noise reduction
        kwargs.pop('constraints', None)  # noise reduction
        if kwargs:
            LOG.debug("Extra kwargs: %s", kwargs)

        # if id specified, use it

        if component_id:
            component = self.get_component(context, component_id)
            if component:
                # check the type/interface also match
                provides = component.provides or {}
                match = False
                for _, provide in provides.iteritems():
                    ptype = provide.get('resource_type')
                    pinterface = provide['interface']
                    if interface and interface != pinterface:
                        continue  # Interface specified and does not match
                    if resource_type and resource_type != ptype:
                        continue  # Type specified and does not match
                    match = True
                    break
                if not match and interface:
                    LOG.debug("Found component by id '%s', but type '%s' "
                              "and interface '%s' did not match",
                              component_id, resource_type or '*',
                              interface or '*')
                    return []
                # if no interface, check type at least matches 'is'
                if not match:
                    if resource_type and resource_type != component.get('is'):
                        LOG.debug("Found component by id '%s', but type '%s'"
                                  "did not match", component_id, resource_type)
                        return []
                # Check role if it exists
                if role and role not in component.get('roles', []):
                    LOG.debug("Found component by id '%s', but role '%s'"
                              "did not match", component_id, role)
                    return []

                LOG.debug("Found component by id: %s", component_id)
                return [component]
            else:
                LOG.debug("No match for component id: %s", component_id)
                return []

        # use type, interface to find a component (and check the role)

        LOG.debug("Searching for component %s:%s in provider '%s'",
                  resource_type or '*', interface or '*', self.key)
        catalog = self.get_catalog(context)
        if not catalog:
            LOG.debug("No catalog available for provider: '%s'", self.key)
            return []
        matches = []
        # Loop through catalog
        for key, components in catalog.iteritems():
            if key == 'lists':
                continue  # ignore lists, we are looking for components
            if key == 'current_region':
                continue
            for iter_id, component in components.iteritems():
                if component_id and component_id != iter_id:
                    continue  # ID specified and does not match
                if role and role not in component.get('roles', []):
                    continue  # Component does not provide given role
                comp = cmcomp.Component(component, id=iter_id)
                provides = comp.provides or {}
                for entry in provides.values():
                    ptype = entry.get('resource_type')
                    pinterface = entry['interface']
                    if interface and interface != pinterface:
                        continue  # Interface specified and does not match
                    if resource_type and resource_type != ptype:
                        continue  # Type specified and does not match
                    LOG.debug("'%s' matches in provider '%s' and provides %s",
                              iter_id, self.key, provides)
                    matches.append(cmcomp.Component(component,
                                                    id=iter_id,
                                                    provider=self))

        return matches

    @staticmethod
    def evaluate(function_string):
        '''Evaluate an option value.'''
        return utils.evaluate(function_string)

    # pylint: disable=W0613
    @staticmethod
    def proxy(path, request, tenant_id=None):
        '''Proxy request through to provider.'''
        raise exceptions.CheckmateException("Provider does not support call")

    @staticmethod
    def parse_memory_setting(text):
        '''Parses a string and extracts a number in megabytes.

        Unit default is megabyte if not provided.
        Supported names are megabyte, gigabyte, terabyte with their
        abbreviations.
        '''

        if not text or (isinstance(text, basestring) and text.strip()) == "":
            raise exceptions.CheckmateException("No memory privided")
        if isinstance(text, int):
            return text
        number = ''.join([n for n in text.strip() if n.isdigit()]).strip()
        unit = ''.join([c for c in text.strip() if c.isalpha()]).strip()
        result = 0
        if unit.lower() in ['mb', 'megabyte', 'megabytes']:
            result = int(number)
            unit = 'mb'
        elif unit.lower() in ['gb', 'gigabyte', 'gigabytes']:
            result = int(number) * 1024
            unit = 'gb'
        elif unit.lower() in ['tb', 'terabyte', 'terabytes']:
            result = int(number) * 1024 * 1024
            unit = 'tb'
        elif len(unit):
            raise exceptions.CheckmateException("Unrecognized unit of "
                                                "memory: %s" % unit)
        else:
            result = int(number)
        LOG.debug("Parsed '%s' as '%s %s', and returned %s megabyte",
                  text, number, unit, result)
        return result

    def get_setting(self, name, default=None):
        '''Returns a provider-specific setting.

        Currently detects settings coming from the provider constraints.

        :param name: the name of the setting
        :param default: optional default alue to return if the setting is not
                        found
        '''
        constraints = self._dict.get('constraints')
        if not constraints:
            return default
        matches = [c for c in constraints
                   if isinstance(c, dict) and c.keys()[0] == name]
        if matches:
            return matches[0].values()[0]
        return default

    # pylint: disable=W0613
    def delete_resource_tasks(self, wf_spec, context, deployment_id, resource,
                              key):
        '''Return a celery task/canvas for deleting the resource.'''
        LOG.debug("%s.%s.delete_resource_tasks called, "
                  "but was not implemented", self.vendor, self.name)

    def sync_resource_status(self, request_context,
                             deployment_id, resource, key):
        '''Update the status of the supplied resource based on the
        actual deployed item.
        '''
        LOG.debug("%s.%s.sync_resource_status called, "
                  "but was not implemented", self.vendor, self.name)

    def get_resource_status(self, context, deployment_id, resource, key,
                            sync_callable=None, api=None):
        '''Return remote status for resource.  Call from provider.'''

        if sync_callable:
            ctx = context.get_queued_task_dict(deployment=deployment_id,
                                               resource=key)
            return sync_callable(ctx, resource, key, api)
        else:
            LOG.debug("%s.%s.get_resource_status called, but was not "
                      "implemented", self.vendor, self.name)

    @classmethod
    def translate_status(cls, status):
        '''Return checkmate status for resource based on schema.'''
        if (hasattr(cls, '__status_mapping__') and
                status in cls.__status_mapping__):
            return cls.__status_mapping__[status]
        else:
            LOG.debug("Resource status %s was not found in status mapping",
                      status)
            #TODO(Nate): add other updates like status-message etc.
            return "UNDEFINED"

    def _verify_existing_resource(self, resource, key):
        '''Private method for Resource verification.'''
        if (resource.get('status') != "DELETED" and
                resource.get("provider") != self.name):
            raise exceptions.CheckmateException("%s did not provide resource"
                                                " %s" % (self.name, key))


def register_providers(providers):
    '''Add provider classes to list of available providers.'''
    for provider in providers:
        name = '%s.%s' % (provider.vendor, provider.name)
        if name in PROVIDER_CLASSES:
            raise CheckmateProviderConflict(name)
        PROVIDER_CLASSES[name] = provider


def get_provider_class(vendor, key):
    '''Given a vendor name, and provider key, return the provider class.'''
    name = "%s.%s" % (vendor, key)
    if name in PROVIDER_CLASSES:
        return PROVIDER_CLASSES[name]
    # Attempt instantiation by name
    class_name = "checkmate.providers.%s" % name.replace('-', '_')
    LOG.debug("Instantiating unregistered provider class: %s",
              class_name)
    try:
        klass = utils.import_class(class_name)
        if klass:
            LOG.warning("Unregistered provider class loaded: %s", class_name)
        return klass
    except StandardError as exc:
        LOG.exception(exc)
        raise CheckmateInvalidProvider("Unable to load provider '%s'" % name)


def user_has_access(context, roles):
    '''Return True if user has permissions to create resources.'''
    for role in roles:
        if role in context.roles:
            return True
    return False


class ProviderTask(celery.Task):
    '''Celery Task for providers.'''
    abstract = True

    def __call__(self, context, *args, **kwargs):
        utils.match_celery_logging(LOG)

        if isinstance(context, dict):
            context = middleware.RequestContext(**context)
        elif not isinstance(context, middleware.RequestContext):
            raise exceptions.CheckmateException(
                'Context passed into ProviderTask is an unsupported type %s.'
                % type(context))
        if context.region is None and 'region' in kwargs:
            context.region = kwargs.get('region')

        try:
            self.api = kwargs.get('api') or self.provider.connect(
                context, context.region)
        # TODO(Nate): Generalize exception raised in providers connect
        except exceptions.CheckmateValidationException:
            raise
        except StandardError as exc:
            return self.retry(exc=exc)

        self.partial = functools.partial(self.callback, context)

        try:
            data = self.run(context, *args, **kwargs)
        except celery_exceptions.RetryTaskError as exc:
            return self.retry(exc=exc)
        except exceptions.CheckmateResumableException as exc:
            return self.retry(exc=exc)

        self.callback(context, data)
        return {'instance:%s' % context.resource: data}

    def callback(self, context, data):
        '''Calls postback with instance.id to ensure posted to resource.'''
        from checkmate.deployments import tasks as deployment_tasks
        # TODO(Paul/Nate): Added here to get around circular dep issue.
        results = {
            'resources': {
                context['resource']: {
                    'instance': data
                }
            }
        }
        if 'status' in data:
            status = data['status']
            results['resources'][context['resource']]['status'] = \
                self.provider.translate_status(status)
            if status == "ERROR":
                results['status'] = "FAILED"

        deployment_tasks.postback(context['deployment'], results)
