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

"""
Module for interfacing with Rackspace Cloud Files provider.
"""
import logging

from celery import task
import cloudfiles

from checkmate.common import statsd
from checkmate import exceptions
from checkmate import middleware
from checkmate.providers import base
from checkmate import utils

LOG = logging.getLogger(__name__)


class Provider(base.ProviderBase):
    """Provider class for Rackspace Cloud Files."""
    name = 'files'
    vendor = 'rackspace'


def connect(context):
    """Returns CF api object."""

    if isinstance(context, dict):
        context = middleware.RequestContext(**context)
    if not context.auth_token:
        raise exceptions.CheckmateNoTokenError()
    try:
        api = cloudfiles.get_connection(
            context.username, context.apikey, timeout=15
        )
    except cloudfiles.errors.AuthenticationFailed:
        LOG.error('Cloud Files authentication failed.')
        raise
    except cloudfiles.errors.AuthenticationError:
        LOG.error('Cloud Files authentication error.')
        raise
    except StandardError as exc:
        LOG.error('Error connecting to Cloud Files: %s', exc)
        raise

    return api


#
# Celery tasks
#
@task.task
@statsd.collect
def create_container(context, deployment, name, api=None):
    """Creates a new container"""
    utils.match_celery_logging(LOG)
    if api is None:
        api = connect(context)
    try:
        meta = deployment.get("metadata", None)
        if meta:
            new_meta = {}
            for key in meta:
                new_meta["x-container-meta-"+key] = meta[key]
                api.create_container(name, metadata=new_meta)
        else:
            api.create_container(name)
        LOG.debug('Created container %s.', name)
    except cloudfiles.errors.InvalidContainerName:
        LOG.error('Invalid container name: %s', name)
        raise
    except cloudfiles.errors.ContainerExists:
        LOG.error('Container %s already exists.', name)
        raise


@task.task
@statsd.collect
def delete_container(deployment, name, api=None):
    """Deletes a container"""
    utils.match_celery_logging(LOG)
    if api is None:
        api = connect(deployment)

    try:
        api.delete_container(name)
        LOG.debug('Deleted container %s.', name)
    except cloudfiles.errors.ContainerNotEmpty:
        LOG.error('Cannot delete container %s because it is not empty.', name)
        raise
    except cloudfiles.errors.NoSuchContainer:
        LOG.error('Canot delete container %s because it does not exist.', name)
        raise
