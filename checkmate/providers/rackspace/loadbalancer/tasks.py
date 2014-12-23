# pylint: disable=W0613,R0913
# Copyright (c) 2011-2013 Rackspace Hosting
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

"""Rackspace Cloud Loadbalancer provider tasks."""

import logging

from celery import task
import pyrax

from checkmate.common import statsd
from checkmate import exceptions
from checkmate.providers import base
from checkmate.providers.rackspace.loadbalancer.manager import Manager
from checkmate.providers.rackspace.loadbalancer import provider
from checkmate import utils

LOG = logging.getLogger(__name__)


@task.task(base=base.RackspaceProviderTask, default_retry_delay=10,
           max_retries=2, provider=provider.Provider)
@statsd.collect
def enable_content_caching(context, lb_id, api=None):
    """Task to enable loadbalancer content caching."""
    return Manager.enable_content_caching(lb_id, enable_content_caching.api,
                                          context.simulation)


@task.task(base=base.RackspaceProviderTask, provider=provider.Provider)
@statsd.collect
def create_loadbalancer(context, name, vip_type, protocol, region=None,
                        api=None, port=None, algorithm='ROUND_ROBIN',
                        tags=None, parent_lb=None):
    """Task to create a loadbalancer."""
    return Manager.create_loadbalancer(
        context, name, vip_type, protocol, create_loadbalancer.api,
        create_loadbalancer.partial, port=port, algorithm=algorithm,
        tags=tags, parent_lb=parent_lb, simulate=context.simulation)


@task.task(base=base.RackspaceProviderTask, provider=provider.Provider,
           default_retry_delay=30, max_retries=120, acks_late=True)
@statsd.collect
def wait_on_build(context, lb_id, region=None, api=None):
    """Task to wait for loadbalancer build completion."""
    return Manager.wait_on_build(lb_id, wait_on_build.api,
                                 wait_on_build.partial, context.simulation)


@task.task(base=base.RackspaceProviderTask, provider=provider.Provider)
@statsd.collect
def collect_record_data(context, record):
    """Task to collect dns record data."""
    return Manager.collect_record_data(record)


@task.task(base=base.RackspaceProviderTask, provider=provider.Provider)
@statsd.collect
def delete_lb_task(context, lb_id, region=None, api=None):
    """Task to delete a loadbalancer."""
    return Manager.delete_lb_task(lb_id, delete_lb_task.api,
                                  context.simulation)


@task.task(base=base.RackspaceProviderTask, provider=provider.Provider,
           default_retry_delay=2, max_retries=60)
@statsd.collect
def wait_on_lb_delete_task(context, lb_id, region=None, api=None):
    """Task to wait for loadbalancer delete."""
    return Manager.wait_on_lb_delete_task(lb_id, wait_on_lb_delete_task.api,
                                          context.simulation)


@task.task(base=base.RackspaceProviderTask, provider=provider.Provider,
           default_retry_delay=10, max_retries=10)
@statsd.collect
def add_node(context, lb_id, ipaddr, region=None, api=None):
    """Task to add node to loadbalancer."""
    return Manager.add_node(lb_id, ipaddr, add_node.api, context.simulation)


@task.task(base=base.RackspaceProviderTask, provider=provider.Provider,
           default_retry_delay=10, max_retries=10)
@statsd.collect
def delete_node(context, lb_id, ipaddr, region=None, api=None):
    """Task to delete a node from loadbalancer."""
    return Manager.delete_node(lb_id, ipaddr, delete_node.api,
                               context.simulation)


@task.task(base=base.RackspaceProviderTask, provider=provider.Provider,
           default_retry_delay=10, max_retries=10)
@statsd.collect
def set_monitor(context, lb_id, mon_type, region=None, path='/', delay=10,
                timeout=10, attempts=3, body='(.*)',
                status='^[234][0-9][0-9]$', api=None):
    """Task to set monitor for a loadbalancer."""
    return Manager.set_monitor(lb_id, mon_type, set_monitor.api,
                               path=path, delay=delay, timeout=timeout,
                               attempts=attempts, body=body, status=status,
                               simulate=context.simulation)


@task.task(base=base.RackspaceProviderTask, provider=provider.Provider,
           default_retry_delay=10, max_retries=10)
@statsd.collect
def update_node_status(context, relation, lb_id, ip_address, node_status,
                       resource_status, api=None):
    """Task to update loadbalancer node status."""
    return Manager.update_node_status(context, lb_id, ip_address,
                                      node_status, resource_status, relation,
                                      update_node_status.partial,
                                      update_node_status.api,
                                      context.simulation)


@task
@statsd.collect
def sync_resource_task(context, resource, resource_key, api=None):
    """Sync provider resource status with deployment."""
    utils.match_celery_logging(LOG)
    if context.get('simulation') is True:
        return {
            'resources': {
                resource_key: {
                    'status': resource.get('status', 'DELETED')
                }
            }
        }

    if api is None:
        api = provider.Provider.connect(context, resource.get("region"))

    instance_id = resource.get("instance", {}).get('id')

    try:
        if not instance_id:
            message = "No instance id supplied for resource %s" % resource_key
            raise exceptions.CheckmateException(message)
        clb = api.get(instance_id)

        status = {'status': clb.status}
    except pyrax.exceptions.ClientException as exc:
        if exc.code not in ['404', '422']:
            return
        status = {'status': 'DELETED'}
    except exceptions.CheckmateException:
        status = {'status': 'DELETED'}

    if status.get('status'):
        LOG.info("Marking load balancer instance %s as %s", instance_id,
                 status['status'])
    return {'resources': {resource_key: status}}
