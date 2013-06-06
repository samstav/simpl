"""
  Celery tasks to authenticate against the Rackspace Cloud
"""
import logging

from celery.task import task
import cloudlb
from keystoneclient.v2_0 import client

from checkmate.utils import match_celery_logging

LOG = logging.getLogger(__name__)


def _get_ddi(context, tenants):
    """Given a list of tenants, find the DDI tenant

    This is a hackish way to get the tenant. What's the right way?
    """
    for tenant in tenants:
        if 'Mosso' not in tenant.id:
            return tenant.id
    LOG.debug("ERROR: Could not find the expected DDI in tenant list")


# Celeryd functions
@task
def get_token(context):
    match_celery_logging(LOG)
    LOG.debug('Auth %s' % (context['username']))
    if 'apikey' in context:
        LOG.debug("Using cloudlb to handle APIKEY aurthentication")
        clb = cloudlb.CloudLoadBalancer(
            context['username'], context['apikey'], context['region']
        )
        clb.client.authenticate()
        LOG.debug('Auth token for user %s is %s' % (
            context['username'], clb.client.auth_token))
        return clb.client.auth_token
    elif 'password' in context:
        keystone = client.Client(
            username=context['username'],
            password=context['password'],
            tenant_name=context.get('tenant'),
            auth_url=context.get(
                'auth_url',
                "https://identity.api.rackspacecloud.com/v2.0"
            )
        )

    if 'tenant' in context:
        keystone.tenant_id = context['tenant']
    else:
        keystone.tenant_id = _get_ddi(context, keystone.tenants.list())
    LOG.debug(
        'Auth token for user %s is %s (tenant %s)' % (
            context['username'], keystone.auth_token, keystone.tenant_id
        )
    )
    return keystone.auth_token
