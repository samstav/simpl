"""
Celery tasks to authenticate against the Rackspace Cloud
"""
import logging
import httplib
import json
import sys

from celery.task import task
from checkmate.utils import match_celery_logging

LOG = logging.getLogger(__name__)


class NoTenatIdFound(Exception):
    pass


def parse_region(context):
    """
    Pull region/auth url information from conext.
    :param context:
    """
    if context.get('region') is None:
        raise AttributeError('No Region Specified')
    else:
        region = context.get('region').upper()

    if any([region == 'LON']):
        url = context.get('auth_url', 'lon.identity.api.rackspacecloud.com')
        rax = True
    elif any([region == 'DFW',
              region == 'ORD',
              region == 'SYD']):
        url = context.get('auth_url', 'identity.api.rackspacecloud.com')
        rax = True
    else:
        if context.get('auth_url'):
            url = context.get('auth_url')
            rax = False
        else:
            raise AttributeError('FAIL\t: You have to specify an Auth URL')
    return url, rax


# Celeryd functions
@task
def get_token(context):
    """
    Authentication For Openstack API, Pulls the full Openstack Service
    Catalog Credentials are the Users API Username and Key/Password
    "osauth" has a Built in Rackspace Method for Authentication

    Set a DC Endpoint and Authentication URL for the Open Stack environment
    :param context:
    """
    _url, _rax = parse_region(context=context)

    # Setup our Authentication POST
    _username = context.get('username')
    setup = {'username': _username}
    if context.get('apikey'):
        prefix = 'RAX-KSKEY:apiKeyCredentials'
        setup['apiKey'] = context.get('apikey')
    elif context.get('password'):
        prefix = 'passwordCredentials'
        setup['password'] = context.get('password')
    else:
        raise AttributeError('No Password or APIKey Specified')

    # remove the prefix for the Authentication URL if Found
    authurl = _url.strip('http?s://')
    url_data = authurl.split('/')
    aurl = url_data[0]
    authjsonreq = json.dumps({'auth': {prefix: setup}})
    headers = {'Content-Type': 'application/json'}
    tokenurl = '/v2.0/tokens'

    # Setup the Authentication URL
    if ('https' in _url or _rax is True):
        conn = httplib.HTTPSConnection(aurl)
    else:
        conn = httplib.HTTPConnection(aurl)

    # Make the request for authentication
    conn.request('POST', tokenurl, authjsonreq, headers)
    try:
        if sys.version_info < (2, 7, 0):
            resp = conn.getresponse()
        else:
            resp = conn.getresponse(buffering=True)
    except Exception, exc:
        LOG.debug("Failure to perform Authentication %s" % exc)
    else:
        resp_read = resp.read()
    jrp = json.loads(resp_read)
    jra = jrp.get('access')
    token = jra.get('token').get('id')
    # Tenant ID set as it was originaly in the method, but its not used
    if 'tenant' in jra:
        tenantid = jra.get('token').get('tenant').get('id')
    elif 'user' in jra:
        tenantid = jra.get('user').get('name')
    else:
        raise NoTenatIdFound('When attempting to grab the tenant/user ',
                             ' nothing was found.')
    LOG.debug('Auth token for user %s is %s (tenant %s)' % (_username,
                                                            token,
                                                            tenantid))
    return token
