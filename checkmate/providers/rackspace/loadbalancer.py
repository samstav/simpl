'''
Rackspace Cloud Load Balancer provider and celery tasks
'''
import copy
import logging
import sys

from celery.canvas import chain, group
from cloudlb.errors import CloudlbException, NotFound, RateLimit
from SpiffWorkflow.operators import PathAttrib, Attrib
from SpiffWorkflow.specs import Celery

import cloudlb

from checkmate.common.caching import Memorize, MemorizeMethod
from checkmate.deployments import (
    resource_postback,
    alt_resource_postback,
)
from checkmate.deployments.tasks import reset_failed_resource_task
from checkmate.exceptions import (
    CheckmateException,
    CheckmateNoTokenError,
    CheckmateBadState,
    CheckmateRetriableException,
)
from checkmate.middleware import RequestContext
from checkmate.providers.base import ProviderBase, user_has_access
from checkmate.providers.rackspace import dns
from checkmate.utils import match_celery_logging
from checkmate.workflow import wait_for


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

#FIXME: delete tasks talk to database directly, so we load drivers and manager
import os
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


class Provider(ProviderBase):
    '''Rackspace load balancer provider'''
    name = 'load-balancer'
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
            raise CheckmateException("Could not identify which region to "
                                     "create load-balancer in")
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
        dns = str(deployment.get_setting("create_dns",
                                         resource_type=resource_type,
                                         service_name=service,
                                         default="false"))
        return dns.lower() in ['true', '1', 'yes']

    @MemorizeMethod(timeout=3600, sensitive_args=[1], store=LB_API_CACHE)
    def _get_abs_limits(self, username, auth_token, api_endpoint, region):
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
        cur_lbs = len(clb.loadbalancers.list() or [])
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
        vip_tasks = self.find_tasks(wfspec, provider=self.key, tag='vip')
        parent_lb = None

        if vip_tasks:
            parent_lb_resource_id = vip_tasks[0].get_property('resource')
            parent_lb = PathAttrib("instance:%s/id" % parent_lb_resource_id)
            create_lb_task_tags.remove('vip')

        create_lb = Celery(
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
        build_wait_task = Celery(
            wfspec,
            task_name,
            celery_call,
            call_args=[
                context.get_queued_task_dict(
                    deployment=deployment['id'],
                    resource=key
                ),
                PathAttrib('instance:%s/id' % key),
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
            create_record_task = Celery(wfspec, task_name, celery_call,
                                        call_args=[
                                            context.get_queued_task_dict(
                                                deployment=deployment['id'],
                                                resource=key),
                                            parse_domain(name),
                                            '.'.join(name.split('.')[1:]),
                                            "A",
                                            PathAttrib('instance:%s/public_ip'
                                                       % key)],
                                        rec_ttl=300,
                                        makedomain=True,
                                        result_key="dns-record")
            build_wait_task.connect(create_record_task)
            task_name = ("Update Load Balancer %s (%s) DNS Data"
                         % (key, resource['service']))
            celery_call = ('checkmate.providers.rackspace.loadbalancer.'
                           'collect_record_data')
            crd = Celery(wfspec, task_name, celery_call,
                         call_args=[
                             deployment["id"],
                             key,
                             Attrib('dns-record')
                         ])
            create_record_task.connect(crd)

        task_name = ('Add monitor to Loadbalancer %s (%s) build' %
                     (key, resource['service']))
        celery_call = 'checkmate.providers.rackspace.loadbalancer.set_monitor'
        set_monitor_task = Celery(
            wfspec,
            task_name,
            celery_call,
            call_args=[
                context.get_queued_task_dict(
                    deployment=deployment['id'],
                    resource=key
                ),
                PathAttrib('instance:%s/id' % key),
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
        return super(Provider, self).get_resource_status(context,
                                                         deployment_id,
                                                         resource, key,
                                                         sync_callable=
                                                         sync_resource_task,
                                                         api=api)

    def sync_resource_status(self, context, deployment_id, resource,
                             key):
        self._verify_existing_resource(resource, key)
        ctx = context.get_queued_task_dict(deployment=deployment_id,
                                           resource=key)
        chain(
            sync_resource_task.s(ctx, resource, key),
            alt_resource_postback.s(deployment_id)
        )()

    def delete_resource_tasks(self, context, deployment_id, resource, key):
        self._verify_existing_resource(resource, key)
        lb_id = resource.get("instance", {}).get("id")
        dom_id = resource.get("instance", {}).get("domain_id")
        rec_id = resource.get("instance", {}).get("record_id")
        region = resource.get("region")
        if isinstance(context, RequestContext):
            context = context.get_queued_task_dict(deployment=deployment_id,
                                                   resource=key)
        else:
            context['deployment'] = deployment_id
            context['resource'] = key

        del_task = chain(delete_lb_task.s(context, key, lb_id, region),
                         alt_resource_postback.s(deployment_id),
                         wait_on_lb_delete.si(context, key, deployment_id,
                                              lb_id, region),
                         alt_resource_postback.s(deployment_id))

        delete_stuff = del_task
        if dom_id and rec_id:
            delete_stuff = group(del_task,
                                 delete_record.s(context, dom_id,
                                                 rec_id))
        return delete_stuff

    def add_connection_tasks(self, resource, key, relation, relation_key,
                             wfspec, deployment, context):
        interface = relation['interface']
        if interface and "vip" != interface.lower():
            self._add_node_connection(resource, key, relation, relation_key,
                                      wfspec, deployment, context, interface)

    def _add_node_connection(self, resource, key, relation, relation_key,
                             wfspec, deployment, context, interface):
        comp = self.find_components(context, id="rsCloudLB")
        if not comp:
            raise CheckmateException("Could not locate component for id "
                                     "'rsCloudLB'")
        else:
            comp = comp[0]  # there should be only one
            options = comp.get('options', {})
            protocol_option = options.get("protocol", {})
            protocols = protocol_option.get("choice", [])
            if interface not in protocols:
                raise CheckmateException("'%s' is an invalid relation "
                                         "interface for provider '%s'. Valid "
                                         "options are: %s" % (interface,
                                                              self.key,
                                                              protocols))

        # Get all tasks we need to precede the LB Add Node task
        finals = self.find_tasks(wfspec, resource=relation['target'],
                                 tag='final')
        create_lb = self.find_tasks(wfspec, resource=key, provider=self.key,
                                    tag='final')[0]
        target_resource = deployment['resources'][relation['target']]
        if 'hosted_on' in target_resource:
            target = target_resource['hosted_on']
        else:
            target = relation['target']
            # determine the port based on protocol
        #Create the add node task
        add_node_task = Celery(wfspec,
                               "Add Node %s to LB %s" % (relation['target'],
                                                         key),
                               'checkmate.providers.rackspace.loadbalancer.'
                               'add_node',
                               call_args=[
                                   context.get_queued_task_dict(
                                       deployment=deployment['id'],
                                       resource=key),
                                   PathAttrib('instance:%s/id' % key),
                                   PathAttrib('instance:%s/private_ip' %
                                              target),
                                   resource['region'], resource],
                               defines=dict(relation=relation_key,
                                            provider=self.key,
                                            task_tags=['final']),
                               properties={'estimated_duration': 20})

        #Make it wait on all other provider completions
        finals.append(create_lb)
        wait_for(wfspec, add_node_task, finals,
                 name="Wait before adding %s to LB %s" % (relation['target'],
                                                          key),
                 description="Wait for Load Balancer ID "
                             "and for server to be fully configured before "
                             "adding it to load balancer",
                 defines=dict(relation=relation_key, provider=self.key,
                              task_tags=['root']))

    def get_catalog(self, context, type_filter=None):
        '''Return stored/override catalog if it exists, else connect, build,
        and return one
        '''

        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #        this for every provider
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
            algorithms = _get_algorithms(api_endpoint, context.auth_token)
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

            protocols = _get_protocols(api_endpoint, context.auth_token)
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
            # TODO: add support for arbitrary combinations of secure and
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
    def find_url(catalog, region):
        '''Find endpoint URL for region'''
        for service in catalog:
            if service['type'] == 'rax:load-balancer':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    if endpoint.get('region') == region:
                        return endpoint['publicURL']

    @staticmethod
    def find_a_region(catalog):
        '''Any region'''
        for service in catalog:
            if service['type'] == 'rax:load-balancer':
                endpoints = service['endpoints']
                for endpoint in endpoints:
                    return endpoint['region']

    @staticmethod
    def connect(context, region=None):
        '''Use context info to connect to API and return api object'''
        #FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, dict):
            context = RequestContext(**context)
        if not context.auth_token:
            raise CheckmateNoTokenError()

        # Make sure we use airport codes (translate cities to that)
        if region in REGION_MAP:
            region = REGION_MAP[region]

        if not region:
            region = getattr(context, 'region', None)
            if not region:
                region = Provider.find_a_region(context.catalog)
            if not region:
                raise CheckmateException("Unable to locate a load-balancer "
                                         "endpoint")

        #TODO: instead of hacking auth using a token, submit patch upstream
        url = Provider.find_url(context.catalog, region)
        if not url:
            raise CheckmateException("Unable to locate region url for LBaaS "
                                     "for region '%s'" % region)
        api = cloudlb.CloudLoadBalancer(context.username, 'dummy', region)
        api.client.auth_token = context.auth_token
        api.client.region_account_url = url

        return api


@Memorize(timeout=3600, sensitive_args=[1], store=API_ALGORTIHM_CACHE)
def _get_algorithms(api_endpoint, auth_token):
    '''Ask CLB for Algorithms'''
    # the region must be supplied but is not used
    api = cloudlb.CloudLoadBalancer('ignore', 'ignore', 'DFW')
    api.client.auth_token = auth_token
    api.client.region_account_url = api_endpoint
    LOG.info("Calling Cloud Load Balancers to get algorithms for %s",
             api.client.region_account_url)


@Memorize(timeout=3600, sensitive_args=[1], store=API_PROTOCOL_CACHE)
def _get_protocols(api_endpoint, auth_token):
    '''Ask CLB for Protocols'''
    # the region must be supplied but is not used
    api = cloudlb.CloudLoadBalancer('ignore', 'ignore', 'DFW')
    api.client.auth_token = auth_token
    api.client.region_account_url = api_endpoint
    LOG.info("Calling Cloud Load Balancers to get protocols for %s",
             api.client.region_account_url)

    return api.get_protocols()

from celery.task import task

from checkmate.providers.rackspace.dns import parse_domain, delete_record

# Cloud Load Balancers needs an IP for all load balancers. To create one we
# sometimes need a dummy node. This is the IP address we use for the dummy
# node. Requests to manage this node are intentionally errored out.
PLACEHOLDER_IP = '1.2.3.4'

#
# Celery tasks
#


@task
def create_loadbalancer(context, name, vip_type, protocol, region, api=None,
                        dns=False, port=None, algorithm='ROUND_ROBIN',
                        tags=None,
                        monitor_path='/', monitor_delay=10, monitor_timeout=10,
                        monitor_attempts=3, monitor_body='(.*)',
                        monitor_status='^[234][0-9][0-9]$', parent_lb=None):
    '''Celery task to create Cloud Load Balancer'''
    assert 'deployment' in context, "Deployment not supplied in context"
    match_celery_logging(LOG)

    if context.get('simulation') is True:
        resource_key = context['resource']
        vip = "4.4.4.20%s" % resource_key
        results = {
            'instance:%s' % resource_key: {
                'status': "BUILD",
                'id': "LB0%s" % resource_key,
                'public_ip': vip,
                'port': port,
                'protocol': protocol,
                'interfaces': {
                    'vip': {
                        'ip': vip,
                        'public_ip': vip,
                    },
                },
            }
        }
        # Send data back to deployment
        resource_postback.delay(context['deployment'], results)
        return results

    if api is None:
        api = Provider.connect(context, region)

    reset_failed_resource_task.delay(context["deployment"],
                                     context["resource"])

    #FIXME: should pull default from lb api but thats not exposed via the
    #       client yet
    if not port:
        port = 443 if "https" == protocol.lower() else 80

    fakenode = cloudlb.Node(address=PLACEHOLDER_IP, condition="ENABLED",
                            port=port)

    # determine new or shared vip
    vip = None
    if not parent_lb:
        vip = cloudlb.VirtualIP(type=vip_type)
    else:
        # share vip with another lb in the deployment
        other_lb = api.loadbalancers.get(parent_lb)
        if not other_lb:
            return create_loadbalancer.retry(
                exc=CheckmateException("Could not locate load balancer %s for "
                                       "shared vip" % parent_lb))
        for _vip in other_lb.virtualIps:
            if vip_type.upper() == _vip.type:
                vip = cloudlb.VirtualIP(id=_vip.id)
                break
        if not vip:
            create_loadbalancer.retry(
                exc=CheckmateException("Cannot get %s vip for load balancer "
                                       "%s") % (vip_type, parent_lb))
    instance_key = 'instance:%s' % context['resource']
    # Add RAX-CHECKMATE to metadata
    # support old way of getting metadata from generate_template
    meta = tags or context.get("metadata", None)

    try:
        if meta:
            # attach checkmate metadata to the lb if available
            new_meta = []
            # Assumes that meta data is in format
            #   "meta" : {"key" : "value" , "key2" : "value2"}
            for key in meta:
                new_meta.append({"key": key, "value": meta[key]})
            loadbalancer = api.loadbalancers.create(
                name=name, port=port, protocol=protocol.upper(),
                nodes=[fakenode], virtualIps=[vip],
                algorithm=algorithm, metadata=new_meta)
        else:
            loadbalancer = api.loadbalancers.create(
                name=name, port=port, protocol=protocol.upper(),
                nodes=[fakenode], virtualIps=[vip], algorithm=algorithm)
    except RateLimit as rate_limit_exc:
        raise CheckmateRetriableException(rate_limit_exc.reason, "")

    # Put the instance_id in the db as soon as it's available
    instance_id = {
        instance_key: {
            'id': loadbalancer.id
        }
    }
    resource_postback.delay(context['deployment'], instance_id)

    # update our assigned vip
    for ip_data in loadbalancer.virtualIps:
        if ip_data.ipVersion == 'IPV4' and ip_data.type == "PUBLIC":
            vip = ip_data.address

    LOG.debug('Load balancer %s building. VIP = %s', loadbalancer.id, vip)

    results = {
        instance_key: {
            'id': loadbalancer.id,
            'public_ip': vip,
            'port': loadbalancer.port,
            'protocol': loadbalancer.protocol,
            'status': "BUILD",
            'interfaces': {
                'vip': {
                    'ip': vip,
                    'public_ip': vip,
                }
            }
        }
    }

    # Send data back to deployment
    resource_postback.delay(context['deployment'], results)
    return results


@task
def collect_record_data(deployment_id, resource_key, record):
    assert deployment_id, "No deployment id specified"
    assert resource_key, "No resource key specified"
    assert record, "No record specified"

    if "id" not in record:
        raise CheckmateException("Missing record id in %s" % record)
    if "domain" not in record:
        raise CheckmateException("No domain specified for record %s"
                                 % record.get("id"))
    contents = {
        "instance:%s" % resource_key: {
            "domain_id": record.get("domain"),
            "record_id": record.get("id")
        }
    }
    resource_postback.delay(deployment_id, contents)
    return contents


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
        lb = api.loadbalancers.get(resource.get("instance", {}).get("id"))
        # TODO(Nate): Update sync to use postback instead of resource postback
        #and also add in checkmate translated status to resource root
        #instance = {'port': resource['instance']['port'],
        #            'protocol': resource['instance']['protocol']}
        #if hasattr(lb, 'port') and resource['instance']['port'] != lb.port:
        #    instance['port'] = lb.port
        #if hasattr(lb, 'port') and
        #   resource['instance']['protocol'] != lb.protocol:
        #    instance['protocol'] = lb.protocol
        return {
            key: {
                'status': lb.status
                #'instance': instance
            }
        }
    except NotFound:
        return {
            key: {
                'status': 'DELETED'
            }
        }


@task
def delete_lb_task(context, key, lbid, region, api=None):
    """Celery task to delete a Cloud Load Balancer"""
    match_celery_logging(LOG)

    if context.get('simulation') is True:
        resource_key = context['resource']
        results = {
            "instance:%s" % resource_key: {
                'status': 'DELETING',
                "status-message": "Waiting on resource deletion"
            }
        }
        return results

    def on_failure(exc, task_id, args, kwargs, einfo):
        results = {
            "instance:%s" % args[1]: {
                'status': 'ERROR',
                'status-message': ('Unexpected error deleting loadbalancer'
                    ' %s' % key),
                'error-traceback': 'Task %s: %s' % (task_id, einfo.traceback)
            }
        }
        resource_postback.delay(args[2], results)

    delete_lb_task.on_failure = on_failure

    if not lbid:
        LOG.error("Must provide a load balancer id")
        return
    if api is None:
        api = Provider.connect(context, region)

    instance_key = "instance:%s" % key
    try:
        dlb = api.loadbalancers.get(lbid)
    except cloudlb.errors.NotFound:
        LOG.debug('Load balancer %s was already deleted.', lbid)
        results = {
            instance_key: {
                'status': 'DELETED',
                'status-message': ''
            }
        }
        return results
    LOG.debug("Found load balancer %s [%s] to delete" % (dlb, dlb.status))
    if dlb.status != "DELETED":
        dlb.delete()
    LOG.debug('Deleting Load balancer %s.', lbid)
    return {
        instance_key: {
            'status': 'DELETING',
            'status-message': 'Waiting on resource deletion'
        }
    }


@task(default_retry_delay=2, max_retries=60)
def wait_on_lb_delete(context, key, dep_id, lbid, region, api=None):
    match_celery_logging(LOG)
    inst_key = "instance:%s" % key

    if context.get('simulation') is True:
        results = {inst_key: {'status': 'DELETED'}}
        return results

    def on_failure(exc, task_id, args, kwargs, einfo):
        """ Handle task failure """
        results = {
            "instance:%s" % args[1]: {
                'status': 'ERROR',
                'status-message': ('Unexpected error waiting on loadbalancer'
                    ' %s delete' % key),
                'error-traceback': 'Task %s: %s' % (task_id, einfo.traceback)
            }
        }
        resource_postback.delay(args[2], results)

    wait_on_lb_delete.on_failure = on_failure

    if api is None:
        api = Provider.connect(context, region)
    dlb = None
    LOG.debug("Checking on loadbalancer %s delete status", lbid)
    try:
        dlb = api.loadbalancers.get(lbid)
    except cloudlb.errors.NotFound:
        pass
    if (not dlb) or "DELETED" == dlb.status:
        return {
            inst_key: {
                'status': 'DELETED',
                'status-message': ''
            }
        }
    else:
        msg = ("Waiting on state DELETED. Load balancer is in state %s"
               % dlb.status)
        results = {
            inst_key: {
                'status': 'DELETING',
                "status-message": msg
            }
        }
        resource_postback.delay(dep_id, results)
        wait_on_lb_delete.retry(exc=CheckmateException(msg))


@task(default_retry_delay=10, max_retries=10)
def add_node(context, lbid, ipaddr, region, resource, api=None):
    '''Celery task to add a node to a Cloud Load Balancer'''
    match_celery_logging(LOG)

    if context.get('simulation') is True:
        results = {}
        return results

    if api is None:
        api = Provider.connect(context, region)

    if ipaddr == PLACEHOLDER_IP:
        raise CheckmateException("IP %s is reserved as a placeholder IP by "
                                 "checkmate" % ipaddr)

    loadbalancer = api.loadbalancers.get(lbid)

    if loadbalancer.status != "ACTIVE":
        exc = CheckmateException("Loadbalancer %s cannot be modified while "
                                 "status is %s" % (lbid, loadbalancer.status))
        return add_node.retry(exc=exc)
    if not (loadbalancer and loadbalancer.port):
        exc = CheckmateBadState("Could not retrieve data for load balancer %s"
                                % lbid)
        return add_node.retry(exc=exc)
    results = None
    port = loadbalancer.port

    #    status_results = {'status': "CONFIGURE"}
    #    instance_key = 'instance:%s' % context['resource']
    #    status_results = {instance_key: status_results}
    #    resource_postback.delay(context['deployment'], status_results)

    # Check existing nodes and asses what we need to do
    new_node = None  # We store our new node here
    placeholder = None  # We store our placeholder node here
    for node in loadbalancer.nodes:
        if node.address == ipaddr:
            if node.port == port and node.condition == "ENABLED":
                new_node = node
            else:
                # Node exists. Let's just update it
                if node.port != port:
                    node.port = port
                if node.condition != "ENABLED":
                    node.condition = "ENABLED"
                node.update()
                LOG.debug("Updated %s:%d from load balancer %d", node.address,
                          node.port, lbid)
                # We return this at the end of the call
            results = {'id': node.id}
        elif node.address == PLACEHOLDER_IP:
            # This is the dummy, placeholder node
            placeholder = node

    # Create new node
    if not new_node:
        node = cloudlb.Node(address=ipaddr, port=port, condition="ENABLED")
        try:
            results = loadbalancer.add_nodes([node])
            # I don't believe you! Check... this has been unreliable. Possible
            # because we need to refresh nodes
            lb_fresh = api.loadbalancers.get(lbid)
            if [n for n in lb_fresh.nodes if n.address == ipaddr]:
                #OK!
                results = {'id': results[0].id}
            else:
                LOG.warning("CloudLB says node %s (ID=%s) was added to LB %s, "
                            "but upon validating, it does not look like that "
                            "is the case!", ipaddr, results[0].id, lbid)
                # Try again!
                exc = CheckmateException("Validation failed - Node was not "
                                         "added")
                return add_node.retry(exc=exc)
        except cloudlb.errors.ResponseError, exc:
            if exc.status == 422:
                LOG.debug("Cannot modify load balancer %d. Will retry "
                          "adding %s (%d %s)", lbid, ipaddr, exc.status,
                          exc.reason)
                return add_node.retry(exc=exc)
            LOG.debug("Response error from load balancer %d. Will retry "
                      "adding %s (%d %s)", lbid, ipaddr, exc.status,
                      exc.reason)
            return add_node.retry(exc=exc)
        except Exception, exc:
            LOG.debug("Error adding %s behind load balancer %d. Error: "
                      "%s. Retrying", ipaddr, lbid, str(exc))
            return add_node.retry(exc=exc)

    # Delete placeholder
    if placeholder:
        try:
            placeholder.delete()
            LOG.debug('Removed %s:%s from load balancer %s',
                      placeholder.address, placeholder.port, lbid)
        # The lb client exceptions extend Exception and are missed
        # by the generic handler
        except (CloudlbException, StandardError) as exc:
            return add_node.retry(exc=exc)

    return results


@task(default_retry_delay=10, max_retries=10)
def delete_node(context, lbid, ipaddr, port, region, api=None):
    '''Celery task to delete a node from a Cloud Load Balancer'''
    match_celery_logging(LOG)

    if context.get('simulation') is True:
        return

    if api is None:
        api = Provider.connect(context, region)

    loadbalancer = api.loadbalancers.get(lbid)
    node_to_delete = None
    for node in loadbalancer.nodes:
        if node.address == ipaddr and node.port == port:
            node_to_delete = node
    if node_to_delete:
        try:
            node_to_delete.delete()
            LOG.debug('Removed %s:%s from load balancer %s', ipaddr, port,
                      lbid)
        except cloudlb.errors.ResponseError, exc:
            if exc.status == 422:
                LOG.debug("Cannot modify load balancer %d. Will retry "
                          "deleting %s:%s (%s %s)", lbid, ipaddr, port,
                          exc.status, exc.reason)
                delete_node.retry(exc=exc)
            LOG.debug('Response error from load balancer %d. Will retry '
                      'deleting %s:%s (%s %s)', lbid, ipaddr, port, exc.status,
                      exc.reason)
            delete_node.retry(exc=exc)
        except Exception, exc:
            LOG.debug("Error deleting %s:%s from load balancer %s. Error: %s. "
                      "Retrying", ipaddr, port, lbid, str(exc))
            delete_node.retry(exc=exc)
    else:
        LOG.debug('No LB node matching %s:%s on LB %s', ipaddr, port, lbid)


@task(default_retry_delay=10, max_retries=10)
def set_monitor(context, lbid, mon_type, region, path='/', delay=10,
                timeout=10, attempts=3, body='(.*)',
                status='^[234][0-9][0-9]$', api=None):
    '''Create a monitor for a Cloud Load Balancer'''
    match_celery_logging(LOG)

    if context.get('simulation') is True:
        return

    if api is None:
        api = Provider.connect(context, region)

    LOG.debug("Setting monitor on lbid: %s", lbid)
    loadbalancer = api.loadbalancers.get(lbid)

    try:
        hm_monitor = loadbalancer.healthmonitor()
        monitor = cloudlb.healthmonitor.HealthMonitor(
            type=mon_type, delay=delay,
            timeout=timeout,
            attemptsBeforeDeactivation=attempts,
            path=path,
            statusRegex=status,
            bodyRegex=body)
        hm_monitor.add(monitor)
    except cloudlb.errors.ImmutableEntity as im_ent:
        LOG.debug("Cannot modify loadbalancer %s yet.", lbid, exc_info=True)
        set_monitor.retry(exc=im_ent)
    except cloudlb.errors.ResponseError as response_error:
        if response_error.status == 422:
            LOG.debug("Cannot modify load balancer %s. Will retry setting %s "
                      "monitor (%s %s)", lbid, type, response_error.status,
                      response_error.reason)
            set_monitor.retry(exc=response_error)
        LOG.debug("Response error from load balancer %s. Will retry setting "
                  "%s monitor (%s %s)", lbid, type, response_error.status,
                  response_error.reason)
        set_monitor.retry(exc=response_error)
    except Exception as exc:
        LOG.debug("Error setting %s monitor on load balancer %s. Error: %s. "
                  "Retrying", type, lbid, str(exc))
        set_monitor.retry(exc=exc)


@task(default_retry_delay=30, max_retries=120, acks_late=True)
def wait_on_build(context, lbid, region, api=None):
    '''Checks to see if a lb's status is ACTIVE, so we can change resource
    status in deployment
    '''

    match_celery_logging(LOG)
    assert lbid, "ID must be provided"
    assert 'deployment' in context, "Deployment not supplied in context"
    LOG.debug("Getting loadbalancer %s", lbid)

    if context.get('simulation') is True:
        instance_key = 'instance:%s' % context['resource']
        results = {
            instance_key: {
                'status': 'ACTIVE',
                'status-message': ''
            }
        }
        resource_postback.delay(context['deployment'], results)
        return results

    if api is None:
        api = Provider.connect(context, region)

    loadbalancer = api.loadbalancers.get(lbid)

    instance_key = 'instance:%s' % context['resource']
    if loadbalancer.status == "ERROR":
        msg = ("Loadbalancer %s build failed" % (lbid))
        results = {
            instance_key: {
                'status': 'ERROR',
                'status-message': msg
            }
        }
        resource_postback.delay(context['deployment'], results)

        # Delete the loadbalancer if it failed building
        Provider({}).delete_resource_tasks(context,
                                           context['deployment'],
                                           get_resource_by_id(
                                               context['deployment'],
                                               context['resource']),
                                           instance_key).apply_async()
        raise CheckmateRetriableException(msg, "")
    elif loadbalancer.status == "ACTIVE":
        results = {
            instance_key: {
                'id': lbid,
                'status': 'ACTIVE',
                'status-message': ''
            }
        }
        resource_postback.delay(context['deployment'], results)
        return results
    else:
        msg = ("Loadbalancer status is %s, retrying" % (loadbalancer.status))
        return wait_on_build.retry(exc=CheckmateException(msg))
