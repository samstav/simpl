# pylint: disable=R0912,R0913,R0914,R0915,W0613

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
"""Rackspace solo provider tasks."""
import urlparse

from celery import task as ctask

from checkmate.common import statsd
from checkmate import deployments
from checkmate.providers.opscode.solo.manager import Manager
from checkmate.providers.opscode.solo import Provider
from checkmate.providers import ProviderTask


def register_scheme(scheme):
    """Use this to register a new scheme with urlparse.

    New schemes will be parsed in the same way as http is parsed
    """
    for method in filter(lambda s: s.startswith('uses_'), dir(urlparse)):
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly


@ctask.task
@statsd.collect
def write_databag(environment, bagname, itemname, contents, resource,
                  path=None, secret_file=None, merge=True,
                  kitchen_name='kitchen'):
    """DEPRECATED: Use write_databag_v2."""
    context = {
        'deployment_id': environment,
        'resource_key': resource
    }
    write_databag_v2(context, environment, bagname, itemname, contents,
                     path=path, secret_file=secret_file,
                     kitchen_name=kitchen_name)


@ctask.task(base=ProviderTask, provider=Provider)
@statsd.collect
def write_databag_v2(context, environment, bag_name, item_name, contents,
                     path=None, secret_file=None, kitchen_name='kitchen'):
    """Updates a data_bag or encrypted_data_bag

    :param environment: the ID of the environment
    :param bag_name: the name of the databag (in solo, this ends up being a
            directory)
    :param item_name: the name of the item (in solo this ends up being a
    .json file)
    :param contents: this is a dict of attributes to write in to the databag
    :param path: optional override to the default path where environments live
    :param secret_file: the path to a certificate used to encrypt a data_bag
    :param kitchen_name: Optional name of kitchen to write to.  default=kitchen
    """
    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        data = {
            'status': 'ERROR',
            'error-message': 'Error writing software configuration'
        }
        write_databag_v2.partial(data)

    write_databag_v2.on_failure = on_failure
    return Manager.write_data_bag(environment, bag_name, item_name, contents,
                                  write_databag_v2.partial, path=path,
                                  secret_file=secret_file,
                                  kitchen_name=kitchen_name,
                                  simulate=context.simulation)


@ctask.task(countdown=20, max_retries=3)
@statsd.collect
def cook(host, environment, resource, recipes=None, roles=None, path=None,
         username='root', password=None, identity_file=None, port=22,
         attributes=None, kitchen_name='kitchen'):
    """DEPRECATED: Use cook_v2."""
    context = {
        'deployment_id': environment,
        'resource_key': resource
    }
    cook_v2(context, host, environment, resource, recipes=recipes,
            roles=roles, path=path, username=username, password=password,
            identity_file=identity_file, port=port, attributes=attributes,
            kitchen_name=kitchen_name)


@ctask.task(base=ProviderTask, provider=Provider, countdown=20, max_retries=3)
@statsd.collect
def cook_v2(context, host, environment, recipes=None, roles=None,
            path=None, username='root', password=None, identity_file=None,
            port=22, attributes=None, kitchen_name='kitchen'):
    """Apply recipes/roles to a server"""

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        data = {
            'status': 'ERROR',
            'error-message': 'Error installing software'
        }
        cook_v2.partial(data)

    cook_v2.on_failure = on_failure

    return Manager.cook(host, environment, cook_v2.partial, recipes=recipes,
                        roles=roles, path=path, username=username,
                        password=password, identity_file=identity_file,
                        port=port, attributes=attributes,
                        kitchen_name=kitchen_name,
                        simulate=context.simulation)


@ctask.task(default_retry_delay=10, max_retries=6)
@statsd.collect
def delete_environment(name, path=None):
    """Remove the chef environment from the file system."""
    Manager.delete_environment(name, path=path)


@ctask.task
@statsd.collect
def delete_cookbooks(name, service_name, path=None):
    """Remove cookbooks directory and contents from the file system."""
    Manager.delete_cookbooks(name, service_name, path=path)


@ctask.task(max_retries=3)
@statsd.collect
def create_environment(context, name, service_name, path=None,
                       private_key=None, public_key_ssh=None,
                       secret_key=None, source_repo=None):
    """Create a knife-solo environment

    The environment is a directory structure that is self-contained and
    separate from other environments. It is used by this provider to run knife
    solo commands.

    :param name: the name of the environment. This will be the directory name.
    :param path: an override to the root path where to create this environment
    :param private_key: PEM-formatted private key
    :param public_key_ssh: SSH-formatted public key
    :param secret_key: used for data bag encryption
    :param source_repo: provides cookbook repository in valid git syntax
    """
    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        deployments.update_all_provider_resources.delay(
            Provider.name,
            context['deployment_id'],
            'ERROR',
            message=('Error creating chef environment: %s' % exc.args[1])
        )

    create_environment.on_failure = on_failure
    return Manager.create_environment(name, service_name, path=path,
                                      private_key=private_key,
                                      public_key_ssh=public_key_ssh,
                                      secret_key=secret_key,
                                      source_repo=source_repo,
                                      simulation=context['simulation'])


@ctask.task(max_retries=3, soft_time_limit=600)
@statsd.collect
def register_node(host, environment, resource, path=None, password=None,
                  bootstrap_version=None, attributes=None, identity_file=None,
                  kitchen_name='kitchen'):
    """DEPRECATED: Use register_node_v2."""
    context = {
        'deployment_id': environment,
        'resource_key': resource
    }
    register_node_v2(context, host, environment, path=path,
                     password=password, bootstrap_version=bootstrap_version,
                     attributes=attributes, identity_file=identity_file,
                     kitchen_name=kitchen_name)


@ctask.task(base=ProviderTask, provider=Provider, max_retries=3,
            soft_time_limit=600)
@statsd.collect
def register_node_v2(context, host, environment, path=None,
                     password=None, bootstrap_version=None, attributes=None,
                     identity_file=None, kitchen_name='kitchen'):
    """Register a node in Chef.

    Using 'knife prepare' we will:
    - update apt caches on Ubuntu by default (which bootstrap does not do)
    - install chef on the client
    - register the node by creating as .json file for it in /nodes/

    Note: Maintaining same 'register_node' name as chefserver.py

    :param host: the public IP of the host (that's how knife solo tracks the
        nodes)
    :param environment: the ID of the environment/deployment
    :param path: an optional override for path to the environment root
    :param password: the node's password
    :param bootstrap_version: override for knife bootstrap (default=latest)
    :param attributes: attributes to set on node (dict)
    :param identity_file: private key file to use to connect to the node
    """
    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        host = args[1]
        data = {
            'status': 'ERROR',
            'error-message': 'Error registering host %s' % host
        }
        register_node_v2.partial(data)

    register_node_v2.on_failure = on_failure
    return Manager.register_node(host, environment, register_node_v2.partial,
                                 path=path, password=password,
                                 bootstrap_version=bootstrap_version,
                                 attributes=attributes,
                                 identity_file=identity_file,
                                 kitchen_name=kitchen_name,
                                 simulate=context.simulation)


@ctask.task(countdown=20, max_retries=3)
@statsd.collect
def manage_role(name, environment, resource, path=None, desc=None,
                run_list=None, default_attributes=None,
                override_attributes=None, env_run_lists=None,
                kitchen_name='kitchen'):
    """DEPRECATED: use manage_role_v2."""
    context = {
        'deployment_id': environment,
        'resource_key': resource
    }
    manage_role_v2(context, name, environment, path=path, desc=desc,
                   run_list=run_list, default_attributes=default_attributes,
                   override_attributes=override_attributes,
                   env_run_lists=env_run_lists, kitchen_name=kitchen_name)


@ctask.task(base=ProviderTask, provider=Provider, countdown=20, max_retries=3)
@statsd.collect
def manage_role_v2(context, name, environment, path=None, desc=None,
                   run_list=None, default_attributes=None,
                   override_attributes=None, env_run_lists=None,
                   kitchen_name='kitchen'):
    """Write/Update role."""
    return Manager.manage_role(name, environment, manage_role_v2.partial,
                               path=path, desc=desc, run_list=run_list,
                               default_attributes=default_attributes,
                               override_attributes=override_attributes,
                               env_run_lists=env_run_lists,
                               kitchen_name=kitchen_name,
                               simulate=context.simulation)


@ctask.task(base=ProviderTask, provider=Provider, countdown=20, max_retries=3)
@statsd.collect
def delete_resource(context):
    """Marks the resource as deleted."""
    assert "resource_key" in context
    return Manager.delete_resource()
