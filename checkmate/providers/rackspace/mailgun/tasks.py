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
Rackspace mailgun provider tasks
"""
from celery import task

from checkmate.common import statsd
from checkmate.providers.base import ProviderTask
from checkmate.providers.rackspace.mailgun import Manager
from checkmate.providers.rackspace.mailgun import Provider


# Disable pylint on api and callback as their passed in from ProviderTask
# pylint: disable=W0613
@task.task(base=ProviderTask, default_retry_delay=10, max_retries=2,
           provider=Provider)
@statsd.collect
def create_domain(context, domain_name, password, api=None, callback=None):
    '''Task for creating a domain in Mailgun.'''
    return Manager.create_domain(domain_name, password, context,
                                 create_domain.api, context.simulation)


@task.task(base=ProviderTask, default_retry_delay=10, max_retries=2,
           provider=Provider)
@statsd.collect
def delete_domain(context, domain_name, exists, api=None, callback=None):
    '''Task for deleting a domain in Mailgun.'''
    return Manager.delete_domain(domain_name, delete_domain.api, exists,
                                 context.simulation)
