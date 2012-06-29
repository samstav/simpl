import logging
import os

from novaclient.exceptions import EndpointNotFound, AmbiguousEndpoints
from novaclient.v1_1 import client
import openstack.compute
from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery, Transform

from checkmate.exceptions import CheckmateNoTokenError, CheckmateNoMapping, \
        CheckmateServerBuildFailed
from checkmate.providers.rackspace.compute import RackspaceComputeProviderBase
from checkmate.utils import get_source_body
from checkmate.workflows import wait_for

LOG = logging.getLogger(__name__)


class Provider(RackspaceComputeProviderBase):
    name = 'legacy'

    def generate_template(self, deployment, resource_type, service, name=None):
        template = RackspaceComputeProviderBase.generate_template(self,
                deployment, resource_type, service, name=name)

        image = self.get_deployment_setting(deployment, 'os',
                resource_type=resource_type, service=service)
        if isinstance(image, int):
            pass
        elif image == 'Ubuntu 11.10':
            image = 119
        else:
            raise CheckmateNoMapping("No image mapping for '%s' in '%s'" % (
                    image, self.name))

        flavor = self.get_deployment_setting(deployment, 'memory',
                resource_type=resource_type, service=service, default=1)
        if isinstance(flavor, int):
            pass
        elif flavor == '512 Mb':
            flavor = 2
        else:
            raise CheckmateNoMapping("No flavor mapping for '%s' in '%s'" % (
                    flavor, self.name))

        template['flavor'] = flavor
        template['image'] = image
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
               'checkmate.providers.rackspace.compute_legacy.create_server',
               call_args=[Attrib('context'),
               resource.get('dns-name')],
               image=resource.get('image', 119),
               flavor=resource.get('flavor', 1),
               files=Attrib('files'),
               ip_address_type='public',
               prefix=key,
               defines=dict(resource=key,
                            provider=self.key,
                            task_tags=['create']),
               properties={'estimated_duration': 20})

        build_wait_task = Celery(wfspec, 'Check that Server is Up:%s'
                % key, 'checkmate.providers.rackspace.compute_legacy.'
                        'wait_on_build',
                call_args=[Attrib('context'), Attrib('id')],
                password=Attrib('password'),
                identity_file=Attrib('private_key_path'),
                prefix=key,
                properties={'estimated_duration': 150},
                defines=dict(resource=key,
                             provider=self.key,
                             task_tags=['final']))
        create_server_task.connect(build_wait_task)

        if wait_on is None:
            wait_on = []
        wait_on.append(self.prep_task)
        join = wait_for(wfspec, create_server_task, wait_on,
                name="Server Wait on:%s" % key,
                defines=dict(resource=key,
                             provider=self.key,
                             task_tags=['root']))

        return dict(root=join, final=build_wait_task,
                create=create_server_task)

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

"""
  Celery tasks to manipulate Rackspace Cloud Servers.
"""
from celery.task import task
import openstack.compute

from checkmate.ssh import test_connection


def _get_server_object(deployment):
    return openstack.compute.Compute(username=deployment['username'],
                                     apikey=deployment['apikey'])


""" Celeryd tasks """


@task
def create_server(deployment, name, api_object=None, flavor=1, files=None,
            image=119, ip_address_type='public', prefix=None):
    """Create a Rackspace Cloud server.

    :param deployment: the deployment information
    :type deployment: dict
    :param name: the name of the server
    :param api_object: existing, authenticated connection to API
    :param image: the image ID to use when building the server (which OS)
    :param flavor: the size of the server
    :param files: a list of files to inject
    :type files: dict
    :param prefix: a strig to prepend to any results. Used by Spiff and
            CheckMate
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
    if api_object is None:
        api_object = _get_server_object(deployment)

    LOG.debug('Image=%s, Flavor=%s, Name=%s, Files=%s' % (
                  image, flavor, name, files))

    # Check image and flavor IDs (better descriptions if we error here)
    image_object = api_object.images.find(id=image)
    LOG.debug("Image id %s found. Name=%s" % (image, image_object.name))
    flavor_object = api_object.flavors.find(id=flavor)
    LOG.debug("Flavor id %s found. Name=%s" % (flavor, flavor_object.name))

    try:
        server = api_object.servers.create(image=image, flavor=flavor,
                                           name=name, files=files)
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

    results = dict(id=server.id, ip=ip_address, password=server.adminPass,
            private_ip=private_ip_address)
    if prefix:
        # Add each value back in with the prefix
        results.update({'%s.%s' % (prefix, key): value for key, value in
                results.iteritems()})
    return results


@task(default_retry_delay=10, max_retries=18)  # ~3 minute wait
def wait_on_build(deployment, id, ip_address_type='public',
            check_ssh=True, username='root', timeout=10, password=None,
            identity_file=None, port=22, api_object=None, prefix=None):
    """Checks build is complete and. optionally, that SSH is working.

    :param ip_adress_type: the type of IP addresss to return as 'ip' in the
        response
    :returns: False when build not ready. Dict with ip addresses when done.
    """
    if api_object is None:
        api_object = _get_server_object(deployment)

    server = api_object.servers.find(id=id)
    results = {'id': id,
            'status': server.status,
            'addresses': _convert_v1_adresses_to_v2(server.addresses)
            }

    if server.status == 'ERROR':
        raise StocktonServerBuildFailed("Server %s build failed" % id)

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
        wait_on_build.update_state(state='PROGRESS',
                meta=results)
        LOG.debug("Server %s progress is %s. Retrying after %s seconds" % (id,
                server.progress, countdown))
        return wait_on_build.retry(countdown=countdown)

    if server.status != 'ACTIVE':
        LOG.warning("Server %s status is %s, which is not recognized. "
                "Assuming it is active" % (id, server.status))

    if not ip:
        raise StocktonException("Could not find IP of server %s" % (id))
    else:
        up = test_connection(deployment, ip, username, timeout=timeout,
                password=password, identity_file=identity_file, port=port)
        if up:
            LOG.info("Server %s is up" % id)
            if prefix:
                # Add each value back in with the prefix
                results.update({'%s.%s' % (prefix, key): value for key, value
                        in results.iteritems()})
            return results
        return wait_on_build.retry(exc=StocktonException("Server "
                "%s not ready yet" % id))


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
def delete_server(deployment, serverid, api_object=None):
    if api_object is None:
        api_object = _get_server_object(deployment)
    api_object.servers.delete(serverid)
    LOG.debug('Server %d deleted.' % serverid)
