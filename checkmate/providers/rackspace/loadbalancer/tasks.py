# pylint: disable=W0613
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
Rackspace Cloud Loadbalancer provider tasks.
"""
from celery import task

from checkmate.common import statsd
from checkmate.providers import base
from checkmate.providers.rackspace.loadbalancer import manager
from checkmate.providers.rackspace.loadbalancer import provider


@task.task(base=base.ProviderTask, default_retry_delay=10, max_retries=2,
           provider=provider.Provider)
@statsd.collect
def enable_content_caching(context, lbid, api=None, callback=None):
    """Task to enable loadbalancer content caching."""
    return manager.Manager.enable_content_caching(lbid,
                                                  enable_content_caching.api,
                                                  context.simulation)
