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


def get_config(region, t_id, token, instance_id):
    url = _build_url(region, t_id, '/instances/%s/configuration' % instance_id)
    params = {'accountId': t_id, 'instanceId': instance_id}
    response = requests.get(url, headers=_build_headers(token), params=params)
    return response.json()


def get_flavor(region, t_id, token, flavor_id):
    url = _build_url(region, t_id, '/flavors/%s' % flavor_id)
    response = requests.get(url, headers=_build_headers(token))
    return response.json()


def get_flavor_ref(region, t_id, token, flavor_id):
    flavor_info = get_flavor(region, t_id, token, flavor_id)
    if 'links' in flavor_info.get('flavor', {}):
        for link in flavor_info['flavor']['links']:
            if link['rel'] == 'self':
                return link.get('href')
    return None


def get_instance(region, t_id, token, instance_id):
    url = _build_url(region, t_id, '/instances/%s' % instance_id)
    response = requests.get(url, headers=_build_headers(token))

    if response.ok:
        return response.json()

    return {'status_code': response.status_code, 'reason': response.reason}


def create_instance(region, t_id, token, name, flavor):
    """Calls _create_instance then formats the response for Checkmate."""
    results = _create_instance(region, t_id, token, name, flavor)
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
                    'host': instance.get('hostname')
                }
            }
        }

    # TODO(pablo): this should probably raise an exception
    return results  # Error: let the information bubble up


def delete_instance(region, t_id, token, instance_id):
    url = _build_url(region, t_id, '/instances/%s' % instance_id)
    params = {'accountId': t_id, 'instanceId': instance_id}
    response = requests.delete(url, headers=_build_headers(token),
                               params=params)
    return '%d, %s' % (response.status_code, response.reason)


def _create_instance(region, t_id, token, name, flavor):
    """Returns the raw response from creating a new instance."""
    assert isinstance(region, unicode), 'Region must be unicode'
    assert region.upper() in REGIONS, 'Must be a valid region (e.g. ORD)'
    assert isinstance(t_id, unicode), 't_id must be unicode'
    assert isinstance(token, unicode), 'A valid token must be provided'
    assert isinstance(flavor, int), 'flavor must be an int from 101 - 108'
    assert flavor in range(101, 109), (
        'flavor must be an int from 101 - 108')

    url = _build_url(region, t_id, '/instances')
    data = DATA.copy()
    data['instance']['name'] = name
    data['instance']['flavorRef'] = get_flavor_ref(region, t_id, token, flavor)
    data = json.dumps(data)
    response = requests.post(url, headers=_build_headers(token), data=data)
    if response.ok:
        return response.json()

    return {'status_code': response.status_code, 'reason': response.reason}


def _build_url(region, t_id, uri):
    assert uri.startswith('/'), 'uri must include the leading slash "/"'
    return URL % (region.lower(), t_id) + uri


def _build_headers(token):
    headers = HEADERS.copy()
    headers['X-Auth-Token'] = token
    return headers
