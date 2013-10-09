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
"""Retrieves and parses Chefmap files."""
import logging
import os
import urlparse

import yaml
from yaml.composer import ComposerError
from yaml.parser import ParserError
from yaml.scanner import ScannerError

from checkmate.common import templating
from checkmate import exceptions
from checkmate.providers.opscode.solo import tasks
from checkmate.providers.opscode.solo import SoloProviderNotReady
from checkmate import utils


LOG = logging.getLogger(__name__)


def register_scheme(scheme):
    """Use this to register a new scheme with urlparse and have it be
    parsed in the same way as http is parsed
    """
    for method in [s for s in dir(urlparse) if s.startswith('uses_')]:
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly


class ChefMap(object):
    """Retrieves and parses Chefmap files."""

    def __init__(self, url=None, raw=None, parsed=None):
        """Create a new Chefmap instance.

        :param url: is the path to the root git repo. Supported protocols
                       are http, https, and git. The .git extension is
                       optional. Appending a branch name as a #fragment works::

                map_file = ChefMap("http://github.com/user/repo")
                map_file = ChefMap("https://github.com/org/repo.git")
                map_file = ChefMap("git://github.com/user/repo#master")
        :param raw: provide the raw content of the map file
        :param parsed: provide parsed content of the map file

        :return: solo.ChefMap

        """
        self.url = url
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
            self._parsed = templating.parse(self.raw)
        return self._parsed

    def get_map_file(self):
        """Return the Chefmap file as a string."""
        if self.url.startswith("file://"):
            chefmap_dir = self.url[7:]  # strip off "file://"
            chefmap_path = os.path.join(chefmap_dir, "Chefmap")
            with open(chefmap_path) as chefmap:
                return chefmap.read()
        else:
            tasks._cache_blueprint(self.url)
            repo_cache = tasks._get_blueprints_cache_path(self.url)
            if os.path.exists(os.path.join(repo_cache, "Chefmap")):
                with open(os.path.join(repo_cache, "Chefmap")) as chefmap:
                    return chefmap.read()
            else:
                error_message = "No Chefmap in repository %s" % repo_cache
                raise exceptions.CheckmateException(error_message)

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

    def get_component_output_template(self, component_id):
        """Get output template for a specific component."""
        for component in self.components:
            if component_id == component['id']:
                return component.get('output')

    def get_component_run_list(self, component_id):
        """Get run_list for a specific component."""
        for component in self.components:
            if component_id == component['id']:
                return component.get('run_list')

    def has_runtime_options(self, component_id):
        """Check if a component has maps that can only be resolved at run-time.

        Those would be items like:
        - requirement sources where the required resource does not exist yet

        :returns: boolean
        """
        for component in self.components:
            if component_id == component['id']:
                maps = (m for m in component.get('maps', [])
                        if (self.parse_map_uri(
                            m.get('source'))['scheme'] in ['requirements']))
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
        # FIXME: hack to get v0.5 out. Until we implement search() or Craig's
        # ValueFilter. For now, just write arrays for all 'clients' mappings
        if not ChefMap.is_writable_val(value):
            return
        write_array = False
        if 'source' in mapping:
            url = ChefMap.parse_map_uri(mapping['source'])
            if url['scheme'] == 'clients':
                write_array = True

        for target in mapping.get('targets', []):
            url = ChefMap.parse_map_uri(target)
            if url['scheme'] == 'attributes':
                if 'resource' not in mapping:
                    message = 'Resource hint required in attribute mapping'
                    raise exceptions.CheckmateException(message)

                path = '%s:%s' % (url['scheme'], mapping['resource'])
                if path not in output:
                    output[path] = {}
                if write_array:
                    existing = utils.read_path(output[path],
                                               url['path'].strip('/'))
                    if not existing:
                        existing = []
                    if value not in existing:
                        existing.append(value)
                    value = existing
                utils.write_path(output[path], url['path'].strip('/'), value)
                LOG.debug("Wrote to target '%s': %s", target, value)
            elif url['scheme'] == 'outputs':
                if url['scheme'] not in output:
                    output[url['scheme']] = {}
                if write_array:
                    existing = utils.read_path(output[url['scheme']],
                                               url['path'].strip('/'))
                    if not existing:
                        existing = []
                    if value not in existing:
                        existing.append(value)
                    value = existing
                utils.write_path(
                    output[url['scheme']], url['path'].strip('/'), value
                )
                LOG.debug("Wrote to target '%s': %s", target, value)
            elif url['scheme'] in ['databags', 'encrypted-databags', 'roles']:
                if url['scheme'] not in output:
                    output[url['scheme']] = {}
                path = os.path.join(url['netloc'], url['path'].strip('/'))
                if write_array:
                    existing = utils.read_path(output[url['scheme']], path)
                    if not existing:
                        existing = []
                    if value not in existing:
                        existing.append(value)
                    value = existing
                utils.write_path(output[url['scheme']], path, value)
                LOG.debug("Wrote to target '%s': %s", target, value)
            else:
                raise NotImplementedError("Unsupported url scheme '%s' in url "
                                          "'%s'" % (url['scheme'], target))

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
            if url['scheme'] in ['requirements', 'clients']:
                path = mapping.get('path', url['netloc'])
                try:
                    value = utils.read_path(data, os.path.join(path,
                                            url['path']))
                except (KeyError, TypeError) as exc:
                    LOG.debug("'%s' not yet available at '%s': %s",
                              mapping['source'], path, exc,
                              extra={'data': data})
                    raise SoloProviderNotReady("Not ready")
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
