import logging
import os

from novaclient.exceptions import EndpointNotFound, AmbiguousEndpoints
from novaclient.v1_1 import client
import openstack.compute
from SpiffWorkflow.operators import Attrib, PathAttrib
from SpiffWorkflow.specs import Celery, Transform

from checkmate.deployments import Deployment, resource_postback
from checkmate.exceptions import CheckmateNoTokenError, CheckmateNoMapping, \
        CheckmateServerBuildFailed, CheckmateException
from checkmate.providers.rackspace.compute import RackspaceComputeProviderBase
from checkmate.utils import get_source_body, match_celery_logging
from checkmate.workflows import wait_for

LOG = logging.getLogger(__name__)

REGION_MAP = {'dallas': 'DFW',
              'chicago': 'ORD',
              'london': 'LON'}
REVERSE_MAP = {'DFW': 'dallas',
               'ORD': 'chicago',
               'LON': 'london'}


class Provider(RackspaceComputeProviderBase):
    name = 'legacy'

    def generate_template(self, deployment, resource_type, service, context,
            name=None):
        template = RackspaceComputeProviderBase.generate_template(self,
                deployment, resource_type, service, context, name=name)

        catalog = self.get_catalog(context)

        # Get region
        region = deployment.get_setting('region', resource_type=resource_type,
                                        service_name=service,
                                        provider_key=self.key)
        airport_region = None
        
        if not region:
            LOG.warning("No region specified for Legacy Compute provider in \
                        deployment.")
        else:  
            if region in REGION_MAP:
                airport_region = REGION_MAP[region]
            elif region in REVERSE_MAP:
                airport_region = region
                region = REVERSE_MAP[region]
            else:
                raise CheckmateException("No region mapping found for %s" 
                                         % region)         

            # If legacy region is specified, make sure it matches catalog region
            region_catalog = self.get_catalog(context, type_filter='regions')
            legacy_regions = region_catalog.get('lists', {}).get('regions', {})   
   
            if legacy_regions and (region or airport_region) not in legacy_regions:
                raise CheckmateException("Legacy set to spin up in %s. Cannot provision servers in %s."
                                         % (legacy_regions, region))
            else:
                LOG.warning("Region %s specified in deployment, but not Legacy \
                            Compute catalog" % region)

        image = deployment.get_setting('os', resource_type=resource_type,
                service_name=service, provider_key=self.key, default=119)
        if isinstance(image, int):
            image = str(image)
        if not image.isdigit():
            # Assume it is an OS name and find it
            for key, value in catalog['lists']['types'].iteritems():
                if image == value['name']:
                    LOG.debug("Mapping image from '%s' to '%s'" % (image, key))
                    image = key
                    break
        if image not in catalog['lists']['types']:
            raise CheckmateNoMapping("No image mapping for '%s' in '%s'" % (
                    image, self.name))

        flavor = deployment.get_setting('memory', resource_type=resource_type,
                service_name=service, provider_key=self.key, default=2)
        if isinstance(flavor, int):
            flavor = str(flavor)
        if not flavor.isdigit():
            # Assume it is a memory amount
            #FIXME: handle units (Gb or Mb)
            number = flavor.split(' ')[0]
            for key, value in catalog['lists']['sizes'].iteritems():
                if number == str(value['memory']):
                    LOG.debug("Mapping flavor from '%s' to '%s'" % (flavor,
                            key))
                    flavor = key
                    break
        if flavor not in catalog['lists']['sizes']:
            raise CheckmateNoMapping("No flavor mapping for '%s' in '%s'" % (
                    flavor, self.key))

        template['flavor'] = flavor
        template['image'] = image
        if airport_region:
            template['region'] = airport_region
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
               'checkmate.providers.rackspace.compute_legacy.create_server',
               call_args=[context.get_queued_task_dict(
                                deployment=deployment['id'],
                                resource=key),
                        resource.get('dns-name')],
               image=resource.get('image', 119),
               flavor=resource.get('flavor', 2),
               files=self._kwargs.get('files', None),
               ip_address_type='public',
               defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['create']),
               properties={'estimated_duration': 20})

        build_wait_task = Celery(wfspec, 'Wait for Server %s build'
                % key, 'checkmate.providers.rackspace.compute_legacy.'
                        'wait_on_build',
                call_args=[context.get_queued_task_dict(
                                deployment=deployment['id'],
                                resource=key),
                        PathAttrib('instance:%s/id' % key)],
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
                name="Server %s Wait on Prerequisites" % key,
                defines=dict(resource=key,
                             provider=self.key,
                             task_tags=['root']))

        return dict(root=join, final=build_wait_task,
                create=create_server_task)

    def get_catalog(self, context, type_filter=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one"""
        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #        this for every provider
        results = RackspaceComputeProviderBase.get_catalog(self, context, \
            type_filter=type_filter)
        if results:
            # We have a prexisting or overridecatalog stored
            return results
       
        # build a live catalog this should be the on_get_catalog called if no
        # stored/override existed
        api = self._connect(context)

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context.catalog:
                if service['name'] == 'cloudServers':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        tenant_id = endpoint['tenantId']
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
                        else:
                            region = api.servers.get_region(tenant_id)
                            endpoint['region'] = region
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
                    str(i.id): {
                        'name': i.name,
                        'os': i.name,
                        } for i in images if int(i.id) < 1000}
        if type_filter is None or type_filter == 'image':
            images = api.images.list()
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['images'] = {
                    str(i.id): {
                        'name': i.name
                        } for i in images if int(i.id) > 1000}
        if type_filter is None or type_filter == 'size':
            flavors = api.flavors.list()
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['sizes'] = {
                str(f.id): {
                    'name': f.name,
                    'memory': f.ram,
                    'disk': f.disk,
                    } for f in flavors}

        self.validate_catalog(results)
        return results

    @staticmethod
    def _connect(context):
        """Use context info to connect to API and return api object"""
        #FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, dict):
            from checkmate.server import RequestContext
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
from celery.task import task
import openstack.compute

from checkmate.ssh import test_connection


""" Celeryd tasks """


@task
def create_server(context, name, api_object=None, flavor=2, files=None,
            image=119, ip_address_type='public'):
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
        api_object = Provider._connect(context)

    LOG.debug('Image=%s, Flavor=%s, Name=%s, Files=%s' % (
                  image, flavor, name, files))

    # Check image and flavor IDs (better descriptions if we error here)
    image_object = api_object.images.find(id=int(image))
    LOG.debug("Image id %s found. Name=%s" % (image, image_object.name))
    flavor_object = api_object.flavors.find(id=int(flavor))
    LOG.debug("Flavor id %s found. Name=%s" % (flavor, flavor_object.name))

    try:
        server = api_object.servers.create(image=int(image),
                flavor=int(flavor), name=name, files=files)
        create_server.update_state(state="PROGRESS",
                                   meta={"server.id": server.id})
        LOG.debug(
            'Created server %s (%s).  Admin pass = %s' % (
            name, server.id, server.adminPass))
    except openstack.compute.exceptions.Unauthorized:
        LOG.debug(
            'Cannot create server.  Bad username and apikey/authtoken ' \
            'combination.')
        raise
    except Exception, exc:
        LOG.debug(
            'Error creating server %s (image: %s, flavor: %s) Error: %s' % (
            name, image, flavor, str(exc)))
        raise

    ip_address = str(server.addresses[ip_address_type][0])
    private_ip_address = str(server.addresses['private'][0])

    instance_key = 'instance:%s' % context['resource']
    results = {instance_key: dict(id=server.id, ip=ip_address,
            password=server.adminPass, private_ip=private_ip_address)}
    # Send data back to deployment
    resource_postback.delay(context['deployment'], results)
    return results


@task(default_retry_delay=10, max_retries=18)  # ~3 minute wait
def wait_on_build(context, server_id, ip_address_type='public',
            check_ssh=True, username='root', timeout=10, password=None,
            identity_file=None, port=22, api_object=None):
    """Checks build is complete and. optionally, that SSH is working.

    :param ip_adress_type: the type of IP addresss to return as 'ip' in the
        response
    :returns: False when build not ready. Dict with ip addresses when done.
    """
    match_celery_logging(LOG)
    if api_object is None:
        api_object = Provider._connect(context)

    assert server_id, "ID must be provided"
    LOG.debug("Getting server %s" % server_id)
    server = api_object.servers.find(id=server_id)
    results = {'id': server_id,
            'status': server.status,
            'addresses': _convert_v1_adresses_to_v2(server.addresses)
            }

    if server.status == 'ERROR':
        raise CheckmateServerBuildFailed("Server %s build failed" % server_id)

    ip = None
    if server.addresses:
        addresses = server.addresses.get(ip_address_type or 'public', None)
        if addresses:
            if isinstance(addresses, list):
                ip = addresses[0]
            results['ip'] = ip
        addresses = server.addresses.get('private', None)
        if addresses:
            if isinstance(addresses, list):
                private_ip = addresses[0]
            results['private_ip'] = private_ip
        addresses = server.addresses.get('public', None)
        if addresses:
            if isinstance(addresses, list):
                public_ip = addresses[0]
            results['public_ip'] = public_ip

    if server.status == 'BUILD':
        results['progress'] = server.progress
        countdown = 100 - server.progress
        if countdown <= 0:
            countdown = 15  # progress is not accurate. Allow at least 15s wait
        wait_on_build.update_state(state='PROGRESS',
                meta=results)
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
            # Send data back to deployment
            resource_postback.delay(context['deployment'], results)
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
        api_object = Provider._connect(context)
    api_object.servers.delete(serverid)
    LOG.debug('Server %d deleted.' % serverid)
