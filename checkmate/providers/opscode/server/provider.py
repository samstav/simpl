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
"""Implements a Chef Server configuration management provider."""
import logging

from SpiffWorkflow import operators
from SpiffWorkflow import specs

from checkmate.providers import ProviderBase

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    """Implements a Chef Server configuration management provider."""
    name = 'chef-server'
    vendor = 'opscode'

    def provides(self, resource_type=None, interface=None):
        return [dict(application='http'), dict(database='mysql')]

    def prep_environment(self, wfspec, deployment, context):
        ProviderBase.prep_environment(self, wfspec, deployment, context)
        create_environment = specs.Celery(
            wfspec,
            'Create Chef Environment',
            'checkmate.providers.opscode.server.tasks.manage_env',
            call_args=[
                operators.Attrib('context'),
                deployment['id'],
                'Checkmate Environment'
            ],
            properties={'estimated_duration': 10}
        )
        self.prep_task = create_environment
        return {'root': self.prep_task, 'final': self.prep_task}

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        register_node_task = specs.Celery(
            wfspec,
            'Register Server:%s (%s)' % (key, resource['service']),
            'checkmate.providers.opscode.server.tasks.register_node',
            call_args=[
                operators.Attrib('context'),
                resource.get('dns-name'),
                ['wordpress-web']
            ],
            environment=deployment['id'],
            defines=dict(resource=key, provider=self.key),
            description="Register the node in the Chef Server. "
                        "Nothing is done the node itself",
            properties={'estimated_duration': 20}
        )
        self.prep_task.connect(register_node_task)

        ssh_apt_get_task = specs.Celery(
            wfspec,
            'Apt-get Fix:%s (%s)' % (key, resource['service']),
            'checkmate.ssh.execute',
            call_args=[
                operators.Attrib('ip'),
                "sudo apt-get update",
                'root'
            ],
            password=operators.Attrib('password'),
            identity_file=operators.Attrib('private_key_path'),
            properties={'estimated_duration': 100}
        )
        # TODO: stop assuming only one wait_on=create_server_task
        wait_on[0].connect(ssh_apt_get_task)

        bootstrap_task = specs.Celery(
            wfspec,
            'Bootstrap Server:%s (%s)' % (key, resource['service']),
            'checkmate.providers.opscode.server.tasks.bootstrap',
            call_args=[
                operators.Attrib('context'),
                resource.get('dns-name'),
                operators.Attrib('ip')
            ],
            password=operators.Attrib('password'),
            identity_file=operators.Attrib('private_key_path'),
            run_roles=['build', 'wordpress-web'],
            environment=deployment['id'],
            properties={'estimated_duration': 90}
        )
        wfspec.wait_for(bootstrap_task,
                        [ssh_apt_get_task, register_node_task],
                        name="Wait for Server Build:%s (%s)" % (
                            key, resource['service']))
        return {'root': register_node_task, 'final': bootstrap_task}

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment):
        target = deployment['resources'][relation['target']]
        interface = relation['interface']

        if interface == 'mysql':
            #Take output from Create DB task and write it into
            # the 'override' dict to be available to future tasks

            db_final = self.find_resource_task(wfspec, relation['target'],
                                               target['provider'], 'final')

            compile_override = specs.Transform(
                wfspec,
                "Prepare Overrides",
                transforms=[
                    "my_task.attributes['overrides']={'wordpress': {'db': "
                    "{'host': my_task.attributes['hostname'], "
                    "'database': my_task.attributes['context']['db_name'], "
                    "'user': my_task.attributes['context']['db_username'], "
                    "'password': my_task.attributes['context']"
                    "['db_password']}}}"
                ],
                description="Get all the variables we need (like database "
                            "name and password) and compile them into JSON "
                            "that we can set on the role or environment",
                defines=dict(
                    relation=relation_key, provider=self.key, task_tags=None
                )
            )
            db_final.connect(compile_override)

            set_overrides = specs.Celery(
                wfspec,
                "Write Database Settings",
                'checkmate.providers.opscode.server.tasks.manage_env',
                call_args=[operators.Attrib('context'), deployment['id']],
                desc='Checkmate Environment',
                override_attributes=operators.Attrib('overrides'),
                description="Take the JSON prepared earlier and write it into"
                            "the environment overrides. It will be used by "
                            "the Chef recipe to connect to the database",
                defines=dict(
                    relation=relation_key, resource=key,
                    provider=self.key, task_tags=None
                ),
                properties={'estimated_duration': 15}
            )

            wait_on = [compile_override, self.prep_task]
            wfspec.wait_for(
                set_overrides, wait_on,
                name="Wait on Environment and Settings:%s" % key
            )

            config_final = self.find_resource_task(wfspec, key, self.key,
                                                   'final')
            # Assuming input is join
            assert isinstance(config_final.inputs[0], specs.Merge)
            set_overrides.connect(config_final.inputs[0])

        else:
            LOG.warning(
                "Provider '%s' does not recognized connection interface '%s'",
                self.key, interface
            )
