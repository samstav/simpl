"""
Utilities For Authenticating against All Openstack / Rax Clouds.
"""

import httplib
import logging
import traceback

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
                              'tenantId': auth_body.get('tenant')}}
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


def parse_srvcatalog(srv_cata):
    """Parse the service catalog and return the tenantID and token.

    :param srv_cata:
    """

    access = srv_cata.get('access')
    token = access.get('token').get('id')

    # Tenant ID set as it was originally in the method, but its not used
    if 'tenant' in access.get('token'):
        tenantid = access.get('token').get('tenant').get('id')
    elif 'user' in access:
        tenantid = access.get('user').get('name')
    else:
        LOG.error('No Token Found to Parse Here is the DATA: %s\n%s',
                  srv_cata, traceback.format_exc())
        raise exceptions.NoTenantIdFound('When attempting to grab the '
                                         'tenant/user nothing was found.')
    return token, tenantid


def parse_url(url):
    """Return a clean URL. Remove the prefix for the Auth URL if Found.

    :param url:
    :return aurl:
    """

    authurl = url.strip('http?s://')
    url_data = authurl.split('/')
    return url_data[0]


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
            if 'racksapce' in auth_dict.get('auth_url'):
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
