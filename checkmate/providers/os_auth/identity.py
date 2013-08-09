"""
Celery tasks to authenticate against the Rackspace Cloud
"""
import logging
import httplib
import json

from celery.task import task
from checkmate.common import statsd
from checkmate.utils import match_celery_logging

LOG = logging.getLogger(__name__)


class NoTenatIdFound(Exception):
    pass


class AuthenticationFailure(Exception):
    pass


def parse_region(auth_dict):
    """
    Pull region/auth url information from conext.

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
              region == 'SYD']):
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

    return os_authenticate(auth_dict=context)[0]


@statsd.collect
def os_authenticate(auth_dict):
    """Authentication For Openstack API.

    Pulls the full Openstack Service Catalog Credentials are the Users API
    Username and Key/Password "osauth" has a Built in Rackspace Method for
    Authentication

    Set a DC Endpoint and Authentication URL for the Open Stack environment

    :param auth_dict:
    """

    _url, _rax = parse_region(auth_dict=auth_dict)

    # Setup our Authentication POST

    # username and setup are only used in APIKEY/PASSWORD Authentication
    username = auth_dict.get('username')
    setup = {'username': username}
    if auth_dict.get('token'):
        auth_json = {'auth': {'token': {'id': auth_dict.get('token')},
                              'tenantId': auth_dict.get('tenant')}}
    elif auth_dict.get('apikey'):
        prefix = 'RAX-KSKEY:apiKeyCredentials'
        setup['apiKey'] = auth_dict.get('apikey')
        auth_json = {'auth': {prefix: setup}}
    elif auth_dict.get('password'):
        prefix = 'passwordCredentials'
        setup['password'] = auth_dict.get('password')
        auth_json = {'auth': {prefix: setup}}
    else:
        raise AttributeError('No Password or APIKey/Password Specified')

    # remove the prefix for the Authentication URL if Found
    authurl = _url.strip('http?s://')
    url_data = authurl.split('/')
    aurl = url_data[0]
    LOG.debug('POST == DICT > JSON DUMP %s' % auth_json)
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
    except Exception, exc:
        raise AttributeError("Failure to perform Authentication %s" % exc)
    else:
        resp_read = resp.read()
        status_code = resp.status
        if status_code >= 300:
            raise AuthenticationFailure('Failed to authenticate %s'
                                        % status_code)
    finally:
        conn.close()

    try:
        jrp = json.loads(resp_read)
    except ValueError, exp:
        raise httplib.HTTPException('JSON Decode Failure. %s' % exp)
    else:
        jra = jrp.get('access')
        token = jra.get('token').get('id')

    # Tenant ID set as it was originally in the method, but its not used
    if 'tenant' in jra.get('token'):
        tenantid = jra.get('token').get('tenant').get('id')
    elif 'user' in jra:
        tenantid = jra.get('user').get('name')
    else:
        raise NoTenatIdFound('When attempting to grab the tenant/user ',
                             ' nothing was found.')
    LOG.debug('Auth token for user %s is %s (tenant %s)' % (username,
                                                            token,
                                                            tenantid))
    return token, tenantid, username, jrp
