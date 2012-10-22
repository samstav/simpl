import logging

from SpiffWorkflow.operators import PathAttrib
from SpiffWorkflow.specs import Celery

from checkmate.deployments import resource_postback
from checkmate.exceptions import CheckmateException, CheckmateNoTokenError,\
    CheckmateBadState
from checkmate.providers import ProviderBase
from checkmate.workflows import wait_for
from checkmate.utils import match_celery_logging
from copy import deepcopy

LOG = logging.getLogger(__name__)

# Any names should become airport codes
REGION_MAP = {'dallas': 'DFW',
              'chicago': 'ORD',
              'london': 'LON'}


class Provider(ProviderBase):
    name = 'load-balancer'
    vendor = 'rackspace'

    def generate_template(self, deployment, resource_type, service, context,
            name=None):
        template = ProviderBase.generate_template(self,
                deployment, resource_type, service, context, name=name)

        # Get region
        region = deployment.get_setting('region', resource_type=resource_type,
                service_name=service, provider_key=self.key)
        if not region:
            raise CheckmateException("Could not identify which region to "
                    "create load-balancer in")

        template['region'] = region
        return template

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        proto = deployment.get_setting("protocol", resource_type="load-balancer",
                                       service_name=resource.get('service', None), 
                                       default="HTTP")
        # handle our custom protocol
        dual = ("http_and_https" == proto)
        if dual:
            proto = "http"
            
        create_lb = Celery(wfspec, 'Create %s Loadbalancer' % proto,
                'checkmate.providers.rackspace.loadbalancer.'
                        'create_loadbalancer',
                call_args=[context.get_queued_task_dict(
                                deployment=deployment['id'],
                                resource=key),
                        resource.get('dns-name'), 
                        'PUBLIC', 
                        proto.upper(),
                        resource['region']],
                defines=dict(resource=key,
                        provider=self.key,
                        task_tags=['create','root','final']),
                properties={'estimated_duration': 30})
        final = create_lb
        if dual:
            resource2 = deepcopy(resource)
            resource2['index'] = str(len([res for 
                                      res in deployment.get("resources").keys() 
                                      if res.isdigit()]))
            if 'relations' not in resource2:
                resource2['relations'] = {}
            resource2['relations'].update({
                "lb1-lb2":{
                    "interface": "vip",
                    "source": resource['index'],
                    "state": "planned",
                    "name": "lb1-lb2"
                }
            })
            if not "relations" in resource:
                resource['relations'] = {}
            resource['relations'].update({
                "lb2-lb1":{
                    "interface": "vip",
                    "target": resource2['index'],
                    "state": "planned",
                    "name": "lb1-lb2"
                }
            })
            deployment['resources'].update({resource2['index']: resource2})
            
            final = Celery(wfspec, 'Create HTTPS Loadbalancer (dual protocol)',
                'checkmate.providers.rackspace.loadbalancer.'
                        'create_loadbalancer',
                call_args=[context.get_queued_task_dict(
                                deployment=deployment['id'],
                                resource=resource2['index']),
                        "%s-2" % resource2.get('dns-name'), 
                        'PUBLIC', 
                        "HTTPS",
                        resource2['region']],
                defines=dict(resource=resource2['index'],
                        provider=self.key,
                        task_tags=['create', 'final']),
                properties={'estimated_duration': 30},
                parent_lb=PathAttrib("instance:%s/id" % key))
            final.follow(create_lb)

        return dict(root=create_lb, final=final)

    def add_connection_tasks(self, resource, key, relation, relation_key,
            wfspec, deployment, context):
        interface = relation['interface']
        if interface and "vip" != interface.lower():
            self._add_node_connection(resource, key, relation, relation_key, 
                                      wfspec, deployment, context, interface)
    
    def _add_node_connection(self,resource, key, relation, relation_key,
            wfspec, deployment, context, interface):

        comp = self.find_components(context, id="rsCloudLB")

        if not comp:
            raise CheckmateException("Could not locate component for id 'rsCloudLB'")
        else:
            comp = comp[0] # there should be only one
            print "comp: %s" % comp
            print "options: %s" % comp.get('options',{})
            print "protocol: %s" % comp.get('options',{}).get("protocol",{})
            print "choice: %s" % comp.get('options',{}).get("protocol",{}).get("choice",[])
            if not interface in comp.get('options',{}).get("protocol",{}).get("choice",[]):
                raise CheckmateException("Invalid relation interface for this provider: {}".format(interface))
                
        # Get all tasks we need to precede the LB Add Node task
        finals = self.find_tasks(wfspec, resource=relation['target'],
                tag='final')
        create_lb = self.find_tasks(wfspec, resource=key,
                provider=self.key, tag='final')[0]
        target_resource = deployment['resources'][relation['target']]
        if 'hosted_on' in target_resource:
            target = target_resource['hosted_on']
        else:
            target = relation['target']
        # determine the port based on protocol
        #Create the add node task
        add_node = Celery(wfspec,
                "Add Node %s to LB %s" % (relation['target'], key),
                'checkmate.providers.rackspace.loadbalancer.add_node',
                call_args=[context.get_queued_task_dict(
                            deployment=deployment['id'],
                            resource=key),
                        PathAttrib('instance:%s/id' % key),
                        PathAttrib('instance:%s/private_ip' % target),
                        resource['region']],
                defines=dict(relation=relation_key, provider=self.key,
                        task_tags=['final']),
                properties={'estimated_duration': 20})

        #Make it wait on all other provider completions
        finals.append(create_lb)
        wait_for(wfspec, add_node, finals,
                name="Wait before adding %s to LB %s" % (relation['target'], key),
                description="Wait for Load Balancer ID "
                        "and for server to be fully configured before "
                        "adding it to load balancer",
                defines=dict(relation=relation_key,
                            provider=self.key,
                            task_tags=['root']))

    def get_catalog(self, context, type_filter=None):
        """Return stored/override catalog if it exists, else connect, build,
        and return one"""

        # TODO: maybe implement this an on_get_catalog so we don't have to do
        #        this for every provider
        results = ProviderBase.get_catalog(self, context,
            type_filter=type_filter)
        if results:
            # We have a prexisting or overridecatalog stored
            return results

        # build a live catalog ()this would be the on_get_catalog called if no
        # stored/override existed
        api = self._connect(context)
        results = {}

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
            protocols = api.get_protocols()
            # add our custom protocol for handling both http and https on same vip
            if not "http_and_https" in protocols:
                protocols.extend(["http_and_https"])
            algorithms = api.get_algorithms()
            options = {'algorithm': {'type': 'list', 'choice': algorithms}}
            options.update({'protocol':{'type':'list', 'choice': [p.lower() for p in protocols]}})
            
            results['load-balancer'] = {
                "rsCloudLB": {
                    'id': 'rsCloudLB',
                    'is': 'load-balancer',
                    'provides': [{'load-balancer':'proxy'}],
                    'options': options
                }
            }
#            items = {}
#            for protocol in protocols:
#                item = {
#                        'id': protocol.lower(),
#                        'is': 'load-balancer',
#                        'provides': [{'load-balancer': protocol.lower()}],
#                        'options': options,
#                    }
#                items[protocol.lower()] = item
#            results['load-balancer'] = items

        self.validate_catalog(results)
        return results

    @staticmethod
    def _connect(context, region=None):
        """Use context info to connect to API and return api object"""
        #FIXME: figure out better serialization/deserialization scheme
        if isinstance(context, dict):
            from checkmate.middleware import RequestContext
            context = RequestContext(**context)
        if not context.auth_token:
            raise CheckmateNoTokenError()

        # Make sure we use airport codes (translate cities to that)
        if region in REGION_MAP:
            region = REGION_MAP[region]

        def find_url(catalog, region):
            for service in catalog:
                if service['type'] == 'rax:load-balancer':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if endpoint.get('region') == region:
                            return endpoint['publicURL']

        def find_a_region(catalog):
            """Any region"""
            for service in catalog:
                if service['type'] == 'rax:database':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        return endpoint['region']

        if not region:
            region = find_a_region(context.catalog) or 'DFW'

        #TODO: instead of hacking auth using a token, submit patch upstream
        url = find_url(context.catalog, region)
        if not url:
            raise CheckmateException("Unable to locate region url for LBaaS "
                    "for region '%s'" % region)
        api = cloudlb.CloudLoadBalancer(context.username, 'dummy', region)
        api.client.auth_token = context.auth_token
        api.client.region_account_url = url

        return api

"""
  Celery tasks to manipulate Rackspace Cloud Load Balancers
"""
import cloudlb
from celery.task import task #@UnresolvedImport

from checkmate.providers.rackspace.dns import create_record,\
        parse_domain

# Cloud Load Balancers needs an IP for all load balancers. To create one we
# sometimes need a dummy node. This is the IP address we use for the dummy
# node. Requests to manage this node are intentionally errored out.
PLACEHOLDER_IP = '1.2.3.4'

#
# Celery tasks
#
@task
def create_loadbalancer(context, name, vip_type, protocol, region,
                                   api=None, dns=False,
                                   monitor_path='/', port=None,
                                   monitor_delay=10, monitor_timeout=10,
                                   monitor_attempts=3, monitor_body='(.*)',
                                   monitor_status='^[234][0-9][0-9]$',
                                   parent_lb=None):
    match_celery_logging(LOG)
    if api is None:
        api = Provider._connect(context, region)
        
    #FIXME: should pull default from lb api but thats not exposed via the client yet
    if not port:
        port = 443 if "https" == protocol.lower() else 80
    
    fakenode = cloudlb.Node(address=PLACEHOLDER_IP, condition="ENABLED", port=port)
    
    # determine new or shared vip
    vip = None
    if not parent_lb:
        vip = cloudlb.VirtualIP(type=vip_type)
    else: # share vip with another lb in the deployment
        other_lb = api.loadbalancers.get(parent_lb)
        if not other_lb:
            return create_loadbalancer.retry(exc=CheckmateException(
                    "Could not locate load balancer %s for shared vip" % parent_lb))
        for _vip in other_lb.virtualIps: 
            if vip_type.upper() == _vip.type:
                vip = cloudlb.VirtualIP(id=_vip.id)
                break
        if not vip:
            create_loadbalancer.retry(exc=CheckmateException("Cannot get %s vip for load balancer %s") % (vip_type, parent_lb))
    
    meta = context.get("metadata",None)
    if meta: # attach checkmate metadata to the lb if available
        new_meta = []
        #Assumes that meta data is in format "meta" : {"key" : "value" , "key2" : "value2"}
        for key in meta:
            new_meta.append({"key" : key, "value" : meta[key]})
        lb = api.loadbalancers.create(name=name, port=port, protocol=protocol.upper(),
                                      nodes=[fakenode], virtualIps=[vip],
                                      metadata=new_meta)
    else:
        lb = api.loadbalancers.create(name=name, port=port, protocol=protocol.upper(),
                                      nodes=[fakenode], virtualIps=[vip])
        
    # update our assigned vip
    for ip in lb.virtualIps:
        if ip.ipVersion == 'IPV4':
            vip = ip.address

    LOG.debug('Load balancer %d created.  VIP = %s' % (lb.id, vip))
    
    #FIXME: This should be handled by the DNS provider, not this one!
    if dns:
        create_record.delay(context, parse_domain(name), name, #@UndefinedVariable
                                       'A', vip, region, ttl=300)
    
    # attach an appropriate monitor for our nodes
    monitor_type = protocol.upper()
    set_monitor.delay(context, lb.id, monitor_type, region, monitor_path,
                      monitor_delay, monitor_timeout, monitor_attempts,
                      monitor_body, monitor_status)

    results = {'instance:%s' % context['resource']: {'id': lb.id,
            'public_ip': vip, 'port': lb.port, 'protocol': lb.protocol}}

    # Send data back to deployment
    resource_postback.delay(context['deployment'], results) #@UndefinedVariable

    return results

@task
def delete_loadbalancer(context, lbid, region, api=None):
    match_celery_logging(LOG)
    if api is None:
        api = Provider._connect(context, region)

    lb = api.loadbalancers.get(lbid)
    lb.delete()
    LOG.debug('Load balancer %d deleted.' % lbid)


@task(default_retry_delay=10, max_retries=10)
def add_node(context, lbid, ip, region, api=None):
    match_celery_logging(LOG)
    if api is None:
        api = Provider._connect(context, region)

    if ip == PLACEHOLDER_IP:
        raise CheckmateException("IP %s is reserved as a placeholder IP"
                "by checkmate" % ip)

    lb = api.loadbalancers.get(lbid)
    if not (lb and lb.port):
        return add_node.retry(exc=CheckmateBadState(
                "Could not retrieve data for load balancer {}".format(lbid)))
    results = None
    port = lb.port

    # Check existing nodes and asses what we need to do
    new_node = None  # We store our new node here
    placeholder = None  # We store our placeholder node here
    for node in lb.nodes:
        if node.address == ip:
            if node.port == port and node.condition == "ENABLED":
                new_node = node
            else:
                # Node exists. Let's just update it
                if node.port != port:
                    node.port = port
                if node.condition != "ENABLED":
                    node.condition = "ENABLED"
                node.update()
                LOG.debug("Updated %s:%d from load balancer %d" % (
                        node.address, node.port, lbid))
                new_node - node
            # We return this at the end of the call
            results = {'id': node.id}
        elif node.address == PLACEHOLDER_IP:
            # This is the dummy, placeholder node
            placeholder = node

    # Create new node
    if not new_node:
        node = cloudlb.Node(address=ip, port=port, condition="ENABLED")
        try:
            results = lb.add_nodes([node])
            # I don't believe you! Check... this has been unreliable. Possible
            # because we need to refresh nodes
            lb_fresh = api.loadbalancers.get(lbid)
            if [n for n in lb_fresh.nodes if n.address == ip]:
                #OK!
                results = {'id': results[0].id}
            else:
                LOG.warning("CloudLB says node %s (ID=%s) was added to LB %s, "
                        "but upon validating, it does not look like that is "
                        "the case!" % (ip, results[0].id, lbid))
                # Try again!
                return add_node.retry(exc=CheckmateException(
                        "Validation failed - Node was not added"))
        except cloudlb.errors.ResponseError, exc:
            if exc.status == 422:
                LOG.debug("Cannot modify load balancer %d. Will retry "
                        "adding %s (%d %s)" % (lbid, ip, exc.status,
                        exc.reason))
                return add_node.retry(exc=exc)
            LOG.debug("Response error from load balancer %d. Will retry "
                    "adding %s (%d %s)" % (lbid, ip, exc.status, exc.reason))
            return add_node.retry(exc=exc)
        except Exception, exc:
            LOG.debug("Error adding %s behind load balancer %d. Error: "
                    "%s. Retrying" % (ip, lbid, str(exc)))
            return add_node.retry(exc=exc)

    # Delete placeholder
    if placeholder:
        try:
            placeholder.delete()
            LOG.debug('Removed %s:%d from load balancer %d' % (
                    placeholder.address, placeholder.port, lbid))
        except Exception, exc:
            return add_node.retry(exc=exc)

    return results


@task(default_retry_delay=10, max_retries=10)
def delete_node(context, lbid, ip, port, region, api=None):
    match_celery_logging(LOG)
    if api is None:
        api = Provider._connect(context, region)

    lb = api.loadbalancers.get(lbid)
    node_to_delete = None
    for node in lb.nodes:
        if node.address == ip and node.port == port:
            node_to_delete = node
    if node_to_delete is not None:
        try:
            node.delete()
            LOG.debug('Removed %s:%d from load balancer %d' % (
                ip, port, lbid))
        except cloudlb.errors.ResponseError, exc:
            if exc.status == 422:
                LOG.debug("Cannot modify load balancer %d. Will retry "
                        "deleting %s:%d (%d %s)" % (lbid, ip, port, exc.status,
                        exc.reason))
                delete_node.retry(exc=exc)
            LOG.debug('Response error from load balancer %d. Will retry ' \
                'deleting %s:%d (%d %s)' % (
                lbid, ip, port, exc.status, exc.reason))
            delete_node.retry(exc=exc)
        except Exception, exc:
            LOG.debug("Error deleting %s:%d from load balancer %d. Error: %s. "
                    "Retrying" % (ip, port, lbid, str(exc)))
            delete_node.retry(exc=exc)
    else:
        LOG.debug('No LB node matching %s:%d on LB %d' % (
            ip, port, lbid))


@task(default_retry_delay=10, max_retries=10)
def set_monitor(context, lbid, mon_type, region, path='/', delay=10,
                           timeout=10, attempts=3, body='(.*)',
                           status='^[234][0-9][0-9]$', api=None):
    match_celery_logging(LOG)
    if api is None:
        api = Provider._connect(context, region)

    lb = api.loadbalancers.get(lbid)

    try:
        hm_monitor = lb.healthmonitor()
        hm = cloudlb.healthmonitor.HealthMonitor(type=mon_type, delay=delay,
                 timeout=timeout,
                 attemptsBeforeDeactivation=attempts,
                 path=path,
                 statusRegex=status,
                 bodyRegex=body)
        hm_monitor.add(hm)
    except cloudlb.errors.ResponseError as re:
        if re.status == 422:
            LOG.debug("Cannot modify load balancer %d. Will retry setting %s "
                    "monitor (%d %s)" % (lbid, type, re.status, re.reason))
            set_monitor.retry(exc=re)
        LOG.debug("Response error from load balancer %d. Will retry setting "
                "%s monitor (%d %s)" % (lbid, type, re.status, re.reason))
        set_monitor.retry(exc=re)
    except Exception as exc:
        LOG.debug('Error setting %s monitor on load balancer %d. Error: %s. ' \
                'Retrying' % (type, lbid, str(exc)))
        set_monitor.retry(exc=exc)
