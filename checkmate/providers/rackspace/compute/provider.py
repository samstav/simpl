# pylint: disable=E1103, C0302

# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Provider for OpenStack Compute API.

- Supports Rackspace Open Cloud Compute Extensions and Auth

Flavors and Images:
- we use image metadata where possible to not have to code against names.
- images have `flavor_classes` and `vm_mode` values which we use to match with
  flavors.

    00a5dffd-1f9a-47a8-9ccc-7267a362a9da:
      constraints:
        auto_disk_config: 'True'
        flavor_classes: '*,!io1,!memory1,!compute1,!onmetal'
        vm_mode: xen
      name: Ubuntu 14.04 LTS (Trusty Tahr) (PV)
      os: Ubuntu 14.04
      type: linux
- flavors have a `class` attribute which is what is used in images. The
  `policy_class` is not used to match with images.
    io1-90:
      name: 90 GB I/O v1
      memory: 92160
      network: 7500.0
      cores: 24
      disk: 40
      extra:
        class: io1
        disk_io_index: '70'
        number_of_data_disks: '3'
        policy_class: io_flavor


- performance1 and performance2 have been superceded by general and io-
  optimized flavors respectively. So we try not to choose those performance1/2.
- general and standard accepts PV and PVHVM images.
- io, memory, and cpu optimized flavors require PVHVM images. PV/HVM doesn't
  apply to Windows images.
- onmetal needs onmetal images

Automatic disk configuration can be used with PV images but fails with PVHVM
images

Refs:
- http://docs.rackspace.com/servers/api/v2/cs-devguide/content/
  server_flavors.html
- http://www.rackspace.com/knowledge_center/article/
  choosing-a-virtualization-mode-pv-versus-pvhvm
"""

import copy
import logging
import os

import eventlet
import pyrax
import redis
from SpiffWorkflow import operators as swops
from SpiffWorkflow import specs

from checkmate.common import caching
from checkmate.common import config
from checkmate.common import schema
from checkmate.common import templating
from checkmate import deployments as cmdeps
from checkmate import exceptions as cmexc
from checkmate import middleware as cmmid
from checkmate.providers import base as cmbase
from checkmate.providers.rackspace import base
from checkmate import utils

CLIENT = eventlet.import_patched('novaclient.v1_1.client')
CONFIG = config.current()
IMAGE_MAP = {
    'lucid': 'Ubuntu 10.04',
    'maverick': 'Ubuntu 10.10',
    'precise': 'Ubuntu 12.04',
    'quantal': 'Ubuntu 12.10',
    'ringtail': 'Ubuntu 13.04',
    'saucy': 'Ubuntu 13.10',
    'trusty': 'Ubuntu 14.04',
    'utopic': 'Ubuntu 14.10',
    'squeeze': 'Debian 6',
    'wheezy': 'Debian 7',
    'beefy miracle': 'Fedora 17',
    'spherical cow': 'Fedora 18',
    'schroedinger': 'Fedora 19',
    'heisenbug': 'Fedora 20',
    'opensuse': 'openSUSE',
    'coreos': 'CoreOS',
}
KNOWN_OSES = {
    'ubuntu': ['10.04', '10.10', '11.04', '11.10', '12.04', '12.10', '13.04',
               '13.10', '14.04', '14.10'],
    'centos': ['5.11', '6.4', '6.5', '6.6', '7'],
    'cirros': ['0.3'],
    'debian': ['6', '7'],
    'fedora': ['17', '18', '19', '20', '21'],
    'coreos': ['Stable', 'Alpha', 'Beta'],
}
LOG = logging.getLogger(__name__)
RACKSPACE_DISTRO_KEY = 'os_distro'
RACKSPACE_VERSION_KEY = 'os_version'
DEFAULT_OS = 'Ubuntu 14.04'

OPENSTACK_DISTRO_KEY = 'org.openstack__1__os_distro'
OPENSTACK_VERSION_KEY = 'org.openstack__1__os_version'
CATALOG_TEMPLATE = schema.load_catalog(os.path.join(os.path.dirname(__file__),
                                                    'catalog.yaml'))
API_IMAGE_CACHE = {}
API_FLAVOR_CACHE = {}
API_LIMITS_CACHE = {}
REDIS = None

if 'CHECKMATE_CACHE_CONNECTION_STRING' in os.environ:
    try:
        REDIS = redis.from_url(os.environ['CHECKMATE_CACHE_CONNECTION_STRING'])
    except StandardError as exception:
        LOG.warn("Error connecting to Redis: %s", exception)

# FIXME: delete tasks talk to database directly, so we load drivers and manager
MANAGERS = {'deployments': cmdeps.Manager()}
GET_RESOURCE_BY_ID = MANAGERS['deployments'].get_resource_by_id
pyrax.set_setting('identity_type', 'rackspace')


class RackspaceComputeProviderBase(base.RackspaceProviderBase):

    """Generic functions for rackspace Compute providers."""

    def __init__(self, provider, key=None):
        base.RackspaceProviderBase.__init__(self, provider, key=key)
        # kwargs added to server creation calls (contain things like ssh keys)
        self._kwargs = {}
        with open(os.path.join(os.path.dirname(__file__),
                               "scripts", "managed_cloud",
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

    """The Base Provider Class for Rackspace NOVA."""

    name = 'nova'

    __status_mapping__ = {
        'NEW': 'NEW',
        'ACTIVE': 'ACTIVE',
        'BUILD': 'BUILD',
        'DELETED': 'DELETED',
        'DELETING': 'DELETING',
        'ERROR': 'ERROR',
        'HARD_REBOOT': 'CONFIGURE',
        'MIGRATING': 'CONFIGURE',
        'OFFLINE': 'OFFLINE',
        'ONLINE': 'ACTIVE',
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
                          index, key, definition, planner):
        templates = RackspaceComputeProviderBase.generate_template(
            self, deployment, resource_type, service, context, index,
            key, definition, planner
        )

        # Get region
        region = deployment.get_setting('region', resource_type=resource_type,
                                        service_name=service,
                                        provider_key=self.key)
        if not region:
            message = "Could not identify which region to create servers in"
            raise cmexc.CheckmateException(
                message, friendly_message=cmexc.BLUEPRINT_ERROR)
        local_context = copy.deepcopy(context)
        local_context['region'] = region
        catalog = self.get_catalog(local_context)

        memory = deployment.get_setting('memory',
                                        resource_type=resource_type,
                                        service_name=service,
                                        provider_key=self.key,
                                        default=512)
        memory = self.parse_memory_setting(memory)
        disk = deployment.get_setting('disk',
                                      resource_type=resource_type,
                                      service_name=service,
                                      provider_key=self.key)
        if disk:
            disk = self.parse_memory_setting(disk, default_unit='gb')

        vol_dedicated = deployment.get_setting('dedicated',
                                               resource_type='volume',
                                               service_name=service)
        vol_size = deployment.get_setting('size',
                                          resource_type='volume',
                                          service_name=service)
        if disk > 0 and vol_size > 0 and disk != vol_size:
            if vol_dedicated is False:
                msg = ("Compute and volume disk size cannot be different if "
                       "dedicated is explicitely set to False. Check your "
                       "settings in the '%s' service." % service)
                raise cmexc.CheckmateValidationException(
                    msg, friendly_message=msg)
            vol_dedicated = True

        cpu_count = deployment.get_setting('cpus',
                                           resource_type=resource_type,
                                           service_name=service,
                                           provider_key=self.key)
        flavor_class_rules = None
        vm_mode = deployment.get_setting('virtualization-mode',
                                         resource_type=resource_type,
                                         service_name=service,
                                         provider_key=self.key)
        if vm_mode == 'metal':
            flavor_class_rules = 'onmetal'

        os_name = deployment.get_setting('os',
                                         resource_type=resource_type,
                                         service_name=service,
                                         provider_key=self.key,
                                         default=DEFAULT_OS)
        flavor = None
        flavor_id = None
        flavor_setting = deployment.get_setting('flavor',
                                                resource_type=resource_type,
                                                service_name=service,
                                                provider_key=self.key)
        image = None
        image_id = None
        image_setting = deployment.get_setting('image',
                                               resource_type=resource_type,
                                               service_name=service,
                                               provider_key=self.key)
        # Find all matching flavors
        flavors = catalog['lists']['sizes']
        if flavor_setting:
            LOG.debug("Explicit flavor '%s' specified in blueprint.",
                      flavor_setting)
            flavor = flavors.get(flavor_setting) or {}
            flavor_id = flavor_setting
            if not flavor:
                if image_setting:
                    LOG.info("Explicit flavor '%s' appears to be hidden.",
                             flavor_setting)
                else:
                    raise cmexc.CheckmateValidationException(
                        "Explicit flavor '%s' appears to be hidden and the "
                        "'image' setting was not supplied. When chooosing a "
                        "hidden flavor, you must include the image id "
                        "explicitely since Checkmate does not have enough "
                        "information about the flavor to select a matching "
                        "image." % flavor_setting)
        else:
            flavor_matches = filter_flavors(flavors,
                                            class_rules=flavor_class_rules,
                                            min_memory=memory,
                                            min_disk=disk, min_cores=cpu_count,
                                            include_diskless=True)
            if not flavor_matches:
                raise cmexc.CheckmateNoMapping(
                    "No flavors found with memory %s, disk %s, cpus=%s" %
                    (memory, disk, cpu_count))

        # Find all matching images
        images = catalog['lists'].get('types', {})
        if image_setting:
            LOG.debug("Explicit image '%s' specified in blueprint.",
                      image_setting)
            image = images.get(image_setting) or {}
            image_id = image_setting
            if not image:
                if flavor_setting:
                    LOG.info("Explicit image '%s' appears to be hidden.",
                             image_setting)
                else:
                    raise cmexc.CheckmateValidationException(
                        "Explicit image '%s' appears to be hidden and the "
                        "'image' setting was not supplied. When chooosing a "
                        "hidden image, you must include the image id "
                        "explicitely since Checkmate does not have enough "
                        "information about the image to select a matching "
                        "image.", image_setting)
        else:
            image_matches = filter_images(images, os_name=os_name,
                                          vm_mode=vm_mode)
            if not image_matches:
                # Match the old way
                for img_id, img in images.iteritems():
                    if (os_name == img['name'] or
                            (os_name.lower() == img['os'].lower())):
                        LOG.debug("Matching image from '%s' to '%s'", os_name,
                                  img_id)
                        image_matches[img_id] = img
                if image_matches:
                    LOG.info("OS '%s' was matched by name.", os_name)
            if not image_matches:
                # Sounds like we did not match an image
                LOG.debug("%s not found in: %s", os_name, images.keys())
                raise cmexc.CheckmateNoMapping(
                    "Unable to detect image for '%s' in '%s'" %
                    (os_name, self.name))

        # Sort flavors by least cost assuming:
        # - general purpose is cheapest
        # - optimized is next
        # - standard and performance1/2 should no longer be selected
        # - onmetal as last resort
        if not flavor_id:
            general = filter_flavors(flavor_matches, class_rules='general1')
            metal = filter_flavors(flavor_matches, class_rules='onmetal1')
            other = filter_flavors(flavor_matches,
                                   class_rules='*,!general1,!onmetal')
            if general:
                for flid, current in general.iteritems():
                    if flavor is None or current['memory'] < flavor['memory']:
                        flavor = current
                        flavor_id = flid
            if not flavor_id and other:
                for flid, current in other.iteritems():
                    if flavor is None or current['memory'] < flavor['memory']:
                        flavor = current
                        flavor_id = flid
            if not flavor_id and metal:
                for flid, current in metal.iteritems():
                    if flavor is None or current['memory'] < flavor['memory']:
                        flavor = current
                        flavor_id = flid
                        if vm_mode != 'metal':
                            LOG.warning("OnMetal server selected without "
                                        "being explicitely requested in "
                                        "deployment %s", deployment['id'])
        assert flavor_id
        if not image_id:
            for matched_image_id, image_data in image_matches.iteritems():
                if is_compatible(image_data, flavor):
                    image = image_data
                    image_id = matched_image_id
                    break
        userdata = deployment.get_setting('userdata',
                                          resource_type=resource_type,
                                          service_name=service,
                                          provider_key=self.key)
        networks = deployment.get_setting('networks',
                                          resource_type=resource_type,
                                          service_name=service,
                                          provider_key=self.key)
        if networks:
            # requires novaclient extensions, e.g. rackspace-novaclient
            # or os_virtual_interfacesv2_python_novaclient_ext
            # TODO(sam): do type/attribute-checking here?
            for nic in networks:
                if 'uuid' in nic:
                    nic['net-id'] = nic.pop('uuid')
                elif 'UUID' in nic:
                    nic['net-id'] = nic.pop('UUID')

        initial_status = 'ACTIVE'
        if planner.operation.get('type') == 'SCALE UP':
            if planner.operation.get('initial-status'):
                initial_status = planner.operation['initial-status']

        for template in templates:
            template['desired-state']['status'] = initial_status
            template['desired-state']['region'] = region
            template['desired-state']['flavor'] = flavor_id
            template['desired-state']['flavor-info'] = flavor
            if flavor['disk'] == 0:
                template['desired-state']['boot_from_image'] = True
            if disk:
                template['desired-state']['disk'] = disk
            template['desired-state']['image'] = image_id
            template['desired-state']['image-info'] = image
            template['desired-state']['os-type'] = image.get('type')
            template['desired-state']['os'] = image.get('os')
            if userdata:
                template['desired-state']['userdata'] = userdata
                template['desired-state']['config_drive'] = True
            if networks:
                template['desired-state']['networks'] = networks
        if vol_dedicated:
            # Add a CBS volume requirement and have the planner parse it
            definition['requires']['cbs-attach'] = {
                'interface': 'iscsi', 'resource_type': 'volume'}
            planner.resolve_remaining_service_requirements(
                context, service)
            planner.resolve_recursive_requirements(context, [])
        return templates

    def verify_limits(self, context, resources):
        """Verify that deployment stays within absolute resource limits."""
        region = getattr(context, 'region', None)
        if not region:
            region = Provider.find_a_region(context.catalog)
        url = Provider.find_url(context.catalog, region)
        flavors = _get_flavors(url, context.auth_token)['flavors']

        memory_needed = 0
        cores_needed = 0
        for compute in resources:
            flavor = compute['desired-state']['flavor']
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
        """Verify that the user has permissions to create compute resources."""
        roles = [
            'identity:user-admin', 'admin',  # full access
            'nova:admin', 'nova:creator',  # old roles
            'compute:admin', 'compute:creator',  # new roles
        ]
        if cmbase.user_has_access(context, roles):
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
        """Add resource creation tasks to workflow.

        :param resource: the dict of the resource generated by
                generate_template earlier
        :returns: returns the root task in the chain of tasks
        TODO(any): use environment keys instead of private key
        """
        wait_on, _, component = self._add_resource_tasks_helper(
            resource, key, wfspec, deployment, context, wait_on)
        desired = resource['desired-state']
        files = self._kwargs.get('files')
        userdata = desired.get('userdata')
        if userdata:
            kwargs = self.get_context_parameters(deployment=deployment,
                                                 resource=resource,
                                                 component=component)
            kwargs['inputs'] = deployment.get('inputs') or {}
            kwargs['blueprint'] = blueprint = deployment.get('blueprint') or {}
            kwargs['options'] = blueprint.get('options') or {}
            kwargs['services'] = blueprint.get('services') or {}
            kwargs['resources'] = deployment.get('resources') or {}
            userdata = templating.parse(userdata, **kwargs)

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
            deployment_id=deployment['id'],
            resource_key=key,
            region=desired['region'],
            resource=resource)
        create_server_task = specs.Celery(
            wfspec, 'Create Server %s (%s)' % (key, resource['service']),
            'checkmate.providers.rackspace.compute.tasks.create_server',
            call_args=[
                queued_task_dict,
                resource.get('dns-name'),
            ],
            image=desired.get('image'),
            boot_from_image=desired.get('boot_from_image', False),
            disk=desired.get('disk'),
            flavor=desired.get('flavor', "2"),
            files=files,
            userdata=userdata,
            config_drive=desired.get('config_drive'),
            networks=desired.get('networks'),
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
                swops.PathAttrib('resources/%s/instance/id' % key),
            ],
            desired_state=desired,
            properties={'estimated_duration': 150,
                        'auto_retry_count': 3},
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['build']
            )
        )

        task_name = 'Wait for Server %s (%s) build' % (key,
                                                       resource['service'])
        celery_call = ('checkmate.providers.rackspace.compute.'
                       'tasks.wait_on_build')
        build_wait_task = specs.Celery(
            wfspec, task_name, celery_call, **kwargs)
        create_server_task.connect(build_wait_task)

        proxy_kwargs = self.get_bastion_kwargs()
        verify_ssh_task = specs.Celery(
            wfspec, 'Verify server %s (%s) ssh connection' % (
                key, resource['service']),
            'checkmate.providers.rackspace.compute'
            '.tasks.verify_ssh_connection',
            call_args=[
                queued_task_dict,
                swops.PathAttrib('resources/%s/instance/id' % key),
                swops.PathAttrib('resources/%s/instance/ip' % key)
            ],
            password=swops.PathAttrib('resources/%s/instance/password' % key),
            private_key=deployment.settings().get('keys', {}).get(
                'deployment', {}).get('private_key'),
            properties={'estimated_duration': 10,
                        'auto_retry_count': 3},
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['final']
            )
            **proxy_kwargs
        )
        build_wait_task.connect(verify_ssh_task)

        # If Managed Cloud Linux servers, add a Completion task to release
        # RBA. Other providers may delay this task until they are done.
        if ('rax_managed' in context.roles and
                resource['component'] == 'linux_instance'):
            touch_complete = specs.Celery(
                wfspec, 'Mark Server %s (%s) Complete' % (key,
                                                          resource['service']),
                'checkmate.ssh.execute_2',
                call_args=[
                    queued_task_dict,
                    swops.PathAttrib("resources/%s/instance/ip" % key),
                    "touch /tmp/checkmate-complete",
                    "root",
                ],
                password=swops.PathAttrib(
                    'resources/%s/instance/password' % key),
                private_key=deployment.settings().get('keys', {}).get(
                    'deployment', {}).get('private_key'),
                properties={'estimated_duration': 10},
                defines=dict(
                    resource=key,
                    provider=self.key,
                    task_tags=['complete']
                )
                **proxy_kwargs
            )
            verify_ssh_task.connect(touch_complete)

        if wait_on is None:
            wait_on = []
        # refactor to remove pylint error on missing attribute
        preps = getattr(self, 'prep_task', None)
        if preps:
            wait_on.append(preps)

        join = wfspec.wait_for(
            create_server_task,
            wait_on,
            name="Server Wait on:%s (%s)" % (key, resource['service'])
        )
        return dict(
            root=join,
            final=build_wait_task,
            create=create_server_task
        )

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        target = relation['target']
        if target != key:
            target_resource = deployment['resources'][target]
            compute_wait_tasks = wfspec.find_task_specs(resource=key,
                                                        provider=self.key,
                                                        tag='build')
            compute_final_tasks = wfspec.find_task_specs(resource=key,
                                                         provider=self.key,
                                                         tag='final')
            # Target final
            target_final_tasks = wfspec.find_task_specs(resource=target,
                                                        tag='final')

            desired = resource['desired-state']
            queued_context = context.get_queued_task_dict(
                deployment_id=deployment['id'], resource_key=key,
                region=desired['region'])
            if target_resource['type'] == 'volume':
                vol_device_name = deployment.get_setting(
                    'device-name', resource_type='volume',
                    service_name=resource['service'])
                # Create the attach task
                connect_task = specs.Celery(
                    wfspec,
                    "Attach Server %s to Volume %s" % (key, target),
                    'checkmate.providers.rackspace.compute.tasks.attach',
                    call_args=[
                        queued_context,
                        swops.PathAttrib('resources/%s/instance/id' % key),
                        swops.PathAttrib('resources/%s/instance/id' % target),
                    ],
                    device_name=vol_device_name,
                    defines=dict(relation=relation_key, provider=self.key,
                                 task_tags=['attach']),
                    properties={'estimated_duration': 10}
                )
                # Wait for seerver and volume build before connecting
                wfspec.wait_for(
                    connect_task,
                    target_final_tasks + compute_wait_tasks,
                    name="Attach (%s) Wait on %s and %s" % (
                        resource['service'], key, target)
                )
                # Tell anything else needing this server to wait on attach
                if compute_final_tasks:
                    wfspec.wait_for(
                        compute_final_tasks[0],
                        [connect_task],
                        name="Server Wait on Attach:%s (%s)" % (
                            key, resource['service'])
                    )
            else:
                LOG.info("Ignoring connection to cloud server from '%s'",
                         target_resource['type'])

    def get_resource_status(self, context, deployment_id, resource, key,
                            sync_callable=None, api=None):
        from checkmate.providers.rackspace.compute import sync_resource_task
        result = super(Provider, self).get_resource_status(
            context, deployment_id, resource, key,
            sync_callable=sync_resource_task, api=api
        )
        i_key = 'resources/%s/instance' % key
        if result[i_key].get('status') in ['ACTIVE', 'DELETED']:
            result[i_key]['instance'] = {'status-message': ''}
        return result

    def delete_resource_tasks(self, wf_spec, context, deployment_id, resource,
                              key):
        self._verify_existing_resource(resource, key)
        inst_id = resource.get("instance", {}).get("id")
        region = (resource.get("region") or
                  resource.get("instance", {}).get("region"))
        if isinstance(context, cmmid.RequestContext):
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

        delete_server = specs.Celery(
            wf_spec,
            'Delete Server (%s)' % key,
            'checkmate.providers.rackspace.compute.tasks.delete_server_task',
            call_args=[context],
            properties={
                'estimated_duration': 5,
            }
        )
        wait_on_delete = specs.Celery(
            wf_spec,
            'Wait on Delete Server (%s)' % key,
            'checkmate.providers.rackspace.compute.tasks'
            '.wait_on_delete_server',
            call_args=[context],
            properties={
                'estimated_duration': 10,
            }
        )
        delete_server.connect(wait_on_delete)
        return {'root': delete_server, 'final': wait_on_delete}

    @staticmethod
    def _get_api_info(context, **kwargs):
        """Get Flavors, Images and Types available in a given Region."""
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
                results = utils.merge_dictionary(
                    results, ret, extend_lists=True)
        else:
            for region, url in urls.items():
                if not url:
                    if len(urls) == 1:
                        LOG.warning("Failed to find compute endpoint for %s "
                                    "in region %s", context.tenant, region)
                    continue
                flavors = _get_flavors(url, context.auth_token)
                images = _get_images_and_types(url, context.auth_token)
                results = utils.merge_dictionary(
                    results, flavors, extend_lists=True)
                results = utils.merge_dictionary(
                    results, images, extend_lists=True)
        return results

    def get_catalog(self, context, type_filter=None, **kwargs):
        """Return the catalog:

        - from stored/override if it exists
        - otherwise, connect, build and return one
        """
        # TODO(any): maybe implement this an on_get_catalog so we don't have to
        #       do this for every provider
        results = RackspaceComputeProviderBase.get_catalog(
            self, context, type_filter=type_filter)
        if results:
            # We have a prexisting or overriding catalog stored
            return results

        # build a live catalog this would be the on_get_catalog called if no
        # stored/override existed
        images = None
        flavors = None
        types = None

        if not context.catalog:
            raise cmexc.CheckmateException(
                friendly_message="Missing tenant catalog", http_status=400)

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
            # TODO(any): add regression tests. copy.copy leaking across tenants
            results['compute'] = copy.deepcopy(CATALOG_TEMPLATE['compute'])
            linux = results['compute']['linux_instance']
            windows = results['compute']['windows_instance']
            if types:
                linch = linux['options']['os']['display-hints']['choice']
                winch = windows['options']['os']['display-hints']['choice']
                for image in types.values():
                    if image['type'] == 'windows':
                        winch.append({
                            'name': image['name'],
                            'value': image['os'],
                        })
                    else:
                        linch.append({
                            'name': image['name'],
                            'value': image['os']
                        })

            if flavors:
                linch = linux['options']['memory']['display-hints']['choice']
                winch = windows['options']['memory']['display-hints']['choice']
                for flavor in flavors.values():
                    choice = {
                        'value': int(flavor['memory']),
                        'name': "%s (%s Gb disk)" % (flavor['name'],
                                                     flavor['disk'])
                    }
                    linch.append(choice)
                    if flavor['memory'] >= 1024:  # Windows needs min 1Gb
                        winch.append(choice)

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
    def get_resources(context, tenant_id=None):
        """Proxy request through to nova compute provider."""
        if not pyrax.get_setting("identity_type"):
            pyrax.set_setting("identity_type", "rackspace")

        servers = []
        pyrax.auth_with_token(context.auth_token, tenant_name=context.tenant)
        for region in pyrax.regions:
            api = pyrax.connect_to_cloudservers(region=region)
            servers += api.list()

        results = []
        for _, server in enumerate(servers):
            if 'RAX-CHECKMATE' in server.metadata:
                continue

            resource = {
                'status': server.status,
                'provider': 'nova',
                'type': 'compute',
                'dns-name': server.name,
                'instance': {
                    'status': server.status,
                    'addresses': server.addresses,
                    'id': server.id,
                    'flavor': server.flavor['id'],
                    'region': server.manager.api.client.region_name,
                    'image': server.image['id']
                },
            }
            results.append(resource)
            utils.merge_dictionary(
                resource['instance'],
                utils.get_ips_from_server(server, context.roles)
            )
        return results

    @staticmethod
    def find_url(catalog, region):
        """Get the Public URL of a service."""
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
        """Any region."""
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
        """Use context info to connect to API and return api object."""
        # FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, dict):
            context = cmmid.RequestContext(**context)
        # TODO(any): Hard-coded to Rax auth for now
        if not context.auth_token:
            raise cmexc.CheckmateNoTokenError()

        if not region:
            region = getattr(context, 'region', None)
            if not region:
                region = utils.read_path(context.resource, 'instance/region')
            if not region:
                region = utils.read_path(context.resource,
                                         'desired-state/region')
            if not region:
                region = Provider.find_a_region(context.catalog) or 'DFW'
        url = Provider.find_url(context.catalog, region)
        plugin = AuthPlugin(context.auth_token, url,
                            auth_source=context.auth_source)
        insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1',
                                                                    'true']
        api = CLIENT.Client(context.username, 'ignore', context.tenant,
                            insecure=insecure, auth_system="rackspace",
                            auth_plugin=plugin)
        return api


class AuthPlugin(object):
    """Handles auth."""
    def __init__(self, auth_token, nova_url, auth_source=None):
        self.token = auth_token
        self.nova_url = nova_url
        self.auth_source = auth_source or "http://localhost:35357/v2.0/tokens"
        self.done = False

    def get_auth_url(self):
        """Respond to novaclient auth_url call."""
        LOG.debug("Nova client called auth_url from plugin")
        return self.auth_source

    def authenticate(self, novaclient, auth_url):  # pylint: disable=W0613
        """Respond to novaclient authenticate call."""
        if self.done:
            LOG.debug("Called a second time from Nova. Assuming token expired")
            raise cmexc.CheckmateException(
                "Auth Token expired",
                "Your authentication token expired before work on your "
                "deployment was completed. To resume that work, you just need "
                "to 'retry' the operation to supply a fresh token that we can "
                "use to continue working with", cmexc.CAN_RESUME)
        else:
            LOG.debug("Nova client called authenticate from plugin")
            novaclient.auth_token = self.token
            novaclient.management_url = self.nova_url
            self.done = True


@caching.Cache(timeout=3600, sensitive_args=[1], store=API_IMAGE_CACHE,
               backing_store=REDIS, backing_store_key='rax.compute.images')
def _get_images_and_types(api_endpoint, auth_token):
    """Ask Nova for Images and Types."""
    assert api_endpoint, "No API endpoint specified when getting images"
    plugin = AuthPlugin(auth_token, api_endpoint)
    insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1', 'true']
    try:
        api = CLIENT.Client('fake-user', 'fake-pass', 'fake-tenant',
                            insecure=insecure, auth_system="rackspace",
                            auth_plugin=plugin)
        ret = {'images': {}, 'types': {}}
        LOG.info("Calling Nova to get images for %s", api_endpoint)
        images = api.images.list(detailed=True)
        LOG.debug("Parsing image list: %s", images)
        # Parse pyrax image list into Checkate catalog entries
        for i in images:
            metadata = i.metadata or {}
            if metadata.get('image_type') == 'snapshot':
                # We don't support booting from snapshots
                LOG.debug("Ignoring snapshot image %s", i.id)
                continue
            detected_os = detect_image_os(i.name, metadata=metadata)
            if detected_os:
                vm_mode = metadata.get('vm_mode') or 'windows'  # null==Windows
                classes = metadata.get('flavor_classes')
                if not classes:
                    default_hypervisor_filters = {
                        # onmetal needs metal, and only it can run metal images
                        'metal': 'onmetal',
                        'hvm': '*,!onmetal',
                        'xen': ('*,!io1,!memory1,!compute1,!performace2,'
                                '!onmetal'),
                        'windows': '*,!onmetal',
                    }
                    classes = default_hypervisor_filters[vm_mode]
                else:
                    # performance2 is not correctly listed in most images so
                    # let's add it to the filter so it does not get selected
                    # by mistake
                    if vm_mode == 'xen' and '!performance2' not in classes:
                        classes = classes + ',!performance2'
                # Build image dict formatted for the catalog
                img = {
                    'name': i.name,
                    'os': detected_os['os'],
                    'type': detected_os['type'],
                    'constraints': {
                        'vm_mode': vm_mode,
                        'auto_disk_config': metadata.get('auto_disk_config'),
                        'flavor_classes': classes,
                    }
                }
                # Add it to types (which is image types)
                ret['types'][str(i.id)] = img
                # Add the name to the list that is used to generate dropdowns
                ret['images'][i.id] = {'name': i.name}
        LOG.debug("Found images %s: %s", api_endpoint, ret['images'].keys())
    except Exception as exc:
        LOG.error("Error retrieving Cloud Server images from %s: %s",
                  api_endpoint, exc)
        raise
    return ret


def detect_image_os(name, metadata=None):
    """Attempt to detect OS from name and/or metadata.

    Ideally, we can use metadata and get a firm lock on an image's OS. But from
    experience we know that image metadata is not always reliable. And in some
    situations, like when talking to a private cloud instance or when scanning
    a custom image, there is no metadata. So this function tries to ascertain
    the OS of an image from the name as well.

    :arg name: the name of the image
    :keyword metadata: the image metadata if available.
    :returns: dict with name, os, and type as follows if detected:
        {
            'name': the original name of the image,
            'os': OS and version in Checkmate format (ex. Ubuntu 12.04)
            'type': 'linux' or 'windows'
        }
    """
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

    # Look for keywords like 'precise'
    lower_name = name.lower()
    for hint, mapped_os in IMAGE_MAP.iteritems():
        if hint in lower_name:
            os_name = mapped_os
            LOG.debug("Identified image using hint '%s': %s", hint, os_name)
            return {'name': name, 'os': os_name, 'type': 'linux'}

    # Look for Checkmate name
    for mapped_os in IMAGE_MAP.itervalues():
        if mapped_os.lower() in lower_name:
            os_name = mapped_os
            LOG.debug("Identified image using name '%s': %s", mapped_os,
                      os_name)
            return {'name': name, 'os': os_name, 'type': 'linux'}

    # Parse for known OSes and versions
    for os_lower, versions in KNOWN_OSES.iteritems():
        if os_lower in lower_name:
            for version in versions:
                if version.lower() in lower_name:
                    os_name = '%s %s' % (os_lower.title(), version)
                    LOG.debug("Identified image as known OS: %s", os_name)
                    return {'name': name, 'os': os_name, 'type': 'linux'}

    if ' LTS ' in name:
        # NOTE: hack to find some images by name in Rackspace
        os_name = name.split(' LTS ')[0].split(' (')[0]
        LOG.debug("Identified image by name split: %s", os_name)
        return {'name': name, 'os': os_name, 'type': 'linux'}

    # NOTE: hack to make our blueprints work with iNova
    if 'LTS' in name:
        os_name = name.split('LTS')[0].strip()
        LOG.debug("Identified image by iNova name: %s", os_name)
        return {'name': name, 'os': os_name, 'type': 'linux'}

    if not os_name:
        LOG.debug("Could not identify image: %s", name,
                  extra={'metadata': metadata})
    return {}


def filter_flavors(flavors, class_rules=None, min_disk=None, min_memory=None,
                   min_cores=None, include_diskless=False):
    """Return filtered list of flavors.

    :keyword class_rules: class string to filter on (ex. '*,!onmetal')
    :keyword include_diskless: includes flavors that use an external cloud
        block device for storage. Their disk value shows up as 0.
    :returns: dict of compatible flavors (keyed by flavor id)
    """
    results = {}
    rules = None
    if class_rules:
        rules = class_rules.split(',')
    # Loop through images and add the ones that match all tests to `results`
    for key, value in flavors.items():
        if rules:
            try:
                if not passes_rules(value['extra']['class'], rules):
                    continue
            except KeyError:
                pass
        if min_disk is not None:
            try:
                if int(value['disk']) < int(min_disk):
                    # Disk too small, skip unless
                    if not (include_diskless and int(value['disk']) == 0):
                        continue
            except KeyError:
                pass
        if min_memory is not None:
            try:
                if int(value['memory']) < int(min_memory):
                    continue
            except KeyError:
                pass
        if min_cores is not None:
            try:
                if int(value['cores']) < int(min_cores):
                    continue
            except KeyError:
                pass
        results[key] = value
    return results


def filter_images(images, os_name=None, flavor_class=None, vm_mode=None):
    """Return filtered list of images.

    :keyword os_name: in Checkmate normalized form, not image name. Ex.
        Ubuntu 14.04
    :keyword flavor_class: from the `class` attribute of a flavor. Ex. io1
    """
    results = {}
    # Loop through images and add the ones that match all tests to `results`
    for key, value in images.iteritems():
        if os_name is not None and value['os'] != os_name:
            continue
        if flavor_class:
            try:
                rules = value['constraints']['flavor_classes'].split(',')
                if not passes_rules(flavor_class, rules):
                    continue
            except (KeyError, AttributeError):
                pass
        if vm_mode is not None:
            try:
                if value['constraints']['vm_mode'] != vm_mode:
                    continue
            except KeyError:
                pass
        results[key] = value
    return results


def is_compatible(image, flavor):
    """Test compatibility of an image and a flavor."""
    if not (image and flavor):
        return False
    flavor_class = flavor['extra']['class']
    rules = image['constraints']['flavor_classes'] or ''
    return passes_rules(flavor_class, rules.split(','))


def passes_rules(flavor_class, rules):
    """Test if a flavor class passes the supplied rules.

    Rules come from the api as a comma-seprated string like '*,!onmetal'. This
    function expects to receive the split array.
    """
    assert isinstance(rules, list)
    if not rules:
        return True
    not_flavor_class = '!' + flavor_class
    if not_flavor_class in rules:
        return False
    if flavor_class in rules:
        return True
    if '*' in rules:
        return True
    assert not (len(rules) == 1 and rules[0].startswith('!')), (
        "A rule with only a !class won't match anything. Add '*,' to the rule")
    return False


@caching.Cache(timeout=3600, sensitive_args=[1], store=API_FLAVOR_CACHE,
               backing_store=REDIS, backing_store_key='rax.compute.flavors')
def _get_flavors(api_endpoint, auth_token):
    """Ask Nova for Flavors (RAM, CPU, HDD) options."""
    assert api_endpoint, "No API endpoint specified when getting flavors"
    plugin = AuthPlugin(auth_token, api_endpoint)
    insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1', 'true']
    try:
        api = CLIENT.Client('fake-user', 'fake-pass', 'fake-tenant',
                            insecure=insecure, auth_system="rackspace",
                            auth_plugin=plugin)
        LOG.info("Calling Nova to get flavors for %s", api_endpoint)
        flavors = api.flavors.list()
        formatted = {}
        deprecated_classes = {
            'standard',  # superceded by general class
            'performance1',  # superceded by general class
            'performance2',  # superceded by io, memory, and compute classes
        }
        for flavor in flavors:
            extra = getattr(flavor, 'OS-FLV-WITH-EXT-SPECS:extra_specs')
            # This is what pyrax returns:
            # getattr(f, 'OS-FLV-WITH-EXT-SPECS:extra_specs')
            # > {u'number_of_data_disks': u'0', u'class': u'compute1',
            # > u'disk_io_index': u'-1', u'policy_class': u'compute_flavor'}
            data = {
                'name': flavor.name,
                'memory': flavor.ram,
                'disk': flavor.disk,
                'cores': flavor.vcpus,
                'network': flavor.rxtx_factor,
                'extra': extra,
            }
            if extra['class'] in deprecated_classes:
                data['deprecated'] = True
            formatted[str(flavor.id)] = data
        result = {'flavors': formatted}
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
    """Retrieve account limits as a dict."""
    plugin = AuthPlugin(auth_token, api_endpoint)
    insecure = str(os.environ.get('NOVA_INSECURE')).lower() in ['1', 'true']
    api = CLIENT.Client('fake-user', 'fake-pass', 'fake-tenant',
                        insecure=insecure, auth_system="rackspace",
                        auth_plugin=plugin)
    LOG.info("Calling Nova to get limits for %s", api_endpoint)
    api_limits = api.limits.get()

    def limits_dict(limits):
        """Convert limits to dict."""
        new_dict = {}
        for limit in limits:
            new_dict[limit.name.encode('ascii')] = limit.value
        return new_dict
    return limits_dict(api_limits.absolute)
