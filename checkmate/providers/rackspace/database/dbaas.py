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

"""Provider module for interfacing with Redis via Cloud Databases."""

import json
import logging

import requests
from voluptuous import (
    All,
    Any,
    Required,
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


###
# Datastore Stuffs
###


def get_datastore(region, t_id, token, datastore_id):
    """Return datastore details for the given datatstore_id."""
    url = _build_url(region, t_id, '/datastores/%s' % datastore_id)
    return _handle_response(requests.get(url, headers=_build_headers(token)))


def get_datastores(region, t_id, token):
    """List all available datastores/details for the given region and tenant

    Returns a list containing details for each datastore type (e.g. MySQL,
    Percona, MariaDB) and support details such as: versions supported,
    datastore id's, links to retrieve details, etc.
    """
    url = _build_url(region, t_id, '/datastores')
    return _handle_response(requests.get(url, headers=_build_headers(token)))


def get_datastore_version(region, t_id, token, datastore_id, version_id):
    """List datastore details for the given datastore_id/version_id."""
    urn = '/datastores/%s/versions/%s' % (datastore_id, version_id)
    url = _build_url(region, t_id, urn)
    return _handle_response(requests.get(url, headers=_build_headers(token)))


def get_datastore_versions(region, t_id, token, datastore_id):
    """List all available versions for the given datastore_id."""
    url = _build_url(region, t_id, '/datastores/%s/versions' % datastore_id)
    return _handle_response(requests.get(url, headers=_build_headers(token)))


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


def _handle_response(response):
    """Helper function to return response content as json or error info."""
    if response.ok:
        return response.json()
    # TODO(pablo): this should raise an exception
    return {'status_code': response.status_code, 'reason': response.reason}
