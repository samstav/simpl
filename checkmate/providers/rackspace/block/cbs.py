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
# pylint: disable=C0103

"""Provider module for interfacing with Cloud Block Storage."""

import json
import logging
import os

import requests
from voluptuous import (
    Any,
    Required,
    Schema
)

from checkmate.common import schema
from checkmate import exceptions

LOG = logging.getLogger(__name__)

_headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}
_volume_schema = Schema(
    {
        'id': basestring,
        Required('size'): int,
        'display_description': Any(basestring, None),
        'display_name': Any(basestring, None),
        'snapshot_id': Any(basestring, None),
        'volume_type': Any('SATA', 'SSD'),
        'source_volid': Any(basestring, None),
        'availability_zone': 'nova',
        'metadata': dict,
        'imageRef': Any(basestring, None),
        'bootable': Any(basestring, None),
        'status': basestring,
        'region': basestring,
        'created_at': basestring,
        'attachments': list(),
        'interfaces': {
            'iscsi': {}
        }
    },
    required=False
)


def validate_volume(volume):
    """Validate volume schema."""
    return _volume_schema(volume)


def _build_headers(token):
    """Helper function to build a dict of HTTP headers for a request."""
    headers = _headers.copy()
    headers['X-Auth-Token'] = token
    return headers


def _handle_response(response):
    """Helper function to return response content as json or error info."""
    if response.ok:
        return response.json()
    response.raise_for_status()


def _get_token(context):
    """Return token from context."""
    return context['auth_token']


def get_regions(context):
    """Extract regions where block storage exists from token object."""
    regions = set()
    for service in context['catalog']:
        if (service['type'] == 'volume' and
                service['name'] == 'cloudBlockStorage'):
            for endpoint in service['endpoints']:
                regions.add(endpoint['region'])
    return list(regions)


def get_region_endpoint(context, region):
    """Extract block storage region endpoint from token object."""
    for service in context['catalog']:
        if (service['type'] == 'volume' and
                service['name'] == 'cloudBlockStorage'):
            for endpoint in service['endpoints']:
                if endpoint['region'] == region:
                    return endpoint['publicURL']


def get_volume(context, region, volume_id):
    """Return volume from region."""
    base_url = get_region_endpoint(context, region)
    if not base_url:
        raise exceptions.CheckmateException("No Rackspace Endpoint for Block "
                                            "Storage in %s" % region)

    url = os.path.join(base_url, 'volumes', volume_id)
    token = _get_token(context)
    response = requests.get(url, headers=_build_headers(token))
    return _handle_response(response)['volume']


def list_volumes(context, region):
    """Return tenant volume list from region."""
    base_url = get_region_endpoint(context, region)
    if not base_url:
        raise exceptions.CheckmateException("No Rackspace Endpoint for Block "
                                            "Storage in %s" % region)

    url = os.path.join(base_url, 'volumes')
    token = _get_token(context)
    response = requests.get(url, headers=_build_headers(token))
    return _handle_response(response)['volumes']


def get_volume_types(context, region):
    """Return tenant volume types from region."""
    base_url = get_region_endpoint(context, region)
    url = os.path.join(base_url, 'types')
    token = _get_token(context)
    response = requests.get(url, headers=_build_headers(token))
    return _handle_response(response)['volume_types']


def get_volume_type_details(context, region, type_id):
    """Return tenant volume type details (useless?!)."""
    base_url = get_region_endpoint(context, region)
    url = os.path.join(base_url, 'types', type_id)
    token = _get_token(context)
    response = requests.get(url, headers=_build_headers(token))
    return _handle_response(response)


def create_volume(context, region, size, **kwargs):
    """Calls _create_volume then formats the response for Checkmate."""
    base_url = get_region_endpoint(context, region)
    if not base_url:
        raise exceptions.CheckmateException("No Rackspace Endpoint for Block "
                                            "Storage in %s" % region)
    url = os.path.join(base_url, 'volumes')
    token = _get_token(context)
    instance = kwargs.copy()
    instance['size'] = size

    if not schema.check_schema(_volume_schema, instance):
        _volume_schema(instance)
    data = {'volume': instance}
    data = json.dumps(data)
    response = requests.post(url, headers=_build_headers(token), data=data)

    if response.ok:
        results = response.json()
        if 'volume' in results:
            instance = results['volume']
            return instance
        return results
    response.raise_for_status()


def delete_volume(context, region, volume_id):
    """Delete the specified block storage volume."""
    base_url = get_region_endpoint(context, region)
    url = os.path.join(base_url, 'volumes', volume_id)
    token = _get_token(context)
    response = requests.delete(url, headers=_build_headers(token))
    return u'%d, %s' % (response.status_code, response.reason)
