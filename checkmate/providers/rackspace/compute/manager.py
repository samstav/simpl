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

"""Rackspace Compute provider manager."""

import json
import logging

from novaclient import exceptions as ncexc
import requests

from checkmate import exceptions as cmexec
from checkmate import rdp
from checkmate import ssh
from checkmate import utils

LOG = logging.getLogger(__name__)


class Manager(object):

    """Contains logic for Compute provider logic."""

    @staticmethod
    def create_server(context, name, update_state, api=None, flavor="2",
                      files=None, image=None, tags=None, config_drive=None,
                      userdata=None, networks=None, boot_from_image=False,
                      disk=None):
        # pylint: disable=R0914
        """Create a Rackspace Cloud server using novaclient.

        Note: Nova server creation requests are asynchronous. The IP address
        of the server is not available when thios call returns. A separate
        operation must poll for that data.

        :param context: the context information
        :type context: dict
        :param name: the name of the server
        :param api: existing, authenticated connection to API
        :param image: the image ID to use when building the server (which OS)
        :param flavor: the size of the server (a string ID)
        :param userdata:
        :param config_drive: If True, enable config drive on the server.
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
        deployment_id = context["deployment_id"]
        resource_key = context['resource_key']
        if context.get('simulation') is True:
            results = {
                'id': str(1000 + int(resource_key)),
                'status': "BUILD",
                'password': 'RandomPass',
                'flavor': flavor,
                'image': image,
                'error-message': '',
                'status-message': '',
            }
            return results
        utils.match_celery_logging(LOG)

        LOG.debug('Image=%s, Flavor=%s, Name=%s, Files=%s', image, flavor,
                  name, files)

        try:
            # Check image and flavor IDs (better descriptions if we error here)
            image_object = api.images.find(id=image)
            LOG.debug("Image id %s found. Name=%s", image, image_object.name)
            flavor_object = api.flavors.find(id=str(flavor))
            LOG.debug("Flavor id %s found. Name=%s", flavor,
                      flavor_object.name)
        except requests.ConnectionError as exc:
            msg = ("Connection error talking to %s endpoint" %
                   (api.client.management_url))
            LOG.error(msg, exc_info=True)
            raise cmexec.CheckmateException(message=msg,
                                            options=cmexec.CAN_RESUME)

        # Add RAX-CHECKMATE to metadata
        # support old way of getting metadata from generate_template
        meta = tags or context.get("metadata", None)
        kwargs = {}
        if boot_from_image:
            kwargs["block_device_mapping_v2"] = [
                {
                    "boot_index": 0,
                    "uuid": image,
                    "volume_size": disk or 50,
                    "source_type": "image",
                    "destination_type": "volume",
                    "delete_on_termination": True
                }
            ]
            image_object = None
        try:
            server = api.servers.create(name, image_object, flavor_object,
                                        meta=meta, files=files,
                                        config_drive=config_drive,
                                        userdata=userdata,
                                        nics=networks,
                                        **kwargs)
        except ncexc.OverLimit as exc:
            raise cmexec.CheckmateException(
                message=str(exc),
                friendly_message="You have reached the maximum number of "
                                 "servers that can be spun up using this "
                                 "account. Please delete some servers to "
                                 "continue or contact your support team to"
                                 " increase your limit",
                options=cmexec.CAN_RETRY
            )
        except requests.ConnectionError:
            msg = ("Connection error talking to %s endpoint" %
                   api.client.management_url)
            LOG.error(msg, exc_info=True)
            raise cmexec.CheckmateException(
                message=msg, options=cmexec.CAN_RESUME)

        update_state(state="PROGRESS",
                     meta={"server.id": server.id})

        LOG.info('Created server %s (%s) for deployment %s.', name, server.id,
                 deployment_id)

        result = {
            'id': server.id,
            'password': server.adminPass,
            'region': api.client.region_name,
            'status': 'NEW',
            'flavor': flavor,
            'image': image,
            'error-message': '',
            'status-message': '',
        }
        return result

    @staticmethod
    def wait_on_build(context, server_id, callback, update_task_state,
                      ip_address_type='public', api=None, desired_state=None):
        """Checks build is complete.

        :param context: context data
        :param server_id: server id of the server to wait for
        :param region: region in which the server exists
        :param ip_address_type: the type of IP address to return as 'ip' in the
            response
        :param api: api object for getting server details
        :return: False when build not ready. Dict with ip addresses when done.
        """
        desired_state = desired_state or {}
        utils.match_celery_logging(LOG)
        resource_key = context['resource_key']

        if context.get('simulation') is True:
            results = {
                'status': desired_state.get('status') or "ACTIVE",
                'status-message': "",
                'ip': '4.4.4.%s' % resource_key,
                'public_ip': '4.4.4.%s' % resource_key,
                'private_ip': '10.1.2.%s' % resource_key,
                'addresses': {
                    'public': [
                        {
                            "version": 4,
                            "addr": "4.4.4.%s" % resource_key,
                        },
                        {
                            "version": 6,
                            "addr": "2001:babe::ff04:36c%s" % resource_key,
                        }
                    ],
                    'private': [
                        {
                            "version": 4,
                            "addr": "10.1.2.%s" % resource_key,
                        }
                    ]
                }
            }
            return results

        assert server_id, "ID must be provided"
        LOG.debug("Getting server %s", server_id)

        try:
            server = api.servers.find(id=server_id)
        except (ncexc.NotFound, ncexc.NoUniqueMatch):
            msg = "No server matching id %s" % server_id
            LOG.error(msg, exc_info=True)
            raise cmexec.CheckmateException(msg)
        except requests.ConnectionError:
            msg = ("Connection error talking to %s endpoint" %
                   api.client.management_url)
            LOG.error(msg, exc_info=True)
            raise cmexec.CheckmateException(message=msg,
                                            options=cmexec.CAN_RESUME)

        results = {
            'id': server_id,
            'status': server.status,
            'addresses': server.addresses,
            'region': api.client.region_name,
        }

        if server.status == 'ERROR':
            results = {
                'status': 'ERROR',
                'status-message': "Server %s build failed" % server_id,
            }

            callback(results)
            raise cmexec.CheckmateException(
                results['status-message'],
                results['status-message'],
                cmexec.CAN_RESET)
        if server.status == 'BUILD':
            results['progress'] = server.progress
            results['status-message'] = "%s%% Complete" % server.progress
            # countdown = 100 - server.progress
            # if countdown <= 0:
            #     countdown = 15  # progress not accurate. Allow at least 15s
            #            # wait
            update_task_state(state='PROGRESS', meta=results)
            # progress indicate shows percentage, give no indication of seconds
            # left to build.
            # It often, if not usually takes at least 30 seconds after a server
            # hits 100% before it will be "ACTIVE".  We used to use % left as a
            # countdown value, but reverting to the above configured countdown.
            msg = (
                "Server '%s' progress is %s. Retrying after 30 seconds" %
                (server_id, server.progress)
            )
            LOG.debug(msg)
            results['progress'] = server.progress
            callback(results)
            raise cmexec.CheckmateException(message=msg,
                                            options=cmexec.CAN_RESUME)

        if server.status != 'ACTIVE':
            # this may fail with custom/unexpected statuses like "networking"
            # or a manual rebuild performed by the user to fix some problem
            # so lets retry instead and notify via the normal task mechanisms
            msg = ("Server '%s' status is %s, which is not recognized. "
                   "Not assuming it is active" % (server_id, server.status))
            results['status-message'] = msg
            callback(results)
            raise cmexec.CheckmateException(message=msg,
                                            options=cmexec.CAN_RESUME)

        # if a rack_connect account, wait for rack_connect configuration to
        # finish
        rackconnected = utils.is_rackconnect_account(context)
        if rackconnected:
            if 'rackconnect_automation_status' not in server.metadata:
                msg = ("RackConnect server still does not have the "
                       "'rackconnect_automation_status' metadata tag")
                results['status-message'] = msg
                callback(results)
                raise cmexec.CheckmateException(message=msg,
                                                options=cmexec.CAN_RESUME)
            else:
                rc_automation_status = server.metadata[
                    'rackconnect_automation_status']
                if rc_automation_status == 'DEPLOYED':
                    LOG.debug("Rack Connect server ready. Metadata found'")
                    results["rackconnect-automation-status"] = (
                        rc_automation_status)
                elif rc_automation_status == 'FAILED':
                    msg = ("Rackconnect server metadata has "
                           "'rackconnect_automation_status' set to FAILED.")
                    LOG.debug(msg)
                    results['status'] = 'ERROR'
                    results['status-message'] = msg
                    results["rackconnect-automation-status"] = (
                        rc_automation_status)

                    context["instance_id"] = server_id
                    callback(results)

                    raise cmexec.CheckmateException(
                        message=msg,
                        friendly_message=cmexec.UNEXPECTED_ERROR
                    )
                elif rc_automation_status == 'UNPROCESSABLE':
                    reason = Manager.get_rackconnect_error_reason(
                        server.metadata)
                    msg = ("RackConnect server "
                           "metadata has 'rackconnect_automation_status' is "
                           "set to %s.%s RackConnect will not be enabled for "
                           "this server(#%s)." % (rc_automation_status,
                                                  reason,
                                                  server_id))
                    LOG.warn(msg)
                    results["rackconnect-automation-status"] = (
                        rc_automation_status)
                else:
                    msg = ("Rack Connect server "
                           "'rackconnect_automation_status' metadata tag is "
                           "still not 'DEPLOYED'. It is '%s'" %
                           rc_automation_status)
                    results['status-message'] = msg

                    callback(results)
                    raise cmexec.CheckmateException(message=msg,
                                                    options=cmexec.CAN_RESUME)

        ips = utils.get_ips_from_server(
            server,
            rackconnected,
            primary_address_type=ip_address_type
        )
        utils.merge_dictionary(results, ips)

        # we might not get an ip right away, so wait until its populated
        if 'ip' not in results:
            raise cmexec.CheckmateException(
                message="Could not find IP of server %s" % server_id,
                options=cmexec.CAN_RESUME)
        results['status'] = desired_state.get('status', 'ACTIVE')
        results['status-message'] = ''

        return results

    @staticmethod
    def attach_volume(context, region, server_id, volume_id, api,
                      device_name=None, callback=None):
        """Attach a Cloud Block Storage volume to a Server."""
        utils.match_celery_logging(LOG)
        if context.get('simulation') is True:
            data = {
                'attachments': {
                    device_name or '/dev/xvdb': volume_id,
                },
                'devices': {
                    # TODO(zns): make label an input
                    'data': device_name or '/dev/xvdb',
                }
            }
            if callable(callback):
                callback(data)
            return data

        assert server_id, "ID must be provided"
        LOG.debug("Getting server %s", server_id)
        try:
            server = api.servers.find(id=server_id)
        except (ncexc.NotFound, ncexc.NoUniqueMatch):
            msg = "No server matching id %s" % server_id
            LOG.error(msg, exc_info=True)
            raise cmexec.CheckmateException(msg)
        except requests.ConnectionError:
            msg = ("Connection error talking to %s endpoint" %
                   api.client.management_url)
            LOG.error(msg, exc_info=True)
            raise cmexec.CheckmateException(message=msg,
                                            options=cmexec.CAN_RESUME)
        # Hybrid pyrax and requests - lovin' it
        # TODO(zns): fix it
        url = [l['href'] for l in server.links if l['rel'] == 'self'][0]
        headers = {
            'X-Auth-Token': context['auth_token'],
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        body = {
            'volumeAttachment': {
                'volumeId': volume_id,
                'device': device_name,  # None means auto assigned
            }
        }
        response = requests.post(url + '/os-volume_attachments',
                                 data=json.dumps(body), headers=headers)
        if response.ok:
            LOG.debug("Volume attached: %s", response.json())
            result = response.json()
            attachment = result['volumeAttachment']
            data = {
                'attachments': {
                    attachment['device']: attachment['id']
                },
                'devices': {
                    # TODO(zns): make label an input
                    'data': attachment['device'],
                }
            }
            if callable(callback):
                callback(data)
            return data
        response.raise_for_status()

    @staticmethod
    def get_rackconnect_error_reason(metadata):
        """Return reason for rackconnect going into UNPROCESSED status

        @param metadata: Server metadata
        @return:
        """
        reason = metadata.get("rackconnect_unprocessable_reason", None)
        return "" if not reason else " Reason: %s." % reason

    @staticmethod
    def verify_ssh_connection(context, server_id, server_ip,
                              username='root', timeout=10, password=None,
                              identity_file=None, port=22, api=None,
                              private_key=None, proxy_address=None,
                              proxy_credentials=None):
        """Verifies the ssh connection to a server

        :param context: context data
        :param server_id: server id
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
        utils.match_celery_logging(LOG)

        if context.get('simulation') is True:
            return {
                "status": True,
                "status-message": "verify_ssh_connection is simulated"
            }

        try:
            server = api.servers.find(id=server_id)
        except (ncexc.NotFound, ncexc.NoUniqueMatch):
            msg = "No server matching id %s" % server_id
            LOG.error(msg, exc_info=True)
            raise cmexec.CheckmateException(msg)
        except requests.ConnectionError:
            msg = ("Connection error talking to %s endpoint" %
                   api.client.management_url)
            LOG.error(msg, exc_info=True)
            raise cmexec.CheckmateException(message=msg,
                                            options=cmexec.CAN_RESUME)

        image = server.image
        if not isinstance(image, basestring):
            image = image['id']
        if image:
            image_details = api.images.find(id=image)
            metadata = image_details.metadata
            image_name = image_details.name.lower()
        else:
            # Just try linux
            metadata = {'os_type': 'linux'}
            image_name = "unkown"
        if ((metadata and metadata['os_type'] == 'linux') or
                ('windows' not in image_name)):
            msg = ("Server '%s' is ACTIVE but 'ssh %s@%s -p %d' is failing "
                   "to connect." % (server_id, username, server_ip, port))
            is_up = ssh.test_connection(context, server_ip, username,
                                        timeout=timeout,
                                        password=password,
                                        identity_file=identity_file,
                                        port=port,
                                        private_key=private_key,
                                        proxy_address=None,
                                        proxy_credentials=None)
        else:
            msg = ("Server '%s' is ACTIVE but is not responding to ping"
                   " attempts" % server_id)
            is_up = rdp.test_connection(context, server_ip, timeout=timeout)

        return {
            "status": is_up,
            "status-message": "" if is_up else msg
        }

    @staticmethod
    def delete_server_task(context, api, callback):
        """Celery Task to delete a Nova compute instance."""
        utils.match_celery_logging(LOG)

        assert "deployment_id" in context or "deployment" in context, \
            "No deployment id in context"
        assert "resource_key" in context, "No resource key in context"
        assert "region" in context, "No region provided"
        assert 'resource' in context, "No resource definition provided"

        server = None
        inst_id = context.get("instance_id")
        resource_key = context.get('resource_key')
        deployment_id = context.get("deployment_id", context.get("deployment"))

        results = {
            'status': 'DELETING',
            'status-message': ''
        }

        if inst_id is None:
            msg = ("Instance ID is not available for Compute Instance, "
                   "skipping delete_server_task for resource %s in deployment"
                   " %s" % (resource_key, deployment_id))
            LOG.info(msg)
            results['status'] = 'DELETED'
            results['status-message'] = msg
            return results

        try:
            if context.get('simulation') is not True:
                server = api.servers.get(inst_id)
        except (ncexc.NotFound, ncexc.NoUniqueMatch):
            LOG.warn("Server %s already deleted", inst_id)
        except requests.ConnectionError:
            msg = ("Connection error talking to %s endpoint" %
                   api.client.management_url)
            LOG.error(msg, exc_info=True)
            raise cmexec.CheckmateException(message=msg,
                                            options=cmexec.CAN_RESUME)
        if (not server) or (server.status == 'DELETED'):
            results['status'] = 'DELETED'

        elif server.status in ['ACTIVE', 'ERROR', 'SHUTOFF']:
            results['status-message'] = 'Waiting on resource deletion'
            try:
                server.delete()
            except requests.ConnectionError:
                msg = ("Connection error talking to %s endpoint" %
                       api.client.management_url)
                LOG.error(msg, exc_info=True)
                raise cmexec.CheckmateException(message=msg,
                                                options=cmexec.CAN_RESUME)
        else:
            msg = ('Instance is in state %s. Waiting on ACTIVE resource.'
                   % server.status)
            results['status-message'] = msg
            callback(results)
            raise cmexec.CheckmateException(message=msg,
                                            options=cmexec.CAN_RESUME)
        return results

    @staticmethod
    def wait_on_delete_server(context, api, callback):
        """Wait for a server resource to be deleted."""
        utils.match_celery_logging(LOG)
        assert "deployment_id" in context, "No deployment id in context"
        assert "resource_key" in context, "No resource key in context"
        assert "region" in context, "No region provided"
        assert 'resource' in context, "No resource definition provided"

        server = None
        inst_id = context.get("instance_id")

        resource_key = context.get('resource_key')
        deployment_id = context.get('deployment_id')

        if inst_id is None:
            msg = ("Instance ID is not available for Compute Instance, "
                   "skipping wait_on_delete_task for resource %s in "
                   "deployment %s"
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
                   api.client.management_url)
            LOG.error(msg, exc_info=True)
            raise cmexec.CheckmateException(message=msg,
                                            options=cmexec.CAN_RESUME)
        if (not server) or (server.status == "DELETED"):
            results = {
                'status': 'DELETED',
                'status-message': ''
            }

        else:
            msg = ('Instance is in state %s. Waiting on DELETED resource.'
                   % server.status)
            results = {
                'status': 'DELETING',
                'status-message': msg
            }
            callback(results)
            raise cmexec.CheckmateException(message=msg,
                                            options=cmexec.CAN_RESUME)
        return results

    @staticmethod
    def _on_failure(exc, task_id, args, kwargs, einfo, action, method,
                    callback):
        # pylint: disable=W0613
        """Helper method to get failure handler."""
        dep_id = args[0].get('deployment_id')
        resource_key = args[0].get('resource_key')

        if dep_id and resource_key:
            callback({
                'status': 'ERROR',
                'status-message': ('Unexpected error %s compute instance %s' %
                                   (action, resource_key)),
                'error-message': str(exc)
            }, resource_key=resource_key)
        else:
            LOG.error("Missing deployment id and/or resource resource_key in "
                      "%s error callback.", method)

    @staticmethod
    def get_on_failure(action, method, callback):
        """Used by tasks for failure handlers."""
        def on_failure(exc, task_id, args, kwargs, einfo):
            """Celery Task on_failure function."""
            Manager._on_failure(exc, task_id, args, kwargs, einfo, action,
                                method, callback)
        return on_failure
