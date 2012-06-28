import logging

from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery, Merge, Transform

from checkmate.exceptions import CheckmateException
from checkmate.providers import ProviderBase, register_providers
from checkmate.utils import get_source_body
from checkmate.workflows import wait_for

LOG = logging.getLogger(__name__)


class LocalProvider(ProviderBase):
    name = 'chef-local'
    vendor = 'opscode'

    """Implements a Chef Local/Solo configuration management provider"""
    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
        self.prep_task = None

    def prep_environment(self, wfspec, deployment):
        if self.prep_task is not None:
            return  # already prepped
        create_environment = Celery(wfspec, 'Create Chef Environment',
                'stockton.cheflocal.distribute_create_environment',
                call_args=[deployment['id']],
                defines=dict(provider=self.key,
                            task_tags=['root']),
                properties={'estimated_duration': 10})

        def get_keys_code(my_task):
            my_task.attributes['context']['keys']['environment'] =\
                    {'public_key': my_task.attributes['public_key'],
                     'public_key_path': my_task.attributes['public_key_path']}

        write_key = Transform(wfspec, "Get Environment Key",
                transforms=[get_source_body(get_keys_code)],
                description="Add environment public key data to context so "
                        "providers have access to them")
        create_environment.connect(write_key)
        self.prep_task = write_key

        return {'root': create_environment, 'final': write_key}

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        if wait_on is None:
            wait_on = []
        self.add_wait_on_host_tasks(resource, wfspec, deployment, wait_on)

        # Add tasks
        register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                'stockton.cheflocal.distribute_register_node',
                call_args=[Attrib('ip'), deployment['id']],
                password=Attrib('password'),
                omnibus_version="0.10.10-1",
                defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['root']),
                description="Install Chef client on the target machine and "
                       "register it in the environment",
                properties={'estimated_duration': 120})

        # Register only when server is up and environment is ready
        if wait_on:
            tasks = wait_on[:]
            tasks.append(self.prep_task)
            root = wait_for(wfspec, register_node_task, tasks, name="Check "
                    "that Environment is Ready and Server is Up:%s" % key)
        else:
            self.prep_task.connect(register_node_task)
            root = register_node_task

        bootstrap_task = Celery(wfspec, 'Configure Server:%s' % key,
               'stockton.cheflocal.distribute_cook',
                call_args=[Attrib('ip'), deployment['id']],
                roles=['build-ks', 'wordpress-web'],
                password=Attrib('password'),
                identity_file=Attrib('private_key_path'),
                description="Push and apply Chef recipes on the server",
                defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['final']),
                properties={'estimated_duration': 100})
        # Note: This join is assumed to exist by create_workflow
        wait_for(wfspec, bootstrap_task, [register_node_task, write_bag],
                name="Check on Registration and Overrides:%s" % key,
                description="Before applying chef recipes, we need to know "
                "that the server has chef on it and that the overrides "
                "(database settings) have been applied")

        # The connection to overrides will be done later (using the join)
        return dict(root=root, final=bootstrap_task)

    def add_connection_tasks(self, resource, key, relation, relation_key,
            wfspec, deployment):
        target = deployment['resources'][relation['target']]
        interface = relation['interface']

        if interface == 'mysql':
            #Take output from Create DB task and write it into
            # the 'override' dict to be available to future tasks

            db_final = self.find_tasks(wfspec, provider=target['provider'],
                    tag='final')
            if not db_final:
                raise CheckmateException("Database creation task not found")
            if len(db_final) > 1:
                raise CheckmateException("Multiple database creation tasks "
                        "found")
            db_final = db_final[0]

            def compile_override_code(my_task):
                my_task.attributes['overrides'] = {'wordpress': {'db':
                    {'host': my_task.attributes['hostname'],
                    'database': my_task.attributes['context']['db_name'],
                    'user': my_task.attributes['context']['db_username'],
                    'password': my_task.attributes['context']
                    ['db_password']}}}

            compile_override = Transform(wfspec, "Prepare Overrides",
                    transforms=[get_source_body(compile_override_code)],
                    description="Get all the variables "
                            "we need (like database name and password) and "
                            "compile them into JSON that we can set on the "
                            "role or environment",
                    defines=dict(relation=relation_key,
                                provider=self.key,
                                task_tags=None))
            db_final.connect(compile_override)

            set_overrides = Celery(wfspec, 'Write Database Settings',
                    'stockton.cheflocal.distribute_manage_role',
                    call_args=['wordpress-web', deployment['id']],
                    override_attributes=Attrib('overrides'),
                    description="Take the JSON prepared earlier and write "
                            "it into the wordpress role. It will be used "
                            "by the Chef recipe to connect to the DB",
                    defines=dict(relation=relation_key,
                                resource=key,
                                provider=self.key,
                                task_tags=None),
                    properties={'estimated_duration': 10})
            wait_on = [compile_override, self.prep_task]
            wait_for(wfspec, set_overrides, wait_on,
                    name="Wait on Environment and Settings:%s" % key)

            config_final = self.find_tasks(wfspec, resource=key,
                    provider=self.key, tag='final')[0]
            # Assuming input is join
            assert isinstance(config_final.inputs[0], Merge)
            set_overrides.connect(config_final.inputs[0])
        elif relation.get('relation') == 'host':
            pass
        else:
            LOG.warning("Provider '%s' does not recognized connection "
                    "interface '%s'" % (self.key, interface))

    def get_catalog(self, context, type_filter=None):
        #TODO: remove hard-coding
        results = {}
        if type_filter is None or type_filter == 'application':
            results = {'application': {
                    'apache2': {
                        'name': 'apache',
                        },
                    'mysql': {
                        'name': 'mysql',
                        },
                    'php5': {
                        'name': 'php5',
                        },
                    }}

        return results


class ServerProvider(ProviderBase):
    name = 'chef-server'
    vendor = 'opscode'

    """Implements a Chef Server configuration management provider"""
    def __init__(self, provider, key=None):
        super(ServerProvider, self).__init__(provider, key=key)
        self.prep_task = None

    def prep_environment(self, wfspec, deployment):
        create_environment = Celery(wfspec, 'Create Chef Environment',
                'stockton.chefserver.distribute_manage_env',
                call_args=[Attrib('context'), deployment['id'],
                        'CheckMate Environment'],
                properties={'estimated_duration': 10})
        self.prep_task = create_environment
        return {'root': self.prep_task, 'final': self.prep_task}

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                        'stockton.chefserver.distribute_register_node',
                        call_args=[Attrib('context'),
                               resource.get('dns-name'), ['wordpress-web']],
                        environment=deployment['id'],
                        defines=dict(resource=key, provider=self.key),
                        description="Register the "
                                "node in the Chef Server. Nothing is done "
                                "the node itself",
                        properties={'estimated_duration': 20})
        self.prep_task.connect(register_node_task)

        ssh_apt_get_task = Celery(wfspec, 'Apt-get Fix:%s' % key,
                           'stockton.ssh.ssh_execute',
                            call_args=[Attrib('ip'),
                                    "sudo apt-get update",
                                    'root'],
                            password=Attrib('password'),
                            identity_file=Attrib('private_key_path'),
                            properties={'estimated_duration': 100})
        # TODO: stop assuming only one wait_on=create_server_task
        wait_on[0].connect(ssh_apt_get_task)

        bootstrap_task = Celery(wfspec, 'Bootstrap Server:%s' % key,
                           'stockton.chefserver.distribute_bootstrap',
                            call_args=[Attrib('context'),
                                    resource.get('dns-name'), Attrib('ip')],
                            password=Attrib('password'),
                            identity_file=Attrib('private_key_path'),
                            run_roles=['build', 'wordpress-web'],
                            environment=deployment['id'],
                            properties={'estimated_duration': 90})
        wait_for(wfspec, bootstrap_task,
                [ssh_apt_get_task, register_node_task],
                name="Wait for Server Build:%s" % key)
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

            compile_override = Transform(wfspec, "Prepare Overrides",
                    transforms=[
                    "my_task.attributes['overrides']={'wordpress': {'db': "
                    "{'host': my_task.attributes['hostname'], "
                    "'database': my_task.attributes['context']['db_name'], "
                    "'user': my_task.attributes['context']['db_username'], "
                    "'password': my_task.attributes['context']"
                    "['db_password']}}}"],
                    description="Get all the variables "
                            "we need (like database name and password) and "
                            "compile them into JSON that we can set on the "
                            "role or environment",
                    defines=dict(relation=relation_key,
                                provider=self.key,
                                task_tags=None))
            db_final.connect(compile_override)

            set_overrides = Celery(wfspec,
                "Write Database Settings",
                'stockton.chefserver.distribute_manage_env',
                call_args=[Attrib('context'), deployment['id']],
                    desc='CheckMate Environment',
                    override_attributes=Attrib('overrides'),
                description="Take the JSON prepared earlier and write "
                        "it into the environment overrides. It will "
                        "be used by the Chef recipe to connect to "
                        "the database",
                defines=dict(relation=relation_key,
                            resource=key,
                            provider=self.key,
                            task_tags=None),
                properties={'estimated_duration': 15})

            wait_on = [compile_override, self.prep_task]
            wait_for(wfspec, set_overrides, wait_on,
                    name="Wait on Environment and Settings:%s" % key)

            config_final = self.find_resource_task(wfspec, key, self.key,
                    'final')
            # Assuming input is join
            assert isinstance(config_final.inputs[0], Merge)
            set_overrides.connect(config_final.inputs[0])

        else:
            LOG.warning("Provider '%s' does not recognized connection "
                    "interface '%s'" % (self.key, interface),
                    defines=dict(relation=relation_key,
                                provider=self.key,
                                task_tags=None))


register_providers([ServerProvider, LocalProvider])
