# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Script provider tasks."""

from celery.task import task

from checkmate.common import statsd
from checkmate.providers.base import ProviderTask
from checkmate.providers.core.script import Manager
from checkmate.providers.core.script import Provider


# Disable pylint on api and callback as they're passed in from ProviderTask
@task(base=ProviderTask, default_retry_delay=30, max_retries=3,
      provider=Provider)
@statsd.collect
def create_resource(context, deployment_id, resource, host, username,
                    password=None, private_key=None, install_script=None,
                    timeout=60, host_os=None, api=None, callback=None):
    """Waits on the instance to be created, deletes the instance if it goes
    into an ERRORed status.

    :param context: Context
    :param api:
    :param callback:
    :return:
    """
    manager = Manager(api=api or create_resource.api,
                      callback=callback or create_resource.partial,
                      simulate=context.simulation)
    return manager.create_resource(context, deployment_id, resource, host,
                                   username, password=password,
                                   private_key=private_key,
                                   install_script=install_script,
                                   host_os=host_os, timeout=timeout)
