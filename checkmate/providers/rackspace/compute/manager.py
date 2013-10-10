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
