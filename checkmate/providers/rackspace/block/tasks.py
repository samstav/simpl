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

# encoding: utf-8

"""Rackspace Cloud Block Storage provider tasks."""

import logging

from celery.task import task

from checkmate.common import statsd
from checkmate.providers.base import RackspaceProviderTask
from checkmate.providers.rackspace.block.manager import Manager
from checkmate.providers.rackspace.block.provider import Provider

LOG = logging.getLogger(__name__)


# Disable pylint on api and callback as their passed in from ProviderTask
# pylint: disable=W0613, R0913
@task(base=RackspaceProviderTask, default_retry_delay=10, max_retries=2,
      provider=Provider)
@statsd.collect
def create_volume(context, region, size, tags=None,
                  api=None, callback=None):
    """Create a Cloud Block Storage instance."""
    return Manager.create_volume(size,
                                 context,
                                 api or create_volume.api,
                                 callback or create_volume.partial,
                                 tags=tags,
                                 region=region,
                                 simulate=context.simulation)


@task(base=RackspaceProviderTask, default_retry_delay=10, max_retries=2,
      provider=Provider)
@statsd.collect
def delete_volume(context, region, volume_id,
                  api=None, callback=None):
    """Delete a Cloud Block Storage volume."""
    return Manager.delete_volume(context,
                                 region,
                                 volume_id,
                                 api or delete_volume.api,
                                 callback or delete_volume.partial,
                                 simulate=context.simulation)
