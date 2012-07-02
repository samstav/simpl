import logging

from SpiffWorkflow.operators import Attrib
from SpiffWorkflow.specs import Celery, Transform

from checkmate.exceptions import CheckmateException
from checkmate.providers import ProviderBase
from checkmate.workflows import wait_for

LOG = logging.getLogger(__name__)


class Provider(ProviderBase):
    name = 'load-balancer'
    vendor = 'rackspace'

    def add_resource_tasks(self, resource, key, wfspec, deployment, context,
                wait_on=None):
        create_lb = Celery(wfspec, 'Create LB',
                'checkmate.providers.rackspace.loadbalancer.'
                        'create_loadbalancer',
                call_args=[Attrib('context'),
                resource.get('dns-name'), 'PUBLIC', 'HTTP', 80],
                dns=True,  # TODO: shouldn't this be parameterized?
                defines=dict(resource=key,
                    provider=self.key,
                    task_tags=['create', 'root']),
                properties={'estimated_duration': 30})

        save_lbid = Transform(wfspec, "Get LB ID",
                transforms=[
                    "my_task.attributes['lbid']=my_task.attributes['id']"],
                defines=dict(resource=key, provider=self.key,
                        task_tags=['final']),
                description="Copies LB ID to lbid field so it doesn't"
                        "conflict with other id fields")
        create_lb.connect(save_lbid)

        return dict(root=create_lb, final=save_lbid)

    def add_connection_tasks(self, resource, key, relation, relation_key,
            wfspec, deployment):
        interface = relation['interface']

        if interface == 'http':
            # Get all tasks we need to precede the LB Add Node task
            finals = self.find_tasks(wfspec, resource=relation['target'],
                    tag='final')
            create_lb = self.find_tasks(wfspec, resource=key,
                    provider=self.key, tag='final')[0]

            #Create the add node task
            add_node = Celery(wfspec,
                    "Add LB Node:%s" % relation['target'],
                    'checkmate.providers.rackspace.loadbalancer.add_node',
                    call_args=[Attrib('context'),  Attrib('lbid'),
                            Attrib('private_ip'), 80],
                    defines=dict(relation=relation_key, provider=self.key,
                            task_tags=['final']),
                    properties={'estimated_duration': 20})

            #Make it wait on all other provider completions
            finals.append(create_lb)
            wait_for(wfspec, add_node, finals,
                    name="Wait before adding to LB:%s" % relation['target'],
                    description="Wait for Load Balancer ID "
                            "and for server to be fully configured before "
                            "adding it to load balancer",
                    defines=dict(relation=relation_key,
                                provider=self.key,
                                task_tags=['root']))

    def get_catalog(self, context, type_filter=None):
        #TODO: add more than just regions
        results = {}

        if type_filter is None or type_filter == 'regions':
            regions = {}
            for service in context.catalog:
                if service['type'] == 'rax:load-balancer':
                    endpoints = service['endpoints']
                    for endpoint in endpoints:
                        if 'region' in endpoint:
                            regions[endpoint['region']] = endpoint['publicURL']
            results['regions'] = regions

        return results


"""
  Celery tasks to manipulate Rackspace Cloud Load Balancers
"""
import cloudlb
import logging
from celery.task import task

from checkmate.providers.rackspace.dns import create_record,\
        parse_domain


LOG = logging.getLogger(__name__)

# Cloud Load Balancers needs an IP for all load balancers. To create one we
# sometimes need a dummy node. This is the IP address we use for the dummy
# node. Requests to manage this node are intentionally errored out.
PLACEHOLDER_IP = '1.2.3.4'


def _get_lb_object(deployment):
    """Connect to API and return connection object
    :param deployment: a deployment dict with connection information"""
    api = cloudlb.CloudLoadBalancer(deployment['username'],
      deployment['apikey'], deployment['region'])
    return api

""" Celery tasks """


@task
def create_loadbalancer(deployment, name, type, protocol, port,
                                   api=None, dns=False, monitor_type="HTTP",
                                   monitor_path='/',
                                   monitor_delay=10, monitor_timeout=10,
                                   monitor_attempts=3, monitor_body='(.*)',
                                   monitor_status='^[234][0-9][0-9]$'):
    if api is None:
        api = _get_lb_object(deployment)

    fakenode = cloudlb.Node(address=PLACEHOLDER_IP, port=80,
            condition="ENABLED")
    vip = cloudlb.VirtualIP(type=type)
    lb = api.loadbalancers.create(name=name, port=port, protocol=protocol,
                                  nodes=[fakenode], virtualIps=[vip])
    for ip in lb.virtualIps:
        if ip.ipVersion == 'IPV4':
            vip = ip.address

    LOG.debug('Load balancer %d created.  VIP = %s' % (lb.id, vip))

    if dns:
        create_record.delay(deployment, parse_domain(name), name,
                                       'A', vip, ttl=300)

    set_monitor.delay(deployment, lb.id, monitor_type, monitor_path,
                      monitor_delay, monitor_timeout, monitor_attempts,
                      monitor_body, monitor_status)

    return {'id': lb.id, 'vip': vip}


@task
def delete_loadbalancer(deployment, lbid, api=None):
    if api is None:
        api = _get_lb_object(deployment)

    lb = api.loadbalancers.get(lbid)
    lb.delete()
    LOG.debug('Load balancer %d deleted.' % lbid)


@task(default_retry_delay=10, max_retries=10)
def add_node(deployment, lbid, ip, port, api=None):
    if api is None:
        api = _get_lb_object(deployment)

    if ip == PLACEHOLDER_IP:
        raise CheckmateException("IP %s is reserved as a placeholder IP"
                "by checkmate" % ip)

    lb = api.loadbalancers.get(lbid)
    results = None

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
def delete_node(deployment, lbid, ip, port, api=None):
    if api is None:
        api = _get_lb_object(deployment)

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
def set_monitor(deployment, lbid, type, path='/', delay=10,
                           timeout=10, attempts=3, body='(.*)',
                           status='^[234][0-9][0-9]$', api=None):
    if api is None:
        api = _get_lb_object(deployment)

    lb = api.loadbalancers.get(lbid)

    try:
        hm_monitor = lb.healthmonitor()
        hm = cloudlb.healthmonitor.HealthMonitor(type=type, delay=delay,
                 timeout=timeout,
                 attemptsBeforeDeactivation=attempts,
                 path=path,
                 statusRegex=status,
                 bodyRegex=body)
        hm_monitor.add(hm)
    except cloudlb.errors.ResponseError, exc:
        if exc.status == 422:
            LOG.debug("Cannot modify load balancer %d. Will retry setting %s "
                    "monitor (%d %s)" % (lbid, type, exc.status, exc.reason))
            set_monitor.retry(exc=exc)
        LOG.debug("Response error from load balancer %d. Will retry setting "
                "%s monitor (%d %s)" % (lbid, type, exc.status, exc.reason))
        set_monitor.retry(exc=exc)
    except Exception, exc:
        LOG.debug('Error setting %s monitor on load balancer %d. Error: %s. ' \
                'Retrying' % (type, lbid, str(exc)))
        set_monitor.retry(exc=exc)
