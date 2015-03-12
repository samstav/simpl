# pylint: disable=E1103,R0913,R0912
# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Rackspace Compute provider tasks."""

import logging

from celery import task as ctask
from checkmate.common import statsd
from checkmate import exceptions as cmexc
from checkmate.providers import base
from checkmate.providers.rackspace.compute import manager
from checkmate.providers.rackspace.compute import provider
LOG = logging.getLogger(__name__)


@ctask.task(base=base.RackspaceProviderTask, default_retry_delay=15,
            max_retries=40, provider=provider.Provider)
@statsd.collect
def create_server(context, name, region=None, api=None, flavor="2",
                  files=None, image=None, tags=None, userdata=None,
                  config_drive=None, networks=None, boot_from_image=False,
                  disk=None, key_name=None):
    # pylint: disable=W0613
    """Create a Rackspace Cloud server using novaclient.

    Note: Nova server creation requests are asynchronous. The IP address of the
    server is not available when thios call returns. A separate operation must
    poll for that data.

    :param context: the context information
    :type context: dict
    :param name: the name of the server
    :param api: existing, authenticated connection to API
    :param image: the image ID to use when building the server (which OS)
    :param boot_from_image: if flavor should be booted from image
    :param flavor: the size of the server (a string ID)
    :param files: a list of files to inject
    :type files: dict
    :param tags: used for adding metadata to created server
    :param key_name: name of keypair to inject into server
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
    create_server.on_failure = _on_failure(
        action="creating",
        method="create_server",
        callback=create_server.partial
    )
    data = manager.Manager.create_server(context, name,
                                         create_server.update_state,
                                         api=create_server.api,
                                         flavor=flavor, files=files,
                                         image=image, tags=tags,
                                         userdata=userdata,
                                         config_drive=config_drive,
                                         networks=networks,
                                         boot_from_image=boot_from_image,
                                         disk=disk,
                                         key_name=key_name)
    return data


@ctask.task(base=base.RackspaceProviderTask, default_retry_delay=15,
            max_retries=160, provider=provider.Provider)
@statsd.collect
def wait_on_build(context, server_id, region=None, ip_address_type='public',
                  api=None, desired_state=None):
    # pylint: disable=W0613
    """Checks build is complete.

    :param context: context data
    :param server_id: server id of the server to wait for
    :param region: region in which the server exists
    :param ip_address_type: the type of IP address to return as 'ip' in the
        response
    :param api: api object for getting server details
    :return: False when build not ready. Dict with ip addresses when done.
    """

    return manager.Manager.wait_on_build(
        context, server_id, wait_on_build.partial, wait_on_build.update_state,
        ip_address_type=ip_address_type, api=wait_on_build.api,
        desired_state=desired_state)


@ctask.task(base=base.RackspaceProviderTask, default_retry_delay=15,
            max_retries=40, provider=provider.Provider)
@statsd.collect
def verify_ssh_connection(context, server_id, server_ip, region=None,
                          username='root', timeout=10, password=None,
                          identity_file=None, port=22, api=None,
                          private_key=None, proxy_address=None,
                          proxy_credentials=None):
    # pylint: disable=W0613
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

    data = manager.Manager.verify_ssh_connection(
        context, server_id, server_ip, username=username, timeout=timeout,
        password=password, identity_file=identity_file, port=port,
        api=verify_ssh_connection.api, private_key=private_key,
        proxy_address=proxy_address, proxy_credentials=proxy_credentials)

    is_up = data["status"]
    if not is_up:
        if (verify_ssh_connection.max_retries ==
                verify_ssh_connection.request.retries):
            exception = cmexc.CheckmateException(
                message="SSH verification task has failed",
                friendly_message="Could not verify that SSH connectivity "
                                 "is working",
                options=cmexc.CAN_RESET)

            verify_ssh_connection.partial({
                'status': 'ERROR',
                'status-message': 'SSH verification has failed'
            })
            raise exception
        verify_ssh_connection.partial({
            'status-message': data["status-message"]
        })
        raise cmexc.CheckmateException(options=cmexc.CAN_RESUME)


@ctask.task(base=base.RackspaceProviderTask, default_retry_delay=15,
            max_retries=40, provider=provider.Provider)
@statsd.collect
def attach(context, server_id, volume_id, device_name=None, region=None,
           api=None):
    """Attach disk to server."""
    return manager.Manager.attach_volume(context, region, server_id, volume_id,
                                         attach.api,
                                         device_name=device_name,
                                         callback=attach.partial)


@ctask.task(base=base.RackspaceProviderTask, default_retry_delay=30,
            max_retries=120, provider=provider.Provider)
@statsd.collect
def wait_on_delete_server(context, api=None):
    # pylint: disable=W0613
    """Wait for a server resource to be deleted."""
    wait_on_delete_server.on_failure = _on_failure(
        action="while waiting on",
        method="wait_on_delete_server",
        callback=wait_on_delete_server.partial
    )
    return manager.Manager.wait_on_delete_server(
        context, wait_on_delete_server.api, wait_on_delete_server.partial)


@ctask.task(base=base.RackspaceProviderTask, default_retry_delay=30,
            max_retries=120, provider=provider.Provider)
@statsd.collect
def delete_server_task(context, api=None):
    # pylint: disable=W0613
    """Celery Task to delete a Nova compute instance."""
    delete_server_task.on_failure = _on_failure(
        action="deleting",
        method="delete_server_task",
        callback=delete_server_task.partial
    )
    return manager.Manager.delete_server_task(
        context, delete_server_task.api, delete_server_task.partial)


def _on_failure(action="", method="", callback=lambda *_, **__: None):
    """Gets a on_failure method from the Manager."""
    return manager.Manager.get_on_failure(action, method, callback)
