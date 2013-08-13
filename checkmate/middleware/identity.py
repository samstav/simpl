"""
Celery tasks to authenticate against OpenStack Keystone
"""
import logging
import httplib
import json

from celery.task import task
from checkmate.common import statsd

LOG = logging.getLogger(__name__)


class NoTenantIdFound(Exception):
    '''Tenant not foubd.'''
    pass


class AuthenticationFailure(Exception):
    '''Authentication Failed.'''
    pass


def parse_region(auth_dict):
    """
    Pull region/auth url information from context.

    :param auth_dict:
    """

    authurl = 'identity.api.rackspacecloud.com'

    if auth_dict.get('region') is None:
        if auth_dict.get('auth_url'):
            return auth_dict.get('auth_url'), False
        else:
            return authurl, True
    else:
        region = auth_dict.get('region').upper()

    if any([region == 'LON']):
        url = auth_dict.get('auth_url', 'lon.%s' % authurl)
        rax = True
    elif any([region == 'DFW',
              region == 'ORD',
              region == 'SYD',
              region == 'IAD']):
        url = auth_dict.get('auth_url', '%s' % authurl)
        rax = True
    else:
        url = auth_dict.get('auth_url')
        rax = False
    return url, rax


# Celeryd functions
@task
@statsd.collect
def get_token(context):
    """return token post authentication.

    :param context:
    """

    return authenticate(auth_dict=context)[0]


@statsd.collect
def authenticate(auth_dict):
    """Authentication For Openstack API.

    Pulls the full Openstack Service Catalog Credentials are the Users API
    Username and Key/Password "osauth" has a Built in Rackspace Method for
    Authentication

    Set a DC Endpoint and Authentication URL for the OpenStack environment

    :param auth_dict: required parameters are auth_url
    """

    _url, _rax = parse_region(auth_dict=auth_dict)

    # Setup our Authentication POST

    # username and setup are only used in APIKEY/PASSWORD Authentication
    username = auth_dict.get('username')
    setup = {'username': username}
    if 'token' in auth_dict:
        auth_json = {'auth': {'token': {'id': auth_dict['token']},
                              'tenantId': auth_dict.get('tenant')}}
    elif 'apikey' in auth_dict:
        prefix = 'RAX-KSKEY:apiKeyCredentials'
        setup['apiKey'] = auth_dict['apikey']
        auth_json = {'auth': {prefix: setup}}
    elif 'password' in auth_dict:
        prefix = 'passwordCredentials'
        setup['password'] = auth_dict['password']
        auth_json = {'auth': {prefix: setup}}
    else:
        raise AttributeError('No Password or APIKey/Password Specified')

    # remove the prefix for the Authentication URL if Found
    authurl = _url.strip('http?s://')
    url_data = authurl.split('/')
    aurl = url_data[0]
    LOG.debug('POST == DICT > JSON DUMP %s', auth_json)
    authjsonreq = json.dumps(auth_json)
    headers = {'Content-Type': 'application/json'}
    tokenurl = '/v2.0/tokens'

    try:
        # Setup the Authentication URL for HTTP(S)
        if any(['https' in _url, _rax is True]):
            conn = httplib.HTTPSConnection(aurl)
        else:
            conn = httplib.HTTPConnection(aurl)
        # Make the request for authentication
        conn.request('POST', tokenurl, authjsonreq, headers)
        resp = conn.getresponse()
    except Exception as exc:
        LOG.error('HTTP connection exception: %s', exc)
        raise AuthenticationFailure('Unable to communicate with %s' % authurl)
    else:
        resp_read = resp.read()
        status_code = resp.status
        if status_code >= 300:
            raise AuthenticationFailure('Failed to authenticate %s'
                                        % status_code)
    finally:
        conn.close()

    try:
        parsed_response = json.loads(resp_read)
    except ValueError, exp:
        raise httplib.HTTPException('JSON Decode Failure. %s' % exp)
    else:
        access = parsed_response.get('access')
        token = access.get('token').get('id')

    # Tenant ID set as it was originally in the method, but its not used
    if 'tenant' in access.get('token'):
        tenantid = access.get('token').get('tenant').get('id')
    elif 'user' in access:
        tenantid = access.get('user').get('name')
    else:
        raise NoTenantIdFound('When attempting to grab the tenant/user '
                              'nothing was found.')
    LOG.debug('Auth token for user %s is %s (tenant %s)', username, token,
              tenantid)
    return token, tenantid, username, parsed_response
