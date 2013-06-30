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
from SpiffWorkflow.operators import PathAttrib
from SpiffWorkflow.specs import Celery

from checkmate.common import caching
from checkmate.deployments import (
    resource_postback,
    alt_resource_postback,
)
from checkmate.deployments.tasks import reset_failed_resource_task
from checkmate.exceptions import (
    CheckmateDoesNotExist,
    CheckmateNoTokenError,
    CheckmateNoMapping,
    CheckmateException,
    CheckmateRetriableException,
    CheckmateServerBuildFailed,
)
from checkmate.middleware import RequestContext
from checkmate.providers import ProviderBase, user_has_access
import checkmate.rdp
import checkmate.ssh
from checkmate.utils import (
    match_celery_logging,
    isUUID,
    yaml_to_dict,
    get_class_name,
)
from checkmate.workflow import wait_for


LOG = logging.getLogger(__name__)
UBUNTU_12_04_IMAGE_ID = "5cebb13a-f783-4f8c-8058-c4182c724ccd"
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


class RackspaceComputeProviderBase(ProviderBase):
    """Generic functions for rackspace Compute providers."""
    vendor = 'rackspace'

    def __init__(self, provider, key=None):
        ProviderBase.__init__(self, provider, key=key)
        #kwargs added to server creation calls (contain things like ssh keys)
        self._kwargs = {}
        with open(os.path.join(os.path.dirname(__file__),
                               "managed_cloud",
                               "delay.sh")) as open_file:
            self.managed_cloud_script = open_file.read()

    def prep_environment(self, wfspec, deployment, context):
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
            raise CheckmateException("Could not identify which region to "
                                     "create servers in")

        catalog = self.get_catalog(context)

        # Find and translate image
        image = deployment.get_setting('os', resource_type=resource_type,
                                       service_name=service,
                                       provider_key=self.key,
                                       default='Ubuntu 12.04')

        if not isUUID(image):
            # Assume it is an OS name and find it
            for key, value in catalog['lists']['types'].iteritems():
                if image == value['name'] or image == value['os']:
                    LOG.debug("Mapping image from '%s' to '%s'", image, key)
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
            template['flavor'] = flavor
            template['image'] = image
            template['region'] = region
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
        create_server_task = Celery(
            wfspec, 'Create Server %s (%s)' % (key, resource['service']),
            'checkmate.providers.rackspace.compute.create_server',
            call_args=[
                context.get_queued_task_dict(deployment=deployment['id'],
                                             resource=key,
                                             region=resource['region']),
                resource.get('dns-name'),
                resource['region']
            ],
            image=resource.get('image', UBUNTU_12_04_IMAGE_ID),
            flavor=resource.get('flavor', "2"),
            files=self._kwargs.get('files', None),
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
                context.get_queued_task_dict(deployment=deployment['id'],
                                             resource=key),
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
                    context.get_queued_task_dict(deployment=deployment['id'],
                                                 resource=key),
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
        join = wait_for(wfspec, create_server_task, wait_on,
                        name="Server Wait on:%s (%s)" % (key,
                                                         resource['service']))

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

    def delete_resource_tasks(self, context, deployment_id, resource, key):
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
        return chain(delete_server_task.s(context),
                     alt_resource_postback.s(deployment_id),
                     wait_on_delete_server.si(context),
                     alt_resource_postback.s(deployment_id))

    @staticmethod
    def _get_api_info(context):
        '''Get Flavors, Images and Types available in a given Region.'''
        region = getattr(context, 'region', None)
        if not region:
            region = Provider.find_a_region(context.catalog)
        url = Provider.find_url(context.catalog, region)
        jobs = eventlet.GreenPile(2)
        jobs.spawn(_get_flavors, url, context.auth_token)
        jobs.spawn(_get_images_and_types, url, context.auth_token)
        vals = {}
        for ret in jobs:
            vals.update(ret)
        return vals

    def get_catalog(self, context, type_filter=None):
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

        vals = self._get_api_info(context)

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
            if key == 'types':
                types = vals['types']
            if key == 'images':
                images = vals['images']

        if type_filter is None or type_filter == 'compute':
            #TODO: add regression tests - copy.copy was leaking across tenants
            results['compute'] = copy.deepcopy(CATALOG_TEMPLATE['compute'])
            linux = results['compute']['linux_instance']
            windows = results['compute']['windows_instance']
            if types:
                for image in types.values():
                    choice = dict(name=image['name'], value=image['os'])
                    if 'Windows' in image['os']:
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
            self._dict['catalog'] = results
        return results

    @staticmethod
    def find_url(catalog, region):
        '''Get the Public URL of a service.'''
        fall_back = None
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
        return fall_back

    @staticmethod
    def find_a_region(catalog):
        '''Any region.'''
        fall_back = None
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
        return fall_back

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

        os.environ['NOVA_RAX_AUTH'] = "Yes Please!"
        insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1',
                                                                    'true']
        api = client.Client('ignore', 'ignore', None, 'localhost',
                            insecure=insecure)
        api.client.auth_token = context.auth_token

        url = Provider.find_url(context.catalog, region)
        api.client.management_url = url

        return api


@caching.Cache(timeout=3600, sensitive_args=[1], store=API_IMAGE_CACHE)
def _get_images_and_types(api_endpoint, auth_token):
    '''Ask Nova for Images and Types.'''
    insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1', 'true']
    api = client.Client('ignore', 'ignore', None, 'localhost',
                        insecure=insecure)
    api.client.auth_token = auth_token
    api.client.management_url = api_endpoint

    ret = {'images': {}, 'types': {}}
    LOG.info("Calling Nova to get images for %s", api.client.management_url)
    images = api.images.list()
    for i in images:
        if 'LAMP' in i.name:
            continue
        img = {
            'name': i.name,
            'os': i.name.split(' LTS ')[0].split(' (')[0]
        }
        #FIXME: hack to make our blueprints work with Private OpenStack
        if 'precise' in img['os']:
            img['os'] = 'Ubuntu 12.04'
        ret['types'][str(i.id)] = img
        ret['images'][i.id] = {'name': i.name}
    return ret


@caching.Cache(timeout=3600, sensitive_args=[1], store=API_FLAVOR_CACHE)
def _get_flavors(api_endpoint, auth_token):
    '''Ask Nova for Flavors (RAM, CPU, HDD) options.'''
    insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1', 'true']
    api = client.Client('ignore', 'ignore', None, 'localhost',
                        insecure=insecure)
    api.client.auth_token = auth_token
    api.client.management_url = api_endpoint

    LOG.info("Calling Nova to get flavors for %s", api.client.management_url)
    flavors = api.flavors.list()
    return {
        'flavors': {
            str(f.id): {
                'name': f.name,
                'memory': f.ram,
                'disk': f.disk,
                'cores': f.vcpus,
            } for f in flavors
        }
    }


@caching.Cache(timeout=1800, sensitive_args=[1], store=API_LIMITS_CACHE)
def _get_limits(api_endpoint, auth_token):
    insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1', 'true']
    api = client.Client('ignore', 'ignore', None, 'localhost',
                        insecure=insecure)
    api.client.auth_token = auth_token
    api.client.management_url = api_endpoint
    api_limits = api.limits.get()

    def limits_dict(limits):
        d = {}
        for limit in limits:
            d[limit.name.encode('ascii')] = limit.value
        return d
    return limits_dict(api_limits.absolute)


REGION_MAP = {'dallas': 'DFW',
              'chicago': 'ORD',
              'london': 'LON'}


def _on_failure(exc, task_id, args, kwargs, einfo, action, method):
    '''Handle task failure.'''
    dep_id = args[0].get('deployment')
    key = args[0].get('resource')
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
def create_server(context, name, region, api_object=None, flavor="2",
                  files=None, image=UBUNTU_12_04_IMAGE_ID, tags=None):
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

    deployment_id = context["deployment"]
    if context.get('simulation') is True:
        resource_key = context['resource']
        results = {
            'instance:%s' % resource_key: {
                'id': str(1000 + int(resource_key)),
                'status': "BUILD",
                'password': 'RandomPass',
            }
        }
        # Send data back to deployment
        resource_postback.delay(context['deployment'], results)
        return results

    match_celery_logging(LOG)

    def on_failure(exc, task_id, args, kwargs, einfo):
        action = "creating"
        method = "create_server"
        _on_failure(exc, task_id, args, kwargs, einfo, action, method)

    reset_failed_resource_task.delay(deployment_id, context["resource"])
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
    instance_key = 'instance:%s' % context['resource']
    try:
        server = api_object.servers.create(name, image_object, flavor_object,
                                           meta=meta, files=files)
    except OverLimit as exc:
        raise CheckmateRetriableException("You have reached the maximum "
                                          "number of servers that can be "
                                          "spun up using this account. "
                                          "Please delete some servers to "
                                          "continue or contact your support "
                                          "team to increase your limit", "",
                                          get_class_name(exc),
                                          action_required=True)

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
            'image': image
        }
    }

    # Send data back to deployment
    resource_postback.delay(context['deployment'], results)
    return results


@task
def sync_resource_task(context, resource, resource_key, api=None):
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
def delete_server_task(context, api=None):
    '''Celery Task to delete a Nova compute instance.'''
    match_celery_logging(LOG)

    assert "deployment_id" in context, "No deployment id in context"
    assert "resource_key" in context, "No resource key in context"
    assert "region" in context, "No region provided"
    assert "instance_id" in context, "No server id provided"
    assert 'resource' in context, "No resource definition provided"

    def on_failure(exc, task_id, args, kwargs, einfo):
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
        return ret
    if server.status in ['ACTIVE', 'ERROR', 'SHUTOFF']:
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
        LOG.info("Deleted server %s", inst_id)
        return ret
    else:
        msg = ('Instance is in state %s. Waiting on ACTIVE resource.'
               % server.status)
        resource_postback.delay(context.get("deployment_id"),
                                {inst_key: {'status': 'DELETING',
                                            'status-message': msg}})
        delete_server_task.retry(exc=CheckmateException(msg))


@task(default_retry_delay=30, max_retries=120)
def wait_on_delete_server(context, api=None):
    '''Wait for a server resource to be deleted.'''
    match_celery_logging(LOG)
    assert "deployment_id" in context, "No deployment id in context"
    assert "resource_key" in context, "No resource key in context"
    assert "region" in context, "No region provided"
    assert "instance_id" in context, "No server id provided"
    assert 'resource' in context, "No resource definition provided"

    def on_failure(exc, task_id, args, kwargs, einfo):
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
        return ret
    else:
        msg = ('Instance is in state %s. Waiting on DELETED resource.'
               % server.status)
        resource_postback.delay(context.get("deployment_id"),
                                {inst_key: {'status': 'DELETING',
                                            'status-message': msg}})
        wait_on_delete_server.retry(exc=CheckmateException(msg))


# max 60 minute wait
# pylint: disable=W0613
@task(default_retry_delay=30, max_retries=120,
      acks_late=True)
def wait_on_build(context, server_id, region, resource,
                  ip_address_type='public', verify_up=True, username='root',
                  timeout=10, password=None, identity_file=None, port=22,
                  api_object=None, private_key=None):
    """Checks build is complete and. optionally, that SSH is working.

    :param ip_adress_type: the type of IP addresss to return as 'ip' in the
        response
    :param prefix: a string to prepend to any results. Used by Spiff and
            Checkmate
    :returns: False when build not ready. Dict with ip addresses when done.
    """
    match_celery_logging(LOG)

    if context.get('simulation') is True:
        resource_key = context['resource']
        results = {
            'instance:%s' % resource_key: {
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
        resource_postback.delay(context['deployment'], results)
        return results

    if api_object is None:
        api_object = Provider.connect(context, region)

    assert server_id, "ID must be provided"
    LOG.debug("Getting server %s", server_id)
    server = None
    try:
        server = api_object.servers.find(id=server_id)
    except (NotFound, NoUniqueMatch):
        msg = "No server matching id %s" % server_id
        LOG.error(msg, exc_info=True)
        raise CheckmateException(msg)

    results = {
        'id': server_id,
        'status': server.status,
        'addresses': server.addresses,
        'region': api_object.client.region_name,
    }
    instance_key = 'instance:%s' % context['resource']

    if server.status == 'ERROR':
        results = {'status': 'ERROR',
                   'status-message': "Server %s build failed" % server_id}
        results = {instance_key: results}
        resource_postback.delay(context['deployment'], results)
        Provider({}).delete_resource_tasks(context,
                                           context['deployment'],
                                           get_resource_by_id(
                                               context['deployment'],
                                               context['resource']),
                                           context['resource']).apply_async()
        raise CheckmateRetriableException("Server %s build failed" % server_id,
                                          "",
                                          get_class_name(
                                              CheckmateServerBuildFailed()),
                                          action_required=True)

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
        resource_postback.delay(context['deployment'], {instance_key: results})
        return wait_on_build.retry(exc=CheckmateException(msg))

    if server.status != 'ACTIVE':
        # this may fail with custom/unexpected statuses like "networking"
        # or a manual rebuild performed by the user to fix some problem
        # so lets retry instead and notify via the normal task mechanisms
        msg = ("Server '%s' status is %s, which is not recognized. "
               "Not assuming it is active" % (server_id, server.status))
        results['status-message'] = msg
        resource_postback.delay(context['deployment'], {instance_key: results})
        return wait_on_build.retry(exc=CheckmateException(msg))

    # if a rack_connect account, wait for rack_connect configuration to finish
    if 'rack_connect' in context['roles']:
        if 'rackconnect_automation_status' not in server.metadata:
            msg = ("Rack Connect server still does not have the "
                   "'rackconnect_automation_status' metadata tag")
            results['status-message'] = msg
            resource_postback.delay(context['deployment'],
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
                resource_postback.delay(context['deployment'],
                                        {instance_key: results})
                wait_on_build.retry(exc=CheckmateException(msg))

    # should be active now, grab an appropriate address and check connectivity
    ip = None
    if server.addresses:
        # Get requested IP
        if ip_address_type != 'public':
            addresses = server.addresses.get(ip_address_type or 'public', [])
            for address in addresses:
                if address['version'] == 4:
                    ip = address['addr']
                    break
        else:
            ip = server.accessIPv4
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
        if image_details.metadata['os_type'] == 'linux':
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
            resource_postback.delay(context['deployment'],
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
    instance_key = 'instance:%s' % context['resource']
    results = {instance_key: results}
    resource_postback.delay(context['deployment'], results)
    return results
