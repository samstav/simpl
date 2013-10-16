# pylint: disable=E1103,R0913,R0912
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

"""
Rackspace Compute provider tasks.
"""

import logging

from celery import task as ctask
from checkmate.common import statsd
from checkmate import exceptions as cmexc
from checkmate import providers as cprov
from checkmate.providers.rackspace.compute import manager
from checkmate.providers.rackspace.compute import provider
LOG = logging.getLogger(__name__)


@ctask.task(base=cprov.RackspaceProviderTask, default_retry_delay=15,
            max_retries=40, provider=provider.Provider)
@statsd.collect
def create_server(context, name, region=None, api=None, flavor="2",
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
    :param tags: used for adding metadata to created server
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
    create_server.on_failure = _on_failure(action="creating",
                                           method="create_server")
    data = manager.Manager.create_server(context, name, api=create_server.api,
                                         flavor=flavor, files=files,
                                         image=image, tags=tags)
    create_server.update_state(state="PROGRESS",
                               meta={"server.id": data["id"]})
    return data


@ctask.task(base=cprov.RackspaceProviderTask, default_retry_delay=15,
            max_retries=40, provider=provider.Provider)
@statsd.collect
def wait_on_build(context, server_id, region=None, ip_address_type='public',
                  api=None):
    return manager.Manager.wait_on_build(
        context, server_id, wait_on_build.partial, wait_on_build.update_state,
        ip_address_type=ip_address_type, api=wait_on_build.api)


@ctask.task(base=cprov.RackspaceProviderTask, default_retry_delay=15,
            max_retries=40, provider=provider.Provider)
@statsd.collect
def verify_ssh_connection(context, server_id, server_ip, region=None,
                          username='root', timeout=10, password=None,
                          identity_file=None, port=22, api=None,
                          private_key=None):
    data = manager.Manager.verify_ssh_connection(
        context, server_id, server_ip, username=username, timeout=timeout,
        password=password, identity_file=identity_file, port=port,
        api=verify_ssh_connection.api, private_key=private_key)
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
            else:
                verify_ssh_connection.partial({
                    'status-message': data["status-message"]
                })
                raise cmexc.CheckmateException(options=cmexc.CAN_RESUME)


@ctask.task(base=cprov.RackspaceProviderTask, default_retry_delay=30,
            max_retries=120, provider=provider.Provider)
@statsd.collect
def wait_on_delete_server(context, api=None):
    wait_on_delete_server.on_failure = \
        _on_failure(action="while waiting on", method="wait_on_delete_server")
    return manager.Manager.wait_on_delete_server(
        context, wait_on_delete_server.api, wait_on_delete_server.partial)


@ctask.task(base=cprov.RackspaceProviderTask, default_retry_delay=30,
            max_retries=120, provider=provider.Provider)
@statsd.collect
def delete_server_task(context, api=None):
    delete_server_task.on_failure = _on_failure(action="deleting",
                                                method="delete_server_task")
    return manager.Manager.delete_server_task(
        context, delete_server_task.api, delete_server_task.partial)


def _on_failure(action="", method=""):
    return manager.Manager.get_on_failure(action, method)
