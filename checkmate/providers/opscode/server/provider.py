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
import yaml
from yaml.composer import ComposerError
from yaml.parser import ParserError
from yaml.scanner import ScannerError

from checkmate.common import schema
from checkmate import exceptions
from checkmate.providers import ProviderBase
from checkmate.providers.opscode import solo
from checkmate.providers.opscode.chef_map import ChefMap


LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    """Implements a Chef Server configuration management provider."""
    name = 'chef-server'
    vendor = 'opscode'

    __status_mapping__ = {
        'ACTIVE': 'ACTIVE',
        'BUILD': 'BUILD',
        'DELETED': 'DELETED',
        'ERROR': 'ERROR',
        'CONFIGURE': 'CONFIGURE',
    }

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)

        # Map File
        self.source = self.get_setting('source')
        if self.source:
            self.map_file = ChefMap(url=self.source)
        else:
            # Create noop map file
            self.map_file = ChefMap(raw="")

    def prep_environment(self, wfspec, deployment, context):
        ProviderBase.prep_environment(self, wfspec, deployment, context)
        if self.prep_task:
            return  # already prepped
        create_environment = specs.Celery(
            wfspec,
            'Create Chef Environment',
            'checkmate.providers.opscode.server.tasks.manage_env',
            call_args=[
                operators.Attrib('context'),
                deployment['id'],
                'Checkmate Environment'
            ],
            defines=dict(resource='workspace', provider=self.key),
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
            defines=dict(resource=key, provider=self.key),
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
            defines=dict(resource=key, provider=self.key),
            properties={'estimated_duration': 90}
        )
        wfspec.wait_for(bootstrap_task,
                        [ssh_apt_get_task, register_node_task],
                        name="Wait for Server Build:%s (%s)" % (
                            key, resource['service']))
        return {'root': register_node_task, 'final': bootstrap_task}

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        target = deployment['resources'][relation['target']]
        interface = relation['interface']

        if interface == 'mysql':
            #Take output from Create DB task and write it into
            # the 'override' dict to be available to future tasks

            db_final = wfspec.find_task_specs(relation=relation['target'],
                                              provider=target['provider'],
                                              tag='final')

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

            config_final = wfspec.find_task_specs(relation=key,
                                                  provider=self.key,
                                                  tag='final')
            # Assuming input is join
            assert isinstance(config_final.inputs[0], specs.Merge)
            set_overrides.connect(config_final.inputs[0])

        else:
            LOG.warning(
                "Provider '%s' does not recognized connection interface '%s'",
                self.key, interface
            )

    def get_catalog(self, context, type_filter=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one.

        NOTE: copied in chef-server Provider
        """
        # TODO(zns): maybe implement this an on_get_catalog so we don't have to
        #        do this for every provider
        results = ProviderBase.get_catalog(self, context,
                                           type_filter=type_filter)
        if results:
            # We have a prexisting or injected catalog stored. Use it.
            return results

        if self.source:
            # Get remote catalog
            catalog = self.get_remote_catalog()

            # Validate and cache catalog
            self.validate_catalog(catalog)
            if type_filter is None:
                self._dict['catalog'] = catalog
            return catalog

    def get_remote_catalog(self, source=None):
        """Get the remote catalog from a repo by obtaining a Chefmap file, if
        it exists, and parsing it.

        NOTE: copied in chef-server Provider
        """
        if source:
            map_file = ChefMap(url=source)
        else:
            map_file = self.map_file
        catalog = {}
        try:
            for doc in yaml.safe_load_all(map_file.parsed):
                if 'id' in doc:
                    for key in doc.keys():
                        if key not in schema.COMPONENT_SCHEMA:
                            del doc[key]
                    resource_type = doc.get('is', 'application')
                    if resource_type not in catalog:
                        catalog[resource_type] = {}
                    catalog[resource_type][doc['id']] = doc
            LOG.debug('Obtained remote catalog from %s', map_file.url)
        except ValueError:
            msg = 'Catalog source did not return parsable content'
            raise exceptions.CheckmateException(msg)
        except (ParserError, ScannerError) as exc:
            raise exceptions.CheckmateValidationException(
                "Invalid YAML syntax in Chefmap. Check:\n%s" % exc)
        except ComposerError as exc:
            raise exceptions.CheckmateValidationException(
                "Invalid YAML structure in Chefmap. Check:\n%s" % exc)
        return catalog
