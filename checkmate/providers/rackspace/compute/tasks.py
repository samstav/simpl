import logging

from celery.task import task
from checkmate.common import statsd
from checkmate.providers import RackspaceProviderTask
from checkmate.providers.rackspace.compute.manager import Manager
from checkmate.providers.rackspace.compute import Provider

LOG = logging.getLogger(__name__)


@task(base=RackspaceProviderTask, default_retry_delay=15,
      max_retries=40, provider=Provider)
@statsd.collect
def create_server(context, name, region, api=None, flavor="2",
                  files=None, image=None, tags=None):
    on_failure = Manager.get_on_failure("creating", "create_server")
    create_server.on_failure = on_failure
    data = Manager.create_server(context, name, region, api=api,
                                 flavor=flavor, files=files, image=image,
                                 tags=tags)
    create_server.update_state(state="PROGRESS",
                               meta={"server.id": data["id"]})
    return data

@task(base=RackspaceProviderTask, default_retry_delay=15,
      max_retries=40, provider=Provider)
@statsd.collect
def wait_on_build(context, server_id, region, ip_address_type='public',
                  api=None):
    data = Manager.wait_on_build(context, server_id, region,
                                 wait_on_build.partial,
                                 wait_on_build.update_state,
                                 ip_address_type=ip_address_type, api=api)
    return data
