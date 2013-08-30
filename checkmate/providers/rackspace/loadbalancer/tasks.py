"""
Rackspace Cloud Loadbalancer provider tasks.
"""
from celery.task import task

from checkmate.common import statsd
from checkmate.providers.base import ProviderTask
from checkmate.providers.rackspace.loadbalancer import Manager
from checkmate.providers.rackspace.loadbalancer import Provider


@task(base=ProviderTask, default_retry_delay=10, max_retries=2,
      provider=Provider)
@statsd.collect
def enable_content_caching(context, lbid, api=None, callback=None):
    """Task to enable loadbalancer content caching."""
    return Manager.enable_content_caching(lbid, enable_content_caching.api,
                                          context.simulation)
