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

"""Utilities For Authenticating against All Openstack / Rax Clouds."""

import httplib
import logging
import traceback
import urlparse

from checkmate.middleware.os_auth import exceptions
from webob.exc import HTTPUnauthorized


LOG = logging.getLogger(__name__)


def parse_reqtype(auth_body):
    """Setup our Authentication POST.

    username and setup are only used in APIKEY/PASSWORD Authentication
    :param auth_body:
    """
    setup = {'username': auth_body.get('username')}
    if auth_body.get('token') is not None:
        auth_body = {'auth': {'token': {'id': auth_body.get('token')},
                              'tenantName': auth_body.get('tenant')}}
    elif auth_body.get('apikey') is not None:
        prefix = 'RAX-KSKEY:apiKeyCredentials'
        setup['apiKey'] = auth_body.get('apikey')
        auth_body = {'auth': {prefix: setup}}
    elif auth_body.get('password') is not None:
        prefix = 'passwordCredentials'
        setup['password'] = auth_body.get('password')
        auth_body = {'auth': {prefix: setup}}
    else:
        LOG.error(traceback.format_exc())
        raise AttributeError('No Password or APIKey/Password Specified')
    LOG.debug('AUTH Request Type > %s', auth_body)
    return auth_body


def parse_auth_response(auth_response):
    """Parse the auth reponse and return the tenant, token, and username.

    :param auth_response: the full object returned from an auth call
    :returns: tuple of token, tenant identifier, and username
    """
    access = auth_response.get('access')
    token = access.get('token').get('id')

    if 'tenant' in access.get('token'):
        # Scoped token (has tenant)
        tenantid = access.get('token').get('tenant').get('name')
        username = access.get('user').get('name')
    elif 'user' in access:
        # Unscoped token (no tenant)
        tenantid = None
        username = access.get('user').get('name')
    else:
        LOG.error('No Token Found to Parse Here is the DATA: %s\n%s',
                  auth_response, traceback.format_exc())
        raise exceptions.NoTenantIdFound('When attempting to grab the '
                                         'tenant or user nothing was found.')
    return token, tenantid, username


def parse_url(url):
    """Return a clean URL. Remove the prefix for the Auth URL if Found.

    :param url:
    :return aurl:
    """
    if url.startswith(('http://', 'https://')):
        _authurl = urlparse.urlparse(url)
        return _authurl.netloc
    else:
        return url.split('/')[0]


def is_https(url, rax):
    """Check URL to determine the Connection type.

    :param url:
    :param rax:
    :return True|False:
    """
    if any(['https' in url, rax is True]):
        return True
    else:
        return False


def parse_region(auth_dict):
    """Pull region/auth url information from context.

    :param auth_dict:
    """
    base_auth_url = 'identity.api.rackspacecloud.com'

    if auth_dict.get('region') is None:
        if auth_dict.get('auth_url'):
            if 'rackspace' in auth_dict.get('auth_url'):
                return auth_dict.get('auth_url'), True
            else:
                return auth_dict.get('auth_url'), False
        else:
            return base_auth_url, True
    else:
        region = auth_dict.get('region').upper()

    if any([region == 'LON']):
        url = auth_dict.get('auth_url', 'lon.%s' % base_auth_url)
        rax = True
    elif any([region == 'DFW',
              region == 'ORD',
              region == 'SYD',
              region == 'IAD']):
        url = auth_dict.get('auth_url', '%s' % base_auth_url)
        rax = True
    else:
        url = auth_dict.get('auth_url')
        rax = False
    return url, rax


def request_process(aurl, req, https=True):
    """Perform HTTP(s) request based on Provided Params.

    :param aurl:
    :param req:
    :param https:
    :return:
    """
    LOG.debug('REQUEST DATA %s %s %s', aurl, req, https)
    try:
        # Setup the Authentication URL for HTTP(S)
        if https:
            conn = httplib.HTTPSConnection(aurl)
        else:
            conn = httplib.HTTPConnection(aurl)
    except httplib.InvalidURL as exc:
        raise HTTPUnauthorized('Failed to open connection %s' % exc)

    try:
        # Make the request for authentication
        _method, _url, _body, _headers = req
        conn.request(method=_method, url=_url, body=_body, headers=_headers)
        resp = conn.getresponse()
    except Exception as exc:
        LOG.error('Not able to perform Request ERROR: %s', exc)
        raise AttributeError("Failure to perform Authentication %s ERROR:\n%s"
                             % (exc, traceback.format_exc()))
    else:
        resp_read = resp.read()
        status_code = resp.status
        if status_code >= 300:
            LOG.error('HTTP connection exception: '
                      'Response %s - Response Code %s\n%s',
                      resp_read, status_code, traceback.format_exc())
            raise HTTPUnauthorized('Failed to authenticate %s' % status_code)

        LOG.debug('Connection successful MSG: %s - STATUS: %s', resp.reason,
                  resp.status)
        return resp_read
    finally:
        conn.close()
