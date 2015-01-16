# Copyright (c) 2011-2014 Rackspace Hosting
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

# encoding: utf-8
# pylint: disable=C0103

"""Provider module for interfacing with Redis via Cloud Databases."""

import json
import logging
import time

import requests
from voluptuous import (
    All,
    Any,
    Schema
)
DATA = {
    'instance': {
        'datastore': {'version': '2.8', 'type': 'redis'}
    }
}
HEADERS = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}
LOG = logging.getLogger(__name__)
# TODO(pablo): URL and REGIONS should be populated from a catalog call
REGIONS = ['DFW', 'HKG', 'IAD', 'LON', 'ORD', 'SYD']
URL = 'https://%s.databases.api.rackspacecloud.com/v1.0/%s'  # region, t_id

_config_params_cache = {}
_version_id_cache = {'expires': None}
# TODO(pablo): statuses should become Checkmate's (not Cloud Databases')
validate_instance = Schema(
    {
        'id': basestring,
        'name': basestring,
        'status': Any('BUILD', 'REBOOT', 'ACTIVE', 'FAILED', 'BACKUP',
                      'BLOCKED', 'RESIZE', 'RESTART_REQUIRED', 'SHUTDOWN'),
        'region': basestring,
        'flavor': All(int, Any(1, 2, 3, 4, 5, 6, 7, 8,
                               101, 102, 103, 104, 105, 106, 107, 108)),
        'disk': None,
        'interfaces': {
            'redis': {
                'host': basestring,
                'password': basestring,
            }
        }
    },
    required=True
)
validate_db_config = Schema(
    {
        'configuration': {
            'created': basestring,
            'datastore_name': basestring,
            'datastore_version_id': basestring,
            'datastore_version_name': basestring,
            'description': basestring,
            'id': basestring,
            'instance_count': int,
            'name': basestring,
            'updated': basestring,
            'values': dict
        }
    },
    required=True
)


###
# Configuration Stuffs
###


def create_configuration(region, t_id, token, details):
    """Create a configuration to be used by database instances

    `details` must be a dict containing the following:
    {
        'datastore': {
            'type': '<one of mariadb, mysql, percona>',
            'version': '<valid version for datastore type>'
        },
        'description': '<optional configuration description>',
        'name': '<configuration name>',
        'values': {
            'some_valid_key': 'some_valid_value',
            'another_valid_key': 'another_valid_value'
        }
    }
    """
    url = _build_url(region, t_id, '/configurations')
    data = json.dumps({'configuration': details})
    response = requests.post(url, headers=_build_headers(token), data=data)

    if response.ok:
        return response.json()

    # TODO(pablo): this should raise an exception
    return {'status_code': response.status_code, 'reason': response.reason}


def delete_configuration(region, t_id, token, config_id):
    """Delete the configuration instance referenced by config_id."""
    url = _build_url(region, t_id, '/configurations/%s' % config_id)
    response = requests.delete(url, headers=_build_headers(token))
    return u'%d, %s' % (response.status_code, response.reason)


def get_configuration(region, t_id, token, config_id):
    """Return the database configuration document for config_id."""
    url = _build_url(region, t_id, '/configurations/%s' % config_id)
    return _handle_response(requests.get(url, headers=_build_headers(token)))


def get_configurations(region, t_id, token):
    """List all database configurations for the given region and tenant."""
    url = _build_url(region, t_id, '/configurations')
    return _handle_response(requests.get(url, headers=_build_headers(token)))


def get_config_params(region, t_id, token, db_name, db_version):
    """Return the list of config params available for the given db/version

    Refresh _config_params_cache if needed (may also trigger a
    _version_id_cache refresh)

    Return list of configuration parameters
    """
    key = _build_datastore_key(region, db_name, db_version)
    if _config_params_refresh_needed(region, db_name, db_version):
        _refresh_config_params_cache(region, t_id, token, db_name, db_version)
    return _config_params_cache.get(key)


###
# Datastore Stuffs
###


def get_datastores(region, t_id, token):
    """List all available datastores/details for the given region and tenant

    Returns a list containing details for each datastore type (e.g. MySQL,
    Percona, MariaDB) and support details such as: versions supported,
    datastore id's, links to retrieve details, etc.
    """
    url = _build_url(region, t_id, '/datastores')
    return _handle_response(requests.get(url, headers=_build_headers(token)))


def get_datastore_version_id(region, t_id, token, db_name, db_version):
    """Return the version id for the given database name/version."""
    key = _build_datastore_key(region, db_name, db_version)
    if _version_id_refresh_needed(key):
        _refresh_version_id_cache(region, t_id, token)

    return _version_id_cache.get(key)


###
# Flavor Stuffs
###


def get_flavor(region, t_id, token, flavor_id):
    """List database instance flavors available for the given region/tenant."""
    url = _build_url(region, t_id, '/flavors/%s' % flavor_id)
    response = requests.get(url, headers=_build_headers(token))
    return response.json()


def get_flavor_ref(region, t_id, token, flavor_id):
    """Return the reference link for the given flavor_id."""
    flavor_info = get_flavor(region, t_id, token, flavor_id)
    if 'links' in flavor_info.get('flavor', {}):
        for link in flavor_info['flavor']['links']:
            if link['rel'] == 'self':
                return link.get('href')
    return None


###
# Instance Stuffs
###


def create_instance(region, t_id, token, name, flavor):
    """Calls _create_instance then formats the response for Checkmate."""
    url = _build_url(region, t_id, '/instances')
    data = DATA.copy()
    data['instance']['name'] = name
    data['instance']['flavorRef'] = get_flavor_ref(region, t_id, token, flavor)
    data = json.dumps(data)
    response = requests.post(url, headers=_build_headers(token), data=data)

    if response.ok:
        results = response.json()
        if 'instance' in results:
            instance = results['instance']
            return {
                'id': instance.get('id'),
                'name': instance.get('name'),
                'status': 'BUILD',
                'region': region,
                'flavor': flavor,
                'disk': None,
                'interfaces': {
                    'redis': {
                        'host': instance.get('hostname'),
                        'password': instance.get('password'),
                    }
                }
            }
        return results
    else:
        # TODO(pablo): this should raise an exception
        return {'status_code': response.status_code, 'reason': response.reason}


def delete_instance(region, t_id, token, instance_id):
    """Delete the database instance referenced by region/tenant/instance_id."""
    url = _build_url(region, t_id, '/instances/%s' % instance_id)
    response = requests.delete(url, headers=_build_headers(token))
    return u'%d, %s' % (response.status_code, response.reason)


def get_instance(region, t_id, token, instance_id):
    """Return database instance details for the given instance_id."""
    url = _build_url(region, t_id, '/instances/%s' % instance_id)
    return _handle_response(requests.get(url, headers=_build_headers(token)))


def get_instances(region, t_id, token):
    """List all database instances for the given region/tenant."""
    url = _build_url(region, t_id, '/instances')
    return _handle_response(requests.get(url, headers=_build_headers(token)))


###
# Helper Functions
###


def _build_datastore_key(region, db_name, db_version):
    """Ensure all datastore cache keys are consistent."""
    return '%s:%s:%s' % (region, db_name, db_version)


def _build_headers(token):
    """Helper function to build a dict of HTTP headers for a request."""
    headers = HEADERS.copy()
    headers['X-Auth-Token'] = token
    return headers


def _build_url(region, t_id, uri):
    """Helper function to build the full URL for an HTTP request."""
    if not uri.startswith('/'):
        uri = '/' + uri
    return URL % (region.lower(), t_id) + uri


def _expired(expiry):
    """True if current time exceeds expiry time."""
    return expiry < time.time()


def _refresh_config_params_cache(region, t_id, token, db_name, db_version):
    """Lookup version_id, then pull a fresh list of configuration params."""
    version_id = get_datastore_version_id(region, t_id, token, db_name,
                                          db_version)
    key = _build_datastore_key(region, db_name, db_version)
    urn = '/datastores/versions/%s/parameters' % version_id
    url = _build_url(region, t_id, urn)
    response = requests.get(url, headers=_build_headers(token))

    result = {}
    if response.ok:
        result = response.json()
        for param in result['configuration-parameters']:
            param.pop('datastore_version_id')
        result['version_id'] = version_id
        result['expires'] = time.time() + 60 * 60 * 24  # 24 hours
        _config_params_cache[key] = result
    else:  # refresh failed: if it's cached, remove it
        _config_params_cache.pop(key, None)


def _handle_response(response):
    """Helper function to return response content as json or error info."""
    if response.ok:
        return response.json()
    # TODO(pablo): this should raise an exception
    return {'status_code': response.status_code, 'reason': response.reason}


def _refresh_version_id_cache(region, t_id, token):
    """Pull all version ID's from a fresh list of datastores."""
    datastores = get_datastores(region, t_id, token).get('datastores')
    _version_id_cache.clear()
    for datastore in datastores:
        for version in datastore['versions']:
            if 'name' in datastore and 'name' in version:
                key = _build_datastore_key(region, datastore['name'],
                                           version['name'])
                _version_id_cache[key] = version['id']
    _version_id_cache['expires'] = time.time() + 60 * 60 * 48  # 48 hours


def _config_params_refresh_needed(region, db_name, db_version):
    """True if either region:db_name:db_version not found or cache expired."""
    key = _build_datastore_key(region, db_name, db_version)
    return (key not in _config_params_cache or
            _expired(_config_params_cache[key]['expires']))


def _version_id_refresh_needed(key):
    """True if either key not found or key expired."""
    return (key not in _version_id_cache or
            _expired(_version_id_cache['expires']))
