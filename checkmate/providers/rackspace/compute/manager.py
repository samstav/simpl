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
Rackspace Compute provider manager.
"""
import logging
import checkmate.utils
import requests

from novaclient import exceptions as ncexc

from checkmate import exceptions as cmexec
from checkmate.providers.rackspace.compute.provider import Provider
from checkmate import deployments as cmdeps, utils

LOG = logging.getLogger(__name__)


class Manager(object):
    """Contains logic for Compute provider logic."""

    @staticmethod
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
        deployment_id = context["deployment_id"]
        resource_key = context['resource_key']
        if context.get('simulation') is True:
            results = {'id': str(1000 + int(resource_key)),
                       'status': "BUILD",
                       'password': 'RandomPass'}
            return results
        utils.match_celery_logging(LOG)

        LOG.debug('Image=%s, Flavor=%s, Name=%s, Files=%s', image, flavor, name,
                  files)

        if api is None:
            api = Provider.connect(context, region)

        try:
            # Check image and flavor IDs (better descriptions if we error here)
            image_object = api.images.find(id=image)
            LOG.debug("Image id %s found. Name=%s", image, image_object.name)
            flavor_object = api.flavors.find(id=str(flavor))
            LOG.debug("Flavor id %s found. Name=%s", flavor, flavor_object.name)
        except requests.ConnectionError as exc:
            msg = ("Connection error talking to %s endpoint" %
                   (api.client.management_url))
            LOG.error(msg, exc_info=True)
            raise cmexec.CheckmateException(message=msg,
                                            options=cmexec.CAN_RESUME)

        # Add RAX-CHECKMATE to metadata
        # support old way of getting metadata from generate_template
        meta = tags or context.get("metadata", None)
        try:
            server = api.servers.create(name, image_object, flavor_object,
                                        meta=meta, files=files,
                                        disk_config='AUTO')
        except ncexc.OverLimit as exc:
            raise cmexec.CheckmateException(
                message =str(exc),
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

        LOG.info('Created server %s (%s) for deployment %s.', name, server.id,
                 deployment_id)

        result = {'id': server.id,
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
    def wait_on_build(context, server_id, region, callback, update_task_state,
                      ip_address_type='public', api=None):
        """Checks build is complete.

        :param context: context data
        :param server_id: server id of the server to wait for
        :param region: region in which the server exists
        :param ip_address_type: the type of IP address to return as 'ip' in the
            response
        :param api: api object for getting server details
        :return: False when build not ready. Dict with ip addresses when done.
        """
        utils.match_celery_logging(LOG)
        resource_key = context['resource_key']

        if context.get('simulation') is True:
            results = {
                'status': "ACTIVE",
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

        if api is None:
            api = Provider.connect(context, region)

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

            context["instance_id"] = server_id
            callback(results)
            raise cmexec.CheckmateException(
                results['status-message'],
                results['status-message'],
                cmexec.CAN_RESET)
        if server.status == 'BUILD':
            results['progress'] = server.progress
            results['status-message'] = "%s%% Complete" % server.progress
            #countdown = 100 - server.progress
            #if countdown <= 0:
            #    countdown = 15  # progress is not accurate. Allow at least 15s
            #           # wait
            update_task_state(state='PROGRESS', meta=results)
            # progress indicate shows percentage, give no indication of seconds
            # left to build.
            # It often, if not usually takes at least 30 seconds after a server
            # hits 100% before it will be "ACTIVE".  We used to use % left as a
            # countdown value, but reverting to the above configured countdown.
            msg = ("Server '%s' progress is %s. Retrying after 30 seconds" % (
                   server_id, server.progress))
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

        # if a rack_connect account, wait for rack_connect configuration to finish
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
                    results["rackconnect-automation-status"] = rc_automation_status
                elif rc_automation_status == 'FAILED':
                    msg = ("Rackconnect server metadata has "
                           "'rackconnect_automation_status' set to FAILED.")
                    LOG.debug(msg)
                    results['status'] = 'ERROR'
                    results['status-message'] = msg
                    results["rackconnect-automation-status"] = rc_automation_status

                    context["instance_id"] = server_id
                    callback(results)

                    raise cmexec.CheckmateException(message=msg,
                                                   friendly_message=cmexec
                                                   .UNEXPECTED_ERROR)
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
                    results["rackconnect-automation-status"] = rc_automation_status
                else:
                    msg = ("Rack Connect server 'rackconnect_automation_status' "
                           "metadata tag is still not 'DEPLOYED'. It is '%s'" %
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
        results['status'] = "ACTIVE"
        results['status-message'] = ''

        return results

    @staticmethod
    def get_rackconnect_error_reason(metadata):
        """Get the reason why rackconnect automation went into UNPROCESSED "
        status
        @param metadata: Server metadata
        @return:
        """
        reason = metadata.get("rackconnect_unprocessable_reason", None)
        return "" if not reason else " Reason: %s." % reason


    @staticmethod
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

    @staticmethod
    def get_on_failure(action, method):
        def on_failure(exc, task_id, args, kwargs, einfo):
            Manager._on_failure(exc, task_id, args, kwargs, einfo, action,
                             method)
        return on_failure
