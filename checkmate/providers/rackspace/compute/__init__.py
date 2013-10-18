# pylint: disable=E1103, C0302, R0913

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

from checkmate.common import statsd
from checkmate import exceptions as cmexc
from checkmate.providers.rackspace.compute.provider import Provider
from checkmate.providers.rackspace.compute import tasks
from checkmate import utils

LOG = logging.getLogger(__name__)


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
    return tasks.create_server(context, name, region=region, api=api,
                               flavor=flavor, files=files, image=image,
                               tags=tags)


@ctask.task
@statsd.collect
def sync_resource_task(context, resource, resource_key, api=None):
    #pylint: disable=W0703
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


@ctask.task(default_retry_delay=30, max_retries=120)
@statsd.collect
def delete_server_task(context, api=None):
    """Celery Task to delete a Nova compute instance."""
    return tasks.delete_server_task(context, api=api)


@ctask.task(default_retry_delay=30, max_retries=120)
@statsd.collect
def wait_on_delete_server(context, api=None):
    """Wait for a server resource to be deleted."""
    return tasks.wait_on_delete_server(context, api=api)


# max 60 minute wait
@ctask.task(default_retry_delay=30, max_retries=120, acks_late=True)
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
    return tasks.wait_on_build(context, server_id, region=region,
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
    tasks.verify_ssh_connection(context, server_id, server_ip, region=region,
                                username=username, timeout=timeout,
                                password=password,
                                identity_file=identity_file, port=port,
                                api=api_object, private_key=private_key)
