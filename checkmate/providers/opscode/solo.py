"""Chef Solo configuration management provider"""
import logging

from SpiffWorkflow.operators import Attrib, PathAttrib
from SpiffWorkflow.specs import Celery, Transform, Merge

from checkmate.keys import hash_SHA512
from checkmate.providers import ProviderBase

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    """Implements a Chef Solo configuration management provider"""
    name = 'chef-solo'
    vendor = 'opscode'

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
        self.prep_task = None
        self.collect_data_task = None

    def prep_environment(self, wfspec, deployment, context):
        if self.prep_task:
            return  # already prepped
        self._hash_all_user_resource_passwords(deployment)

        # Create Celery Task
        settings = deployment.settings()
        keys = settings.get('keys', {})
        deployment_keys = keys.get('deployment', {})
        public_key_ssh = deployment_keys.get('public_key_ssh')
        private_key = deployment_keys.get('private_key')
        secret_key = deployment.get_setting('secret_key')
        source_repo = deployment.get_setting('source', provider_key=self.key)
        defines = {'provider': self.key, 'task_tags': ['root']}
        properties = {'estimated_duration': 10}
        task_name = 'checkmate.providers.opscode.local.create_environment'
        create_environment_task = Celery(wfspec,
                                         'Create Chef Environment',
                                         task_name,
                                         call_args=[deployment['id'],
                                                    'kitchen'],
                                         public_key_ssh=public_key_ssh,
                                         private_key=private_key,
                                         secret_key=secret_key,
                                         source_repo=source_repo,
                                         defines=defines,
                                         properties=properties)

        #FIXME: use a map file
        # Call manage_databag(environment, bagname, itemname, contents)
        write_options = Celery(wfspec,
                "Write Data Bag",
               'checkmate.providers.opscode.local.manage_databag',
                call_args=[deployment['id'], deployment['id'],
                        Attrib('app_id'), Attrib('chef_options')],
                kitchen_name="kitchen",
                secret_file='certificates/chef.pem',
                merge=True,
                defines=dict(provider=self.key),
                properties={'estimated_duration': 5})

        collect = Merge(wfspec,
                        "Collect Chef Data",
                        defines={'provider': self.key, 'extend_lists': True})
        # Make sure the environment exists before writing options.
        collect.follow(create_environment_task)
        write_options.follow(collect)
        # Any tasks that need to be collected will wire themselves into
        # this task
        self.collect_data_task = dict(root=collect, final=write_options)
        self.prep_task = create_environment_task
        return {'root': create_environment_task, 'final': write_options}

    def _hash_all_user_resource_passwords(self, deployment):
        """Chef needs all passwords to be a hash"""
        if 'resources' in deployment:
            for resource in deployment['resources'].values():
                if resource.get('type') == 'user':
                    instance = resource.get('instance', {})
                    if 'password' in instance:
                        instance['hash'] = hash_SHA512(instance['password'])


