'''Script configuration management provider

Sample:

environment:
  name: Rackspace Open Cloud
  providers:
    script:
      vendor: core
      catalog:
        application:
          openstack:
            provides:
            - application: http
            requires:
            - host: linux
            dependencies:
              script: |
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

'''
import logging
import urlparse

from SpiffWorkflow import operators
from SpiffWorkflow.specs import Celery

from checkmate import providers

LOG = logging.getLogger(__name__)


def register_scheme(scheme):
    '''Register a new scheme with urlparse

    Use this to register a new scheme with urlparse and have it be
    parsed in the same way as http is parsed
    '''
    # pylint: disable=W0110,W0141
    for method in filter(lambda s: s.startswith('uses_'), dir(urlparse)):
        getattr(urlparse, method).append(scheme)

register_scheme('git')  # without this, urlparse won't handle git:// correctly


# pylint: disable=R0904
class Provider(providers.ProviderBase):
    '''Implements a script configuration management provider.'''
    name = 'script'
    vendor = 'core'

    def prep_environment(self, wfspec, deployment, context):
        providers.ProviderBase.prep_environment(self, wfspec, deployment,
                                                context)
        if self.prep_task:
            return  # already prepped
        results = {}
        source_repo = deployment.get_setting('source', provider_key=self.key)
        if source_repo:
            defines = {'provider': self.key}
            properties = {'estimated_duration': 10, 'task_tags': ['root']}
            task_name = 'checkmate.workspaces.create_workspace'
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

    # pylint: disable=R0913,R0914
    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        '''Create and write settings, generate run_list, and call cook.'''
        wait_on, _, component = self._add_resource_tasks_helper(
            resource, key, wfspec, deployment, context, wait_on)
        script_source = component.get('dependencies', {}).get('script')
        task_name = 'Execute Script %s (%s)' % (key, resource['hosted_on'])
        host_ip_path = "instance:%s/public_ip" % resource['hosted_on']
        password_path = 'instance:%s/password' % resource['hosted_on']
        private_key = deployment.settings().get('keys', {}).get(
            'deployment', {}).get('private_key')
        queued_task_dict = context.get_queued_task_dict(
            deployment_id=deployment['id'], resource_key=key,
            resource=resource)
        execute_task = Celery(wfspec,
                              task_name,
                              'checkmate.ssh.execute_2',
                              call_args=[queued_task_dict,
                                         operators.PathAttrib(host_ip_path),
                                         script_source,
                                         "root"],
                              password=operators.PathAttrib(password_path),
                              private_key=private_key,
                              properties={
                                  'estimated_duration': 600,
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

    # pylint: disable=R0913
    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        '''Generate tasks for a connection.'''
        LOG.debug("Adding connection task for resource '%s' for relation '%s'",
                  key, relation_key, extra={'data': {'resource': resource,
                                                     'relation': relation}})

    def get_catalog(self, context, type_filter=None):
        '''Return stored/override catalog.

        If it does not exist then connect, build, and return one.
        '''

        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #        this for every provider
        results = providers.ProviderBase.get_catalog(self, context,
                                                     type_filter=type_filter)
        return results
