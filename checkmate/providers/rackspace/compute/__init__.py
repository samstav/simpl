# pylint: disable=E1103, C0302

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

"""Provider for OpenStack Compute API

- Supports Rackspace Open Cloud Compute Extensions and Auth
"""

import logging

from celery import task as ctask
from novaclient import exceptions as ncexc
import requests

from checkmate.common import statsd
from checkmate import deployments as cmdeps, utils
from checkmate import exceptions as cmexc
from checkmate.providers.base import RackspaceProviderTask
from checkmate.providers.rackspace.compute.provider import Provider
from checkmate.providers.rackspace.compute import tasks

from checkmate import rdp
from checkmate import ssh

LOG = logging.getLogger(__name__)


def _on_failure(exc, task_id, args, kwargs, einfo, action, method):
    """Handle task failure."""
    dep_id = args[0].get('deployment_id')
    key = args[0].get('resource_key')
    if dep_id and key:
        k = "instance:%s" % key
        ret = {
            k: {
                'status': 'ERROR',
                'status-message': (
                    'Unexpected error %s compute instance %s' % (action, key)
                ),
                'error-message': str(exc)
            }
        }
        cmdeps.resource_postback.delay(dep_id, ret)
    else:
        LOG.error("Missing deployment id and/or resource key in "
                  "%s error callback.", method)
#
# Celery Tasks
#


@ctask.task
@statsd.collect
def create_server(context, name, region, api=None, flavor="2",
                  files=None, image=None, tags=None):
    """Create a Rackspace Cloud server using novaclient.

    Note: Nova server creation requests are asynchronous. The IP address of the
    server is not available when thios call returns. A separate operation must
    poll for that data.

    :param context: the context information
    :type context: dict
    :param name: the name of the server
    :param api: existing, authenticated connection to API
    :param image: the image ID to use when building the server (which OS)
    :param flavor: the size of the server (a string ID)
    :param files: a list of files to inject
    :type files: dict
    :Example:

    {
      '/root/.ssh/authorized_keys': "base64 encoded content..."
    }
    :param tags: metadata tags to add
    :return: dict of created server
    :rtype: dict
    :Example:

    {
      id: "uuid...",
      password: "secret"
    }

    """
    return tasks.create_server(context, name, region, api=api,
                               flavor=flavor, files=files, image=image,
                               tags=tags)


@ctask.task
@statsd.collect
def sync_resource_task(context, resource, resource_key, api=None):
    """Syncs resource status with provider status."""
    utils.match_celery_logging(LOG)
    key = "instance:%s" % resource_key
    if context.get('simulation') is True:
        return {
            key: {
                'status': resource.get('status', 'DELETED')
            }
        }

    if api is None:
        api = Provider.connect(context, resource.get("region"))
    try:
        instance = resource.get("instance") or {}
        instance_id = instance.get("id")
        if not instance_id:
            raise cmexc.CheckmateDoesNotExist("Instance is blank or has no ID")
        LOG.debug("About to query for server %s", instance_id)
        server = api.servers.get(instance_id)

        try:
            if "RAX-CHECKMATE" not in server.metadata.keys():
                checkmate_tag = Provider.generate_resource_tag(
                    context['base_url'], context['tenant'],
                    context['deployment'], resource['index']
                )
                server.manager.set_meta(server, checkmate_tag)
        except Exception as exc:
            LOG.info("Could not set metadata tag "
                     "on checkmate managed compute resource")
            LOG.info(exc)

        return {
            key: {
                'status': server.status
            }
        }
    except (ncexc.NotFound, cmexc.CheckmateDoesNotExist):
        return {
            key: {
                'status': 'DELETED'
            }
        }
    except ncexc.BadRequest as exc:
        if exc.http_status == 400 and exc.message == 'n/a':
            # This is a token expiration failure. Nova probably tried to
            # re-auth and used our dummy data
            raise cmexc.CheckmateNoTokenError("Auth token expired")


@ctask.task(base=RackspaceProviderTask, default_retry_delay=30,
            max_retries=120, provider=Provider)
@statsd.collect
def delete_server_task(context, api=None):
    """Celery Task to delete a Nova compute instance."""
    utils.match_celery_logging(LOG)

    assert "deployment_id" in context or "deployment" in context, \
        "No deployment id in context"
    assert "resource_key" in context, "No resource key in context"
    assert "region" in context, "No region provided"
    assert 'resource' in context, "No resource definition provided"

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handles task failure."""
        action = "deleting"
        method = "delete_server_task"
        _on_failure(exc, task_id, args, kwargs, einfo, action, method)

    delete_server_task.on_failure = on_failure

    if api is None and context.get('simulation') is not True:
        api = Provider.connect(context, region=context.get("region"))

    server = None
    inst_id = context.get("instance_id")
    resource = context.get('resource')
    resource_key = context.get('resource_key')
    deployment_id = context.get("deployment_id", context.get("deployment"))

    if inst_id is None:
        msg = ("Instance ID is not available for Compute Instance, skipping "
               "delete_server_task for resource %s in deployment %s" %
               (resource_key, deployment_id))
        LOG.info(msg)
        results = {
            'status': 'DELETED',
            'status-message': msg
        }
        return results

    results = {}
    try:
        if context.get('simulation') is not True:
            server = api.servers.get(inst_id)
    except (ncexc.NotFound, ncexc.NoUniqueMatch):
        LOG.warn("Server %s already deleted", inst_id)
    except requests.ConnectionError:
        msg = ("Connection error talking to %s endpoint" %
               (api.client.management_url))
        LOG.error(msg, exc_info=True)
        raise cmexc.CheckmateException(message=msg,
                                       options=cmexc.CAN_RESUME)
    if (not server) or (server.status == 'DELETED'):
        results = {
            'status': 'DELETED',
            'status-message': ''
        }
        if 'hosts' in resource:
            hosts_results = {}
            for comp_key in resource.get('hosts', []):
                hosts_results.update({
                    'instance:%s' % comp_key: {
                        'status': 'DELETED',
                        'status-message': ''
                    }
                })
            cmdeps.resource_postback.delay(deployment_id, hosts_results)
    elif server.status in ['ACTIVE', 'ERROR', 'SHUTOFF']:
        results = {
            'status': 'DELETING',
            'status-message': 'Waiting on resource deletion'
        }
        if 'hosts' in resource:
            hosts_results = {}
            for comp_key in resource.get('hosts', []):
                hosts_results.update({
                    'instance:%s' % comp_key: {
                        'status': 'DELETING',
                        'status-message': 'Host %s is being deleted.' %
                                          resource_key
                    }
                })
            cmdeps.resource_postback.delay(deployment_id, hosts_results)
        try:
            server.delete()
        except requests.ConnectionError:
            msg = ("Connection error talking to %s endpoint" %
                   (api.client.management_url))
            LOG.error(msg, exc_info=True)
            raise cmexc.CheckmateException(message=msg,
                                           options=cmexc.CAN_RESUME)
    else:
        msg = ('Instance is in state %s. Waiting on ACTIVE resource.'
               % server.status)
        delete_server_task.partial({
            'status': 'DELETING',
            'status-message': msg
        })
        raise cmexc.CheckmateException(message=msg, options=cmexc.CAN_RESUME)
    return results


@ctask.task(base=RackspaceProviderTask, default_retry_delay=30,
            max_retries=120, provider=Provider)
@statsd.collect
def wait_on_delete_server(context, api=None):
    """Wait for a server resource to be deleted."""
    utils.match_celery_logging(LOG)
    assert "deployment_id" in context, "No deployment id in context"
    assert "resource_key" in context, "No resource key in context"
    assert "region" in context, "No region provided"
    assert 'resource' in context, "No resource definition provided"

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handles task failure."""
        action = "while waiting on"
        method = "wait_on_delete_server"
        _on_failure(exc, task_id, args, kwargs, einfo, action, method)

    wait_on_delete_server.on_failure = on_failure

    if api is None and context.get('simulation') is not True:
        api = Provider.connect(context, region=context.get("region"))

    resource = context.get('resource')
    server = None
    inst_id = context.get("instance_id")

    resource_key = context.get('resource_key')
    deployment_id = context.get('deployment_id')

    if inst_id is None:
        msg = ("Instance ID is not available for Compute Instance, "
               "skipping wait_on_delete_task for resource %s in deployment %s"
               % (resource_key, deployment_id))
        LOG.info(msg)
        results = {
            'status': 'DELETED',
            'status-message': msg
        }
        return results

    results = {}
    try:
        if context.get('simulation') is not True:
            server = api.servers.find(id=inst_id)
    except (ncexc.NotFound, ncexc.NoUniqueMatch):
        pass
    except requests.ConnectionError:
        msg = ("Connection error talking to %s endpoint" %
               (api.client.management_url))
        LOG.error(msg, exc_info=True)
        raise cmexc.CheckmateException(message=msg,
                                       options=cmexc.CAN_RESUME)
    if (not server) or (server.status == "DELETED"):
        results = {
            'status': 'DELETED',
            'status-message': ''
        }
        if 'hosts' in resource:
            hosted_resources = {}
            for hosted in resource.get('hosts', []):
                hosted_resources.update({
                    'instance:%s' % hosted: {
                        'status': 'DELETED',
                        'status-message': ''
                    }
                })
            cmdeps.resource_postback.delay(context.get("deployment_id"),
                                           hosted_resources)
    else:
        msg = ('Instance is in state %s. Waiting on DELETED resource.'
               % server.status)
        results = {
            'status': 'DELETING',
            'status-message': msg
        }
        wait_on_delete_server.partial(results)
        raise cmexc.CheckmateException(message=msg, options=cmexc.CAN_RESUME)
    return results


# max 60 minute wait
@ctask.task
@statsd.collect
def wait_on_build(context, server_id, region, ip_address_type='public',
                  api=None):
    """Checks build is complete.

    :param context: context data
    :param server_id: server id of the server to wait for
    :param region: region in which the server exists
    :param ip_address_type: the type of IP address to return as 'ip' in the
        response
    :param api: api object for getting server details
    :return: False when build not ready. Dict with ip addresses when done.
    """
    return tasks.wait_on_build(context, server_id, region,
                               ip_address_type=ip_address_type, api=api)


@ctask.task(default_retry_delay=1, max_retries=30)
def verify_ssh_connection(context, server_id, region, server_ip,
                          username='root', timeout=10, password=None,
                          identity_file=None, port=22, api_object=None,
                          private_key=None):
    """Verifies the ssh connection to a server
    :param context: context data
    :param server_id: server id
    :param region: region where the server exists
    :param server_ip: ip of the server
    :param username: username for ssh
    :param timeout: timeout for ssh
    :param password: password for ssh
    :param identity_file: identity file for ssh
    :param port: port fpr ssh
    :param api_object: api object for getting server details
    :param private_key: private key
    :return:
    """
    tasks.verify_ssh_connection(context, server_id, region, server_ip,
                                username=username, timeout=timeout,
                                password=password,
                                identity_file=identity_file, port=port,
                                api_object=api_object, private_key=private_key)
