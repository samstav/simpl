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
    if context.get('simulation') is True:
        result = {
            "keypair": {
                "public_key": (
                    "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDWaWqWXQRFwfd06/UwR"
                    "VDEmSNbjTfkmoBMF9i4UqHcmtUK33cy9zt5PF8AXJa1qQqPJ94Ydsp+qQ"
                    "FXeViZiMGKxYUAESDpm4ONG1nMbKfuVhjv98W7JK/09SR18uZtivCnHyy"
                    "m6KR51gEJfvd0Lj3svG42esB9frh44jbqyt1Mr8kJnXTsZb6qFA3Qf5nt"
                    "UqwiDJMlA4lISsNFLgR20eRtJTEhuvmENglbDAkiGpH4UYpNegbLzMaBO"
                    "b6Sa86uf2Zs/1MngdWQ9UMpeXz7wEB5mTODq0x+8igaUw7A6E5LXizU5R"
                    "GiomitBmihOQOywcFgMv+/dooKWZmqDWfgQnfV Generated-by-Nova"
                ),
                "private_key": (
                    "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA1mlqll0E"
                    "RcH3dOv1MEVQxJkjW4035JqATBfYuFKh3JrVCt93\nMvc7eTxfAFyWtak"
                    "KjyfeGHbKfqkBV3lYmYjBisWFABEg6ZuDjRtZzGyn7lYY7/fF\nuySv9P"
                    "UkdfLmbYrwpx8spuikedYBCX73dC497LxuNnrAfX64eOI26srdTK/JCZ1"
                    "0\n7GW+qhQN0H+Z7VKsIgyTJQOJSErDRS4EdtHkbSUxIbr5hDYJWwwJIh"
                    "qR+FGKTXoG\ny8zGgTm+kmvOrn9mbP9TJ4HVkPVDKXl8+8BAeZkzg6tMf"
                    "vIoGlMOwOhOS14s1OUR\noqJorQZooTkDssHBYDL/v3aKClmZqg1n4EJ3"
                    "1QIDAQABAoIBAQDKRisC7X+xW5rb\nGBt4zXuz7RC5NxGqvcMZhkmzImm"
                    "HGB6yIj1uvGTELBsn2TFo8a9/fEn/ZFoGgeQ9\nJMJcHfMQuuSNOpuFJ2"
                    "xEu6/Mthj7NQhTorlMowDIpFggWeXfI/uCflt+nu1D74uM\n7NYAKfvLk"
                    "byb8tQT0G+xwx+yA24g/97FpIj+L8fEX4+BCFt5bEc5kAb8LOmpAYhT\n"
                    "CWh/rGeg5+jXJHlUq2TBB7WigJ39XOYdZ7wIy4H2DuXcakL+yoeKnBRla"
                    "xjJ3vFo\nUMlV8LXUUzt2g6eXIR2O5EnCRcombr9qT2s1z3Hm1/GNjFtS"
                    "jGzi7sRE11xglWkH\nQLEVA2llAoGBAPRO3LBHN/FHPXMECwtjYxWVZIV"
                    "Go0rXQPUYjItJ5/kZ2Nmf3t6f\npJFBkfBHz07i0Wq9fAG9Wyo8+/Uc7o"
                    "iryUda6KaEwM/GuNnpcXKYxFE2ZR0aEHES\nGPfxRIDgNJ0RUe1fr0MP5"
                    "jRzfeWbpMMsYTNsTtY+5xeAQ/2N2BYe9MQzAoGBAOCs\nR8cQggruXcyp"
                    "SSYgZtN0N7nhUxCq73DeNptTn94lBVLUBBfGPmUSX7kSYZ6CGaiL\nUXN"
                    "jb3M110qNhmKdEO5rDxSbomCVuvZ9E0RjnQEd17uPktcsd7dEhaFwj2cG"
                    "yr2E\niyAsxlEGhIoSOH9Ivt8A0MIs7Ro4jqHojS5jLovXAoGACeS/ryv"
                    "TKiQ2atf5Eob9\n1jvsjDEmH7vD16kc1+8wQ7g2Penpfp58bZ14KYDe9l"
                    "TdIjN2OCPQ807w7SY0yrga\nOJeH4GZz4HYtujVn8LobCSboxVru24VeG"
                    "Xxdx9JMjyfKZ5B+anrUWb9rk8bPz0+W\nyBxUvPxjI2KAXl5GJ+8s/l0C"
                    "gYAlbAy4l4NRlsqA4GGSvCrkZaMyjtlrGU2wmxK1\nZIRoV/o/BZl47Eh"
                    "QRXM0PF+OK1ViwXHbqmBR7FHj1RbhLhA35hUo9ZNiSw5NKCAh\ncAYivX"
                    "nFf/CRbpKyL/OiJEF+g58ZWg5iWZLexBsndEl8yf0g393lud30VB9N0JJ"
                    "T\ne6mxGQKBgQDXkW98luR/RBmNhFWKdU3ufuWZdJiADFUXMnICsItNkI"
                    "b01XnzPfzd\nk4j33H7qpBGBQPtPW50/fSphcmUmmqpPvAFoG94xbb3os"
                    "sm4wF1cuaovduYU49EB\nTsX8CbqySO36GG2q1CiRrRStOjZJm2SKNxYQ"
                    "xZN8S836Q3j7hUXJTQ==\n-----END RSA PRIVATE KEY-----\n"),
                "user_id": "f75b5a4bbd1f4821944ff0ae2468fa32",
                "name": name,
                "fingerprint":
                "53:30:be:dd:a4:00:11:1f:94:e8:f3:d8:62:68:9b:76",
            }
        }
    else:
        response = requests.post(url, headers=_build_headers(token), data=data)
        result = _handle_response(response)['keypair']
    keypair = result['keypair']
    keypair['region'] = region
    return keypair


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

    if context.get('simulation') is True:
        result = {
            "keypair": {
                "public_key": public_key,
                "name": name,
                "fingerprint":
                "53:30:be:dd:a4:00:11:1f:94:e8:f3:d8:62:68:9b:76",
            }
        }
    else:
        response = requests.post(url, headers=_build_headers(token), data=data)
        result = _handle_response(response)['keypair']
    keypair = result['keypair']
    keypair['region'] = region
    return keypair


def delete_keypair(context, region, name):
    """Delete keypair from region by name."""
    base_url = get_region_endpoint(context, region)
    if not base_url:
        raise exceptions.CheckmateException("No Rackspace Endpoint for Cloud "
                                            "Servers in %s" % region)

    url = os.path.join(base_url, 'os-keypairs', name)
    token = _get_token(context)

    if context.get('simulation') is True:
        return u'200, OK'
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
