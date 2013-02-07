"""Chef Solo configuration management provider

Sample:

environment:
  name: Rackspace Open Cloud
  providers:
    script:
      vendor: core
      constraints:
      - source: '%repo_url%'
      - script: |
          apt-get update
          apt-get install -y git
          git clone git://github.com/openstack-dev/devstack.git
          cd devstack
          echo 'DATABASE_PASSWORD=simple' > localrc
          echo 'RABBIT_PASSWORD=simple' >> localrc
          echo 'SERVICE_TOKEN=1111' >> localrc
          echo 'SERVICE_PASSWORD=simple' >> localrc
          echo 'ADMIN_PASSWORD=simple' >> localrc
          ./stack.sh > stack.out
      catalog:
        application:
          openstack:
            provides:
            - application: http
            requires:
            - host: linux


"""
import copy
import httplib
import json
import logging
import os
import urlparse

from celery import task
from jinja2 import DictLoader, TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment
from SpiffWorkflow.operators import Attrib, PathAttrib
from SpiffWorkflow.specs import Celery, TransMerge

from checkmate import utils
from checkmate.common import schema
from checkmate.exceptions import (CheckmateException,
                                  CheckmateValidationException)
from checkmate.providers import ProviderBase
from checkmate.workflows import wait_for
from checkmate.utils import match_celery_logging, yaml_to_dict

LOG = logging.getLogger(__name__)


def register_scheme(scheme):
    '''
    Use this to register a new scheme with urlparse and have it be
    parsed in the same way as http is parsed
    '''
    for method in filter(lambda s: s.startswith('uses_'), dir(urlparse)):
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly


class Provider(ProviderBase):
    """Implements a script configuration management provider"""
    name = 'script'
    vendor = 'core'

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
        self.prep_task = None

    def prep_environment(self, wfspec, deployment, context):
        if self.prep_task:
            return  # already prepped
        pass

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        """Create and write settings, generate run_list, and call cook"""
        wait_on, service_name, component = self._add_resource_tasks_helper(
                resource, key, wfspec, deployment, context, wait_on)
        service_name = resource.get('service')
        resource_type = resource.get('type')
        script_source = deployment.get_setting('script',
                                               resource_type=resource_type,
                                               service_name=service_name,
                                               provider_key=self.key)
        task_name = 'Execute Script %s (%s)' % (key, resource['hosted_on'])
        host_ip_path = "instance:%s/public_ip" % resource['hosted_on']
        password_path = 'instance:%s/password' % resource['hosted_on']
        private_key = deployment.settings().get('keys', {}).get(
                                    'deployment', {}).get('private_key')
        execute_task = Celery(wfspec,
                             task_name,
                            'checkmate.ssh.execute',
                            call_args=[PathAttrib(host_ip_path),
                                       script_source,
                                       "root"],
                            password=PathAttrib(password_path),
                            private_key=private_key,
                            properties={'estimated_duration': 600,
                                        'task_tags': ['final']},
                            defines={'resource': key, 'provider': self.key}
                            )

        if wait_on is None:
            wait_on = []
        if getattr(self, 'prep_task', None):
            wait_on.append(self.prep_task)
        join = wait_for(wfspec, execute_task, wait_on,
                name="Server %s (%s) Wait on Prerequisites" % (key,
                     resource['service']),
                properties={'task_tags': ['root']},
                defines=dict(resource=key,
                             provider=self.key))

        return dict(root=join or execute_task, final=execute_task)

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        """Write out or Transform data. Provide final task for relation sources
        to hook into"""
        LOG.debug("Adding connection task for resource '%s' for relation '%s'"
                  % (key, relation_key), extra={'data': {'resource': resource,
                  'relation': relation}})

    def get_catalog(self, context, type_filter=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one"""

        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #        this for every provider
        results = ProviderBase.get_catalog(self, context,
                                           type_filter=type_filter)
        return results
