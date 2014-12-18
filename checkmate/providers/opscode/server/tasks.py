# pylint: disable=W0613,C0103,C0111,R0913

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
"""Tasks for chef server provider."""
import logging

from celery import task as ctask
import chef

from checkmate.common import statsd
from checkmate.deployments import tasks
from checkmate.providers.opscode.server.manager import Manager
from checkmate.providers.opscode.server import Provider
from checkmate.providers import ProviderTask

LOG = logging.getLogger(__name__)


@ctask.task(base=ProviderTask, provider=Provider)
@statsd.collect
def register_node(context, deployment, name, recipes=None, roles=None,
                  attributes=None, environment=None, api=None):
    """Register node on chef server."""

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        data = {
            'status': 'ERROR',
            'error-message': 'Error register node'
        }
        register_node.partial(data)
    register_node.on_failure = on_failure

    # Add any missing recipes to node settings
    run_list = create_role_recipe_string(roles=roles, recipes=recipes)

    if context.simulation:
        LOG.info("Would register node %s with run_list=%s", name,
                 run_list)
        return

    try:
        if api:
            n = chef.Node(name, api=api)
            if run_list is not None:
                n.run_list = run_list
            if attributes is not None:
                n.normal = attributes
            if environment is not None:
                n.chef_environment = environment
            n.save()
        else:
            Manager.register_node(context, deployment, name,
                                  run_list=run_list,
                                  normal_attributes=attributes,
                                  environment=environment)
        LOG.debug('Registered %s with Chef Server. Setting runlist to %s',
                  name, run_list)
        return True
    except chef.ChefError, exc:
        LOG.debug('Node registration failed. Chef Error: %s. Retrying.', exc)
        register_node.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Node registration failed. Error: %s. Retrying.', exc)
        register_node.retry(exc=exc)


@ctask.task(base=ProviderTask, provider=Provider, max_retries=5,
            default_retry_delay=60)
@statsd.collect
def bootstrap(context, deployment, name, ip, username='root', password=None,
              port=22, identity_file=None, roles=None, recipes=None,
              distro='chef-full', environment=None, bootstrap_version=None,
              api=None):

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        data = {
            'status': 'ERROR',
            'error-message': 'Error bootstrap'
        }
        bootstrap.partial(data)
    bootstrap.on_failure = on_failure

    LOG.info('Bootstraping %s on chef server (%s:%d)', name, ip, port)
    run_list = create_role_recipe_string(roles=roles, recipes=recipes)
    return Manager.bootstrap(context, deployment, name, ip,
                             username=username, password=password,
                             port=port, identity_file=identity_file,
                             run_list=run_list, distro=distro,
                             environment=environment,
                             bootstrap_version=bootstrap_version,
                             simulation=context.simulation,
                             callback=bootstrap.partial)


@ctask.task(base=ProviderTask, provider=Provider)
@statsd.collect
def write_databag(context, deployment, bagname, itemname, contents,
                  secret_file=None, api=None):
    """Create/Edit Data Bag."""

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        data = {
            'status': 'ERROR',
            'error-message': 'Error modifying databag'
        }
        write_databag.partial(data)
    write_databag.on_failure = on_failure

    if context.simulation:
        LOG.info("Would create databag: %s", bagname)
        return

    try:
        if api:
            bag = chef.DataBag(bagname, api=api)
            bag.save()
            item = chef.DataBagItem(bag, itemname)
            for key, value in contents.iteritems():
                item[key] = value
            item.save()
        else:
            Manager.update_databag(deployment, bagname, itemname, contents)
        LOG.debug('Databag %s item %s updated.', bagname, itemname)
    except chef.ChefError, exc:
        LOG.debug('Databag management failed. Chef Error: %s. Retrying.', exc)
        write_databag.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Databag management failed. Error: %s. Retrying.', exc)
        write_databag.retry(exc=exc)
    return True


@ctask.task(base=ProviderTask, provider=Provider)
@statsd.collect
def manage_role(context, deployment, name, desc=None, run_list=None,
                default_attributes=None, override_attributes=None,
                env_run_lists=None, api=None):
    """Create/Edit Role."""

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        data = {
            'status': 'ERROR',
            'error-message': 'Error modifying role'
        }
        manage_role.partial(data)
    manage_role.on_failure = on_failure

    if context.simulation:
        LOG.info("Would create role: %s", name)
        return

    try:
        if api:
            r = chef.Role(name, api=api)
            if desc is not None:
                r.description = desc
            if run_list is not None:
                r.run_list = run_list
            if default_attributes is not None:
                r.default_attributes = default_attributes
            if override_attributes is not None:
                r.override_attributes = override_attributes
            if env_run_lists is not None:
                r.env_run_lists = env_run_lists
            r.save()
        else:
            Manager.update_role(name, deployment, desc=None,
                                default_attributes=None,
                                override_attributes=None)
        LOG.debug(
            "Role %s updated. runlist set to %s. Default attributes set "
            "to %s. Override attributes set to %s. Environment run lists "
            "set to %s.", name, run_list, default_attributes,
            override_attributes, env_run_lists)
    except chef.ChefError, exc:
        LOG.debug('Role management failed. Chef Error: %s. Retrying.', exc)
        manage_role.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Role management failed. Error: %s. Retrying.', exc)
        manage_role.retry(exc=exc)
    return True


@ctask.task(base=ProviderTask, provider=Provider, max_retries=3)
@statsd.collect
def manage_environment(context, deployment, name, desc=None, versions=None,
                       default_attributes=None, override_attributes=None,
                       api=None):
    """Create or modify a chef environment.

    :param name: the name of the environment.
    :param source_repo: provides cookbook repository in valid git syntax.
    """
    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        data = {
            'status': 'ERROR',
            'error-message': 'Error modifying chef environment'
        }
        manage_environment.partial(data)
    manage_environment.on_failure = on_failure

    if context.simulation:
        LOG.info("Would modify environment: %s", name)
        return True

    try:
        if api:
            e = chef.Environment(name, api=api)
            if desc is not None:
                e.description = desc
            if versions is not None:
                e.cookbook_versions = versions
            if default_attributes is not None:
                e.default_attributes = default_attributes
            if override_attributes is not None:
                e.override_attributes = override_attributes
            e.save()
        else:
            Manager.update_environment(name, deployment, desc=None,
                                       default_attributes=None,
                                       override_attributes=None)
        LOG.debug(
            "Chef Environment %s updated. Description set to %s "
            "Versions set to %s. Default attributes set to %s. Override "
            "attributes set to %s.", name, desc, versions,
            default_attributes, override_attributes)
        return True
    except chef.ChefError as exc:
        LOG.debug('Environment management failed. Chef Error: %s. Retrying.',
                  exc)
        manage_environment.retry(exc=exc)
    except Exception as exc:
        LOG.debug('Environment management failed. Error: %s. Retrying.', exc)
        manage_environment.retry(exc=exc)


@ctask.task(max_retries=3)
@statsd.collect
def create_kitchen(context, name, service_name, path=None,
                   private_key=None, public_key_ssh=None,
                   secret_key=None, source_repo=None,
                   server_credentials=None):
    """Create a folder with a configured knife.rb file on it.

    The kitchen is a directory structure that is self-contained and
    separate from other kitchens. It is used by this provider to run knife
    and berks commands.

    :param name: the name of the kitchen. This will be the directory name.
    :param path: an override to the root path where to create this kitchen
    :param private_key: PEM-formatted private key
    :param public_key_ssh: SSH-formatted public key
    :param secret_key: used for data bag encryption
    :param source_repo: provides cookbook repository in valid git syntax
    :param server_credentials: keys and info to connect to chef server
    """
    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        if len(exc.args) > 1:
            arg = exc.args[1]
        elif len(exc.args) > 0:
            arg = exc.args[0]
        else:
            arg = "No arguments supplied in exception"
        tasks.update_all_provider_resources.delay(
            Provider.name,
            context['deployment_id'],
            'ERROR',
            message=('Error creating chef kitchen: %s' % arg)
        )

    create_kitchen.on_failure = on_failure
    return Manager.create_kitchen(name, service_name, path=path,
                                  private_key=private_key,
                                  public_key_ssh=public_key_ssh,
                                  secret_key=secret_key,
                                  source_repo=source_repo,
                                  server_credentials=server_credentials,
                                  simulation=context['simulation'])


@ctask.task(max_retries=3)
@statsd.collect
def upload_cookbooks(context, deployment, environment):
    """Upload cookbooks using Berkshelf."""
    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        if len(exc.args) > 1:
            arg = exc.args[1]
        elif len(exc.args) > 0:
            arg = exc.args[0]
        else:
            arg = "No arguments supplied in exception"
        tasks.update_all_provider_resources.delay(
            Provider.name,
            context['deployment_id'],
            'ERROR',
            message=('Error uploading cookbooks: %s' % arg)
        )

    upload_cookbooks.on_failure = on_failure
    return Manager.upload(context, deployment, environment,
                          simulation=context['simulation'])


@ctask.task(base=ProviderTask, provider=Provider)
@statsd.collect
def delete_environment(context, deployment, name, api=None):

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        data = {
            'status': 'ERROR',
            'error-message': 'Error deleting environment'
        }
        delete_environment.partial(data)
    delete_environment.on_failure = on_failure

    if context.simulation:
        LOG.info("Would delete environment: %s", name)
        return True

    try:
        if api:
            e = chef.Environment(name, api=api)
            e.delete()
        else:
            Manager.delete_environment(name, deployment)
        LOG.info("Chef Environment %s deleted.", name)
        return True
    except chef.ChefError, exc:
        LOG.debug('Environment deletion failed. Chef Error: %s. Retrying.',
                  exc)
        delete_environment.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Environment deletion failed. Error: %s. Retrying.', exc)
        delete_environment.retry(exc=exc)


def create_role_recipe_string(roles=None, recipes=None):
    """Return roles and recipes in chef cook format."""
    recipe_string = ''
    if roles is not None:
        for role in roles:
            recipe_string += 'role[%s], ' % role
    if recipes is not None:
        for recipe in recipes:
            recipe_string += 'recipe[%s], ' % recipe
    # remove the trailing space and comma
    return recipe_string[:-2]
