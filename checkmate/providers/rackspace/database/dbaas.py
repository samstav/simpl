# Copyright (c) 2011-2014 Rackspace US, Inc.
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
import time

import requests
import voluptuous

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
_validate_instance_details = voluptuous.Schema(
    {
        'id': basestring,
        'name': basestring,
        'status': voluptuous.Any('BUILD', 'REBOOT', 'ACTIVE', 'FAILED',
                                 'BACKUP', 'BLOCKED', 'RESIZE',
                                 'RESTART_REQUIRED', 'SHUTDOWN'),
        'region': basestring,
        'flavor': voluptuous.All(
            int, voluptuous.Any(1, 2, 3, 4, 5, 6, 7, 8,
                                101, 102, 103, 104, 105, 106, 107, 108)
        ),
        'disk': voluptuous.Any(None, int),
        'interfaces': voluptuous.Any(
            {
                'redis': {
                    'host': basestring,
                    'password': basestring,
                    'port': int
                }
            }, {
                'mysql': {
                    'host': basestring,
                    'port': int
                }
            }
        ),
        voluptuous.Optional('replica_of'): basestring
    },
    required=True
)
_validate_db_config = voluptuous.Schema(
    {
        'configuration': {
            'created': basestring,
            'datastore_name': basestring,
            'datastore_version_id': basestring,
            'datastore_version_name': basestring,
            'description': voluptuous.Any(basestring, None),
            'id': basestring,
            'instance_count': int,
            'name': basestring,
            'updated': basestring,
            'values': dict
        }
    },
    required=True
)


def validate_instance_details(data):
    """Run data through instance validator."""
    return _validate_instance_details(data)


def validate_db_config(data):
    """Run data through database validator."""
    return _validate_db_config(data)


class CDBException(Exception):

    """Raised whenever an HTTP error occurs."""

    pass


###
# Configuration Stuffs
###


def create_configuration(context, db_type, db_version, values):
    """Create a configuration to be used by database instances.

    values is a dict containing valid keys as per `get_config_params`
    """
    url = _build_url(context.region, context.tenant, '/configurations')
    dstore_ids = get_dstore_ids(context, db_type, db_version)
    data = json.dumps({
        'configuration': {
            'datastore': {
                'type': dstore_ids.get('datastore_id'),
                'version': dstore_ids.get('version_id')
            },
            'name': 'checkmate:%s:%s:%s' % (context.region, db_type,
                                            db_version),
            'values': values
        }
    })
    return _handle_response(
        requests.post(url, headers=_build_headers(context.auth_token),
                      data=data)
    )


def delete_configuration(context, config_id):
    """Delete the configuration instance referenced by config_id."""
    url = _build_url(context.region, context.tenant,
                     '/configurations/%s' % config_id)
    return _handle_response(
        requests.delete(url, headers=_build_headers(context.auth_token)))


def get_configuration(context, config_id):
    """Return the database configuration document for config_id."""
    url = _build_url(context.region, context.tenant,
                     '/configurations/%s' % config_id)
    return _handle_response(
        requests.get(url, headers=_build_headers(context.auth_token)))


def get_configurations(context):
    """List all database configurations for the given region and tenant."""
    url = _build_url(context.region, context.tenant, '/configurations')
    return _handle_response(
        requests.get(url, headers=_build_headers(context.auth_token)))


def get_config_params(context, db_type, db_version):
    """Return the list of config params available for the given db/version.

    Refresh _config_params_cache if needed (may also trigger a
    _version_id_cache refresh)

    Return list of configuration parameters
    """
    key = _build_datastore_key(context.region, db_type, db_version)
    if _config_params_refresh_needed(context.region, db_type, db_version):
        _refresh_config_params_cache(context, db_type, db_version)
    return _config_params_cache.get(
        key, {}).get('configuration-parameters', {})


###
# Datastore Stuffs
###


def get_datastores(context):
    """List all available datastores/details for the given region and tenant.

    Returns a list containing details for each datastore type (e.g. MySQL,
    Percona, MariaDB) and support details such as: versions supported,
    datastore id's, links to retrieve details, etc.
    """
    url = _build_url(context.region, context.tenant, '/datastores')
    return _handle_response(
        requests.get(url, headers=_build_headers(context.auth_token)))


def get_dstore_ids(context, db_type, db_version):
    """Return the version ids dict for the given region/db_type/db_version."""
    key = _build_datastore_key(context.region, db_type, db_version)
    if _version_id_refresh_needed(key):
        _refresh_version_id_cache(context)

    return _version_id_cache.get(key, {})


def latest_datastore_ver(context, db_type):
    """Get the latest supported version of the given datastore type."""
    # TODO(pablo): get rid of hard-coding. Do a proper lookup!
    if db_type == 'redis':
        return '2.8'
    return '5.6'


###
# Flavor Stuffs
###


def get_flavor(context, flavor_id):
    """List database instance flavors available for the given region/tenant."""
    url = _build_url(context.region, context.tenant, '/flavors/%s' % flavor_id)
    return _handle_response(
        requests.get(url, headers=_build_headers(context.auth_token)))


def get_flavor_ref(context, flavor_id):
    """Return the reference link for the given flavor_id."""
    flavor_info = get_flavor(context, flavor_id)
    if 'links' in flavor_info.get('flavor', {}):
        for link in flavor_info['flavor']['links']:
            if link['rel'] == 'self':
                return link.get('href')
    return None


###
# Instance Stuffs
###


def create_instance(context, name, flavor, **kwargs):
    """POST to Cloud Databases, then format the response for Checkmate.

    :param context: must have attributes 'region', 'tenant', 'auth_token'.
                    'resource_key' is used in simulation mode.
    :param name: the instance name
    :param flavor: a valid flavor id (will be converted to a flavorRef)
    :param **kwargs: options:
        - config_id: the id of a saved configuration
        - databases: a list of dicts following the add_database format:
            [
                {
                    'character_set': 'utf8',  # Optional
                    'collate': 'utf8_general_ci',  # Optional
                    'name': 'somename'
                },
            ]
        - dstore_type: mysql | percona | mariadb | redis
        - dstore_ver: e.g. '5.6' for mysql or '10' for mariadb
        - replica_of: the database ID to be used to create a replica
        - size: the disk size in gigabytes (GB). Required for non-Redis types
        - simulate: if True, skip the API call and return a simulated instance
        - users: a list of dicts following the add_users format
            [
                {
                    'databases': [
                        {'name': 'somename'},
                    ],
                    'name': 'someuser',
                    'password': 'somepassword'
                },
            ]

    :return instance_details: a Checkmate-friendly 'instance' dict
    """
    url = _build_url(context.region, context.tenant, '/instances')
    inputs = {'name': name}
    if kwargs.get('size'):
        inputs['volume'] = {'size': int(kwargs['size'])}
    if kwargs.get('config_id'):
        inputs['configuration'] = kwargs['config_id']
    if kwargs.get('dstore_type') and kwargs.get('dstore_ver'):
        inputs['datastore'] = {
            'type': kwargs['dstore_type'],
            'version': str(kwargs['dstore_ver'])
        }
    if kwargs.get('databases'):
        inputs['databases'] = kwargs['databases']
    if kwargs.get('replica_of'):
        inputs['replica_of'] = kwargs['replica_of']
    if kwargs.get('users'):
        inputs['users'] = kwargs['users']

    if kwargs.get('simulate', False) is True:
        resource_key = context.get('resource_key')
        db_type = inputs.get('datastore', {}).get('type', 'mysql')
        instance = {
            'flavor': {'id': str(flavor)},
            'hostname': '%s%s.rax.net' % (db_type, resource_key),
            'id': '%s%s' % (db_type.upper(), resource_key),
            'name': name,
            'status': 'BUILD',
            'datastore': {
                'version': inputs.get('datastore', {}).get('version', '5.6'),
                'type': db_type
            }
        }
        if db_type == 'redis':
            instance['password'] = 'TopSecret'
        else:
            instance['volume'] = inputs.get('volume')
        return _build_create_response(context.region, instance, inputs)
    else:
        inputs['flavorRef'] = get_flavor_ref(context, flavor)
        response = requests.post(url,
                                 headers=_build_headers(context.auth_token),
                                 data=json.dumps({'instance': inputs}))

    if not response.ok:
        raise CDBException('%d: %s' % (response.status_code, response.reason))

    results = response.json()
    if 'instance' not in results:
        raise CDBException('The "instance" key is missing from the response.')

    return _build_create_response(context.region, results['instance'], inputs)


def delete_instance(context, instance_id):
    """Delete the database instance referenced by region/tenant/instance_id."""
    url = _build_url(context.region, context.tenant,
                     '/instances/%s' % instance_id)
    return _handle_response(
        requests.delete(url, headers=_build_headers(context.auth_token)))


def get_instance(context, instance_id):
    """Return database instance details for the given instance_id."""
    url = _build_url(context.region, context.tenant,
                     '/instances/%s' % instance_id)
    return _handle_response(
        requests.get(url, headers=_build_headers(context.auth_token)))


def get_instances(context):
    """List all database instances for the given region/tenant."""
    url = _build_url(context.region, context.tenant, '/instances')
    return _handle_response(
        requests.get(url, headers=_build_headers(context.auth_token)))


###
# Replica Functions
#
# NOTE: Creating a replica is achieved through the create_instance function
###


def detach_replica(context, replica_id, replica_of):
    """Detach replica_id from instance replica_of."""
    url = _build_url(context.region, context.tenant,
                     '/instances/%s' % replica_id)
    inputs = {'instance': {'replica_of': replica_of}}
    return _handle_response(
        requests.patch(url, headers=_build_headers(context.auth_token),
                       data=json.dumps(inputs))
    )


def get_replicas(context, master_id):
    """List all replicas for the given master_id."""
    url = _build_url(context.region, context.tenant,
                     '/instances/%s/replicas' % master_id)
    return _handle_response(
        requests.get(url, headers=_build_headers(context.auth_token))
    )


###
# Helper Functions
###


def _build_create_response(region, instance, inputs):
    """Build a Checkmate friendly instance dict from create's response."""
    response = {
        'id': instance.get('id'),
        'name': instance.get('name'),
        'status': instance.get('status'),
        'region': region,
        'flavor': int(instance.get('flavor', {}).get('id', -1)),
        'disk': instance.get('volume', {}).get('size'),
    }

    if instance.get('datastore', {}).get('type') == 'redis':
        interfaces = {
            'redis': {
                'port': 6379,
                'host': instance.get('hostname'),
                'password': instance.get('password')
            }
        }
    else:
        interfaces = {
            'mysql': {
                'host': instance.get('hostname'),
                'port': instance.get('port', 3306),
            }
        }
    response['interfaces'] = interfaces

    if 'databases' in inputs:
        response['databases'] = inputs['databases']
    if 'replica_of' in inputs:
        response['replica_of'] = inputs['replica_of']
    if 'users' in inputs:
        response['users'] = inputs['users']

    return response


def _build_datastore_key(region, db_type, db_version):
    """Ensure all datastore cache keys are consistent."""
    return '%s:%s:%s' % (region, db_type, db_version)


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


def _refresh_config_params_cache(context, db_type, db_version):
    """Lookup version_id, then pull a fresh list of configuration params."""
    ver_id = get_dstore_ids(context, db_type, db_version).get('version_id')
    key = _build_datastore_key(context.region, db_type, db_version)
    urn = '/datastores/versions/%s/parameters' % ver_id
    url = _build_url(context.region, context.tenant, urn)
    response = requests.get(url, headers=_build_headers(context.auth_token))

    result = {}
    if response.ok:
        result = response.json()
        for param in result['configuration-parameters']:
            param.pop('datastore_version_id')
        result['version_id'] = ver_id
        result['expires'] = time.time() + 60 * 60 * 24  # 24 hours
        _config_params_cache[key] = result
    else:  # refresh failed: if it's cached, remove it
        _config_params_cache.pop(key, None)


def _handle_response(response):
    """Helper function to return response content as json or error info."""
    if response.ok:
        try:
            return response.json()
        except (TypeError, ValueError):  # There is no content
            return u'%d, %s' % (response.status_code, response.reason)
    else:
        try:
            # Check for custom error message and return that in error message
            # if found. Otherwise falls back to raise_for_status()
            data = response.json()
            error = data.itervalues().next()
            message = error.get('message') or error.get('description')
            raise CDBException(
                '%d %s: %s' % (response.status_code, response.reason, message))
        except (KeyError, AttributeError, ValueError):
            response.raise_for_status()


def _refresh_version_id_cache(context):
    """Pull all version ID's from a fresh list of datastores."""
    datastores = get_datastores(context).get('datastores')
    _version_id_cache.clear()
    for datastore in datastores:
        for version in datastore['versions']:
            if 'name' in datastore and 'name' in version:
                key = _build_datastore_key(context.region, datastore['name'],
                                           version['name'])
                _version_id_cache[key] = {
                    'datastore_id': datastore.get('id'),
                    'version_id': version.get('id')
                }
    _version_id_cache['expires'] = time.time() + 60 * 60 * 48  # 48 hours


def _config_params_refresh_needed(region, db_type, db_version):
    """True if either region:db_type:db_version not found or cache expired."""
    key = _build_datastore_key(region, db_type, db_version)
    return (key not in _config_params_cache or
            _expired(_config_params_cache[key]['expires']))


def _version_id_refresh_needed(key):
    """True if either key not found or key expired."""
    return (key not in _version_id_cache or
            _expired(_version_id_cache['expires']))
