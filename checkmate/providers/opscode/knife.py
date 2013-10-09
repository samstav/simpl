# pylint: disable=C0302,R0913

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

"""DEPRECATED: Use solo/tasks instead."""
import logging

from celery.task import task

from checkmate import celeryglobal
from checkmate.common import statsd
from checkmate.providers.opscode.solo import tasks

LOG = logging.getLogger(__name__)


@task
@statsd.collect
def write_databag(environment, bagname, itemname, contents, resource,
                  path=None, secret_file=None, merge=True,
                  kitchen_name='kitchen'):
    """DEPRECATED: Please use solo/tasks."""
    LOG.warn("knife.write_databag is deprecated. Please use solo/tasks"
             ".write_databag")
    return tasks.write_databag.delay(environment, bagname, itemname,
                                     contents, resource, path=path,
                                     secret_file=secret_file, merge=merge,
                                     kitchen_name=kitchen_name)


@task(countdown=20, max_retries=3)
@statsd.collect
def cook(host, environment, resource, recipes=None, roles=None, path=None,
         username='root', password=None, identity_file=None, port=22,
         attributes=None, kitchen_name='kitchen'):
    """DEPRECATED: Please use solo/tasks."""
    LOG.warn("knife.cook is deprecated. Please use solo/tasks.cook")
    return tasks.cook.delay(host, environment, resource, recipes=recipes,
                            roles=roles, path=path, username=username,
                            password=password, identity_file=identity_file,
                            port=port, attributes=attributes,
                            kitchen_name=kitchen_name)


@task(base=celeryglobal.RetryTask, default_retry_delay=10, max_retries=6)
@statsd.collect
def delete_environment(name, path=None):
    """DEPRECATED: Please use solo/tasks."""
    LOG.warn("knife.delete_environment is deprecated. Please use "
             "solo/tasks.cook")
    return tasks.delete_environment.delay(name, path=path)


@task
@statsd.collect
def delete_cookbooks(name, service_name, path=None):
    """DEPRECATED: Please use solo/tasks."""
    LOG.warn("knife.delete_cookbooks is deprecated. Please use "
             "solo/tasks.delete_cookbooks")
    return tasks.delete_cookbooks.delay(name, service_name, path=path)


@task
@statsd.collect
def create_environment(name, service_name, path=None, private_key=None,
                       public_key_ssh=None, secret_key=None, source_repo=None,
                       provider='chef-solo'):
    """DEPRECATED: Please use solo/tasks."""
    LOG.warn("knife.create_environment is deprecated. Please use "
             "solo/tasks.create_environment")
    tasks.create_environment.delay(name, service_name, path=path,
                                   private_key=private_key,
                                   public_key_ssh=public_key_ssh,
                                   secret_key=secret_key,
                                   source_repo=source_repo, provider=provider)


@task(max_retries=3, soft_time_limit=600)
@statsd.collect
def register_node(host, environment, resource, path=None, password=None,
                  omnibus_version=None, attributes=None, identity_file=None,
                  kitchen_name='kitchen'):
    """DEPRECATED: Please use solo/tasks."""
    LOG.warn("knife.register_node is deprecated. Please use "
             "solo/tasks.register_node")
    return tasks.register_node.delay(host, environment, resource, path=path,
                                     password=password,
                                     omnibus_version=omnibus_version,
                                     attributes=attributes,
                                     identity_file=identity_file,
                                     kitchen_name=kitchen_name)


@task(countdown=20, max_retries=3)
@statsd.collect
def manage_role(name, environment, resource, path=None, desc=None,
                run_list=None, default_attributes=None,
                override_attributes=None, env_run_lists=None,
                kitchen_name='kitchen'):
    """DEPRECATED: Please use solo/tasks."""
    LOG.warn("knife.manage_role is deprecated. Please use "
             "solo/tasks.manage_role")
    return tasks.manage_role.delay(name, environment, resource, path=path,
                                   desc=desc, run_list=run_list,
                                   default_attributes=default_attributes,
                                   override_attributes=override_attributes,
                                   env_run_lists=env_run_lists,
                                   kitchen_name=kitchen_name)
