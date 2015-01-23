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

"""Rackspace Cloud Block Storage provider manager."""

import logging

from pyrax import exceptions as cdb_errors
import requests

from checkmate import exceptions as cmexc

LOG = logging.getLogger(__name__)


class Manager(object):

    """Block Storage provider model and logic for interaction."""

    #pylint: disable=R0913
    @staticmethod
    def create_volume(size, context, api, callback, region=None,
                      tags=None, simulate=False):
        """Create a Block Storage volume."""
        size = int(size)
        try:
            if simulate:
                resource_key = context.get('resource_key')
                instance = {
                    'id': "CBS%s" % resource_key,
                }
            else:
                instance = api.create_volume(context,
                                             region or context.region,
                                             size,
                                             metadata=tags)
        except cdb_errors.OverLimit as exc:
            raise cmexc.CheckmateException(str(exc), friendly_message=str(exc),
                                           options=cmexc.CAN_RETRY)
        except cdb_errors.ClientException as exc:
            raise cmexc.CheckmateException(str(exc), options=cmexc.CAN_RETRY)
        except Exception as exc:
            raise cmexc.CheckmateException(str(exc))
        if callable(callback):
            callback({'id': instance['id']})

        LOG.info("Created block volume %s. Size %s.", instance['id'],
                 size)

        return instance

    @staticmethod
    def delete_volume(context, region, volume_id, api, callback,
                      simulate=False):
        """Delete a Cloud Block Storage Volume."""
        if simulate:
            results = {
                'status': 'DELETED',
                'status-message': ''
            }
            return results
        volume = None
        status = None
        try:
            volume = api.get_volume(context, region, volume_id)
        except requests.exceptions.HTTPError as exc:
            if exc.errno == 404:
                LOG.debug('Block Volume %s was already deleted.', volume_id)
                results = {
                    'status': 'DELETED',
                    'status-message': ''
                }
            else:
                raise exc

        if volume:
            status = volume['status']
            LOG.debug("Found Block Volume %s [%s] to delete", volume, status)
            if status in ("available", "ACTIVE", "ERROR", "SUSPENDED"):
                LOG.debug('Deleting Block Volume %s.', volume_id)
                api.delete_volume(context, region, volume_id)
                status_message = 'Waiting on resource deletion'
            elif status == "DELETED":
                LOG.debug("Block Volume %s is already deleted", volume_id)
                status_message = ''
            else:
                status_message = ("Cannot delete Block Volume %s, as it "
                                  "currently is in %s state. Waiting for "
                                  "it's status to move to ACTIVE, "
                                  "ERROR or SUSPENDED" % (volume_id, status))
                LOG.debug(status_message)
                raise cmexc.CheckmateException(
                    status_message, options=cmexc.CAN_RESUME)
            results = {
                'status': status or 'DELETING',
                'status-message': status_message
            }
        return results
