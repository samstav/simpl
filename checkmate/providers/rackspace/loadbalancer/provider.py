"""
Provider module for Rackspace Loadbalancers.
"""
import copy
import logging
import os
import sys

from SpiffWorkflow import operators
from SpiffWorkflow import specs

import cloudlb
import pyrax
import redis

from checkmate.common import caching
from checkmate import db
from checkmate import deployments
from checkmate import exceptions
from checkmate import middleware
from checkmate.providers.base import ProviderBase, user_has_access
from checkmate.providers.rackspace import base, dns
from checkmate.providers.rackspace.dns.provider import parse_domain
from checkmate.utils import get_class_name

LOG = logging.getLogger(__name__)

# Any names should become airport codes
REGION_MAP = {
    'dallas': 'DFW',
    'chicago': 'ORD',
    'london': 'LON',
    'sydney': 'SYD',
}

PROTOCOL_PAIRS = {
    'https': 'http',
    'sftp': 'ftp',
    'ldaps': 'ldap',
    'pop3s': 'pop3',
}

API_ALGORTIHM_CACHE = {}
API_PROTOCOL_CACHE = {}
LB_API_CACHE = {}
REDIS = None
if 'CHECKMATE_CACHE_CONNECTION_STRING' in os.environ:
    try:
        REDIS = redis.from_url(os.environ['CHECKMATE_CACHE_CONNECTION_STRING'])
    except StandardError as exception:
        LOG.warn("Error connecting to Redis: %s", exception)

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


class Provider(base.RackspaceProviderBase):
    '''Rackspace load balancer provider'''
    name = 'load-balancer'
    method = 'cloud_loadbalancers'
    vendor = 'rackspace'

    __status_mapping__ = {
        'ACTIVE': 'ACTIVE',
        'BUILD': 'BUILD',
        'DELETED': 'DELETED',
        'ERROR': 'ERROR',
        'PENDING_UPDATE': 'CONFIGURE',
        'PENDING_DELETE': 'DELETING',
        'SUSPENDED': 'ERROR'
    }

    def _get_connection_params(self, connections, deployment, index,
                               resource_type, service):
        """Deployment connection parameters."""
        relation = connections[connections.keys()[index]]['relation-key']
        inbound = deployment.get_setting("inbound",
                                         resource_type=resource_type,
                                         service_name=service,
                                         provider_key=self.key,
                                         relation=relation,
                                         default="http/80")
        return {"protocol": inbound.split('/')[0],
                "port": inbound.split('/')[1]}

    def generate_template(self, deployment, resource_type, service, context,
                          index, key, definition):
        # Get region
        templates = []
        region = deployment.get_setting('region', resource_type=resource_type,
                                        service_name=service,
                                        provider_key=self.key)
        if not region:
            error_message = ("Could not identify which region to "
                             "create load-balancer in")
            raise exceptions.CheckmateUserException(
                error_message,
                get_class_name(exceptions.CheckmateUserException),
                exceptions.BLUEPRINT_ERROR, '')
        number_of_resources = 1
        interface = \
            deployment.get('blueprint')['services'][service]['component'][
                'interface']
        protocol = deployment.get_setting("protocol",
                                          resource_type=resource_type,
                                          service_name=service,
                                          provider_key=self.key,
                                          default="http").lower()
        support_unencrypted = self._support_unencrypted(
            deployment, protocol, resource_type=resource_type, service=service
        )
        if support_unencrypted:
            number_of_resources += 1
        if interface == 'vip':
            connections = definition.get('connections', [])
            number_of_resources = len(connections)

        for index_of_resource in range(index, index + number_of_resources):
            generated_templates = ProviderBase.generate_template(
                self, deployment, resource_type, service, context,
                index_of_resource, self.key, definition
            )
            for template in generated_templates:
                if interface == 'vip':
                    params = self._get_connection_params(
                        connections, deployment, index - index_of_resource,
                        resource_type, service
                    )
                    for key, value in params.iteritems():
                        template[key] = value

                template['region'] = region
                templates.append(template)

        if support_unencrypted:
            templates[len(templates) - 1]['protocol'] = PROTOCOL_PAIRS[
                protocol]
        if self._handle_dns(deployment, service, resource_type=resource_type):
            templates[0]['instance']['dns-A-name'] = \
                deployment.get_setting("domain",
                                       resource_type=resource_type,
                                       service_name=service,
                                       provider_key=self.key,
                                       default=templates[0].get('dns-name'))
        return templates

    def _support_unencrypted(self, deployment, protocol, resource_type=None,
                             service=None):
        """Unencrypted protocol support."""
        values = [False]
        if protocol in PROTOCOL_PAIRS:
            for setting in ['allow_insecure', 'allow_unencrypted']:
                value = deployment.get_setting(setting,
                                               resource_type=resource_type,
                                               service_name=service,
                                               provider_key=self.key,
                                               default=False)
                value = str(value).lower() in ['1', 'yes', 'true', '-1']
                values.append(value)
                if setting == 'allow_insecure' and value:
                    LOG.warning("allow_insecure setting is deprecated."
                                "Please use allow_unencrypted")

        return reduce(lambda x, y: x | y, values)

    def _handle_dns(self, deployment, service, resource_type="load-balancer"):
        """Checks if DNS enabled in blueprint."""
        _dns = str(deployment.get_setting("create_dns",
                                          resource_type=resource_type,
                                          service_name=service,
                                          default="false"))
        return _dns.lower() in ['true', '1', 'yes']

    @caching.CacheMethod(timeout=3600, sensitive_args=[1], store=LB_API_CACHE,
                         backing_store=REDIS,
                         backing_store_key='rax.lb.limits')
    def _get_abs_limits(self, username, auth_token, api_endpoint, region):
        """Get LB absolute limits."""
        api = cloudlb.CloudLoadBalancer(username, 'ignore', region)
        api.client.auth_token = auth_token
        api.client.region_account_url = api_endpoint
        return api.loadbalancers.get_absolute_limits()

    def verify_limits(self, context, resources):
        messages = []
        region = getattr(context, 'region', None)
        if not region:
            region = Provider.find_a_region(context.catalog)
        url = Provider.find_url(context.catalog, region)
        abs_limits = self._get_abs_limits(context.username, context.auth_token,
                                          url, region)
        max_nodes = abs_limits.get("NODE_LIMIT", sys.maxint)
        max_lbs = abs_limits.get("LOADBALANCER_LIMIT", sys.maxint)
        clb = self.connect(context, region=region)
        cur_lbs = len(clb.list() or [])
        avail_lbs = max_lbs - cur_lbs
        req_lbs = len(resources or {})
        if avail_lbs < req_lbs:
            messages.append({
                'type': "INSUFFICIENT-CAPACITY",
                'message': "This deployment would create %s Cloud Load "
                           "Balancers.  You have %s instances available."
                           % (req_lbs, avail_lbs),
                'provider': self.name,
                'severity': "CRITICAL"
            })
        for res in resources:
            if 'dns-A-name' in res.get('instance', {}):
                messages.append(dns.Provider({}).verify_limits(context,
                                [{"type": "dns-record",
                                  "interface": "A",
                                  'dns-name': res.get('instance')
                                                 .get('dns-A-name')}]))
            nodes = len(res.get("relations", {}))
            if max_nodes < nodes:
                messages.append({
                    'type': "INSUFFICIENT-CAPACITY",
                    'message': "Cloud Load Balancer %s would have %s nodes. "
                               "You may only associate up to %s nodes with a "
                               "Cloud Load Balancer."
                               % (res.get("index"), nodes, max_nodes),
                    'provider': self.name,
                    'severity': "CRITICAL"
                })
        return messages

    def verify_access(self, context):
        roles = ['identity:user-admin', 'LBaaS:admin', 'LBaaS:creator']
        if user_has_access(context, roles):
            return {
                'type': "ACCESS-OK",
                'message': "You have access to create Cloud Load Balancers",
                'provider': self.name,
                'severity': "INFORMATIONAL"
            }
        else:
            return {
                'type': "NO-ACCESS",
                'message': "You do not have access to create "
                           "Cloud Load Balancers",
                'provider': self.name,
                'severity': "CRITICAL"
            }

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                           wait_on=None):
        service_name = resource.get('service')
        resource_type = resource.get('type')
        proto = resource['protocol'] if resource.get('protocol', None) \
            else deployment.get_setting("protocol",
                                        resource_type=resource_type,
                                        service_name=service_name,
                                        provider_key=self.key,
                                        default="http").lower()

        port = resource['port'] if resource.get('port', None) \
            else deployment.get_setting("port",
                                        resource_type=resource_type,
                                        service_name=service_name,
                                        provider_key=self.key,
                                        default=None)

        algorithm = deployment.get_setting("algorithm",
                                           resource_type=resource_type,
                                           service_name=service_name,
                                           provider_key=self.key,
                                           default="ROUND_ROBIN")
        dns = self._handle_dns(deployment, service_name,
                               resource_type=resource_type)
        create_lb_task_tags = ['create', 'root', 'vip']

        #Find existing task which has created the vip
        vip_tasks = wfspec.find_task_specs(provider=self.key, tag='vip')
        parent_lb = None

        if vip_tasks:
            parent_lb_resource_id = vip_tasks[0].get_property('resource')
            parent_lb = operators.PathAttrib("instance:%s/id" %
                                             parent_lb_resource_id)
            create_lb_task_tags.remove('vip')

        create_lb = specs.Celery(
            wfspec,
            'Create %s Loadbalancer (%s)' % (proto.upper(), key),
            'checkmate.providers.rackspace.loadbalancer.create_loadbalancer',
            call_args=[
                context.get_queued_task_dict(
                    deployment=deployment['id'],
                    resource=key
                ),
                resource.get('dns-name'),
                'PUBLIC',
                proto.upper(),
                resource['region']
            ],
            defines={'resource': key, 'provider': self.key},
            # FIXME: final task should be the one that finishes
            # when all extra_protocols are done, not this one
            properties={
                'estimated_duration': 30,
                'task_tags': create_lb_task_tags
            },
            dns=dns,
            algorithm=algorithm,
            tags=self.generate_resource_tag(
                context.base_url,
                context.tenant,
                deployment['id'],
                key
            ),
            port=port,
            parent_lb=parent_lb
        )
        if vip_tasks:
            vip_tasks[0].connect(create_lb)

        task_name = ('Wait for Loadbalancer %s (%s) build' %
                     (key, resource['service']))
        celery_call = ('checkmate.providers.rackspace.loadbalancer.'
                       'wait_on_build')
        build_wait_task = specs.Celery(
            wfspec,
            task_name,
            celery_call,
            call_args=[
                context.get_queued_task_dict(
                    deployment=deployment['id'],
                    resource=key
                ),
                operators.PathAttrib('instance:%s/id' % key),
                resource['region']
            ],
            properties={'estimated_druation': 150},
            merge_results=True,
            defines=dict(
                resource=key,
                provider=self.key,
                task_tags=['complete']
            )
        )
        create_lb.connect(build_wait_task)

        if dns:
            task_name = ("Create DNS Record for Load balancer %s (%s)"
                         % (key, resource['service']))
            celery_call = "checkmate.providers.rackspace.dns.create_record"
            name = resource.get('dns-name')
            create_record_task = specs.Celery(
                wfspec, task_name, celery_call,
                call_args=[
                    context.get_queued_task_dict(
                        deployment=deployment['id'], resource=key),
                    parse_domain(name),
                    '.'.join(name.split('.')[1:]), "A",
                    operators.PathAttrib('instance:%s/public_ip' % key)
                ],
                rec_ttl=300,
                makedomain=True,
                result_key="dns-record")
            build_wait_task.connect(create_record_task)
            task_name = ("Update Load Balancer %s (%s) DNS Data"
                         % (key, resource['service']))
            celery_call = ('checkmate.providers.rackspace.loadbalancer.'
                           'collect_record_data')
            crd = specs.Celery(
                wfspec, task_name, celery_call,
                call_args=[
                    deployment["id"], key, operators.Attrib('dns-record')
                ]
            )
            create_record_task.connect(crd)

        task_name = ('Add monitor to Loadbalancer %s (%s) build' %
                     (key, resource['service']))
        celery_call = 'checkmate.providers.rackspace.loadbalancer.set_monitor'
        set_monitor_task = specs.Celery(
            wfspec, task_name, celery_call,
            call_args=[
                context.get_queued_task_dict(deployment=deployment['id'],
                                             resource=key),
                operators.PathAttrib('instance:%s/id' % key),
                proto.upper(),
                resource['region']
            ],
            defines=dict(resource=key, provider=self.key, task_tags=['final'])
        )

        build_wait_task.connect(set_monitor_task)
        final = set_monitor_task
        return dict(root=create_lb, final=final)

    def get_resource_status(self, context, deployment_id, resource, key,
                            sync_callable=None, api=None):
        from checkmate.providers.rackspace.loadbalancer import (
            sync_resource_task
        )

        return super(Provider, self).get_resource_status(context,
                                                         deployment_id,
                                                         resource, key,
                                                         sync_callable=
                                                         sync_resource_task,
                                                         api=api)

    def delete_resource_tasks(self, wf_spec, context, deployment_id, resource,
                              key):
        self._verify_existing_resource(resource, key)
        instance = resource.get("instance") or {}
        lb_id = instance.get("id")
        dom_id = resource.get("instance", {}).get("domain_id")
        rec_id = resource.get("instance", {}).get("record_id")
        region = resource.get("region")
        if isinstance(context, middleware.RequestContext):
            context = context.get_queued_task_dict(deployment=deployment_id,
                                                   resource=key)
        else:
            context['deployment'] = deployment_id
            context['resource'] = key

        delete_lb = specs.Celery(
            wf_spec,
            'Delete Loadbalancer (%s)' % key,
            'checkmate.providers.rackspace.loadbalancer.delete_lb_task',
            call_args=[context, key, lb_id, region],
            properties={
                'estimated_duration': 5,
            },
        )

        wait_on_lb_delete = specs.Celery(
            wf_spec,
            'Wait for Loadbalancer (%s) delete' % key,
            'checkmate.providers.rackspace.loadbalancer.'
            'wait_on_lb_delete_task',
            call_args=[context, key, lb_id, region],
            properties={
                'estimated_duration': 20,
            },
        )

        delete_lb.connect(wait_on_lb_delete)
        task_dict = {'root': [delete_lb]}
        if dom_id and rec_id:
            delete_record = specs.Celery(
                wf_spec,
                'Delete DNS record for %s' % dom_id,
                'checkmate.providers.rackspace.dns.delete_record_task',
                call_args=[context, dom_id, rec_id],
                properties={
                    'estimated_duration': 5,
                },
            )
            task_dict["root"].append(delete_record)
        return task_dict

    def add_delete_connection_tasks(self, wf_spec, context,
                                    deployment, source_resource,
                                    target_resource):
        source_key = source_resource['index']
        target_key = target_resource['index']
        delete_node_task = specs.Celery(
            wf_spec,
            "Remove Node %s from LB %s" % (target_key, source_key),
            "checkmate.providers.rackspace.loadbalancer.delete_node",
            call_args=[
                context.get_queued_task_dict(deployment=deployment['id'],
                                             resource=source_key),
                operators.PathAttrib('instance:%s/id' % source_key),
                operators.PathAttrib('instance:%s/private_ip' % target_key),
                source_resource['region']
            ],
            defines=dict(provider=self.key, resource=target_key,
                         task_tags=['delete_connection']),
            properties={'estimated_duration': 5})
        wf_spec.start.connect(delete_node_task)

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        interface = relation['interface']
        if interface and "vip" != interface.lower():
            self._add_node_connection(resource, key, relation, relation_key,
                                      wfspec, deployment, context, interface)

    def _add_node_connection(self, resource, key, relation, relation_key,
                             wfspec, deployment, context, interface):
        """Workflow gen for adding LB Node."""
        comp = self.find_components(context, id="rsCloudLB")
        if not comp:
            error_message = "Could not locate component for id 'rsCloudLB'"
            raise exceptions.CheckmateUserException(
                error_message,
                get_class_name(exceptions.CheckmateException),
                exceptions.BLUEPRINT_ERROR, '')
        else:
            comp = comp[0]  # there should be only one
            options = comp.get('options', {})
            protocol_option = options.get("protocol", {})
            protocols = protocol_option.get("choice", [])
            if interface not in protocols:
                error_message = ("'%s' is an invalid relation interface for "
                                 "provider '%s'. Valid options are: %s"
                                 % (interface, self.key, protocols))
                raise exceptions.CheckmateUserException(
                    error_message,
                    get_class_name(exceptions.CheckmateException),
                    exceptions.BLUEPRINT_ERROR, '')

        # Get all tasks we need to precede the LB Add Node task
        finals = wfspec.find_task_specs(resource=relation['target'],
                                        tag='final')
        lb_final_tasks = wfspec.find_task_specs(resource=key,
                                                provider=self.key,
                                                tag='final')
        target_resource = deployment['resources'][relation['target']]
        if 'hosted_on' in target_resource:
            target = target_resource['hosted_on']
        else:
            target = relation['target']
            # determine the port based on protocol
        #Create the add node task
        add_node_task = specs.Celery(
            wfspec,
            "Add Node %s to LB %s" % (relation['target'], key),
            'checkmate.providers.rackspace.loadbalancer.'
            'add_node',
            call_args=[
                context.get_queued_task_dict(deployment=deployment['id'],
                                             resource=key),
                operators.PathAttrib('instance:%s/id' % key),
                operators.PathAttrib('instance:%s/private_ip' % target),
                resource['region'], resource
            ],
            defines=dict(relation=relation_key, provider=self.key,
                         task_tags=['final']),
            properties={'estimated_duration': 20}
        )

        #Make it wait on all other provider completions
        if lb_final_tasks:
            finals.append(lb_final_tasks[0])
        wfspec.wait_for(
            add_node_task,
            finals,
            name="Wait before adding %s to LB %s" % (relation['target'], key),
            description="Wait for Load Balancer ID and for server to be "
                        "fully configured before adding it to load balancer",
            defines=dict(relation=relation_key, provider=self.key,
                         task_tags=['root']))

    def get_catalog(self, context, type_filter=None, **kwargs):
        '''Return stored/override catalog if it exists, else connect, build,
        and return one.
        '''

        # TODO(any): maybe implement this an on_get_catalog so we don't have to
        #        do this for every provider
        results = ProviderBase.get_catalog(self, context,
                                           type_filter=type_filter)
        if results:
            # We have a prexisting or overridecatalog stored
            return results

        # build a live catalog ()this would be the on_get_catalog called if no
        # stored/override existed
        results = {}
        region = getattr(context, 'region', None)
        if not region:
            region = Provider.find_a_region(context.catalog)
        api_endpoint = Provider.find_url(context.catalog, region)
        if not api_endpoint:
            LOG.warning("No Cloud Load Balancer endpoint in region %s", region)
            return {}

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context.catalog:
                if service['type'] == 'rax:load-balancer':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
            if 'lists' not in results:
                results['lists'] = {}
            results['lists']['regions'] = regions

        if type_filter is None or type_filter == 'load-balancer':
            algorithms = _get_algorithms(context)
            options = {
                'algorithm': {
                    'type': 'list',
                    'choice': algorithms
                },
                'create_dns': {
                    'type': 'boolean',
                    'default': False
                },
                'allow_insecure': {
                    'type': 'boolean',
                    'default': False,
                    'description': 'For secure protocols (https, pop3s, sftp, '
                                   'ldaps, pop3s) turning this on will also '
                                   'allow the unencrypted version of the '
                                   'protocol.'
                }
            }

            if 'load-balancer' not in results:
                results['load-balancer'] = {}

            # provide list of available load balancer types

            protocols = _get_protocols(context)
            protocols = [p.lower() for p in protocols]
            for protocol in protocols:
                item = {'id': protocol, 'is': 'load-balancer',
                        'provides': [{'load-balancer': protocol}],
                        #FIXME: we don't need to call this the name of a valid,
                        #resource type, but until we get the key'd requires
                        #code in, this stops it failing validation.
                        'requires': [{"application": {'interface': protocol}}],
                        'options': copy.copy(options)}
                results['load-balancer'][protocol] = item

            # provide abstracted 'proxy' load-balancer type

            # add our custom protocol for handling both http and https on same
            # vip
            # TODO(any): add support for arbitrary combinations of secure and
            #       unsecure protocols (ftp/ftps for example)
            if "http_and_https" not in protocols:
                protocols.extend(["http_and_https"])
            protocol_option = {'protocol': {'type': 'list',
                                            'choice': protocols}}
            options.update(protocol_option)
            results['load-balancer']['rsCloudLB'] = {
                'id': 'rsCloudLB',
                'is': 'load-balancer',
                'provides': [{'load-balancer': 'proxy'}],
                'options': options}

        self.validate_catalog(results)
        if type_filter is None:
            self._dict['catalog'] = results
        return results

    @staticmethod
    def get_resources(context, tenant_id=None):
        """Proxy request through to loadbalancer provider"""
        if not pyrax.get_setting("identity_type"):
            pyrax.set_setting("identity_type", "rackspace")

        load_balancers = []
        pyrax.auth_with_token(context.auth_token, tenant_name=context.tenant)
        for region in pyrax.regions:
            api = Provider.connect(context, region=region)
            load_balancers += api.list()
        results = {}
        for idx, clb in enumerate(load_balancers):
            vip = None
            for ip_data in clb.virtual_ips:
                if ip_data.ip_version == 'IPV4' and ip_data.type == "PUBLIC":
                    vip = ip_data.address

            results[idx] = {
                'status': clb.status,
                'index': idx,
                'region': clb.manager.api.region_name,
                'provider': 'load-balancer',
                'dns-name': clb.name,
                'instance': {
                    'protocol': clb.protocol,
                    'interfaces': {
                        'vip': {
                            'public_ip': vip,
                            'ip': vip
                        }
                    },
                    'id': clb.id,
                    'public_ip': vip,
                    'port': clb.port
                },
                'type': 'load-balancer'
            }
        return results

    @staticmethod
    def find_url(catalog, region):
        '''Find endpoint URL for region.'''
        for service in catalog:
            if service['type'] == 'rax:load-balancer':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    if endpoint.get('region') == region:
                        return endpoint['publicURL']

    @staticmethod
    def find_a_region(catalog):
        '''Any region.'''
        for service in catalog:
            if service['type'] == 'rax:load-balancer':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    return endpoint['region']

    @staticmethod
    def connect(context, region=None):
        '''Use context info to connect to API and return api object.'''
        return getattr(base.RackspaceProviderBase._connect(context, region),
                       Provider.method)


@caching.Cache(timeout=3600, sensitive_args=[1], store=API_ALGORTIHM_CACHE,
               backing_store=REDIS, backing_store_key='rax.lb.algorithms')
def _get_algorithms(context):
    '''Ask CLB for Algorithms.'''
    # the region must be supplied but is not used
    try:
        api = Provider.connect(context)
        LOG.info("Calling Cloud Load Balancers to get algorithms for %s",
                 api.region_name)
        results = api.algorithms
        LOG.debug("Found Load Balancer algorithms for %s: %s",
                  api.management_url, results)
    except StandardError as exc:
        LOG.error("Error retrieving Load Balancer algorithms from %s: %s",
                  context['region'], exc)
        raise
    return results


@caching.Cache(timeout=3600, sensitive_args=[1], store=API_PROTOCOL_CACHE,
               backing_store=REDIS, backing_store_key='rax.lb.protocols')
def _get_protocols(context):
    '''Ask CLB for Protocols.'''
    # the region must be supplied but is not used
    try:
        api = Provider.connect(context)
        LOG.info("Calling Cloud Load Balancers to get protocols for %s",
                 api.management_url)
        results = api.protocols
        LOG.debug("Found Load Balancer protocols for %s: %s",
                  api.management_url, results)
    except StandardError as exc:
        LOG.error("Error retrieving Load Balancer protocols from %s: %s",
                  context['region'], exc)
        raise
    return results
