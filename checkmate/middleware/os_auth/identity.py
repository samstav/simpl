"""
Celery tasks to authenticate against OpenStack Keystone
"""

import json
import logging
import traceback

from celery.task import task
from checkmate.common import statsd
from checkmate.middleware.os_auth import auth_utils
from webob.exc import HTTPUnauthorized


LOG = logging.getLogger(__name__)


# Celeryd functions
@task
@statsd.collect
def get_token(context):
    """return token post authentication.

    :param context:
    """
    token = authenticate(auth_dict=context)[0]
    LOG.debug('Current User Token %s', token)
    return token


@statsd.collect
def authenticate(auth_dict):
    """Authentication For Openstack API.

    Pulls the full Openstack Service Catalog Credentials are the Users API
    Username and Key/Password "osauth" has a Built in Rackspace Method for
    Authentication

    Set a DC Endpoint and Authentication URL for the OpenStack environment

    :param auth_dict: required parameters are auth_url
    """

    # Setup the request variables
    _url, _rax = auth_utils.parse_region(auth_dict=auth_dict)
    aurl = auth_utils.parse_url(url=_url)
    protocol = auth_utils.is_https(url=_url, rax=_rax)
    auth_json = auth_utils.parse_reqtype(auth_body=auth_dict)

    # remove the prefix for the Authentication URL if Found
    username = auth_dict.get('username')
    LOG.debug('POST == REQUEST DICT > JSON DUMP %s', auth_json)
    auth_json_req = json.dumps(auth_json)
    headers = {'Content-Type': 'application/json'}
    token_url = '/v2.0/tokens'

    # Send Request
    request = ('POST', token_url, auth_json_req, headers)
    resp_read = auth_utils.request_process(aurl=aurl,
                                           req=request,
                                           https=protocol)
    LOG.debug('POST Authentication Response %s', resp_read)
    try:
        parsed_response = json.loads(resp_read)
        if not username:
            try:
                username = parsed_response['access']['user']['name']
            except Exception:
                pass
    except ValueError as exp:
        LOG.error('Authentication Failure %s\n%s', exp,
                  traceback.format_exc())
        raise HTTPUnauthorized('JSON Decode Failure. ERROR: %s - RESP %s'
                               % (exp, resp_read))
    else:
        token, tenantid = auth_utils.parse_srvcatalog(srv_cata=parsed_response)
        LOG.debug('Auth token for user %s is %s [tenant %s]', username, token,
                  tenantid)
        return token, tenantid, username, parsed_response


def auth_token_validate(auth_dict):
    """Attempt to Validate a Token as an Admin.

    :param auth_dict: Dictionary of Authentication Variables.
    """

    # Setup the request variables
    _url, _rax = auth_utils.parse_region(auth_dict=auth_dict)
    aurl = auth_utils.parse_url(url=_url)
    protocol = auth_utils.is_https(url=_url, rax=_rax)

    # Get variables from the auth_dict
    token = auth_dict.get('token')
    tenant_id = auth_dict.get('tenant')
    service_token = auth_dict.get('service_token')

    path = '%s/%s' % (aurl, token)
    if tenant_id:
        path = "%s?belongsTo=%s" % (path, tenant_id)
        LOG.debug("Validating on tenant '%s'", tenant_id)
    LOG.debug('Validating token with %s', path)

    headers = {'X-Auth-Token': service_token,
               'Accept': 'application/json'}

    request = ('GET', path, None, headers)
    LOG.debug('GET == REQUEST DICT > %s', request)
    resp_read = auth_utils.request_process(aurl=aurl,
                                           req=request,
                                           https=protocol)
    try:
        LOG.debug('TOKEN Validation Data: %s', resp_read)
        return json.loads(resp_read)
    except ValueError as exp:
        LOG.error('ValueError Decoding JSON: %s ERROR: %s', resp_read, exp)
        raise HTTPUnauthorized('No Json was Returned, MSG: "%s" - ERROR: "%s"'
                               % (resp_read, exp))
