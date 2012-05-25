import logging
import os
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery, Merge

from checkmate.providers import ProviderBase


LOG = logging.getLogger(__name__)


class LocalProvider(ProviderBase):
    """Implements a Chef Local/Solo configuration management provider"""
    def __init__(self, provider):
        ProviderBase.__init__(self, provider)
        self.prep_task = None

    def prep_environment(self, wfspec, deployment):
        create_environment = Celery(wfspec, 'Create Chef Environment',
                'stockton.cheflocal.distribute_create_environment',
                call_args=[deployment['id']])
        self.prep_task = create_environment
        return create_environment

    def add_resource_tasks(self, resource, key, wfspec, deployment,
            stockton_deployment, wait_on=None):
        register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                       'stockton.cheflocal.distribute_register_node',
                       call_args=[Attrib('ip'), deployment['id']],
                       password=Attrib('password'),
                       defines={"Resource": key})

        # Register only when server is up and environment is ready
        if wait_on:
            join = Merge(wfspec, "Wait for Server Build:%s" % key)
            join.connect(register_node_task)
            self.prep_task.connect(join)
            for dependency in wait_on:
                dependency.connect(join)
        else:
            self.prep_task.connect(join)

        bootstrap_task = Celery(wfspec, 'Configure Server:%s' % key,
               'stockton.cheflocal.distribute_cook',
                call_args=[Attrib('ip'), deployment['id']],
                roles=['build-ks', 'wordpress-web'],
                password=Attrib('password'),
                identity_file=os.environ.get(
                    'CHECKMATE_PRIVATE_KEY',
                    '~/.ssh/id_rsa'))
        join = Merge(wfspec, "Wait on Server and Settings:%s" % key)
        join.connect(bootstrap_task)
        register_node_task.connect(join)
        return bootstrap_task


class ServerProvider(ProviderBase):
    """Implements a Chef Server configuration management provider"""
    def __init__(self, provider):
        super(ServerProvider, self).__init__(provider)
        self.prep_task = None

    def prep_environment(self, wfspec, deployment):
        create_environment = Celery(wfspec, 'Create Chef Environment',
                'stockton.chefserver.distribute_manage_env',
                call_args=[Attrib('deployment'), deployment['id'],
                'CheckMate Environment'])
        self.prep_task = create_environment
        return create_environment

    def add_resource_tasks(self, resource, key, wfspec, deployment,
            stockton_deployment, wait_on=None):
        register_node_task = Celery(wfspec, 'Register Server:%s' % key,
                        'stockton.chefserver.distribute_register_node',
                        call_args=[Attrib('deployment'),
                               resource.get('dns-name'), ['wordpress-web']],
                        environment=deployment['id'],
                        defines={"Resource": key})
        self.prep_task.connect(register_node_task)

        ssh_apt_get_task = Celery(wfspec, 'Apt-get Fix:%s' % key,
                           'stockton.ssh.ssh_execute',
                            call_args=[Attrib('ip'),
                                    "sudo apt-get update",
                                    'root'],
                            password=Attrib('password'),
                            identity_file=os.environ.get(
                                    'CHECKMATE_PRIVATE_KEY',
                                    '~/.ssh/id_rsa'))
        # TODO: stop assuming only one wait_on=create_server_task
        wait_on[0].connect(ssh_apt_get_task)

        bootstrap_task = Celery(wfspec, 'Bootstrap Server:%s' % key,
                           'stockton.chefserver.distribute_bootstrap',
                            call_args=[Attrib('deployment'),
                                    resource.get('dns-name'), Attrib('ip')],
                            password=Attrib('password'),
                            identity_file=os.environ.get(
                                    'CHECKMATE_PRIVATE_KEY',
                                    '~/.ssh/id_rsa'),
                            run_roles=['build', 'wordpress-web'],
                            environment=deployment['id'])
        join = Merge(wfspec, "Wait for Server Build:%s" % key)
        join.connect(bootstrap_task)
        ssh_apt_get_task.connect(join)
        register_node_task.connect(join)
        return join
