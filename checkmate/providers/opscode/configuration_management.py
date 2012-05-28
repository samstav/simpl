import logging
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery, Merge, Transform

from checkmate.providers import ProviderBase
from checkmate.utils import get_source_body

LOG = logging.getLogger(__name__)


class LocalProvider(ProviderBase):
    """Implements a Chef Local/Solo configuration management provider"""
    def __init__(self, provider):
        ProviderBase.__init__(self, provider)
        self.prep_task = None

    def prep_environment(self, wfspec, deployment):
        create_environment = Celery(wfspec, 'Create Chef Environment',
                'stockton.cheflocal.distribute_create_environment',
                call_args=[deployment['id']],
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
        register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                       'stockton.cheflocal.distribute_register_node',
                       call_args=[Attrib('ip'), deployment['id']],
                       password=Attrib('password'),
                       defines={"Resource": key}, description="Install "
                               "Chef client on the server and register it in "
                               "the environment",
                       properties={'estimated_duration': 120})

        # Register only when server is up and environment is ready
        if wait_on:
            join = Merge(wfspec, "Check that Environment is Ready and Server "
                    "is Up:%s" % key)
            join.connect(register_node_task)
            self.prep_task.connect(join)
            for dependency in wait_on:
                dependency.connect(join)
            root = join
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
                properties={'estimated_duration': 100})
        # This join is assumed to exist by create_workflow
        join = Merge(wfspec, "Check on Registration and Overrides:%s" % key,
                description="Before applying chef recipes, we need to know "
                "that the server has chef on it and that the overrides "
                "(database settings) have been applied")
        join.connect(bootstrap_task)
        register_node_task.connect(join)
        # The connection to overrides will be done later (using the join)
        return {'root': root, 'final': bootstrap_task}


class ServerProvider(ProviderBase):
    """Implements a Chef Server configuration management provider"""
    def __init__(self, provider):
        super(ServerProvider, self).__init__(provider)
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
                        defines={"Resource": key}, description="Register the "
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
        join = Merge(wfspec, "Wait for Server Build:%s" % key)
        join.connect(bootstrap_task)
        ssh_apt_get_task.connect(join)
        register_node_task.connect(join)
        return {'root': register_node_task, 'final': bootstrap_task}
