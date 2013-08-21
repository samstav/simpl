'''Provider for OpenStack Compute API

- Supports Rackspace Open Cloud Compute Extensions and Auth
'''
import copy
import eventlet
import logging
import os

from celery.canvas import chain
from celery.task import task
from novaclient.exceptions import (
    NotFound,
    NoUniqueMatch,
    OverLimit,
    BadRequest,
)
# pylint: disable=C0103

client = eventlet.import_patched('novaclient.v1_1.client')
# from novaclient.v1_1 import client
import redis
from SpiffWorkflow.operators import PathAttrib
from SpiffWorkflow.specs import Celery

from checkmate.common import caching
from checkmate.common import config
from checkmate.common import statsd
from checkmate.deployments import resource_postback
from checkmate.deployments.tasks import reset_failed_resource_task
from checkmate.exceptions import (
    BLUEPRINT_ERROR,
    CheckmateDoesNotExist,
    CheckmateNoTokenError,
    CheckmateNoMapping,
    CheckmateException,
    CheckmateResumableException,
    CheckmateRetriableException,
    CheckmateServerBuildFailed,
    CheckmateUserException,
    UNEXPECTED_ERROR,
)
from checkmate.middleware import RequestContext
from checkmate.providers.rackspace import base
from checkmate.providers import user_has_access
import checkmate.rdp
import checkmate.ssh
from checkmate.utils import (
    get_class_name,
    isUUID,
    match_celery_logging,
    merge_dictionary,
    yaml_to_dict,
)


LOG = logging.getLogger(__name__)
CONFIG = config.current()
IMAGE_MAP = {
    'precise': 'Ubuntu 12.04',
    'lucid': 'Ubuntu 10.04',
    'quantal': 'Ubuntu 12.10',
    'ringtail': 'Ubuntu 13.04',
    'saucy': 'Ubuntu 13.10',
    'squeeze': 'Debian 6',
    'wheezy': 'Debian 7',
    'beefy miracle': 'Fedora 17',
    'spherical cow': 'Fedora 18',
    'schroedinger': 'Fedora 19',
    'opensuse': 'openSUSE',
}
KNOWN_OSES = {
    'ubuntu': ['10.04', '10.12', '11.04', '11.10', '12.04', '12.10', '13.04',
               '13.10'],
    'centos': ['6.4'],
    'cirros': ['0.3'],
    'debian': ['6', '7'],
    'fedora': ['17', '18', '19'],
}
RACKSPACE_DISTRO_KEY = 'os_distro'
RACKSPACE_VERSION_KEY = 'os_version'

OPENSTACK_DISTRO_KEY = 'org.openstack__1__os_distro'
OPENSTACK_VERSION_KEY = 'org.openstack__1__os_version'
CATALOG_TEMPLATE = yaml_to_dict("""compute:
  linux_instance:
    id: linux_instance
    is: compute
    provides:
    - compute: linux
    options:
        'name':
            type: string
            required: true
        'os':
            source_field_name: image
            required: true
            choice: []
        'memory':
            default: 512
            required: true
            source_field_name: flavor
            choice: []
        'personality': &personality
            type: hash
            required: false
            description: File path and contents.
            sample: |
                    "personality: [
                        {
                            "path" : "/etc/banner.txt",
                            "contents" : "ICAgICAgDQoiQSBjbG91ZCBkb2VzIG5vdCBr\
bm93IHdoeSBp dCBtb3ZlcyBpbiBqdXN0IHN1Y2ggYSBkaXJlY3Rpb24gYW5k IGF0IHN1Y2ggYSBz\
cGVlZC4uLkl0IGZlZWxzIGFuIGltcHVs c2lvbi4uLnRoaXMgaXMgdGhlIHBsYWNlIHRvIGdvIG5vd\
y4g QnV0IHRoZSBza3kga25vd3MgdGhlIHJlYXNvbnMgYW5kIHRo ZSBwYXR0ZXJucyBiZWhpbmQgY\
WxsIGNsb3VkcywgYW5kIHlv dSB3aWxsIGtub3csIHRvbywgd2hlbiB5b3UgbGlmdCB5b3Vy c2VsZ\
iBoaWdoIGVub3VnaCB0byBzZWUgYmV5b25kIGhvcml6 b25zLiINCg0KLVJpY2hhcmQgQmFjaA=="
                        }
                    ]
        'metadata': &metadata
            type: hash
            required: false
            description: Metadata key and value pairs.
            sample: |
                    "metadata" : {
                        "My Server Name" : "API Test Server 1"
                    }
  windows_instance:
    id: windows_instance
    is: compute
    provides:
    - compute: windows
    options:
        'name':
            type: string
            required: true
        'metadata': *metadata
        'personality': *personality
        'os':
            required: true
            source_field_name: image
            choice: []
        'memory':
            required: true
            default: 1024
            source_field_name: flavor
            choice: []
""")
API_IMAGE_CACHE = {}
API_FLAVOR_CACHE = {}
API_LIMITS_CACHE = {}
REDIS = None
REGION_MAP = {
    'dallas': 'DFW',
    'chicago': 'ORD',
    'virginia': 'IAD',
    'london': 'LON',
    'sydney': 'SYD',
}

if 'CHECKMATE_CACHE_CONNECTION_STRING' in os.environ:
    try:
        REDIS = redis.from_url(os.environ['CHECKMATE_CACHE_CONNECTION_STRING'])
    except StandardError as exception:
        LOG.warn("Error connecting to Redis: %s", exception)

#FIXME: delete tasks talk to database directly, so we load drivers and manager
from checkmate import db
from checkmate import deployments
DRIVERS = {}
DB = DRIVERS['default'] = db.get_driver()
SIMULATOR_DB = DRIVERS['simulation'] = db.get_driver(
    connection_string=os.environ.get(
        'CHECKMATE_SIMULATOR_CONNECTION_STRING',
        os.environ.get('CHECKMATE_CONNECTION_STRING', 'sqlite://')
    )
)
MANAGERS = {'deployments': deployments.Manager(DRIVERS)}
get_resource_by_id = MANAGERS['deployments'].get_resource_by_id


class RackspaceComputeProviderBase(base.RackspaceProviderBase):
    '''Generic functions for rackspace Compute providers.'''

    def __init__(self, provider, key=None):
        base.RackspaceProviderBase.__init__(self, provider, key=key)
        #kwargs added to server creation calls (contain things like ssh keys)
        self._kwargs = {}
        with open(os.path.join(os.path.dirname(__file__),
                               "managed_cloud",
                               "delay.sh")) as open_file:
            self.managed_cloud_script = open_file.read()

    def prep_environment(self, wfspec, deployment, context):
        base.RackspaceProviderBase.prep_environment(self, wfspec, deployment,
                                                    context)
        keys = set()
        for name, key_pair in deployment.settings()['keys'].iteritems():
            if 'public_key_ssh' in key_pair:
                LOG.debug("Injecting a '%s' public key", name)
                keys.add(key_pair['public_key_ssh'])
        if keys:
            path = '/root/.ssh/authorized_keys'
            if 'files' not in self._kwargs:
                self._kwargs['files'] = {path: '\n'.join(keys)}
            else:
                existing = self._kwargs['files'][path].split('\n')
                keys.update(existing)
                self._kwargs['files'][path] = '\n'.join(keys)
        # Inject managed cloud file to prevent RBA conflicts
        if 'rax_managed' in context.roles:
            path = '/etc/rackspace/pre.chef.d/delay.sh'
            if 'files' not in self._kwargs:
                self._kwargs['files'] = {path: self.managed_cloud_script}
            else:
                self._kwargs['files'][path] = self.managed_cloud_script


class Provider(RackspaceComputeProviderBase):
    '''The Base Provider Class for Rackspace NOVA.'''
    name = 'nova'

    __status_mapping__ = {
        'ACTIVE': 'ACTIVE',
        'BUILD': 'BUILD',
        'DELETED': 'DELETED',
        'ERROR': 'ERROR',
        'HARD_REBOOT': 'CONFIGURE',
        'MIGRATING': 'CONFIGURE',
        'PASSWORD': 'CONFIGURE',
        'REBOOT': 'CONFIGURE',
        'REBUILD': 'BUILD',
        'RESCUE': 'CONFIGURE',
        'RESIZE': 'CONFIGURE',
        'REVERT_RESIZE': 'CONFIGURE',
        'SHUTOFF': 'CONFIGURE',
        'SUSPENDED': 'ERROR',
        'UNKNOWN': 'ERROR',
        'VERIFY_RESIZE': 'CONFIGURE'
    }

    # pylint: disable=R0913
    def generate_template(self, deployment, resource_type, service, context,
                          index, key, definition):
        templates = RackspaceComputeProviderBase.generate_template(
            self, deployment, resource_type, service, context, index,
            key, definition
        )

        # Get region
        region = deployment.get_setting('region', resource_type=resource_type,
                                        service_name=service,
                                        provider_key=self.key)
        if not region:
            message = "Could not identify which region to create servers in"
            raise CheckmateUserException(message, get_class_name(
                CheckmateException), BLUEPRINT_ERROR, '')
        local_context = copy.deepcopy(context)
        local_context['region'] = region

        catalog = self.get_catalog(local_context)
        # Find and translate image
        image = deployment.get_setting('os', resource_type=resource_type,
                                       service_name=service,
                                       provider_key=self.key,
                                       default='Ubuntu 12.04')

        image_types = catalog['lists'].get('types', {})
        if not isUUID(image):
            # Assume it is an OS name and find it
            for key, value in image_types.iteritems():
                if image == value['name'] or image == value['os']:
                    LOG.debug("Mapping image from '%s' to '%s'", image, key)
                    image = key
                    break

        if not isUUID(image):
            # Sounds like we did not match an image
            LOG.debug("%s not found in: %s", image, image_types.keys())
            raise CheckmateNoMapping("No image mapping for '%s' in '%s'" % (
                                     image, self.name))

        if image not in image_types:
            raise CheckmateNoMapping("Image '%s' not found in '%s'" % (
                                     image, self.name))

        # Get setting
        flavor = None
        memory = self.parse_memory_setting(deployment.get_setting('memory',
                                           resource_type=resource_type,
                                           service_name=service,
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
                LOG.debug("Mapping flavor from '%s' to '%s'", memory, key)
                flavor = key
                break
        if not flavor:
            raise CheckmateNoMapping("No flavor mapping for '%s' in '%s'" % (
                                     memory, self.key))

        for template in templates:
            #TODO: remove the entry from the root
            template['flavor'] = flavor
            template['image'] = image
            template['region'] = region
            template['desired-state']['flavor'] = flavor
            template['desired-state']['image'] = image
            template['desired-state']['region'] = region
            template['desired-state']['os-type'] = image_types[image]['type']
            template['desired-state']['os'] = image_types[image]['os']
        return templates

    def verify_limits(self, context, resources):
        '''Verify that deployment stays within absolute resource limits.'''
        region = getattr(context, 'region', None)
        if not region:
            region = Provider.find_a_region(context.catalog)
        url = Provider.find_url(context.catalog, region)
        flavors = _get_flavors(url, context.auth_token)['flavors']

        memory_needed = 0
        cores_needed = 0
        for compute in resources:
            flavor = compute['flavor']
            details = flavors[flavor]
            memory_needed += details['memory']
            cores_needed += details['cores']

        limits = _get_limits(url, context.auth_token)
        memory_available = limits['maxTotalRAMSize'] - limits['totalRAMUsed']
        if memory_available < 0:
            memory_available = 0
        cores_available = limits['maxTotalCores'] - limits['totalCoresUsed']
        if cores_available < 0:
            cores_available = 0

        messages = []
        if memory_needed > memory_available:
            messages.append({
                'type': "INSUFFICIENT-CAPACITY",
                'message': "This deployment would create %s Cloud Servers "
                           "utilizing a total of %s MB memory.  You have "
                           "%s MB of memory available"
                           % (len(resources), memory_needed, memory_available),
                'provider': "compute",
                'severity': "CRITICAL"
            })
        if limits['maxTotalCores'] == -1:  # -1 means cores are unlimited
            return messages
        if cores_needed > cores_available:
            messages.append({
                'type': "INSUFFICIENT-CAPACITY",
                'message': "This deployment would create %s Cloud Servers "
                           "utilizing a total of %s cores.  You have "
                           "%s cores available"
                           % (len(resources), cores_needed, cores_available),
                'provider': "compute",
                'severity': "CRITICAL"
            })
        return messages

    def verify_access(self, context):
        '''Verify that the user has permissions to create compute resources.'''
        roles = ['identity:user-admin', 'nova:admin', 'nova:creator']
        if user_has_access(context, roles):
            return {
                'type': "ACCESS-OK",
                'message': "You have access to create Cloud Servers",
                'provider': "nova",
                'severity': "INFORMATIONAL"
            }
        else:
            return {
                'type': "NO-ACCESS",
                'message': "You do not have access to create Cloud Servers",
                'provider': "nova",
                'severity': "CRITICAL"
            }

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        ''':param resource: the dict of the resource generated by
                generate_template earlier
        :returns: returns the root task in the chain of tasks
        TODO(any): use environment keys instead of private key
        '''

        desired = resource['desired-state']
        files = self._kwargs.get('files')

        if desired['os-type'] == 'windows':
            # Inject firewall puncher in WINDOWS
            with open(os.path.join(os.path.dirname(__file__),
                                   "scripts",
                                   "open_win_firewall.cmd")) as open_file:
                windows_firewall_script = open_file.read()
            path = 'C:\\Cloud-Automation\\bootstrap.bat'
            if files:
                files[path] = windows_firewall_script
            else:
                files = {path: windows_firewall_script}

        queued_task_dict = context.get_queued_task_dict(
            deployment_id=deployment['id'], resource_key=key,
            region=desired['region'], resource=resource)
        create_server_task = Celery(
            wfspec, 'Create Server %s (%s)' % (key, resource['service']),
            'checkmate.providers.rackspace.compute.create_server',
            call_args=[
                queued_task_dict,
                resource.get('dns-name'),
                desired['region']
            ],
            image=desired.get('image'),
            flavor=desired.get('flavor', "2"),
            files=files,
            tags=self.generate_resource_tag(
                context.base_url, context.tenant, deployment['id'],
                resource['index']
            ),
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['create', 'root']
            ),
            properties={'estimated_duration': 20}
        )

        kwargs = dict(
            call_args=[
                queued_task_dict,
                PathAttrib('instance:%s/id' % key),
                resource['region'],
                resource
            ],
            verify_up=True,
            password=PathAttrib('instance:%s/password' % key),
            private_key=deployment.settings().get('keys', {}).get(
                'deployment', {}).get('private_key'),
            merge_results=True,
            properties={'estimated_duration': 150},
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['final']
            )
        )

        task_name = 'Wait for Server %s (%s) build' % (key,
                                                       resource['service'])
        celery_call = 'checkmate.providers.rackspace.compute.wait_on_build'
        build_wait_task = Celery(wfspec, task_name, celery_call, **kwargs)
        create_server_task.connect(build_wait_task)

        # If Managed Cloud Linux servers, add a Completion task to release
        # RBA. Other providers may delay this task until they are done.
        if ('rax_managed' in context.roles and
                resource['component'] == 'linux_instance'):
            touch_complete = Celery(
                wfspec, 'Mark Server %s (%s) Complete' % (key,
                                                          resource['service']),
                'checkmate.ssh.execute_2',
                call_args=[
                    queued_task_dict,
                    PathAttrib("instance:%s/public_ip" % key),
                    "touch /tmp/checkmate-complete",
                    "root",
                ],
                password=PathAttrib('instance:%s/password' % key),
                private_key=deployment.settings().get('keys', {}).get(
                    'deployment', {}).get('private_key'),
                properties={'estimated_duration': 10},
                defines=dict(
                    resource=key,
                    provider=self.key,
                    task_tags=['complete']
                )
            )
            build_wait_task.connect(touch_complete)

        if wait_on is None:
            wait_on = []
        # refactor to remove pylint error on missing attribute
        preps = getattr(self, 'prep_task', None)
        if preps:
            wait_on.append(preps)
        join = wfspec.wait_for(create_server_task, wait_on,
                               name="Server Wait on:%s (%s)" % (key, resource[
                                                                'service']))

        return dict(
            root=join,
            final=build_wait_task,
            create=create_server_task
        )

    def get_resource_status(self, context, deployment_id, resource, key,
                            sync_callable=None, api=None):
        result = super(Provider, self).get_resource_status(context,
                                                           deployment_id,
                                                           resource, key,
                                                           sync_callable=
                                                           sync_resource_task,
                                                           api=api)
        i_key = 'instance:%s' % key
        if result[i_key].get('status') in ['ACTIVE', 'DELETED']:
            result[i_key]['instance'] = {'status-message': ''}
        return result

    def delete_resource_tasks(self, wf_spec, context, deployment_id, resource,
                              key):
        self._verify_existing_resource(resource, key)
        inst_id = resource.get("instance", {}).get("id")
        region = (resource.get("region") or
                  resource.get("instance", {}).get("region"))
        if isinstance(context, RequestContext):
            context = context.get_queued_task_dict(deployment_id=deployment_id,
                                                   resource_key=key,
                                                   resource=resource,
                                                   region=region,
                                                   instance_id=inst_id)
        else:
            context['deployment_id'] = deployment_id
            context['resource_key'] = key
            context['resource'] = resource
            context['region'] = region
            context['instance_id'] = inst_id

        delete_server = Celery(
            wf_spec,
            'Delete Server (%s)' % key,
            'checkmate.providers.rackspace.compute.delete_server_task',
            call_args=[context],
            properties={
                'estimated_duration': 5,
            },
        )
        wait_on_delete = Celery(
            wf_spec,
            'Wait on Delete Server (%s)' % key,
            'checkmate.providers.rackspace.compute.wait_on_delete_server',
            call_args=[context],
            properties={
                'estimated_duration': 10,
            },
        )
        delete_server.connect(wait_on_delete)
        return {'root': delete_server}

    @staticmethod
    def _get_api_info(context, **kwargs):
        '''Get Flavors, Images and Types available in a given Region.'''
        results = {}
        urls = {}
        if context.get('region') or kwargs.get('region'):
            region = context.get('region') or kwargs.get('region').upper()
            urls[region] = Provider.find_url(context.catalog, region)
        else:
            LOG.warning('Region not found in context or kwargs.')
            rax_regions = Provider.get_regions(
                context.catalog, service_name='cloudServersOpenStack',
                resource_type='compute')
            if rax_regions:
                regions = rax_regions
                LOG.debug("Found Rackspace compute regions: %s", rax_regions)
            else:
                regions = Provider.get_regions(context.catalog,
                                               resource_type='compute')
                LOG.debug("Found generic compute regions: %s", regions)
            for region in regions:
                if region:
                    urls[region] = Provider.find_url(context.catalog, region)
        if not urls:
            LOG.warning('No compute endpoints found.')
            return results

        if CONFIG.eventlet:
            jobs = eventlet.GreenPile(min(len(urls) * 2, 16))
            for region, url in urls.items():
                if not url and len(urls) == 1:
                    LOG.warning("Failed to find compute endpoint for %s in "
                                "region %s", context.tenant, region)
                jobs.spawn(_get_flavors, url, context.auth_token)
                jobs.spawn(_get_images_and_types, url, context.auth_token)
            for ret in jobs:
                results = merge_dictionary(results, ret, extend_lists=True)
        else:
            for region, url in urls.items():
                if not url:
                    if len(urls) == 1:
                        LOG.warning("Failed to find compute endpoint for %s "
                                    "in region %s", context.tenant, region)
                    continue
                flavors = _get_flavors(url, context.auth_token)
                images = _get_images_and_types(url, context.auth_token)
                results = merge_dictionary(results, flavors, extend_lists=True)
                results = merge_dictionary(results, images, extend_lists=True)
        return results

    def get_catalog(self, context, type_filter=None, **kwargs):
        '''Return stored/override catalog if it exists, else connect, build,
        and return one.
        '''
        # TODO(any): maybe implement this an on_get_catalog so we don't have to
        #       do this for every provider
        results = RackspaceComputeProviderBase.get_catalog(self, context,
                                                           type_filter=
                                                           type_filter)
        if results:
            # We have a prexisting or overriding catalog stored
            return results

        # build a live catalog this would be the on_get_catalog called if no
        # stored/override existed
        images = None
        flavors = None
        types = None

        vals = self._get_api_info(context, **kwargs)

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

        for key in vals:
            if key == 'flavors':
                flavors = vals['flavors']
            elif key == 'types':
                types = vals['types']
            elif key == 'images':
                images = vals['images']

        if type_filter is None or type_filter == 'compute':
            #TODO(any): add regression tests - copy.copy leaking across tenants
            results['compute'] = copy.deepcopy(CATALOG_TEMPLATE['compute'])
            linux = results['compute']['linux_instance']
            windows = results['compute']['windows_instance']
            if types:
                for image in types.values():
                    choice = dict(name=image['name'], value=image['os'])
                    if image['type'] == 'windows':
                        windows['options']['os']['choice'].append(choice)
                    else:
                        linux['options']['os']['choice'].append(choice)

            if flavors:
                for flavor in flavors.values():
                    choice = dict(value=int(flavor['memory']),
                                  name="%s (%s Gb disk)" % (flavor['name'],
                                                            flavor['disk']))
                    linux['options']['memory']['choice'].append(choice)
                    if flavor['memory'] >= 1024:  # Windows needs min 1Gb
                        windows['options']['memory']['choice'].append(choice)

        if types and (type_filter is None or type_filter == 'type'):
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['types'] = types
        if flavors and (type_filter is None or type_filter == 'size'):
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['sizes'] = flavors
        if images and (type_filter is None or type_filter == 'image'):
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['images'] = images

        self.validate_catalog(results)
        if type_filter is None:
            self._catalog_cache[context.get('region')] = results
        return results

    @staticmethod
    def find_url(catalog, region):
        '''Get the Public URL of a service.'''
        fall_back = None
        openstack_compatible = None
        for service in catalog:
            if service['name'] == 'cloudServersOpenStack':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    if endpoint.get('region') == region:
                        return endpoint['publicURL']
            elif (service['type'] == 'compute' and
                  service['name'] != 'cloudServers'):
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    if endpoint.get('region') == region:
                        fall_back = endpoint['publicURL']
            elif service['type'] == 'compute':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    if endpoint.get('region') == region:
                        openstack_compatible = endpoint['publicURL']
        return fall_back or openstack_compatible

    @staticmethod
    def find_a_region(catalog):
        '''Any region.'''
        fall_back = None
        openstack_compatible = None
        for service in catalog:
            if service['name'] == 'cloudServersOpenStack':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    return endpoint['region']
            elif (service['type'] == 'compute' and
                  service['name'] != 'cloudServers'):
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    fall_back = endpoint.get('region')
            elif service['type'] == 'compute':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    openstack_compatible = endpoint.get('region')
        return fall_back or openstack_compatible

    @staticmethod
    def connect(context, region=None):
        '''Use context info to connect to API and return api object.'''
        #FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, dict):
            context = RequestContext(**context)
        #TODO(any): Hard-coded to Rax auth for now
        if not context.auth_token:
            raise CheckmateNoTokenError()

        if not region:
            region = getattr(context, 'region', None)
            if not region:
                region = Provider.find_a_region(context.catalog) or 'DFW'
        url = Provider.find_url(context.catalog, region)
        plugin = AuthPlugin(context.auth_token, url,
                            auth_source=context.auth_source)
        insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1',
                                                                    'true']
        api = client.Client(context.username, 'ignore', context.tenant,
                            insecure=insecure, auth_system="rackspace",
                            auth_plugin=plugin)
        return api


class AuthPlugin(object):
    '''Handles auth.'''
    def __init__(self, auth_token, nova_url, auth_source=None):
        self.token = auth_token
        self.nova_url = nova_url
        self.auth_source = auth_source or "http://localhost:35357/v2.0/tokens"
        self.done = False

    def get_auth_url(self):
        '''Respond to novaclient auth_url call.'''
        LOG.debug("Nova client called auth_url from plugin")
        return self.auth_source

    def authenticate(self, novaclient, auth_url):  # pylint: disable=W0613
        '''Respond to novaclient authenticate call.'''
        if self.done:
            LOG.debug("Called a second time from Nova. Assuming token expired")
            raise CheckmateResumableException("Auth Token expired",
                                              "CheckmateResumableException",
                                              "Your authentication token "
                                              "expired before work on your "
                                              "deployment was completed. To "
                                              "resume that work, you just "
                                              "need to 'retry' the operation "
                                              "to supply a fresh token that "
                                              "we can use to continue working "
                                              "with", '')
        else:
            LOG.debug("Nova client called authenticate from plugin")
            novaclient.auth_token = self.token
            novaclient.management_url = self.nova_url
            self.done = True


@caching.Cache(timeout=3600, sensitive_args=[1], store=API_IMAGE_CACHE,
               backing_store=REDIS, backing_store_key='rax.compute.images')
def _get_images_and_types(api_endpoint, auth_token):
    '''Ask Nova for Images and Types.'''
    assert api_endpoint, "No API endpoint specified when getting images"
    plugin = AuthPlugin(auth_token, api_endpoint)
    insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1', 'true']
    try:
        api = client.Client('fake-user', 'fake-pass', 'fake-tenant',
                            insecure=insecure, auth_system="rackspace",
                            auth_plugin=plugin)
        ret = {'images': {}, 'types': {}}
        LOG.info("Calling Nova to get images for %s", api_endpoint)
        images = api.images.list(detailed=True)
        LOG.debug("Parsing image list: %s", images)
        for i in images:
            metadata = i.metadata or {}
            detected = detect_image(i.name, metadata=metadata)
            if detected:
                img = {
                    'name': i.name,
                    'os': detected['os'],
                    'type': detected['type'],
                }

                ret['types'][str(i.id)] = img
                ret['images'][i.id] = {'name': i.name}
        LOG.debug("Found images %s: %s", api_endpoint, ret['images'].keys())
    except Exception as exc:
        LOG.error("Error retrieving Cloud Server images from %s: %s",
                  api_endpoint, exc)
        raise
    return ret


def detect_image(name, metadata=None):
    '''Attempt to detect OS from name and/or metadata.

    :returns: string of OS and version (ex. Ubuntu 12.04) in Checkmate format.
    '''
    if 'LAMP' in name:
        return None
    os_name = None
    # Try metadata
    if metadata:
        if (RACKSPACE_DISTRO_KEY in metadata and
                RACKSPACE_VERSION_KEY in metadata):
            os_name = '%s %s' % (metadata[RACKSPACE_DISTRO_KEY].title(),
                                 metadata[RACKSPACE_VERSION_KEY])
            LOG.debug("Identified image by os_distro: %s", os_name)
            return {'name': name, 'os': os_name, 'type': 'linux'}

        if (OPENSTACK_DISTRO_KEY in metadata and
                OPENSTACK_VERSION_KEY in metadata):
            parsed_name = key = metadata[OPENSTACK_DISTRO_KEY].lower()
            version = metadata[OPENSTACK_VERSION_KEY]
            os_type = 'linux'
            if "microsoft.server" in key:
                os_type = 'windows'
                parsed_name = "Microsoft Windows Server"
                if '.0' in version:
                    version = version.split('.')[0]
                elif '.2' in version:
                    version = '%s R2 SP1' % version.split('.')[0]
            elif '.' in parsed_name:
                parsed_name = ' '.join(parsed_name.split('.')[1:])
            os_name = '%s %s' % (parsed_name.title(), version)
            LOG.debug("Identified image by openstack key '%s': %s", key,
                      os_name, extra={'data': metadata})
            return {'name': name, 'os': os_name, 'type': os_type}

    #Look for keywords like 'precise'
    lower_name = name.lower()
    for hint, mapped_os in IMAGE_MAP.iteritems():
        if hint in lower_name:
            os_name = mapped_os
            LOG.debug("Identified image using hint '%s': %s", hint, os_name)
            return {'name': name, 'os': os_name, 'type': 'linux'}

    #Look for Checkmate name
    for mapped_os in IMAGE_MAP.itervalues():
        if mapped_os.lower() in lower_name:
            os_name = mapped_os
            LOG.debug("Identified image using name '%s': %s", mapped_os,
                      os_name)
            return {'name': name, 'os': os_name, 'type': 'linux'}

    #Parse for known OSes and versions
    for os_lower, versions in KNOWN_OSES.iteritems():
        if os_lower in lower_name:
            for version in versions:
                if version.lower() in lower_name:
                    os_name = '%s %s' % (os_lower.title(), version)
                    LOG.debug("Identified image as known OS: %s", os_name)
                    return {'name': name, 'os': os_name, 'type': 'linux'}

    if ' LTS ' in name:
        #NOTE: hack to find some images by name in Rackspace
        os_name = name.split(' LTS ')[0].split(' (')[0]
        LOG.debug("Identified image by name split: %s", os_name)
        return {'name': name, 'os': os_name, 'type': 'linux'}

    #NOTE: hack to make our blueprints work with iNova
    if 'LTS' in name:
        os_name = name.split('LTS')[0].strip()
        LOG.debug("Identified image by iNova name: %s", os_name)
        return {'name': name, 'os': os_name, 'type': 'linux'}

    if not os_name:
        LOG.debug("Could not identify image: %s", name,
                  extra={'metadata': metadata})
    return {}


@caching.Cache(timeout=3600, sensitive_args=[1], store=API_FLAVOR_CACHE,
               backing_store=REDIS, backing_store_key='rax.compute.flavors')
def _get_flavors(api_endpoint, auth_token):
    '''Ask Nova for Flavors (RAM, CPU, HDD) options.'''
    assert api_endpoint, "No API endpoint specified when getting flavors"
    plugin = AuthPlugin(auth_token, api_endpoint)
    insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1', 'true']
    try:
        api = client.Client('fake-user', 'fake-pass', 'fake-tenant',
                            insecure=insecure, auth_system="rackspace",
                            auth_plugin=plugin)
        LOG.info("Calling Nova to get flavors for %s", api_endpoint)
        flavors = api.flavors.list()
        result = {
            'flavors': {
                str(f.id): {
                    'name': f.name,
                    'memory': f.ram,
                    'disk': f.disk,
                    'cores': f.vcpus,
                } for f in flavors
            }
        }
        LOG.debug("Identified flavors: %s", result['flavors'].keys(),
                  extra={'data': result})
    except Exception as exc:
        LOG.error("Error retrieving Cloud Server flavors from %s: %s",
                  api_endpoint, exc)
        raise
    return result


@caching.Cache(timeout=1800, sensitive_args=[1], store=API_LIMITS_CACHE,
               backing_store=REDIS, backing_store_key='rax.compute.limits')
def _get_limits(api_endpoint, auth_token):
    '''Retrieve account limits as a dict.'''
    plugin = AuthPlugin(auth_token, api_endpoint)
    insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1', 'true']
    api = client.Client('fake-user', 'fake-pass', 'fake-tenant',
                        insecure=insecure, auth_system="rackspace",
                        auth_plugin=plugin)
    LOG.info("Calling Nova to get limits for %s", api_endpoint)
    api_limits = api.limits.get()

    def limits_dict(limits):
        '''Convert limits to dict.'''
        d = {}
        for limit in limits:
            d[limit.name.encode('ascii')] = limit.value
        return d
    return limits_dict(api_limits.absolute)


def _on_failure(exc, task_id, args, kwargs, einfo, action, method):
    '''Handle task failure.'''
    dep_id = args[0].get('deployment_id')
    key = args[0].get('resource_key')
    if dep_id and key:
        k = "instance:%s" % key
        ret = {
            k: {
                'status': 'ERROR',
                'status-message': (
                    'Unexpected error %s compute instance %s' % (action, key)
                ),
                'error-message': str(exc)
            }
        }
        resource_postback.delay(dep_id, ret)
    else:
        LOG.error("Missing deployment id and/or resource key in "
                  "%s error callback.", method)
#
# Celery Tasks
#


# pylint: disable=R0913
@task
@statsd.collect
def create_server(context, name, region, api_object=None, flavor="2",
                  files=None, image=None, tags=None):
    '''Create a Rackspace Cloud server using novaclient.

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
    :Example:

    {
      '/root/.ssh/authorized_keys': "base64 encoded content..."
    }
    :param tags: metadata tags to add
    :return: dict of created server
    :rtype: dict
    :Example:

    {
      id: "uuid...",
      password: "secret"
    }

    '''

    deployment_id = context["deployment_id"]
    resource_key = context['resource_key']
    instance_key = 'instance:%s' % resource_key
    if context.get('simulation') is True:
        results = {
            'instance:%s' % resource_key: {
                'id': str(1000 + int(resource_key)),
                'status': "BUILD",
                'password': 'RandomPass',
            }
        }
        # Send data back to deployment
        resource_postback.delay(deployment_id, results)
        return results

    match_celery_logging(LOG)

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handles task failure."""
        action = "creating"
        method = "create_server"
        _on_failure(exc, task_id, args, kwargs, einfo, action, method)

    reset_failed_resource_task.delay(deployment_id, resource_key)
    create_server.on_failure = on_failure

    if api_object is None:
        api_object = Provider.connect(context, region)

    LOG.debug('Image=%s, Flavor=%s, Name=%s, Files=%s', image, flavor, name,
              files)

    # Check image and flavor IDs (better descriptions if we error here)
    image_object = api_object.images.find(id=image)
    LOG.debug("Image id %s found. Name=%s", image, image_object.name)
    flavor_object = api_object.flavors.find(id=str(flavor))
    LOG.debug("Flavor id %s found. Name=%s", flavor, flavor_object.name)

    # Add RAX-CHECKMATE to metadata
    # support old way of getting metadata from generate_template
    meta = tags or context.get("metadata", None)
    try:
        server = api_object.servers.create(name, image_object, flavor_object,
                                           meta=meta, files=files,
                                           disk_config='AUTO')
    except OverLimit as exc:
        raise CheckmateRetriableException(str(exc),
                                          get_class_name(exc),
                                          "You have reached the maximum "
                                          "number of servers that can be "
                                          "spun up using this account. "
                                          "Please delete some servers to "
                                          "continue or contact your support "
                                          "team to increase your limit",
                                          "")

    # Update task in workflow
    create_server.update_state(state="PROGRESS",
                               meta={"server.id": server.id})
    LOG.info('Created server %s (%s) for deployment %s.', name, server.id,
             deployment_id)

    results = {
        instance_key: {
            'id': server.id,
            'password': server.adminPass,
            'region': api_object.client.region_name,
            'status': 'NEW',
            'flavor': flavor,
            'image': image,
            'error-message': '',
            'status-message': '',
        }
    }

    # Send data back to deployment
    resource_postback.delay(deployment_id, results)
    return results


@task
@statsd.collect
def sync_resource_task(context, resource, resource_key, api=None):
    """Syncs resource status with provider status."""
    match_celery_logging(LOG)
    key = "instance:%s" % resource_key
    if context.get('simulation') is True:
        return {
            key: {
                'status': resource.get('status', 'DELETED')
            }
        }

    if api is None:
        api = Provider.connect(context, resource.get("region"))
    try:
        instance = resource.get("instance") or {}
        instance_id = instance.get("id")
        if not instance_id:
            raise CheckmateDoesNotExist("Instance is blank or has no ID")
        LOG.debug("About to query for server %s", instance_id)
        server = api.servers.get(instance_id)
        return {
            key: {
                'status': server.status
            }
        }
    except (NotFound, CheckmateDoesNotExist):
        return {
            key: {
                'status': 'DELETED'
            }
        }
    except BadRequest as exc:
        if exc.http_status == 400 and exc.message == 'n/a':
            # This is a token expiration failure. Nova probably tried to
            # re-auth and used our dummy data
            raise CheckmateNoTokenError("Auth token expired")


@task(default_retry_delay=30, max_retries=120)
@statsd.collect
def delete_server_task(context, api=None):
    '''Celery Task to delete a Nova compute instance.'''
    match_celery_logging(LOG)

    assert "deployment_id" in context, "No deployment id in context"
    assert "resource_key" in context, "No resource key in context"
    assert "region" in context, "No region provided"
    assert 'resource' in context, "No resource definition provided"

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handles task failure."""
        action = "deleting"
        method = "delete_server_task"
        _on_failure(exc, task_id, args, kwargs, einfo, action, method)

    delete_server_task.on_failure = on_failure

    key = context.get("resource_key")
    inst_key = "instance:%s" % key

    if api is None and context.get('simulation') is not True:
        api = Provider.connect(context, region=context.get("region"))
    server = None
    inst_id = context.get("instance_id")
    resource = context.get('resource')
    resource_key = context.get('resource_key')
    deployment_id = context.get('deployment_id')

    if inst_id is None:
        msg = ("Instance ID is not available for Compute Instance, skipping "
               "delete_server_task for resource %s in deployment %s" %
               (resource_key, deployment_id))
        LOG.info(msg)
        results = {
            inst_key: {
                'status': 'DELETED',
                'status-message': msg
            }
        }
        resource_postback.delay(deployment_id, results)
        return
    ret = {}
    try:
        if context.get('simulation') is not True:
            server = api.servers.get(inst_id)
    except (NotFound, NoUniqueMatch):
        LOG.warn("Server %s already deleted", inst_id)
    if (not server) or (server.status == 'DELETED'):
        ret = {
            inst_key: {
                'status': 'DELETED',
                'status-message': ''
            }
        }
        if 'hosts' in resource:
            for comp_key in resource.get('hosts', []):
                ret.update({'instance:%s' % comp_key: {'status': 'DELETED',
                            'status-message': ''}})
    elif server.status in ['ACTIVE', 'ERROR', 'SHUTOFF']:
        ret = {}
        ret.update({
            inst_key: {
                'status': 'DELETING',
                'status-message': 'Waiting on resource deletion'
            }
        })
        if 'hosts' in resource:
            for comp_key in resource.get('hosts', []):
                ret.update({
                    'instance:%s' % comp_key: {
                        'status': 'DELETING',
                        'status-message': 'Host %s is being deleted.' % key
                    }
                })
        server.delete()
    else:
        msg = ('Instance is in state %s. Waiting on ACTIVE resource.'
               % server.status)
        resource_postback.delay(context.get("deployment_id"),
                                {inst_key: {'status': 'DELETING',
                                            'status-message': msg}})
        delete_server_task.retry(exc=CheckmateException(msg))
    resource_postback.delay(context.get("deployment_id"), ret)
    return ret


@task(default_retry_delay=30, max_retries=120)
@statsd.collect
def wait_on_delete_server(context, api=None):
    '''Wait for a server resource to be deleted.'''
    match_celery_logging(LOG)
    assert "deployment_id" in context, "No deployment id in context"
    assert "resource_key" in context, "No resource key in context"
    assert "region" in context, "No region provided"
    assert 'resource' in context, "No resource definition provided"

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handles task failure."""
        action = "while waiting on"
        method = "wait_on_delete_server"
        _on_failure(exc, task_id, args, kwargs, einfo, action, method)

    wait_on_delete_server.on_failure = on_failure

    key = context.get("resource_key")
    inst_key = "instance:%s" % key
    resource = context.get('resource')
    if api is None and context.get('simulation') is not True:
        api = Provider.connect(context, region=context.get("region"))
    server = None
    inst_id = context.get("instance_id")

    resource_key = context.get('resource_key')
    deployment_id = context.get('deployment_id')

    if inst_id is None:
        msg = ("Instance ID is not available for Compute Instance, "
               "skipping wait_on_delete_task for resource %s in deployment %s"
               % (resource_key, deployment_id))
        LOG.info(msg)
        results = {
            inst_key: {
                'status': 'DELETED',
                'status-message': msg
            }
        }
        resource_postback.delay(deployment_id, results)
        return

    ret = {}
    try:
        if context.get('simulation') is not True:
            server = api.servers.find(id=inst_id)
    except (NotFound, NoUniqueMatch):
        pass
    if (not server) or (server.status == "DELETED"):
        ret = {
            inst_key: {
                'status': 'DELETED',
                'status-message': ''
            }
        }
        if 'hosts' in resource:
            for hosted in resource.get('hosts', []):
                ret.update({
                    'instance:%s' % hosted: {
                        'status': 'DELETED',
                        'status-message': ''
                    }
                })
    else:
        msg = ('Instance is in state %s. Waiting on DELETED resource.'
               % server.status)
        resource_postback.delay(context.get("deployment_id"),
                                {inst_key: {'status': 'DELETING',
                                            'status-message': msg}})
        wait_on_delete_server.retry(exc=CheckmateException(msg))
    resource_postback.delay(context.get("deployment_id"), ret)
    return ret


# max 60 minute wait
# pylint: disable=W0613
@task(default_retry_delay=30, max_retries=120,
      acks_late=True)
@statsd.collect
def wait_on_build(context, server_id, region, resource,
                  ip_address_type='public', verify_up=True, username='root',
                  timeout=10, password=None, identity_file=None, port=22,
                  api_object=None, private_key=None):
    '''Checks build is complete and. optionally, that SSH is working.

    :param ip_adress_type: the type of IP addresss to return as 'ip' in the
        response
    :param prefix: a string to prepend to any results. Used by Spiff and
            Checkmate
    :returns: False when build not ready. Dict with ip addresses when done.
    '''
    match_celery_logging(LOG)
    deployment_id = context["deployment_id"]
    resource_key = context['resource_key']
    instance_key = 'instance:%s' % resource_key

    if context.get('simulation') is True:
        results = {
            instance_key: {
                'status': "ACTIVE",
                'status-message': "",
                'ip': '4.4.4.%s' % resource_key,
                'public_ip': '4.4.4.%s' % resource_key,
                'private_ip': '10.1.2.%s' % resource_key,
                'addresses': {
                    'public': [
                        {
                            "version": 4,
                            "addr": "4.4.4.%s" % resource_key,
                        },
                        {
                            "version": 6,
                            "addr": "2001:babe::ff04:36c%s" % resource_key,
                        }
                    ],
                    'private': [
                        {
                            "version": 4,
                            "addr": "10.1.2.%s" % resource_key,
                        }
                    ]
                }
            }
        }
        # Send data back to deployment
        resource_postback.delay(deployment_id, results)
        return results

    if api_object is None:
        api_object = Provider.connect(context, region)

    assert server_id, "ID must be provided"
    LOG.debug("Getting server %s", server_id)
    try:
        server = api_object.servers.find(id=server_id)
    except (NotFound, NoUniqueMatch):
        msg = "No server matching id %s" % server_id
        LOG.error(msg, exc_info=True)
        raise CheckmateUserException(msg, get_class_name(CheckmateException),
                                     UNEXPECTED_ERROR, '')

    results = {
        'id': server_id,
        'status': server.status,
        'addresses': server.addresses,
        'region': api_object.client.region_name,
    }

    if server.status == 'ERROR':
        results = {
            instance_key: {
                'status': 'ERROR',
                'status-message': "Server %s build failed" % server_id,
            }
        }

        resource_postback.delay(deployment_id, results)
        context["instance_id"] = server_id
        chain(delete_server_task.si(context), wait_on_delete_server.si(
            context)).apply_async()

        raise CheckmateRetriableException(
            results[instance_key]['status-message'],
            get_class_name(CheckmateServerBuildFailed()),
            results[instance_key]['status-message'],
            '')

    if server.status == 'BUILD':
        results['progress'] = server.progress
        results['status-message'] = "%s%% Complete" % server.progress
        #countdown = 100 - server.progress
        #if countdown <= 0:
        #    countdown = 15  # progress is not accurate. Allow at least 15s
        #           # wait
        wait_on_build.update_state(state='PROGRESS', meta=results)
        # progress indicate shows percentage, give no inidication of seconds
        # left to build.
        # It often, if not usually takes at least 30 seconds after a server
        # hits 100% before it will be "ACTIVE".  We used to use % left as a
        # countdown value, but reverting to the above configured countdown.
        msg = ("Server '%s' progress is %s. Retrying after 30 seconds" % (
               server_id, server.progress))
        LOG.debug(msg)
        results['progress'] = server.progress
        resource_postback.delay(deployment_id, {instance_key: results})
        return wait_on_build.retry(exc=CheckmateException(msg))

    if server.status != 'ACTIVE':
        # this may fail with custom/unexpected statuses like "networking"
        # or a manual rebuild performed by the user to fix some problem
        # so lets retry instead and notify via the normal task mechanisms
        msg = ("Server '%s' status is %s, which is not recognized. "
               "Not assuming it is active" % (server_id, server.status))
        results['status-message'] = msg
        resource_postback.delay(deployment_id, {instance_key: results})
        return wait_on_build.retry(exc=CheckmateException(msg))

    # if a rack_connect account, wait for rack_connect configuration to finish
    if 'rack_connect' in context['roles']:
        if 'rackconnect_automation_status' not in server.metadata:
            msg = ("Rack Connect server still does not have the "
                   "'rackconnect_automation_status' metadata tag")
            results['status-message'] = msg
            resource_postback.delay(deployment_id,
                                    {instance_key: results})
            wait_on_build.retry(exc=CheckmateException(msg))
        else:
            if server.metadata['rackconnect_automation_status'] == 'DEPLOYED':
                LOG.debug("Rack Connect server ready. Metadata found'")
            else:
                msg = ("Rack Connect server 'rackconnect_automation_status' "
                       "metadata tag is still not 'DEPLOPYED'. It is '%s'" %
                       server.metadata.get('rackconnect_automation_status'))
                results['status-message'] = msg
                resource_postback.delay(deployment_id,
                                        {instance_key: results})
                wait_on_build.retry(exc=CheckmateException(msg))

    # should be active now, grab an appropriate address and check connectivity
    ip = None
    if server.addresses:
        # Get requested IP
        addresses = server.addresses.get(ip_address_type or 'public', [])
        for address in addresses:
            if address['version'] == 4:
                ip = address['addr']
                break
        if ((ip_address_type != 'public' and server.accessIPv4) or
                'rack_connect' in context['roles']):
            ip = server.accessIPv4
            LOG.info("Using accessIPv4 to connect: %s", ip)
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

    # we might not get an ip right away, so wait until its populated
    if not ip:
        return wait_on_build.retry(exc=CheckmateException(
                                   "Could not find IP of server '%s'" %
                                   server_id))

    if verify_up:
        isup = False
        image_details = api_object.images.find(id=server.image['id'])
        metadata = image_details.metadata
        if ((metadata and metadata['os_type'] == 'linux') or
                ('windows' not in image_details.name.lower())):
            msg = "Server '%s' is ACTIVE but 'ssh %s@%s -p %d' is failing " \
                  "to connect." % (server_id, username, ip, port)
            isup = checkmate.ssh.test_connection(context, ip, username,
                                                 timeout=timeout,
                                                 password=password,
                                                 identity_file=identity_file,
                                                 port=port,
                                                 private_key=private_key)
        else:
            msg = "Server '%s' is ACTIVE but is not responding to ping " \
                  " attempts" % server_id
            isup = checkmate.rdp.test_connection(context, ip,
                                                 timeout=timeout)

        if not isup:
            # try again in half a second but only wait for another 2 minutes
            results['status-message'] = msg
            resource_postback.delay(deployment_id,
                                    {instance_key: results})
            raise wait_on_build.retry(exc=CheckmateException(msg),
                                      countdown=0.5,
                                      max_retries=240)
    else:
        LOG.info("Server '%s' is ACTIVE. Not verified to be up", server_id)

    # Check to see if we have another resource that needs to install on this
    # server
    # if 'hosts' in resource:
    #    results['status'] = "CONFIGURE"
    # else:
    results['status'] = "ACTIVE"
    results['status-message'] = ''
    results = {instance_key: results}
    resource_postback.delay(deployment_id, results)
    return results
