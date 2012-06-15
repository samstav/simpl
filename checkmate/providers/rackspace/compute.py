import logging
import os
import openstack.compute
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery, Merge, Transform

from checkmate.exceptions import CheckmateNoTokenError
from checkmate.providers import ProviderBase
from checkmate.utils import get_source_body

LOG = logging.getLogger(__name__)


class LegacyProvider(ProviderBase):
    def __init__(self, provider):
        ProviderBase.__init__(self, provider)
        self.prep_task = None

    def prep_environment(self, wfspec, deployment):
        #file = {'/root/.ssh/authorized_keys': "\n".join(keys)}
        def get_keys_code(my_task):
            keys = []
            for key, value in my_task.attributes['context'].get('keys',
                        {}).iteritems():
                if 'public_key' in value:
                    keys.append(value['public_key'])
            if keys:
                path = '/root/.ssh/authorized_keys'
                if not 'files' in my_task.attributes:
                    my_task.attributes['files'] = {}
                keys_string = '\n'.join(keys)
                if path in my_task.attributes['files']:
                    my_task.attributes['files'][path] += keys_string
                else:
                    my_task.attributes['files'][path] = keys_string

        self.prep_task = Transform(wfspec, "Get Keys to Inject",
                transforms=[get_source_body(get_keys_code)],
                description="Collect keys into correct files syntax")

        #TODO: remove direct-coding to config provider task names
        config_spec = wfspec.task_specs['Create Chef Environment']
        config_spec.connect(self.prep_task)
        return {'root': self.prep_task, 'final': self.prep_task}

    def generate_template(self, deployment, service_name, service, name=None):
        inputs = deployment.get('inputs', {})
        flavor = inputs.get('%s:instance/flavor' % service_name,
                service['config']['settings'].get(
                    '%s:instance/flavor' % service_name,
                    service['config']['settings']
                    ['instance/flavor']['default']))
        image = inputs.get('%s:instance/os' % service_name,
                service['config']['settings'].get(
                        '%s:instance/os' % service_name,
                        service['config']['settings']['instance/os']
                        ['default']))
        if image == 'Ubuntu 11.10':
            image = 119
        if not name:
            name = 'CMDEP%s-server.stabletransit.com' % (deployment['id'][0:7])
        template = {'type': 'server', 'dns-name': name, 'flavor': flavor,
                'image': image, 'instance-id': None}

        return template

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
            wait_on=None):
        """
        :param resource: the dict of the resource generated by
                generate_template earlier
        :returns: returns the root task in the chain of tasks
        TODO: use environment keys instead of private key
        """

        create_server_task = Celery(wfspec, 'Create Server:%s' % key,
                           'stockton.server.distribute_create',
                           call_args=[Attrib('context'),
                           resource.get('dns-name')],
                           image=resource.get('image', 119),
                           flavor=resource.get('flavor', 1),
                           files=Attrib('files'),
                           ip_address_type='public',
                           defines={"Resource": key},
                           properties={'estimated_duration': 20})

        build_wait_task = Celery(wfspec, 'Check that Server is Up:%s'
                % key, 'stockton.server.distribute_wait_on_build',
                call_args=[Attrib('context'), Attrib('id')],
                password=Attrib('password'),
                identity_file=os.environ.get('CHECKMATE_PRIVATE_KEY',
                        '~/.ssh/id_rsa'),
                properties={'estimated_duration': 150})
        create_server_task.connect(build_wait_task)

        join = Merge(wfspec, "Server Wait on:%s" % key)
        join.connect(create_server_task)
        self.prep_task.connect(join)
        if wait_on:
            for dependency in wait_on:
                dependency.connect(join)

        return {'root': join, 'final': build_wait_task}

    def get_catalog(self, context, type_filter=None):
        api = self._connect(context)

        results = {}
        if type_filter is None or type_filter == 'type':
            images = api.images.list()
            results['types'] = {
                    i.id: {
                        'name': i.name,
                        'os': i.name,
                        } for i in images if int(i.id) < 1000}
        if type_filter is None or type_filter == 'image':
            images = api.images.list()
            results['images'] = {
                    i.id: {
                        'name': i.name
                        } for i in images if int(i.id) > 1000}
        if type_filter is None or type_filter == 'size':
            flavors = api.flavors.list()
            results['sizes'] = {
                f.id: {
                    'name': f.name,
                    'ram': f.ram,
                    'disk': f.disk,
                    } for f in flavors}

        return results

    def _connect(self, context):
        """Use context info to connect to API and return api object"""
        if not context.auth_tok:
            raise CheckmateNoTokenError()
        api = openstack.compute.Compute()
        api.client.auth_token = context.auth_tok

        def find_url(catalog):
            for service in catalog:
                if service['name'] == 'cloudServers':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        return endpoint['publicURL']

        url = find_url(context.catalog)
        api.client.management_url = url
        return api


class NovaProvider(ProviderBase):
    def generate_template(self, deployment, service_name, service, name=None):
        inputs = deployment.get('inputs', {})
        flavor = inputs.get('%s:instance/flavor' % service_name,
                service['config']['settings'].get(
                    '%s:instance/flavor' % service_name,
                    service['config']['settings']
                    ['instance/flavor']['default']))
        image = inputs.get('%s:instance/os' % service_name,
                service['config']['settings'].get(
                        '%s:instance/os' % service_name,
                        service['config']['settings']['instance/os']
                        ['default']))
        if image == 'Ubuntu 11.10':
            image = '3afe97b2-26dc-49c5-a2cc-a2fc8d80c001'
        flavor = str(flavor)  # nova uses string IDs
        if not name:
            name = 'CMDEP%s-server.stabletransit.com' % (deployment['id'][0:7])
        template = {'type': 'server', 'dns-name': name, 'flavor': flavor,
                'image': image, 'instance-id': None}

        return template

    def add_resource_tasks(self, resource, key, wfspec, deployment,
            context, wait_on=None):
        """
        :param resource: the dict of the resource generated by
                generate_template earlier
        :returns: returns the root task in the chain of tasks
        TODO: use environment keys instead of private key
        """
        create_server_task = Celery(wfspec, 'Create Server:%s' % key,
                           'stockton.nova.distribute_create',
                           call_args=[Attrib('context'),
                           resource.get('dns-name')],
                           image=resource.get('image',
                                    '3afe97b2-26dc-49c5-a2cc-a2fc8d80c001'),
                           flavor=resource.get('flavor', "1"),
                           files=context['files'],
                           defines={"Resource": key},
                           properties={'estimated_duration': 20})

        build_wait_task = Celery(wfspec, 'Check that Server is Up:%s'
                % key, 'stockton.nova.distribute_wait_on_build',
                call_args=[Attrib('context'), Attrib('id')],
                password=Attrib('password'),
                identity_file=os.environ.get('CHECKMATE_PRIVATE_KEY',
                        '~/.ssh/id_rsa'),
                properties={'estimated_duration': 150})
        create_server_task.connect(build_wait_task)

        if wait_on:
            join = Merge(wfspec, "Server Wait on:%s" % key)
            join.connect(create_server_task)
            for dependency in wait_on:
                dependency.connect(join)

        return {'root': join, 'final': build_wait_task}
