"""
Provider for Rackspace Cloud Servers 1.0 API
"""
import copy
import logging

import openstack.compute
from SpiffWorkflow.operators import PathAttrib
from SpiffWorkflow.specs import Celery

from checkmate.deployments import resource_postback
from checkmate.exceptions import (
    CheckmateNoTokenError,
    CheckmateNoMapping,
    CheckmateException,
    CheckmateRetriableException,
)
from checkmate.providers.rackspace.compute import RackspaceComputeProviderBase
from checkmate.utils import match_celery_logging, yaml_to_dict
from checkmate.workflow import wait_for
from openstack.compute.exceptions import OverLimit

LOG = logging.getLogger(__name__)
# This supports translating airport codes to city names. Checkmate expects to
# deal in the region name as defined in the service catalog, which is in
# airport codes.
REGION_MAP = {
    'dallas': 'DFW',
    'chicago': 'ORD',
    'london': 'LON',
    'sydney': 'SYD',
}
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


class Provider(RackspaceComputeProviderBase):
    name = 'legacy'

    def generate_template(self, deployment, resource_type, service, context,
                          index, key, definition):
        templates = RackspaceComputeProviderBase.generate_template(
            self, deployment, resource_type, service,
            context, index, key, definition
        )
        print templates

        catalog = self.get_catalog(context)

        # Get region
        region = deployment.get_setting('region', resource_type=resource_type,
                                        service_name=service,
                                        provider_key=self.key)
        if not region:
            LOG.warning("No region specified for Legacy Compute provider in "
                        "deployment.")
        else:
            # Convert to and use airport codes
            if region in REGION_MAP:
                region = REGION_MAP[region]

            # If legacy region is specified, make sure it matches catalog
            # region
            region_catalog = self.get_catalog(context, type_filter='regions')
            legacy_regions = region_catalog.get('lists', {}).get('regions', {})

            if not region:
                pass  # region not specified. Assume blueprint does not care.
            elif region not in legacy_regions:
                if legacy_regions:
                    raise CheckmateException("Legacy set to spin up in '%s'. "
                                             "Cannot provision servers "
                                             "in '%s'." %
                                             (legacy_regions.keys()[0],
                                                 region))
                else:
                    LOG.warning("Region %s specified in deployment, but no "
                                "regions are specified in the Legacy Compute "
                                "catalog" % region)
            else:
                LOG.warning("Region %s specified in deployment, but not in "
                            "Legacy Compute catalog" % region)

        image = deployment.get_setting('os',
                                       resource_type=resource_type,
                                       service_name=service,
                                       provider_key=self.key,
                                       default=119)
        if isinstance(image, int):
            image = str(image)
        if not image.isdigit():
            # Assume it is an OS name and find it
            for key, value in catalog['lists']['types'].iteritems():
                if image == value['name'] or image == value['os']:
                    LOG.debug("Mapping image from '%s' to '%s'" % (image, key))
                    image = key
                    break
        if image not in catalog['lists']['types']:
            raise CheckmateNoMapping("No image mapping for '%s' in '%s'" % (
                image, self.name))

        # Get setting
        flavor = None
        memory = self.parse_memory_setting(deployment.get_setting('memory',
                                           resource_type=resource_type,
                                           service_name=service,
                                           provider_key=self.key,
                                           default=512))

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
            raise CheckmateNoMapping(
                "No flavor mapping for '%s' in '%s'" % (memory, self.key)
            )
        for template in templates:
            template['flavor'] = flavor
            template['image'] = image
            if region:
                template['region'] = region
        return templates

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        """
        :param resource: the dict of the resource generated by
                generate_template earlier
        :returns: returns the root task in the chain of tasks
        TODO: use environment keys instead of private key
        """
        create_server_task = Celery(
            wfspec, 'Create Server %s (%s)' % (key, resource['service']),
            'checkmate.providers.rackspace.compute_legacy.create_server',
            call_args=[context.get_queued_task_dict(
                deployment=deployment['id'],
                resource=key),
                resource.get('dns-name')
            ],
            image=resource.get('image', 119),
            flavor=resource.get('flavor', 2),
            files=self._kwargs.get('files', None),
            ip_address_type='public',
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['create']
            ),
            properties={'estimated_duration': 20}
        )

        build_wait_task = Celery(
            wfspec,
            'Wait for Server %s (%s) build' % (key, resource['service']),
            'checkmate.providers.rackspace.compute_legacy.wait_on_build',
            call_args=[context.get_queued_task_dict(
                deployment=deployment['id'],
                resource=key),
                PathAttrib('instance:%s/id' % key)
            ],
            password=PathAttrib('instance:%s/password' % key),
            private_key=deployment.settings().get('keys', {}).get(
                'deployment', {}).get('private_key'),
            merge_results=True,
            properties={'estimated_duration': 150},
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['final']
            ),
            tag=self.generate_resource_tag(
                context.base_url,
                context.tenant,
                deployment['id'], key
            )
        )
        create_server_task.connect(build_wait_task)

        #If Managed Cloud, add a Completion task to release RBA
        # other providers may delay this task until they are done
        if 'rax_managed' in context.roles:
            touch_complete = Celery(
                wfspec,
                'Mark Server %s (%s) Complete' % (key, resource['service']),
                'checkmate.ssh.execute',
                call_args=[
                    PathAttrib("instance:%s/public_ip" % key),
                    "touch /tmp/checkmate-complete", "root"
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
        if getattr(self, 'prep_task', None):
            wait_on.append(self.prep_task)
        join = wait_for(
            wfspec,
            create_server_task,
            wait_on,
            name="Server %s (%s) Wait on Prerequisites" % (
                key,
                resource['service']
            ),
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['root']
            )
        )

        return dict(root=join, final=build_wait_task,
                    create=create_server_task)

    def get_catalog(self, context, type_filter=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one"""
        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #       this for every provider
        results = RackspaceComputeProviderBase.get_catalog(
            self,
            context,
            type_filter=type_filter
        )
        if results:
            # We have a prexisting or overriding catalog stored
            return results

        # build a live catalog this should be the on_get_catalog called if no
        # stored/override existed
        api = self.connect(context)
        images = None
        flavors = None

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context.catalog:
                if service['name'] == 'cloudServers':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        tenant_id = endpoint['tenantId']
                        if 'region' in endpoint:
                            if endpoint['region'] in REGION_MAP:
                                endpoint['region'] = REGION_MAP[endpoint[
                                    'region']]
                            regions[endpoint['region']] = endpoint['publicURL']
                        else:
                            region = api.servers.get_region(tenant_id)
                            endpoint['region'] = region
                            if endpoint['region'] in REGION_MAP:
                                endpoint['region'] = REGION_MAP[endpoint[
                                    'region']]
                            regions[endpoint['region']] = endpoint['publicURL']
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['regions'] = regions

        if type_filter is None or type_filter == 'compute':
            results['compute'] = copy.copy(CATALOG_TEMPLATE['compute'])
            linux = results['compute']['linux_instance']
            windows = results['compute']['windows_instance']
            if not images:
                images = self._images(api)
            for image in images.values():
                choice = dict(name=image['name'], value=image['os'])
                if 'Windows' in image['os']:
                    windows['options']['os']['choice'].append(choice)
                else:
                    linux['options']['os']['choice'].append(choice)

            if not flavors:
                flavors = self._flavors(api)
            for flavor in flavors.values():
                choice = dict(value=int(flavor['memory']),
                              name="%s (%s Gb disk)" % (flavor['name'],
                                                        flavor['disk']))
                linux['options']['memory']['choice'].append(choice)
                if flavor['memory'] >= 1024:  # Windows needs min 1Gb
                    windows['options']['memory']['choice'].append(choice)

        if type_filter is None or type_filter == 'type':
            if not images:
                images = self._images(api)
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['types'] = images
        if type_filter is None or type_filter == 'size':
            if not flavors:
                flavors = self._flavors(api)
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['sizes'] = flavors

        if type_filter is None or type_filter == 'image':
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['images'] = {
                str(i.id): {
                    'name': i.name
                }
                for i in api.images.list() if int(i.id) > 1000
            }

        self.validate_catalog(results)
        if type_filter is None:
            self._dict['catalog'] = results
        return results

    @staticmethod
    def _images(api):
        """Gets current tenant's images and formats them in Checkmate format"""
        images = api.images.list()
        results = {
            str(i.id): {
                'name': i.name,
                'os': i.name.split(' - ')[0].replace(' LTS', ''),
            }
            for i in images if int(i.id) < 1000 and 'LAMP' not in i.name
        }
        return results

    @staticmethod
    def _flavors(api):
        """
        Gets current tenant's flavors and formats them in Checkmate format
        """
        flavors = api.flavors.list()
        results = {
            str(f.id): {
                'name': f.name,
                'memory': f.ram,
                'disk': f.disk,
            }
            for f in flavors
        }
        return results

    @staticmethod
    def connect(context):
        """Use context info to connect to API and return api object"""
        #FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, dict):
            from checkmate.middleware import RequestContext
            context = RequestContext(**context)
        if not context.auth_token:
            raise CheckmateNoTokenError()
        api = openstack.compute.Compute()
        api.client.auth_token = context.auth_token

        def find_url(catalog):
            for service in catalog:
                if service['name'] == 'cloudServers':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        return endpoint['publicURL']

        url = find_url(context.catalog)
        api.client.management_url = url
        LOG.debug("Connected to legacy cloud servers using token of length %s "
                  "and url of %s" % (len(api.client.auth_token), url))
        return api

"""
  Celery tasks to manipulate Rackspace Cloud Servers.
"""
from celery.task import task  # @UnresolvedImport

from checkmate.ssh import test_connection


""" Celeryd tasks """


@task
def create_server(context, name, api_object=None, flavor=2, files=None,
                  image=119, ip_address_type='public', tags=None):
    """Create a Rackspace Cloud server.

    :param context: the context information
    :type context: dict
    :param name: the name of the server
    :param api_object: existing, authenticated connection to API
    :param image: the image ID to use when building the server (which OS)
    :param flavor: the size of the server
    :param files: a list of files to inject
    :type files: dict

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
      ip: "a.b.c.d",
      password: "secret"
    }

    """
    match_celery_logging(LOG)
    if api_object is None:
        api_object = Provider.connect(context)

    LOG.debug('Image=%s, Flavor=%s, Name=%s, Files=%s' % (
              image, flavor, name, files))

    # Check image and flavor IDs (better descriptions if we error here)
    image_object = api_object.images.find(id=int(image))
    LOG.debug("Image id %s found. Name=%s" % (image, image_object.name))
    flavor_object = api_object.flavors.find(id=int(flavor))
    LOG.debug("Flavor id %s found. Name=%s" % (flavor, flavor_object.name))

    # Add RAX-CHECKMATE to metadata
    # support old way of getting metadata from generate_template
    meta = tags or context.get("metadata", None)
    try:
        server = api_object.servers.create(
            image=int(image),
            flavor=int(flavor),
            name=name,
            meta=meta,
            files=files
        )
        create_server.update_state(state="PROGRESS",
                                   meta={"server.id": server.id})
        LOG.debug(
            'Created server %s (%s).  Admin pass = %s' % (
            name, server.id, server.adminPass))
    except openstack.compute.exceptions.Unauthorized:
        LOG.debug(
            'Cannot create server.  Bad username and apikey/authtoken '
            'combination.'
        )
        raise
    except OverLimit:
        raise CheckmateRetriableException("You have reached the maximum "
                                          "number of servers that can be "
                                          "spinned up using this account. "
                                          "Please delete some servers to "
                                          "continue",
                                          "")
    except Exception, exc:
        LOG.debug(
            'Error creating server %s (image: %s, flavor: %s) Error: %s' % (
            name, image, flavor, str(exc)))
        raise


    ip_address = str(server.addresses[ip_address_type][0])
    private_ip_address = str(server.addresses['private'][0])

    instance_key = 'instance:%s' % context['resource']
    results = {instance_key: dict(id=server.id, ip=ip_address,
               password=server.adminPass, private_ip=private_ip_address,
               status="BUILD")}
    # Send data back to deployment
    resource_postback.delay(context['deployment'],
                            results)  # @UndefinedVariable
    return results


@task(default_retry_delay=30, max_retries=120)
def wait_on_build(context, server_id, ip_address_type='public', check_ssh=True,
                  username='root', timeout=10, password=None,
                  identity_file=None, port=22, api_object=None,
                  private_key=None):
    """Checks build is complete and. optionally, that SSH is working.

    :param ip_adress_type: the type of IP addresss to return as 'ip' in the
        response
    :returns: False when build not ready. Dict with ip addresses when done.
    """
    match_celery_logging(LOG)
    if api_object is None:
        api_object = Provider.connect(context)

    assert server_id, "ID must be provided"
    LOG.debug("Getting server %s" % server_id)
    server = api_object.servers.find(id=server_id)
    results = {
        'id': server_id,
        'status': server.status,
        'addresses': _convert_v1_adresses_to_v2(server.addresses)
    }

    if server.status == 'ERROR':
        msg = "Server %s build failed" % server_id
        results = {'status': "ERROR"}
        results['error-message'] = msg
        instance_key = 'instance:%s' % context['resource']
        results = {instance_key: results}
        resource_postback.delay(context['deployment'], results)
        delete_server(context, server_id, api_object)
        raise CheckmateRetriableException(msg, "")

    ip = None
    if server.addresses:
        # Get requested IP
        addresses = server.addresses.get(ip_address_type or 'public', None)
        if addresses:
            if isinstance(addresses, list):
                ip = addresses[0]
            results['ip'] = ip

        # Get public (default) IP
        addresses = server.addresses.get('public', None)
        if addresses:
            if isinstance(addresses, list):
                public_ip = addresses[0]
            results['public_ip'] = public_ip

        # Also get service_net IP
        addresses = server.addresses.get('private', None)
        if addresses:
            if isinstance(addresses, list):
                private_ip = addresses[0]
            results['private_ip'] = private_ip

    if server.status == 'BUILD':
        results['progress'] = server.progress
        #countdown = 100 - server.progress
        #if countdown <= 0:
        #    countdown = 15  # progress is not accurate. Allow at least 15s
        #    wait
        wait_on_build.update_state(state='PROGRESS', meta=results)
        # progress indicate shows percentage, give no inidication of seconds
        # left to build.
        # It often, if not usually takes at least 30 seconds after a server
        # hits 100% before it will be "ACTIVE".  We used to use % left as a
        # countdown value, but reverting to the above configured countdown.
        LOG.debug("Server %s progress is %s. Retrying after 30 seconds" % (
                  server_id, server.progress))
        return wait_on_build.retry()

    if server.status != 'ACTIVE':
        LOG.warning("Server %s status is %s, which is not recognized. "
                    "Assuming it is active" % (server_id, server.status))

    if not ip:
        raise CheckmateException("Could not find IP of server %s" % server_id)
    else:
        up = test_connection(context, ip, username, timeout=timeout,
                             password=password, identity_file=identity_file,
                             port=port, private_key=private_key)
        if up:
            LOG.info("Server %s is up" % server_id)
            results['status'] = "ACTIVE"
            instance_key = 'instance:%s' % context['resource']
            results = {instance_key: results}
            # Send data back to deployment
            resource_postback.delay(context['deployment'],
                                    results)
            return results
        return wait_on_build.retry(exc=CheckmateException("Server %s not "
                                   "ready yet" % server_id))


def _convert_v1_adresses_to_v2(addresses):
    """Convert v1.0 address syntax to v2 format

    v1:
        "addresses": {
            "public": [
                "108.166.59.102"
            ],
            "private": [
                "10.181.97.152"
            ]
        }
    v2:
        "addresses": {
            "private": [
                {
                    "addr": "10.180.4.157",
                    "version": 4
                }
            ],
            "public": [
                {
                    "addr": "50.56.175.68",
                    "version": 4
                },
                {
                    "addr": "2001:4800:780e:0510:d87b:9cbc:ff04:37ec",
                    "version": 6
                }
            ]
        }
    """
    v2 = {'addresses': {}}
    if isinstance(addresses, dict) and 'addresses' in addresses:
        for key, value in addresses['addresses'].iteritems():
            entries = v2['addresses'].get(key, [])
            for ip in value:
                entries.append({'addr': ip, 'version': 4})
            v2['addresses'][key] = entries
    return v2


@task
def delete_server(context, serverid, api_object=None):
    match_celery_logging(LOG)
    if api_object is None:
        api_object = Provider.connect(context)
    api_object.servers.delete(serverid)
    LOG.debug('Server %d deleted.', serverid)
