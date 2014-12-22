# Copyright (c) 2011-2013 Rackspace Hosting
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

"""Simple Script Provider."""

import logging


from SpiffWorkflow import operators
from SpiffWorkflow.specs import Celery

from checkmate.providers import base
from checkmate.providers.core.script import manager
from checkmate import ssh

LOG = logging.getLogger(__name__)


class Provider(base.ProviderBase):

    """Implements a script configuration management provider."""

    name = 'script'
    vendor = 'core'

    __status_mapping__ = {
        'ACTIVE': 'ACTIVE',
        'DELETED': 'DELETED',
        'ERROR': 'ERROR',
    }

    def prep_environment(self, wfspec, deployment, context):
        base.ProviderBase.prep_environment(self, wfspec, deployment,
                                                     context)
        if self.prep_task:
            return  # already prepped
        results = {}
        source_repo = deployment.get_setting('source', provider_key=self.key)
        if source_repo:
            defines = {'provider': self.key}
            properties = {'estimated_duration': 10, 'task_tags': ['root']}
            task_name = 'checkmate.deployments.workspaces.create_workspace'
            queued_task_dict = context.get_queued_task_dict(
                deployment_id=deployment['id'])
            self.prep_task = Celery(wfspec,
                                    'Create Workspace',
                                    task_name,
                                    call_args=[queued_task_dict,
                                               deployment['id']],
                                    source_repo=source_repo,
                                    defines=defines,
                                    properties=properties)
            results = {'root': self.prep_task, 'final': self.prep_task}

        return results

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        """Create and write settings, generate run_list, and call cook."""
        wait_on, _, component = self._add_resource_tasks_helper(
            resource, key, wfspec, deployment, context, wait_on)
        properties = component.get('properties') or {}
        scripts = properties.get('scripts') or {}
        install_script = scripts.get('install')
        if not install_script:
            return dict(root=None, final=None)
        elif isinstance(install_script, basestring):
            script_object = manager.Script({'body': install_script})
        else:
            script_object = manager.Script(install_script)
            kwargs = self.get_context_parameters(deployment=deployment,
                                                 resource=resource,
                                                 component=component)
            kwargs['inputs'] = deployment.get('inputs') or {}
            kwargs['blueprint'] = blueprint = deployment.get('blueprint') or {}
            kwargs['options'] = blueprint.get('options') or {}
            kwargs['services'] = blueprint.get('services') or {}
            kwargs['resources'] = deployment.get('resources') or {}

            params = script_object.evaluate_parameters(**kwargs)
            script_object.parameters = params

        timeout = deployment.get_setting('timeout', provider_key=self.key,
                                         default=300)
        host_id = resource['hosted_on']
        task_name = 'Execute Script %s (%s)' % (key, host_id)
        host_ip_path = "resources/%s/instance/public_ip" % host_id
        password_path = 'resources/%s/instance/password' % host_id
        desired_state = deployment['resources'][host_id].get('desired-state')
        host_os = desired_state.get('os-type') or 'linux'
        LOG.info('Script provider: os-type is %s', host_os)
        private_key = deployment.settings().get('keys', {}).get(
            'deployment', {}).get('private_key')
        queued_task_dict = context.get_queued_task_dict(
            resource_key=key, deployment_id=deployment['id'])

        execute_task = Celery(
            wfspec,
            task_name,
            'checkmate.providers.core.script.tasks.create_resource',
            call_args=[queued_task_dict,
                       deployment['id'],
                       resource,
                       operators.PathAttrib(host_ip_path),
                       "root"],
            password=operators.PathAttrib(password_path),
            private_key=private_key,
            install_script=script_object.body,
            host_os=host_os,
            timeout=timeout,
            properties={
                'estimated_duration': timeout,
                'task_tags': ['final'],
            },
            defines={'resource': key, 'provider': self.key}
        )

        if wait_on is None:
            wait_on = []
        if getattr(self, 'prep_task', None):
            wait_on.append(self.prep_task)
        join = wfspec.wait_for(execute_task, wait_on,
                               name="Server %s (%s) Wait on Prerequisites" %
                               (key, resource['service']),
                               properties={'task_tags': ['root']},
                               defines=dict(resource=key,
                                            provider=self.key))

        return dict(root=join or execute_task, final=execute_task)

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        """Generate tasks for a connection."""
        LOG.debug("Adding connection task for resource '%s' for relation '%s'",
                  key, relation_key, extra={'data': {'resource': resource,
                                                     'relation': relation}})

    @staticmethod
    def connect(context):
        """Returns API connection object for remote calls.

        :param context: the call context from checkmate
        :param *args: just there to handle region which leaked out of
            rackspace providers
        """
        # TODO(zns): remove region (i.e. *args)
        return ssh

    def get_context_parameters(self, **kwargs):
        """Get settings.

        Includes the real data in the context.
        """
        # Add defaults if there is a component and no defaults specified
        if kwargs and 'defaults' not in kwargs and 'component' in kwargs:
            component = kwargs['component']
            # used by setting() in Jinja context to return defaults
            defaults = {}
            for key, option in component.get('options', {}).iteritems():
                if 'default' in option:
                    default = option['default']
                    try:
                        if default.startswith('=generate'):
                            default = self.evaluate(default[1:])
                    except AttributeError:
                        pass  # default probably not a string type
                    defaults[key] = default
            kwargs['defaults'] = defaults
        return kwargs
