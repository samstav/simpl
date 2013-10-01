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

# encoding: utf-8
"""
Rackspace Cloud Databases provider tasks
"""
import logging
from celery.task import task

from checkmate.common import statsd
from checkmate.providers.base import RackspaceProviderTask
from checkmate.providers.rackspace.database import Manager
from checkmate.providers.rackspace.database import Provider

LOG = logging.getLogger(__name__)

# Disable pylint on api and callback as their passed in from ProviderTask
# pylint: disable=W0613
@task(base=RackspaceProviderTask, default_retry_delay=30, max_retries=120,
      acks_late=True, provider=Provider)
@statsd.collect
def wait_on_build(context, region, instance=None, api=None, callback=None):
    """Waits on the instance to be created, deletes the instance if it goes
    into an ERRORed status
    :param context: Context
    :param region: Region
    :param instance: Instance Information
    :param api:
    :param callback:
    :return:
    """
    return Manager.wait_on_build(instance["id"], wait_on_build.api,
                                 wait_on_build.partial,
                                 context.simulation)


# Disable on api and callback.  Suppress num args
# pylint: disable=W0613
@task(base=RackspaceProviderTask, provider=Provider)
@statsd.collect
def sync_resource_task(context, resource, api=None, callback=None):
    """Task to handle syncing remote status with checkmate status."""
    return Manager.sync_resource(resource, sync_resource_task.api,
                                 context.simulation)


# Disable pylint on api and callback as their passed in from ProviderTask
# pylint: disable=W0613, R0913
@task(base=RackspaceProviderTask, default_retry_delay=10, max_retries=2,
      provider=Provider)
@statsd.collect
def create_instance(context, instance_name, flavor, size, databases, region,
                    api=None, callback=None):
    """Creates a Cloud Database instance with optional initial databases.

    :param databases: an array of dictionaries with keys to set the database
    name, character set and collation.  For example:

        databases=[{'name': 'db1'},
                   {'name': 'db2', 'character_set': 'latin5',
                    'collate': 'latin5_turkish_ci'}]
    """
    return Manager.create_instance(instance_name, flavor, size,
                                   databases, context, create_instance.api,
                                   create_instance.partial,
                                   context.simulation)


#pylint: disable=R0913
@task(base=RackspaceProviderTask, default_retry_delay=15, max_retries=40,
      provider=Provider)
@statsd.collect
def create_database(context, name, region=None, character_set=None,
                    collate=None, instance_id=None, instance_attributes=None,
                    callback=None, api=None):
    """Create a database resource.

    This call also creates a server instance if it is not supplied.

    :param name: the database name
    :param region: where to create the database (ex. DFW or dallas)
    :param character_set: character set to use (see MySql and cloud databases
            documanetation)
    :param collate: collation to use (see MySql and cloud databases
            documanetation)
    :param instance_id: create the database on a specific instance id (if not
            supplied, the instance is created)
    :param instance_attributes: kwargs used to create the instance (used if
            instance_id not supplied)
    """
    return Manager.create_database(name, instance_id, create_database.api,
                                   create_database.partial, context=context,
                                   character_set=character_set,
                                   collate=collate,
                                   instance_attrs=instance_attributes,
                                   simulate=context.simulation)


@task(base=RackspaceProviderTask, default_retry_delay=10, max_retries=2,
      provider=Provider)
def add_user(context, instance_id, databases, username, password,
             api=None, callback=None):
    """Add a database user to an instance for one or more databases."""
    return Manager.add_user(instance_id, databases, username, password,
                            add_user.api, add_user.partial, context.simulation)
