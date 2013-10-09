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
import os
import subprocess

from celery.task import task
import chef

from checkmate.common import statsd

LOG = logging.getLogger(__name__)


@task
@statsd.collect
def register_node(deployment, name, runlist=None, attributes=None,
                  environment=None):
    '''Register node on chef server.'''
    try:
        api = chef.autoconfigure(
            base_path=os.environ.get('CHECKMATE_CHEF_PATH')
        )
        n = chef.Node(name, api=api)
        if runlist is not None:
            n.run_list = runlist
        if attributes is not None:
            n.normal = attributes
        if environment is not None:
            n.chef_environment = environment
        n.save()
        LOG.debug('Registered %s with Chef Server. Setting runlist to %s',
                  name, runlist)
    except chef.ChefError, exc:
        LOG.debug('Node registration failed. Chef Error: %s. Retrying.', exc)
        register_node.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Node registration failed. Error: %s. Retrying.', exc)
        register_node.retry(exc=exc)


@task
@statsd.collect
def bootstrap(
    deployment, name, ip, username='root', password=None, port=22,
    identity_file=None, run_roles=None, run_recipes=None,
    distro='chef-full', environment=None
):
    LOG.debug('Bootstraping %s (%s:%d)' % (name, ip, port))
    run_roles_recipes = create_role_recipe_string(roles=run_roles,
                                                  recipes=run_recipes)
    params = ['knife', 'bootstrap', ip, '-x', username, '-N', name]
    if identity_file:
        params.extend(['-i', identity_file])
    if distro:
        params.extend(['-d', distro])
    if run_roles_recipes:
        params.extend(['-r', run_roles_recipes])
    if password:
        params.extend(['-P', password])
    if port:
        params.extend(['-p', str(port)])
    if environment:
        params.extend(['-E', environment])

    path = os.environ.get('CHECKMATE_CHEF_PATH')
    if path:
        if os.path.exists(os.path.join(path, 'knife.rb')):
            params.extend(['-c', os.path.join(path, 'knife.rb')])

    LOG.debug('Running: %s', ' '.join(params))
    result = subprocess.check_output(params)
    if 'FATAL' in result:
        errors = [line for line in result.split('/n') if 'FATAL' in line]
        LOG.debug("Bootstrap errors: %s", '/n'.join(errors))
        raise subprocess.CalledProcessError('/n'.join(errors),
                                            ' '.join(params))
    return True


@task
@statsd.collect
def manage_databag(deployment, bagname, itemname, contents):
    try:
        api = chef.autoconfigure(
            base_path=os.environ.get('CHECKMATE_CHEF_PATH')
        )
        bag = chef.DataBag(bagname, api=api)
        bag.save()
        item = chef.DataBagItem(bag, itemname)
        for key, value in contents.iteritems():
            item[key] = value
        item.save()
        LOG.debug('Databag %s updated. Setting items to %s', bag, item)
    except chef.ChefError, exc:
        LOG.debug('Databag management failed. Chef Error: %s. Retrying.', exc)
        manage_databag.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Databag management failed. Error: %s. Retrying.', exc)
        manage_databag.retry(exc=exc)


@task
@statsd.collect
def manage_role(deployment, name, desc=None, run_list=None,
                default_attributes=None, override_attributes=None,
                env_run_lists=None):
    try:
        api = chef.autoconfigure(
            base_path=os.environ.get('CHECKMATE_CHEF_PATH')
        )
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
        LOG.debug(
            "Role %s updated. runlist set to %s. Default attributes set "
            "to %s. Override attributes set to %s. Environment run lists "
            "set to %s." % (
                name, run_list, default_attributes,
                override_attributes, env_run_lists
            )
        )
    except chef.ChefError, exc:
        LOG.debug(
            'Role management failed. Chef Error: %s. Retrying.' % exc)
        manage_role.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Role management failed. Error: %s. Retrying.' % exc)
        manage_role.retry(exc=exc)


@task
@statsd.collect
def manage_env(deployment, name, desc=None, versions=None,
               default_attributes=None, override_attributes=None):
    try:
        api = chef.autoconfigure(
            base_path=os.environ.get('CHECKMATE_CHEF_PATH')
        )
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
        LOG.debug(
            "Environment %s updated. Description set to %s "
            "Versions set to %s. Default attributes set to %s. Override "
            "attributes set to %s." % (
                name, desc, versions,
                default_attributes, override_attributes
            )
        )
        return True
    except chef.ChefError, exc:
        LOG.debug(
            'Environment management failed. Chef Error: %s. Retrying.' % exc)
        manage_env.retry(exc=exc)
    except Exception, exc:
        LOG.debug(
            'Environment management failed. Error: %s. Retrying.' % exc
        )
        manage_env.retry(exc=exc)


def create_role_recipe_string(roles=None, recipes=None):
    """Return roles and recipes in chef cook format."""
    recipe_string = ''
    if roles is not None:
        for role in roles:
            recipe_string += 'role[%recipe_string], ' % role
    if recipes is not None:
        for recipe in recipes:
            recipe_string += 'recipe[%recipe_string], ' % recipe
    # remove the trailing space and comma
    return recipe_string[:-2]
