"""Provider for OpenStack Compute API

- Supports Rackspace Open CLoud Compute Extensions and Auth
"""
import logging
import os
import uuid

from novaclient.exceptions import EndpointNotFound, AmbiguousEndpoints
from novaclient.v1_1 import client
from SpiffWorkflow.operators import Attrib, PathAttrib
from SpiffWorkflow.specs import Celery, Transform

from checkmate.deployments import Deployment, resource_postback
from checkmate.exceptions import CheckmateNoTokenError, CheckmateNoMapping, \
        CheckmateServerBuildFailed, CheckmateException
from checkmate.providers import ProviderBase
from checkmate.utils import get_source_body, match_celery_logging, isUUID
from checkmate.workflows import wait_for

LOG = logging.getLogger(__name__)

UBUNTU_12_04_IMAGE_ID = "5cebb13a-f783-4f8c-8058-c4182c724ccd"


class RackspaceComputeProviderBase(ProviderBase):
    """Generic functions for rackspace Compute providers"""
    vendor = 'rackspace'

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
        #kwargs aadded to server creation calls (contain things like ssh keys)
        self._kwargs = {}

    def prep_environment(self, wfspec, deployment, context):
        keys = set()
        for value in deployment.settings().get('keys', {}).values():
            if 'public_key_ssh' in value:
                keys.add(value['public_key_ssh'])
            elif 'public_key' in value:
                assert False, "Code still using public_key without _ssh"
        if keys:
            path = '/root/.ssh/authorized_keys'
            if 'files' not in self._kwargs:
                self._kwargs['files'] = {path: '\n'.join(keys)}
            else:
                existing = self._kwargs['files'][path].split('\n')
                keys.update(existing)
                self._kwargs['files'][path] = '\n'.join(keys)


class Provider(RackspaceComputeProviderBase):
    name = 'nova'

    def generate_template(self, deployment, resource_type, service, context,
            name=None):
        template = RackspaceComputeProviderBase.generate_template(self,
                deployment, resource_type, service, context, name=name)

        catalog = self.get_catalog(context)


        # Get region
        region = deployment.get_setting('region', resource_type=resource_type,
                service_name=service, provider_key=self.key)
        if not region:
            raise CheckmateException("Could not identify which region to "
                    "create servers in")

        # Find and translate image
        image = deployment.get_setting('os', resource_type=resource_type,
                service_name=service, provider_key=self.key,
                default='Ubuntu 12.04')

        if not isUUID(image):
            # Assume it is an OS name and find it
            for key, value in catalog['lists']['types'].iteritems():
                if image == value['name'] or image == value['os']:
                    LOG.debug("Mapping image from '%s' to '%s'" % (image, key))
                    image = key
                    break

        if not isUUID(image):
            # Sounds like we did not match an image
            raise CheckmateNoMapping("No image mapping for '%s' in '%s'" % (
                    image, self.name))

        if image not in catalog['lists']['types']:
            raise CheckmateNoMapping("Image '%s' not found in '%s'" % (
                    image, self.name))

        # Get setting
        flavor = None
        memory = self.parse_memory_setting(deployment.get_setting('memory',
                resource_type=resource_type, service_name=service,
                provider_key=self.key, default=512))

        # Find the available memory size that satisfies this
        matches = [e['memory'] for e in catalog['lists']['sizes'].values()
                     if int(e['memory']) >= memory]
        if not matches:
            raise CheckmateNoMapping("No flavor has at least '%s' memory" %
                                     memory)
        match = str(min(matches))
        for key, value in catalog['lists']['sizes'].iteritems():
            if match == str(value['memory']):
                LOG.debug("Mapping flavor from '%s' to '%s'" % (memory, key))
                flavor = key
                break
        if not flavor:
            raise CheckmateNoMapping("No flavor mapping for '%s' in '%s'" % (
                    memory, self.key))

        template['flavor'] = flavor
        template['image'] = image
        template['region'] = region
        return template

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        """
        :param resource: the dict of the resource generated by
                generate_template earlier
        :returns: returns the root task in the chain of tasks
        TODO: use environment keys instead of private key
        """
        create_server_task = Celery(wfspec, 'Create Server %s' % key,
               'checkmate.providers.rackspace.compute.create_server',
               call_args=[context.get_queued_task_dict(
                                deployment=deployment['id'],
                                resource=key),
                        resource.get('dns-name'),
                        resource['region']],
               image=resource.get('image', UBUNTU_12_04_IMAGE_ID),
               flavor=resource.get('flavor', "2"),
               files=self._kwargs.get('files', None),
               defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['create']),
               properties={'estimated_duration': 20})

        build_wait_task = Celery(wfspec, 'Wait for Server %s build'
                % key, 'checkmate.providers.rackspace.compute.wait_on_build',
                call_args=[context.get_queued_task_dict(
                                deployment=deployment['id'],
                                resource=key),
                        PathAttrib('instance:%s/id' % key),
                        resource['region']],
                password=PathAttrib('instance:%s/password' % key),
                identity_file=Attrib('private_key_path'),
                properties={'estimated_duration': 150},
                defines=dict(resource=key,
                             provider=self.key,
                             task_tags=['final']))
        create_server_task.connect(build_wait_task)

        if wait_on is None:
            wait_on = []
        if getattr(self, 'prep_task', None):
            wait_on.append(self.prep_task)
        join = wait_for(wfspec, create_server_task, wait_on,
                name="Server Wait on:%s" % key)

        return dict(root=join, final=build_wait_task,
                create=create_server_task)

    def get_catalog(self, context, type_filter=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one"""
        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #       this for every provider
        results = RackspaceComputeProviderBase.get_catalog(self, context,
            type_filter=type_filter)
        if results:
            # We have a prexisting or overriding catalog stored
            return results

        # build a live catalog this would be the on_get_catalog called if no
        # stored/override existed
        api = self._connect(context)

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context.catalog:
                if service['name'] == 'cloudServersOpenStack':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['regions'] = regions

        if type_filter is None or type_filter == 'compute':
            results['compute'] = dict(
                    linux_instance={
                            'id': 'linux_instance',
                            'provides': [{'compute': 'linux'}],
                            'is': 'compute',
                        },
                    windows_instance={
                            'id': 'windows_instance',
                            'provides': [{'compute': 'windows'}],
                            'is': 'compute',
                        },
                    )

        if type_filter is None or type_filter == 'type':
            images = api.images.list()
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['types'] = {
                    i.id: {
                        'name': i.name,
                        'os': i.name.split(' LTS ')[0].split(' (')[0],
                        } for i in images}
        if type_filter is None or type_filter == 'image':
            images = api.images.list()
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['images'] = {
                    i.id: {
                        'name': i.name
                        } for i in images if False}
        if type_filter is None or type_filter == 'size':
            flavors = api.flavors.list()
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['sizes'] = {
                f.id: {
                    'name': f.name,
                    'memory': f.ram,
                    'disk': f.disk,
                    } for f in flavors}

        self.validate_catalog(results)
        return results

    @staticmethod
    def _connect(context, region=None):
        """Use context info to connect to API and return api object"""
        #FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, dict):
            from checkmate.middleware import RequestContext
            context = RequestContext(**context)
        #TODO: Hard-coded to Rax auth for now
        if not context.auth_token:
            raise CheckmateNoTokenError()

        def find_url(catalog, region):
            for service in catalog:
                if service['name'] == 'cloudServersOpenStack':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if endpoint.get('region') == region:
                            return endpoint['publicURL']

        def find_a_region(catalog):
            """Any region"""
            for service in catalog:
                if service['name'] == 'cloudServersOpenStack':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        return endpoint['region']

        if not region:
            region = find_a_region(context.catalog) or 'DFW'

        os.environ['NOVA_RAX_AUTH'] = "Yes Please!"
        api = client.Client(context.username, 'dummy', None,
                "https://identity.api.rackspacecloud.com/v2.0",
                region_name=region, service_type="compute",
                service_name='cloudServersOpenStack')
        api.client.auth_token = context.auth_token

        url = find_url(context.catalog, region)
        api.client.management_url = url

        return api

"""
  Celery tasks to manipulate OpenStack Compute with support for
  the Rackspace Cloud.
"""

from celery.task import task

from checkmate.ssh import test_connection

REGION_MAP = {'dallas': 'DFW',
              'chicago': 'ORD',
              'london': 'LON'}

#
# Celery Tasks
#
@task
def create_server(context, name, region, api_object=None, flavor="2",
            files=None, image=UBUNTU_12_04_IMAGE_ID):
    """Create a Rackspace Cloud server using novaclient.

    Note: Nova server creation requests are asynchronous. The IP address of the
    server is not available when thios call returns. A separate operation must
    poll for that data.

    :param context: the context information
    :type context: dict
    :param name: the name of the server
    :param api_object: existing, authenticated connection to API
    :param image: the image ID to use when building the server (which OS)
    :param flavor: the size of the server (a string ID)
    :param files: a list of files to inject
    :type files: dict
    :param prefix: a string to prepend to any results. Used by Spiff and
            Checkmate
    :Example:

    {
      '/root/.ssh/authorized_keys': "base64 encoded content..."
    }
    :param ip_address_type: the type of the IP address to return in the
        results. Default is 'public'
    :return: dict of created server
    :rtype: dict
    :Example:

    {
      id: "uuid...",
      password: "secret"
    }

    """
    match_celery_logging(LOG)
    if api_object is None:
        api_object = Provider._connect(context, region)

    LOG.debug('Image=%s, Flavor=%s, Name=%s, Files=%s' % (
                  image, flavor, name, files))

    # Check image and flavor IDs (better descriptions if we error here)
    image_object = api_object.images.find(id=image)
    LOG.debug("Image id %s found. Name=%s" % (image, image_object.name))
    flavor_object = api_object.flavors.find(id=str(flavor))
    LOG.debug("Flavor id %s found. Name=%s" % (flavor, flavor_object.name))

    server = api_object.servers.create(name, image_object, flavor_object,
            files=files)
    create_server.update_state(state="PROGRESS",
                               meta={"server.id": server.id})
    LOG.debug('Created server %s (%s).  Admin pass = %s' % (
            name, server.id, server.adminPass))

    instance_key = 'instance:%s' % context['resource']
    results = {instance_key: {'id': server.id, 'password': server.adminPass}}

    # Send data back to deployment
    resource_postback.delay(context['deployment'], results)
    return results

from checkmate.providers.rackspace.monitoring import initialize_monitoring

@task(default_retry_delay=10, max_retries=18)  # ~3 minute wait
def wait_on_build(context, server_id, region, ip_address_type='public',
            check_ssh=True, username='root', timeout=10, password=None,
            identity_file=None, port=22, api_object=None):
    """Checks build is complete and. optionally, that SSH is working.

    :param ip_adress_type: the type of IP addresss to return as 'ip' in the
        response
    :param prefix: a string to prepend to any results. Used by Spiff and
            Checkmate
    :returns: False when build not ready. Dict with ip addresses when done.
    """
    match_celery_logging(LOG)
    if api_object is None:
        api_object = Provider._connect(context, region)

    assert server_id, "ID must be provided"
    LOG.debug("Getting server %s" % server_id)
    server = api_object.servers.find(id=server_id)
    results = {'id': server_id,
            'status': server.status,
            'addresses': server.addresses
            }

    if server.status == 'ERROR':
        raise CheckmateServerBuildFailed("Server %s build failed" % server_id)

    ip = None
    if server.addresses:
        # Get requested IP
        addresses = server.addresses.get(ip_address_type or 'public', [])
        for address in addresses:
            if address['version'] == 4:
                ip = address['addr']
                break
        results['ip'] = ip

        # Get public (default) IP
        addresses = server.addresses.get('public', [])
        for address in addresses:
            if address['version'] == 4:
                public_ip = address['addr']
                results['public_ip'] = public_ip
                break

        # Also get service_net IP
        private_addresses = server.addresses.get('private', [])
        for address in private_addresses:
            if address['version'] == 4:
                results['private_ip'] = address['addr']
                break

    if server.status == 'BUILD':
        results['progress'] = server.progress
        countdown = 100 - server.progress
        if countdown <= 0:
            countdown = 15  # progress is not accurate. Allow at least 15s wait
        wait_on_build.update_state(state='PROGRESS', meta=results)
        LOG.debug("Server %s progress is %s. Retrying after %s seconds" % (
                  server_id, server.progress, countdown))
        return wait_on_build.retry(countdown=countdown)

    if server.status != 'ACTIVE':
        LOG.warning("Server %s status is %s, which is not recognized. "
                "Assuming it is active" % (server_id, server.status))

    if not ip:
        raise CheckmateException("Could not find IP of server %s" % server_id)
    else:
        up = test_connection(context, ip, username, timeout=timeout,
                password=password, identity_file=identity_file, port=port)
        if up:
            LOG.info("Server %s is up" % server_id)
            instance_key = 'instance:%s' % context['resource']
            results = {instance_key: results}
	    initialize_monitoring.delay(ip=ip, name="Entity for %s" % id,context=deployment,resource="node")
            # Send data back to deployment
            resource_postback.delay(context['deployment'], results)
            return results
        return wait_on_build.retry(exc=CheckmateException("Server "
                "%s not ready yet" % server_id))
