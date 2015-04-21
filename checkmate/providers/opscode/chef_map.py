# Copyright (c) 2011-2015 Rackspace US, Inc.
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
"""Retrieves and parses Chefmap files.

The 'context' for the templating language (see Jinja2 syntax
http://jinja.pocoo.org/docs/templates/) will contain...

Objects:
    deployment: which includes inputs, environment, blueprint, and resources
    component: the current component being evauated
    resource: the current resource being evaluated
    clients: hash of clients for each inbound relation (the join filter is
        useful here http://jinja.pocoo.org/docs/templates/#builtin-filters).
        Client hash includes ip only (so far).

Extended functions (added to normal Jinja functions):
    setting(name) - used to get a setting as Checkmate sees it
    parse_url(url) - returns a url_parse result as
        scheme://netloc/path;parameters?query#fragment (may also include
        username, password, hostname, port)
    hash(string) - returns an MD5 hash as expected by chef for values like
        passwords
    source(string) - evaluates a source string
    bool(var) - evaluates any source to True or False

Extended filters (added to normal Jinja filters):
    base64 - a filter to convert to multiline base64 encoded string
    prepend(string) - ensures the value starts with <string>
    preserve - To make templates work with both YAML and JSON, escape linefeeds
               instead of allowing Jinja to render them.

Example of map using source:

    id: test
    maps:
    - value: 10
      targets:
      - "attributes://{{ source('requirements://host:linux/ip') }}/ten"

"""
import copy
import functools
import logging
import os

import yaml
from yaml.composer import ComposerError
from yaml.parser import ParserError
from yaml.scanner import ScannerError

from checkmate.common import templating
from checkmate.contrib import urlparse
from checkmate import exceptions
from checkmate.providers.opscode.blueprint_cache import BlueprintCache
from checkmate import utils


LOG = logging.getLogger(__name__)


def register_scheme(scheme):
    """Register a new scheme with urlparse and parsed it like 'http' is."""
    for method in [s for s in dir(urlparse) if s.startswith('uses_')]:
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly


class SoloProviderNotReady(exceptions.CheckmateException):

    """Expected data are not yet available."""


class ChefMap(object):

    """Retrieves and parses Chefmap files."""

    def __init__(self, url=None, raw=None, parsed=None, github_token=None):
        """Create a new Chefmap instance.

        :param url: is the path to the root git repo. Supported protocols
                       are http, https, and git. The .git extension is
                       optional. Appending a branch name as a #fragment works::

                map_file = ChefMap("http://github.com/user/repo")
                map_file = ChefMap("https://github.com/org/repo.git")
                map_file = ChefMap("git://github.com/user/repo#master")
        :param raw: provide the raw content of the map file
        :param parsed: provide parsed content of the map file
        :param github_token: for private repos, supply a github oauth token

        :return: opscode.ChefMap
        """
        self.url = url
        self.github_token = github_token
        self._raw = raw
        self._parsed = parsed

    @property
    def raw(self):
        """Returns the raw file contents."""
        if self._raw is None:
            self._raw = self.get_map_file()
        return self._raw

    @property
    def parsed(self):
        """Returns the parsed file contents."""
        if self._parsed is None:
            self._parsed = templating.parse(
                self.raw, extra_globals={'source': templating.noop})
        return self._parsed

    def get_map_file(self):
        """Return the Chefmap file as a string."""
        if self.url.startswith("file://"):
            chefmap_dir = self.url[7:]  # strip off "file://"
            chefmap_path = os.path.join(chefmap_dir, "Chefmap")
            with open(chefmap_path) as chefmap:
                return chefmap.read()
        else:
            cache = BlueprintCache(self.url, github_token=self.github_token)
            cache.update()
            if os.path.exists(os.path.join(cache.cache_path, "Chefmap")):
                with open(os.path.join(cache.cache_path,
                                       "Chefmap")) as chefmap:
                    return chefmap.read()
            else:
                error_message = ("No Chefmap in repository %s" %
                                 cache.cache_path)
                raise exceptions.CheckmateException(error_message)

    def get_map_with_context(self, **kwargs):
        """Returns a map file that was parsed with real data in the context."""
        # Add defaults if there is a component and no defaults specified
        if kwargs and 'defaults' not in kwargs and 'component' in kwargs:
            component = kwargs['component']
            # used by setting() in Jinja context to return defaults
            defaults = {}
            for key, option in component.get('options', {}).iteritems():
                if 'default' in option:
                    default = option['default']
                    try:
                        if default.startswith('=generate'):
                            default = utils.evaluate(default[1:])
                    except AttributeError:
                        pass  # default probably not a string type
                    defaults[key] = default
            kwargs['defaults'] = defaults

        extra_globals = kwargs.setdefault('extra_globals', {})
        if 'source' not in extra_globals:
            extra_globals['source'] = functools.partial(
                self.source, kwargs.get('deployment'), kwargs.get('resource'))
        parsed = templating.parse(self.raw, **kwargs)
        return ChefMap(parsed=parsed, github_token=self.github_token)

    def source(self, deployment, resource, url):
        """Parse and return the value of a 'source' entry."""
        maps = self.get_resource_prepared_maps(
            resource, deployment, maps=[{'source': url}])
        val = self.evaluate_mapping_source(maps[0], deployment)
        LOG.debug("Evaluated map '%s' to %s", url, val)
        return val

    def get_component_run_list(self, component):
        run_list = {}
        component_id = component['id']
        for mcomponent in self.components:
            if mcomponent['id'] == component_id:
                run_list = mcomponent.get('run-list', {})
                assert isinstance(run_list, dict), ("component '%s' run-list "
                                                    "is not a map" %
                                                    component_id)
        if not run_list:
            if 'role' in component:
                name = '%s::%s' % (component_id, component['role'])
            else:
                name = component_id
                if name == 'mysql':
                    # FIXME: hack (install server by default, not client)
                    name += "::server"
            if component_id.endswith('-role'):
                run_list['roles'] = [name[0:-5]]  # trim the '-role'
            else:
                run_list['recipes'] = [name]
        LOG.debug("Component run_list determined to be %s", run_list)
        return run_list

    def get_resource_prepared_maps(self, resource, deployment, maps=None):
        """Parse maps for a resource and identify paths for finding the map
        data.

        By looking at a requirement's key and finding the relations that
        satisfy that key (using the requires-key attribute) and that have a
        'target' attribute, we can identify the resource we need to get the
        data from and provide the path to that resource as a hint to the
        TransMerge task
        """
        if not maps:
            maps = self.get_component_maps(resource['component'])
        result = []
        for mapping in maps or []:

            # find paths for sources

            if 'source' in mapping:
                url = ChefMap.parse_map_uri(mapping['source'])
                if url['scheme'] == 'requirements':
                    key = url['netloc']
                    relations = None
                    if 'relations' in resource:
                        relations = [
                            r for r in resource['relations'].values()
                            if (r.get('requires-key') == key and 'target' in r)
                        ]
                    if relations:
                        target = relations[0]['target']
                        #  account for host
                        #  FIXME: This representation needs to be consistent!
                        if relations[0].get('relation', '') != 'host':
                            mapping['path'] = ('resources/%s/instance/'
                                               'interfaces/%s'
                                               % (target,
                                                  relations[0]['interface']))
                        else:
                            path = 'resources/%s' % target
                            if not url['path'].startswith('instance'):
                                path = '%s/instance' % path
                            mapping['path'] = path
                    result.append(mapping)
                elif url['scheme'] == 'supported':
                    key = url['netloc']
                    relations = None
                    if 'relations' in resource:
                        relations = [
                            r for r in resource['relations'].values()
                            if (r.get('supports-key') == key and 'target' in r)
                        ]
                    if relations:
                        target = relations[0]['target']
                        #  account for host
                        #  FIXME: This representation needs to be consistent!
                        if relations[0].get('relation', '') != 'host':
                            mapping['path'] = ('resources/%s/instance/'
                                               'interfaces/%s'
                                               % (target,
                                                  relations[0]['interface']))
                        else:
                            path = 'resources/%s' % target
                            if not url['path'].startswith('instance'):
                                path = '%s/instance' % path
                            mapping['path'] = path
                    result.append(mapping)
                elif url['scheme'] == 'clients':
                    key = url['netloc']
                    for client in deployment['resources'].values():
                        if 'relations' not in client:
                            continue
                        relations = [
                            r for r in client['relations'].values()
                            if ((r.get('requires-key') == key or
                                 r.get('supports-key') == key) and
                                r.get('target') == resource['index'])
                        ]
                        if relations:
                            mapping['path'] = ('resources/%s/instance' %
                                               client['index'])
                            result.append(copy.copy(mapping))
                else:
                    result.append(mapping)
            else:
                result.append(mapping)

        # Write attribute hints
        key = resource['index']
        for mapping in result:
            mapping['resource'] = key
        return result

    @property
    def components(self):
        """The components in the map file."""
        try:
            result = [
                c for c in yaml.safe_load_all(self.parsed) if 'id' in c
            ]
        except (ParserError, ScannerError) as exc:
            raise exceptions.CheckmateValidationException(
                "Invalid YAML syntax in Chefmap. Check:\n%s" % exc)
        except ComposerError as exc:
            raise exceptions.CheckmateValidationException(
                "Invalid YAML structure in Chefmap. Check:\n%s" % exc)
        return result

    def has_mappings(self, component_id):
        """Does the map file have any mappings for this component."""
        for component in self.components:
            if component_id == component['id']:
                if component.get('maps') or component.get('output'):
                    return True
        return False

    def has_requirement_mapping(self, component_id, requirement_key):
        """Does the map file have any 'requirements' mappings for this
        component's requirement_key requirement.
        """
        for component in self.components:
            if component_id == component['id']:
                for _map in component.get('maps', []):
                    url = self.parse_map_uri(_map.get('source'))
                    if url['scheme'] == 'requirements':
                        if url['netloc'] == requirement_key:
                            return True
        return False

    def has_supported_mapping(self, component_id, supported_key):
        """Does the map file have any 'supported' mappings for this
        component's supported_key 'supports' entry.
        """
        for component in self.components:
            if component_id == component['id']:
                for _map in component.get('maps', []):
                    url = self.parse_map_uri(_map.get('source'))
                    if url['scheme'] == 'supported':
                        if url['netloc'] == supported_key:
                            return True
        return False

    def has_client_mapping(self, component_id, provides_key):
        """Does the map file have any 'clients' mappings for this
        component's provides_key connection point.
        """
        for component in self.components:
            if component_id == component['id']:
                for _map in component.get('maps', []):
                    url = self.parse_map_uri(_map.get('source'))
                    if url['scheme'] == 'clients':
                        if url['netloc'] == provides_key:
                            return True
        return False

    @staticmethod
    def is_writable_val(val):
        """Determine if we should write the value."""
        return val is not None and len(str(val)) > 0

    def get_attributes(self, component_id, deployment):
        """Parse maps and get attributes for a specific component that are
        ready.
        """
        for component in self.components:
            if component_id == component['id']:
                maps = (m for m in component.get('maps', [])
                        if any(target for target in m.get('targets', [])
                               if (self.parse_map_uri(target)['scheme'] ==
                                   'attributes')))
                if maps:
                    result = {}
                    for _map in maps:
                        value = None
                        try:
                            value = self.evaluate_mapping_source(_map,
                                                                 deployment)
                        except SoloProviderNotReady:
                            LOG.debug("Map not ready yet: %s", _map)
                            continue
                        if ChefMap.is_writable_val(value):
                            for target in _map.get('targets', []):
                                url = self.parse_map_uri(target)
                                if url['scheme'] == 'attributes':
                                    utils.write_path(result, url['path'],
                                                     value)
                    return result

    def get_component_maps(self, component_id):
        """Get maps for a specific component."""
        for component in self.components:
            if component_id == component['id']:
                return component.get('maps')
        return []

    def get_component_output_template(self, component_id):
        """Get output template for a specific component."""
        for component in self.components:
            if component_id == component['id']:
                return component.get('output')

    def has_runtime_options(self, component_id):
        """Check if a component has maps that can only be resolved at run-time.

        Those would be items like:
        - requirement sources where the required resource does not exist yet
        - supports sources where the supported resource does not exist yet

        :returns: boolean
        """
        for component in self.components:
            if component_id == component['id']:
                maps = (m for m in component.get('maps', [])
                        if (self.parse_map_uri(
                            m.get('source'))['scheme'] in ['requirements',
                                                           'supported']))
                if any(maps):
                    return True
        return False

    @staticmethod
    def filter_maps_by_schemes(maps, target_schemes=None):
        """Returns the maps that have specific target schemes."""
        if not maps or not target_schemes:
            return maps
        result = []
        for mapping in maps:
            for target in mapping.get('targets', []):
                url = ChefMap.parse_map_uri(target)
                if url['scheme'] in target_schemes:
                    result.append(mapping)
                    break
        return result

    @staticmethod
    def resolve_map(mapping, data, output):
        """Resolve mapping and write output."""
        ChefMap.apply_mapping(
            mapping,
            ChefMap.evaluate_mapping_source(mapping, data),
            output
        )

    @staticmethod
    def apply_mapping(mapping, value, output):
        """Applies the mapping value to all the targets.

        :param mapping: dict of the mapping
        :param value: the value of the mapping. This is evaluated elsewhere.
        :param output: a dict to apply the mapping to
        """
        if not ChefMap.is_writable_val(value):
            return
        write_array = False
        if 'source' in mapping:
            url = ChefMap.parse_map_uri(mapping['source'])
            if url['scheme'] == 'clients':
                write_array = True

        for target in mapping.get('targets', []):
            url = ChefMap.parse_map_uri(target)
            writable_value = value
            writable_path = url['path'].strip('/')

            if url['scheme'] == 'attributes':
                if 'resource' not in mapping:
                    message = 'Resource hint required in attribute mapping'
                    raise exceptions.CheckmateException(message)

                path = 'attributes/resources/%s' % mapping['resource']
                if not utils.path_exists(output, path):
                    utils.write_path(output, path, {})
                seed = utils.read_path(output, path)
            elif url['scheme'] == 'outputs':
                if url['scheme'] not in output:
                    output[url['scheme']] = {}
                seed = output[url['scheme']]
            elif url['scheme'] in ['databags', 'encrypted-databags', 'roles']:
                if url['scheme'] not in output:
                    output[url['scheme']] = {}
                seed = output[url['scheme']]
                writable_path = os.path.join(url['netloc'], url['path'].strip(
                    '/'))
            else:
                raise NotImplementedError("Unsupported url scheme '%s' in url "
                                          "'%s'" % (url['scheme'], target))
            if write_array:
                existing = utils.read_path(seed, writable_path)
                if not existing:
                    existing = []
                if writable_value not in existing:
                    existing.append(writable_value)
                writable_value = existing
            utils.write_path(seed, writable_path, writable_value)
            LOG.debug("Wrote to target '%s': %s", target, writable_value)

    @staticmethod
    def evaluate_mapping_source(mapping, data):
        """Returns the mapping source value.

        Raises a SoloProviderNotReady exception if the source is not yet
        available

        :param mapping: the mapping to resolved
        :param data: the data to read from
        :returns: the value
        """
        value = None
        if 'source' in mapping:
            url = ChefMap.parse_map_uri(mapping['source'])
            if url['scheme'] in ['requirements', 'supported', 'clients']:
                path = mapping.get('path', url['netloc'])
                full_path = os.path.join(path, url['path'])
                alt_path = mapping.get('alt_path')
                if alt_path:
                    alt_path = os.path.join(alt_path, url['path'])
                try:
                    value = utils.read_path(data, full_path)
                    if value is None and alt_path:
                        value = utils.read_path(data, alt_path)
                except (KeyError, TypeError) as exc:
                    LOG.debug("'%s' not yet available at '%s': %s",
                              mapping['source'], full_path, exc,
                              extra={'data': data})
                    raise SoloProviderNotReady("'%s' not ready" % full_path)

                LOG.debug("Resolved mapping '%s' to '%s'", mapping['source'],
                          value)
            else:
                raise NotImplementedError("Unsupported url scheme '%s' in url "
                                          "'%s'" % (url['scheme'],
                                                    mapping['source']))
        elif 'value' in mapping:
            value = mapping['value']
        else:
            message = "Mapping has neither 'source' nor 'value'"
            raise exceptions.CheckmateException(message)
        return value

    @staticmethod
    def resolve_ready_maps(maps, data, output):
        """Parse and apply maps that are ready.

        :param maps: a list of maps to attempt to resolve
        :param data: the source of the data (a deployment)
        :param output: a dict to write the output to
        :returns: unresolved maps
        """
        unresolved = []
        for mapping in maps:
            value = None
            try:
                value = ChefMap.evaluate_mapping_source(mapping, data)
            except SoloProviderNotReady:
                unresolved.append(mapping)
                continue
            if value is not None:
                ChefMap.apply_mapping(mapping, value, output)
            else:
                unresolved.append(mapping)
        return unresolved

    @staticmethod
    def parse_map_uri(uri):
        """Parses the URI format of a map.

        :param uri: string uri based on map file supported sources and targets
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
        if parts.scheme in ['attributes', 'outputs']:
            result['path'] = os.path.join(parts.netloc.strip('/'),
                                          parts.path.strip('/')).strip('/')
        return result
