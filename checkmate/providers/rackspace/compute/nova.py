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

"""Module for interfacing with Cloud Servers."""

import json
import logging
import os

import requests
from voluptuous import Schema

from checkmate import exceptions

LOG = logging.getLogger(__name__)
SERVICE_NAME = 'cloudServersOpenStack'

# pylint: disable=C0103
_headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

_keypair_schema = Schema(
    {
        'name': basestring,
        'public_key': basestring,
        'private_key': basestring,
        'fingerprint': basestring,
        'user_id': basestring,
    },
    required=False
)
# pylint: enable=C0103


def validate_keypair(keypair):
    """Validate keypair schema."""
    return _keypair_schema(keypair)


def _get_token(context):
    """Return token from context."""
    return context['auth_token']


def _handle_response(response):
    """Helper function to return response content as json or error info."""
    if response.ok:
        return response.json()
    try:
        # Check for custom error message and return that in error message if
        # found. Otherwise falls back to raise_for_status()
        data = response.json()
        error = data.itervalues().next()
        message = error.get('message') or error.get('description')
        raise requests.HTTPError(message, response=response)
    except (KeyError, AttributeError, ValueError):
        response.raise_for_status()


def _build_headers(token):
    """Helper function to build a dict of HTTP headers for a request."""
    headers = _headers.copy()
    headers['X-Auth-Token'] = token
    return headers


def list_keypairs(context, region):
    """Return list of keypairs from region."""
    base_url = get_region_endpoint(context, region)
    if not base_url:
        raise exceptions.CheckmateException("No Rackspace Endpoint for Cloud "
                                            "Servers in %s" % region)

    url = os.path.join(base_url, 'os-keypairs')
    token = _get_token(context)

    response = requests.get(url, headers=_build_headers(token))
    return _handle_response(response)['keypairs']


def create_keypair(context, region, name):
    """Generate new keypair in region indexed by name."""
    base_url = get_region_endpoint(context, region)
    if not base_url:
        raise exceptions.CheckmateException("No Rackspace Endpoint for Cloud "
                                            "Servers in %s" % region)

    url = os.path.join(base_url, 'os-keypairs')
    token = _get_token(context)
    data = {'keypair': {'name': name}}
    data = json.dumps(data)

    response = requests.post(url, headers=_build_headers(token), data=data)
    return _handle_response(response)['keypair']


def upload_keypair(context, region, name, public_key):
    """Upload Public Key to region by name."""
    base_url = get_region_endpoint(context, region)
    if not base_url:
        raise exceptions.CheckmateException("No Rackspace Endpoint for Cloud "
                                            "Servers in %s" % region)

    url = os.path.join(base_url, 'os-keypairs')
    token = _get_token(context)
    data = {'keypair': {'name': name, 'public_key': public_key}}
    data = json.dumps(data)

    response = requests.post(url, headers=_build_headers(token), data=data)
    return _handle_response(response)['keypair']


def delete_keypair(context, region, name):
    """Delete keypair from region by name."""
    base_url = get_region_endpoint(context, region)
    if not base_url:
        raise exceptions.CheckmateException("No Rackspace Endpoint for Cloud "
                                            "Servers in %s" % region)

    url = os.path.join(base_url, 'os-keypairs', name)
    token = _get_token(context)

    response = requests.delete(url, headers=_build_headers(token))
    return u'%d, %s' % (response.status_code, response.reason)


def get_region_endpoint(context, region):
    """Extract compute region endpoint from catalog in context."""
    for service in context['catalog']:
        if (service['type'] == 'compute' and
                service['name'] == SERVICE_NAME):
            for endpoint in service['endpoints']:
                if endpoint['region'] == region:
                    return endpoint['publicURL']
