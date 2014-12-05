# encoding: utf-8
# Copyright (c) 2011-2013 Rackspace Hosting
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

import logging

from SpiffWorkflow import operators
from SpiffWorkflow import specs
import yaml
from yaml.composer import ComposerError
from yaml.parser import ParserError
from yaml.scanner import ScannerError

from checkmate.common import schema
from checkmate import exceptions
from checkmate.providers.opscode.chef_map import ChefMap
from checkmate.providers import ProviderBase

LOG = logging.getLogger(__name__)


class BaseOpscodeProvider(ProviderBase):

    """Shared class that holds common code for Opscode providers."""

    def get_prep_tasks(self, wfspec, deployment, resource_key, component,
                       context, collect_tag='collect',
                       ready_tag='options-ready',
                       provider='checkmate.providers.opscode.solo'):
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
            deployment=deployment, resource=resource, omponent=component)
        all_maps = map_with_context.get_resource_prepared_maps(resource,
                                                               deployment)

        chef_options = {}

        # Parse all maps and resolve the ones where the data is ready.

        unresolved = ChefMap.resolve_ready_maps(all_maps, deployment,
                                                chef_options)
        attrib_key = 'attributes:%s' % resource_key
        if attrib_key in chef_options:
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
                secret_file = 'certificates/chef.pem'
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
                call_args=[context.get_queued_task_dict(
                    deployment_id=deployment['id'],
                    resource_key=resource_key),
                    deployment['id'], bag_name, item_name,
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
                call_args=[context.get_queued_task_dict(
                    deployment_id=deployment['id'],
                    resource_key=resource_key), role_name,
                    deployment['id']],
                kitchen_name='kitchen',
                override_attributes=operators.PathAttrib(path),
                run_list=run_list,
                description="Take the JSON prepared earlier and write "
                            "it into the application role. It will be "
                            "used by the Chef recipe to access global "
                            "data",
                merge_results=True,
                defines={
                    'provider': self.key,
                    'resource': resource_key
                },
                properties={
                    'estimated_duration': 5,
                    'task_tags': ['write-role'],
                },
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

    def get_catalog(self, context, type_filter=None, source=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one.

        NOTE: copied in chef-server Provider
        """
        # TODO(zns): maybe implement this an on_get_catalog so we don't have to
        #        do this for every provider
        results = ProviderBase.get_catalog(self, context,
                                           type_filter=type_filter)
        if results:
            # We have a prexisting or injected catalog stored. Use it.
            return results

        if self.source:
            # Get remote catalog
            catalog = self.get_remote_catalog()

            # Validate and cache catalog
            self.validate_catalog(catalog)
            if type_filter is None:
                self._dict['catalog'] = catalog
            return catalog

    def get_remote_catalog(self, source=None):
        """Get the remote catalog from a repo by obtaining a Chefmap file, if
        it exists, and parsing it.

        NOTE: copied in chef-server Provider
        """
        if source:
            map_file = ChefMap(url=source)
        else:
            map_file = self.map_file
        catalog = {}
        try:
            for doc in yaml.safe_load_all(map_file.parsed):
                if 'id' in doc:
                    for key in doc.keys():
                        if key not in schema.COMPONENT_SCHEMA:
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
