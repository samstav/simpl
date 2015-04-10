# encoding: utf-8
# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#
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

"""OpsCode Provider Base Module."""

import copy
import logging
import re

from fastfood import book
from SpiffWorkflow import operators
from SpiffWorkflow import specs
import yaml
from yaml.composer import ComposerError
from yaml.parser import ParserError
from yaml.scanner import ScannerError

from checkmate.common import schema
from checkmate.common import threadlocal
from checkmate import exceptions
from checkmate.providers.opscode.chef_map import ChefMap
from checkmate.providers import base
from checkmate import utils

GENERIC_TIER_ID = 'generic-chef-tier'
CATALOG = utils.yaml_to_dict("""
application:
  %s:
    is: application
    provides:
    - application: http
    requires:
    - host: linux
    options:
      berks_entry:
        type: text
      run_list:
        type: text
      count:
        type: integer  # we don't really need this in the catalog
    meta-data:
      display-hints:
        icon-20x20: "/images/chef-icon-20x20.png"
        tattoo: "/images/chef-tattoo.png"
""" % GENERIC_TIER_ID)
LOG = logging.getLogger(__name__)


def merge_berks_entries(berks_entries):
    """Combine multiple Berksfie snippets into one."""
    if not berks_entries:
        return
    combined = book.Berksfile.from_string('')
    for snippet in berks_entries:
        combined.merge(book.Berksfile.from_string(snippet))
    combined.seek(0)
    return combined.read()


class BaseOpscodeProvider(base.ProviderBase):

    """Shared class that holds common code for Opscode providers."""

    def __init__(self, *args, **kwargs):
        super(BaseOpscodeProvider, self).__init__(*args, **kwargs)

        # Map File
        self.source = self.get_setting('source')
        if self.source:
            context = threadlocal.get_context()
            self.map_file = ChefMap(url=self.source,
                                    github_token=context.get('github_token'))
        else:
            # Create noop map file
            self.map_file = ChefMap(raw="")

        self.berksfile = None

    def generate_template(self, deployment, resource_type, service, context,
                          index, provider_key, definition, planner):
        templates = super(BaseOpscodeProvider, self).generate_template(
            deployment, resource_type, service, context, index, provider_key,
            definition, planner)
        if definition['id'] == GENERIC_TIER_ID:
            # Get berks_entry option or constraints
            berks_entry = deployment.get_setting(
                'berks_entry', resource_type=resource_type,
                service_name=service, provider_key=self.key)
            if berks_entry:
                for template in templates:
                    template['desired-state']['berks_entry'] = berks_entry

        # Get run_list option or constraints
        run_list = deployment.get_setting(
            'run_list', resource_type=resource_type,
            service_name=service, provider_key=self.key)
        if run_list:
            LOG.debug("Retreived run_list from setting for resource %s",
                      index)
        else:
            run_list = self.map_file.get_component_run_list(definition)
            if run_list:
                LOG.debug("Retreived run_list from Chefmap for resource "
                          "%s", index)
        if run_list:
            if isinstance(run_list, basestring):
                run_list = self.parse_run_list(run_list)
            for template in templates:
                template['desired-state']['run_list'] = run_list
        return templates

    def prep_environment(self, wfspec, deployment, context):
        super(BaseOpscodeProvider, self).prep_environment(wfspec, deployment,
                                                          context)
        if self.prep_task:
            return  # already prepped

        # Loop over all components with berks snippets, collect them,
        # merge them, pass them into the task
        snippets = []
        for resource in deployment['resources'].itervalues():
            if (resource.get('provider') == self.name and
                    resource.get('component') == GENERIC_TIER_ID):
                snippet = utils.read_path(resource,
                                          'desired-state/berks_entry')
                if snippet:
                    snippets.append(snippet)
        self.berksfile = merge_berks_entries(snippets)

    def get_prep_tasks(self, wfspec, deployment, resource_key, component,
                       context, collect_tag='collect',
                       ready_tag='options-ready',
                       provider='checkmate.providers.opscode.solo',
                       reset_attribs=True):
        """Create (or get if they exist) tasks that collect and write map
        options.

        The collect task will run its code whenever an input task completes.
        The code to pick up the actual values based on the map comes from the
        Transforms class.

        :param wfspec: the current workflow
        :param deployment: the current deployment
        :param resource_key: the key of the resource we are configuring
        :param component: the component for that resource
        :param collect_tag: the tag to use for the collect task.
        :param ready_tag: the tag to tuse for the final, options-ready task
        :param reset_attribs: does not write attributes resolved at planning
        :returns: a dict with 'root' and 'final' tasks. The tasks are linked
                  together but are not linked into the workflow

        One collect task is created for each resource and marked with a
        'collect' tag.

        If databag tasks are needed, they are marked with a 'write-databag'
        tag.

        If role tasks are needed, they are marked with a 'write-role' tag.

        If a new set of tasks are needed (for example, in order to reconfigure
        a resource when a client is ready) then supply a different set of tags
        for the collect_tag and ready_tag than the default.

        Note:
        Only one databag with one item is currently supported per component.
        Only one role per component is supported now.
        """
        # Do tasks already exist?
        collect_tasks = wfspec.find_task_specs(provider=self.key,
                                               resource=resource_key,
                                               tag=collect_tag)
        if collect_tasks:
            ready_tasks = wfspec.find_task_specs(provider=self.key,
                                                 resource=resource_key,
                                                 tag=ready_tag)
            if not ready_tasks:
                raise exceptions.CheckmateException(
                    "'collect' task exists, but 'options-ready' is missing")
            return {'root': collect_tasks[0], 'final': ready_tasks[0]}

        write_databag = None
        write_role = None

        # Create the task data collection/map parsing task

        component_id = component['id']
        resource = deployment['resources'][resource_key]

        # Get a map file parsed with all the right objhects available in the
        # Jinja context. These objects had not been available until now.

        map_with_context = self.map_file.get_map_with_context(
            deployment=deployment, resource=resource, component=component)
        all_maps = map_with_context.get_resource_prepared_maps(resource,
                                                               deployment)

        chef_options = {}

        # Parse all maps and resolve the ones where the data is ready.

        unresolved = ChefMap.resolve_ready_maps(all_maps, deployment,
                                                chef_options)
        attrib_key = "attributes\resources\%s" % resource_key
        if reset_attribs and attrib_key in chef_options:
            # Remove ones already added in Register
            del chef_options[attrib_key]

        # Create the output template defined in the map file

        output = map_with_context.get_component_output_template(component_id)
        name = "%s Chef Data for %s" % (collect_tag.capitalize(),
                                        resource_key)
        func = "checkmate.providers.opscode.transforms" \
               ".Transforms.collect_options"
        collect_data = specs.SafeTransMerge(
            wfspec,
            name,
            function_name=func,
            description="Get data needed for our cookbooks and place it in a "
                        "structure ready for storage in a databag or role",
            properties={
                'task_tags': [collect_tag],
                'chef_maps': unresolved,
                'chef_output': output,
                'chef_options': chef_options,
                'deployment': deployment['id'],
                'extend_lists': True,
            },
            defines={'provider': self.key, 'resource': resource_key}
        )
        LOG.debug("Created data collection task for '%s'", resource_key)

        # Create the databag writing task (if needed)

        schemes = ['encrypted-databags', 'databags']
        databag_maps = ChefMap.filter_maps_by_schemes(
            all_maps, target_schemes=schemes) or []
        databags = {}
        for mapping in databag_maps:
            for target in mapping.get('targets', []):
                uri = ChefMap.parse_map_uri(target)
                scheme = uri['scheme']
                if scheme not in ['databags', 'encrypted-databags']:
                    continue
                encrypted = scheme == 'encrypted-databags'
                bag_name = uri['netloc']
                path_parts = uri['path'].strip('/').split('/')
                if len(path_parts) < 1:
                    msg = ("Mapping target '%s' is invalid. It needs "
                           "a databag name and a databag item name")
                    raise exceptions.CheckmateValidationException(msg)
                item_name = path_parts[0]

                if bag_name not in databags:
                    databags[bag_name] = {'encrypted': encrypted, 'items': []}
                if encrypted:
                    databags[bag_name]['encrypted'] = True
                if item_name not in databags[bag_name]['items']:
                    databags[bag_name]['items'].append(item_name)

        if len(databags) == 1:
            bag_name = next(databags.iterkeys())
            items = databags[bag_name]['items']
            if len(items) > 1:
                raise NotImplementedError("Chef provider does not "
                                          "currently support more than one "
                                          "databag item per component. '%s' "
                                          "has multiple items: %s" %
                                          (bag_name, items))
            item_name = items[0]
            if databags[bag_name]['encrypted'] is True:
                secret_file = '.chef/encrypted_data_bag_secret'
                path = 'chef_options/encrypted-databags/%s/%s' % (bag_name,
                                                                  item_name)
            else:
                secret_file = None
                path = 'chef_options/databags/%s/%s' % (bag_name, item_name)

            if collect_tag == 'collect':
                name = "Write Data Bag for %s" % resource['index']
            else:
                name = "Rewrite Data Bag for %s (%s)" % (
                    resource['index'], collect_tag.capitalize())
            write_databag = specs.Celery(
                wfspec, name,
                '%s.tasks.write_databag' % provider,
                call_args=[
                    context.get_queued_task_dict(
                        deployment_id=deployment['id'],
                        resource_key=resource_key
                    ),
                    deployment['id'],
                    bag_name,
                    item_name,
                    operators.PathAttrib(path)
                ],
                secret_file=secret_file,
                defines={
                    'provider': self.key,
                    'resource': resource_key,
                },
                properties={
                    'estimated_duration': 5,
                    'task_tags': ['write-databag'],
                }
            )

        elif len(databags) > 1:
            raise NotImplementedError("Chef provider does not currently "
                                      "support more than one databag per "
                                      "component. Databags requested: %s" %
                                      databags.keys())

        # Create the role writing task (if needed)

        roles = {}
        for mcomponent in map_with_context.components:
            if mcomponent['id'] == component_id:

                # Collect from chef-roles

                roles = mcomponent.get('chef-roles', {})

                # Also run through map targets

                for mapping in mcomponent.get('maps', []):
                    for target in mapping.get('targets', []):
                        uri = map_with_context.parse_map_uri(target)
                        scheme = uri['scheme']
                        if scheme != 'roles':
                            continue
                        role_name = uri['netloc']

                        if role_name not in roles:
                            roles[role_name] = {'create': False,
                                                'recipes': []}
        if len(roles) == 1:
            role_name = next(roles.iterkeys())
            role = roles[role_name]
            path = 'chef_options/roles/%s' % role_name
            run_list = None
            recipes = role.get('recipes', [])
            if recipes:
                run_list = ["recipe[%s]" % r for r in recipes]
            # FIXME: right now we create all
            # if role['create'] == True:
            if collect_tag == 'collect':
                name = "Write Role %s for %s" % (role_name, resource_key)
            else:
                name = "Rewrite Role %s for %s (%s)" % (
                    role_name, resource_key, collect_tag.capitalize())
            write_role = specs.Celery(
                wfspec, name,
                '%s.tasks.manage_role' % provider,
                call_args=[
                    context.get_queued_task_dict(
                        deployment_id=deployment['id'],
                        resource_key=resource_key
                    ),
                    role_name,
                    deployment['id']
                ],
                kitchen_name='kitchen',
                override_attributes=operators.PathAttrib(path),
                run_list=run_list,
                description="Take the JSON prepared earlier and write "
                            "it into the application role. It will be "
                            "used by the Chef recipe to access global "
                            "data",
                defines={
                    'provider': self.key,
                    'resource': resource_key
                },
                properties={
                    'estimated_duration': 5,
                    'task_tags': ['write-role'],
                }
            )
        elif len(roles) > 1:
            raise NotImplementedError("Chef provider does not currently "
                                      "support more than one role per "
                                      "component")

        # Chain the tasks: collect -> write databag -> write role
        # Note: databag and role don't depend on each other. They could run in
        # parallel, but chaining them is easier for now and less tasks

        result = {'root': collect_data}
        if write_role:
            write_role.set_property(task_tags=['options-ready'])
            result['final'] = write_role
            if write_databag:
                write_databag.follow(collect_data)
                write_role.follow(write_databag)
            else:
                write_role.follow(collect_data)
        else:
            if write_databag:
                write_databag.follow(collect_data)
                write_databag.set_property(task_tags=['options-ready'])
                result['final'] = write_databag
            else:
                result['final'] = collect_data
                collect_data.properties['task_tags'].append('options-ready')
        return result

    @staticmethod
    def parse_run_list(run_list_str):
        """Parse run_list string into dict."""
        recipes = []
        roles = []
        items = [x.strip() for x in run_list_str.split(',')]
        for item in items:
            # run_type: 'role' or 'recipe'
            # name: name of role or recipe, e.g., 'phpstack::apache'
            run_type, name, _ = re.split(r'[\[\]]', item)
            if run_type == 'role':
                roles.append(name)
            elif run_type == 'recipe':
                recipes.append(name)
            # TODO: what do we do with garbage?
        return dict(recipes=recipes, roles=roles)

    def get_catalog(self, context, type_filter=None, source=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one.

        NOTE: copied in chef-server Provider
        """
        # TODO(zns): maybe implement this an on_get_catalog so we don't have to
        #        do this for every provider
        results = base.ProviderBase.get_catalog(self, context,
                                                type_filter=type_filter)
        if results:
            # We have a prexisting or injected catalog stored. Use it.
            return results

        if self.source:
            # Get remote catalog
            catalog = self.get_remote_catalog(context, source=self.source)

            # Validate and cache catalog
            self.validate_catalog(catalog)
            if type_filter is None:
                self._dict['catalog'] = catalog
            return catalog
        return copy.deepcopy(CATALOG)

    def get_remote_catalog(self, context, source=None):
        """Get the remote catalog from a repo by obtaining a Chefmap file, if
        it exists, and parsing it.

        :param context: call context
        :keyword source: url (supports file:/// also) of a remote catalog
        """
        if source:
            map_file = ChefMap(url=source,
                               github_token=context.get('github_token'))
        else:
            map_file = self.map_file
        catalog = {}
        try:
            for doc in yaml.safe_load_all(map_file.parsed):
                if 'id' in doc:
                    for key in doc.keys():
                        if key not in schema.COMPONENT_STRICT_SCHEMA_DICT:
                            del doc[key]
                    resource_type = doc.get('is', 'application')
                    if resource_type not in catalog:
                        catalog[resource_type] = {}
                    catalog[resource_type][doc['id']] = doc
            LOG.debug('Obtained remote catalog from %s', map_file.url)
        except ValueError:
            msg = 'Catalog source did not return parsable content'
            raise exceptions.CheckmateException(msg)
        except (ParserError, ScannerError) as exc:
            raise exceptions.CheckmateValidationException(
                "Invalid YAML syntax in Chefmap. Check:\n%s" % exc)
        except ComposerError as exc:
            raise exceptions.CheckmateValidationException(
                "Invalid YAML structure in Chefmap. Check:\n%s" % exc)
        return catalog
