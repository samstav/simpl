# pylint: disable=E1102,W0613

# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
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

# pylint: disable=R0913,E1102
"""Rackspace Cloud Load Balancer provider and specs.Celery tasks."""
import logging
import os

from celery import task
import pyrax
import redis

from checkmate.common import statsd
from checkmate import deployments
from checkmate.deployments import tasks as deployment_tasks
from checkmate import exceptions
from checkmate.providers.rackspace.loadbalancer.manager import Manager
from checkmate.providers.rackspace.loadbalancer.provider import Provider
from checkmate import utils

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

MANAGERS = {'deployments': deployments.Manager()}
GET_RESOURCE_BY_ID = MANAGERS['deployments'].get_resource_by_id


# Cloud Load Balancers needs an IP for all load balancers. To create one we
# sometimes need a dummy node. This is the IP address we use for the dummy
# node. Requests to manage this node are intentionally errored out.
PLACEHOLDER_IP = '1.2.3.4'


#
# Celery tasks
#
@task
@statsd.collect
def create_loadbalancer(context, name, vip_type, protocol, region, api=None,
                        dns=False, port=None, algorithm='ROUND_ROBIN',
                        tags=None,
                        parent_lb=None):
    '''Celery task to create Cloud Load Balancer.'''
    assert 'deployment' in context, "Deployment not supplied in context"
    utils.match_celery_logging(LOG)

    deployment_id = context['deployment']
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
        deployments.resource_postback.delay(deployment_id, results)
        return results

    if api is None:
        api = Provider.connect(context, region)

    #FIXME: should pull default from lb api but thats not exposed via the
    #       client yet
    if not port:
        port = 443 if "https" == protocol.lower() else 80

    fakenode = api.Node(address=PLACEHOLDER_IP, condition="ENABLED",
                        port=port)

    # determine new or shared vip
    vip = None
    if not parent_lb:
        vip = api.VirtualIP(type=vip_type)
    else:
        # share vip with another lb in the deployment
        other_lb = api.get(parent_lb)
        if not other_lb:
            return create_loadbalancer.retry(
                exc=exceptions.CheckmateException(
                    "Could not locate load balancer %s for shared vip" %
                    parent_lb))
        for _vip in other_lb.virtual_ips:
            if vip_type.upper() == _vip.type:
                vip = api.VirtualIP(id=_vip.id)
                break
        if not vip:
            create_loadbalancer.retry(
                exc=exceptions.CheckmateException(
                    "Cannot get %s vip for load balancer %s") % (vip_type,
                                                                 parent_lb))
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
            loadbalancer = api.create(
                name=name, port=port, protocol=protocol.upper(),
                nodes=[fakenode], virtual_ips=[vip],
                algorithm=algorithm, metadata=new_meta)
        else:
            loadbalancer = api.create(
                name=name, port=port, protocol=protocol.upper(),
                nodes=[fakenode], virtual_ips=[vip], algorithm=algorithm)
        LOG.info("Created load balancer %s for deployment %s", loadbalancer.id,
                 deployment_id)
    except KeyError as exc:
        if str(exc) == 'retry-after':
            LOG.info("A limit 'may' have been reached creating a load "
                     "balancer for deployment %s", deployment_id)
            error_message = "API limit reached"
            raise exceptions.CheckmateException(error_message,
                                                friendly_message=error_message,
                                                options=exceptions.CAN_RETRY)
        raise
    except pyrax.exceptions.OverLimit as exc:
        LOG.info("API Limit reached creating a load balancer for deployment "
                 "%s", deployment_id)
        raise exceptions.CheckmateException(exc.message,
                                            friendly_message=exc.message,
                                            options=exceptions.CAN_RETRY)

    # Put the instance_id in the db as soon as it's available
    instance_id = {
        instance_key: {
            'id': loadbalancer.id
        }
    }
    deployments.resource_postback.delay(deployment_id, instance_id)

    # update our assigned vip
    for vips in loadbalancer.virtual_ips:
        if vips.ip_version == 'IPV4' and vips.type == "PUBLIC":
            address = vips.address

    LOG.debug('Load balancer %s building. VIP = %s', loadbalancer.id, vip)

    results = {
        instance_key: {
            'id': loadbalancer.id,
            'public_ip': address,
            'port': loadbalancer.port,
            'protocol': loadbalancer.protocol,
            'status': "BUILD",
            'interfaces': {
                'vip': {
                    'ip': address,
                    'public_ip': address,
                }
            }
        }
    }

    # Send data back to deployment
    deployments.resource_postback.delay(deployment_id, results)
    return results


@task
@statsd.collect
def collect_record_data(deployment_id, resource_key, record):
    """Validates DNS record passed in."""
    assert deployment_id, "No deployment id specified"
    assert resource_key, "No resource key specified"
    assert record, "No record specified"

    if "id" not in record:
        message = "Missing record id in %s" % record
        raise exceptions.CheckmateException(message)
    if "domain" not in record:
        message = "No domain specified for record %s" % record.get("id")
        raise exceptions.CheckmateException(message)
    contents = {
        "instance:%s" % resource_key: {
            "domain_id": record.get("domain"),
            "record_id": record.get("id")
        }
    }
    deployments.resource_postback.delay(deployment_id, contents)
    return contents


def _fix_corrupted_data(data):
    """Convert CloudLB's metadata back to a list.

    At one point sync was inadvertently overwriting CloudLB's metadata list
    with a dict. This will convert it back to a list, though with potential
    data loss, because we were throwing away the 'id' key in any of the
    metadata generated by CloudLB.

    This can be removed once the LOG entries stop.
    """
    LOG.warn("Fixing corrupted CloudLB metadata: %s", data)
    fixed_data = []
    for key in data:
        fixed_data.append({'key': key, 'value': data[key]})
    return fixed_data


def _update_metadata(context, resource, clb):
    """Updates metadata on cloud loadbalancer."""
    new_key, new_value = Provider.generate_resource_tag(
        context.get('base_url'), context.get('tenant'),
        context.get('deployment'), resource.get('index')).items()[0]

    new_meta = {'key': new_key, 'value': new_value}
    add_tag = True
    meta = clb.get_metadata()
    if isinstance(meta, dict):
        meta = _fix_corrupted_data(meta)

    for entry in meta:
        if entry['key'] == 'RAX-CHKMATE':
            clb.delete_metadata('RAX-CHKMATE')
        elif (entry['key'] == new_meta['key'] and
                entry['value'] == new_meta['value']):
            add_tag = False

    if add_tag:
        clb.update_metadata(new_meta)


@task
@statsd.collect
def sync_resource_task(context, resource, resource_key, api=None):
    """Sync provider resource status with deployment."""
    utils.match_celery_logging(LOG)
    key = "instance:%s" % resource_key
    if context.get('simulation') is True:
        return {
            key: {
                'status': resource.get('status', 'DELETED')
            }
        }

    if api is None:
        api = Provider.connect(context, resource.get("region"))

    instance_id = resource.get("instance", {}).get('id')

    try:
        if not instance_id:
            error_message = "No instance id supplied for resource %s" % key
            raise exceptions.CheckmateException(error_message)
        clb = api.get(instance_id)

        _update_metadata(context, resource, clb)

        status = {'status': clb.status}
    except pyrax.exceptions.ClientException as exc:
        if exc.code not in ['404', '422']:
            return
        status = {'status': 'DELETED'}
    except exceptions.CheckmateException:
        status = {'status': 'DELETED'}

    if status.get('status'):
        LOG.info("Marking load balancer instance %s as %s", instance_id,
                 status['status'])
    return {key: status}


@task
@statsd.collect
def delete_lb_task(context, key, lbid, region, api=None):
    """Celery task to delete a Cloud Load Balancer"""
    utils.match_celery_logging(LOG)

    if context.get('simulation') is True:
        resource_key = context['resource']
        results = {
            "instance:%s" % resource_key: {
                'status': 'DELETING',
                "status-message": "Waiting on resource deletion"
            }
        }
        deployments.resource_postback.delay(context['deployment'], results)
        return results

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Task failure."""
        dep_id = args[0].get('deployment')
        results = {
            "instance:%s" % args[1]: {
                'status': 'ERROR',
                'status-message': ('Unexpected error deleting loadbalancer'
                                   ' %s' % key),
                'error-message': str(exc)
            }
        }
        deployments.resource_postback.delay(dep_id, results)

    delete_lb_task.on_failure = on_failure
    instance_key = "instance:%s" % key

    if not lbid:
        msg = ("Instance ID is not available for Loadbalancer, skipping "
               "delete_lb_task for resource %s in deployment %s" %
               (context["resource"], context["deployment"]))
        LOG.info(msg)
        results = {
            instance_key: {
                'status': 'DELETED',
                'status-message': msg
            }
        }
        deployments.resource_postback.delay(context['deployment'], results)
        return
    if api is None:
        api = Provider.connect(context, region)

    dlb = None
    try:
        dlb = api.get(lbid)
    except pyrax.exceptions.NotFound:
        LOG.debug('Load balancer %s was already deleted.', lbid)
        results = {
            instance_key: {
                'status': 'DELETED',
                'status-message': ''
            }
        }

    if dlb:
        LOG.debug("Found load balancer %s [%s] to delete", dlb, dlb.status)
        if dlb.status in ("ACTIVE", "ERROR", "SUSPENDED"):
            LOG.debug('Deleting Load balancer %s.', lbid)
            dlb.delete()
            status_message = 'Waiting on resource deletion'
        else:
            status_message = ("Cannot delete LoadBalancer %s, as it currently "
                              "is in %s state. Waiting for load-balancer "
                              "status to move to ACTIVE, ERROR or SUSPENDED" %
                              (lbid, dlb.status))
            LOG.debug(status_message)
        results = {
            instance_key: {
                'status': 'DELETING',
                'status-message': status_message
            }
        }
    deployments.resource_postback.delay(context['deployment'], results)
    return results


@task(default_retry_delay=2, max_retries=60)
@statsd.collect
def wait_on_lb_delete_task(context, key, lb_id, region, api=None):
    """DELETED status check."""
    utils.match_celery_logging(LOG)
    inst_key = "instance:%s" % key
    results = {}

    if context.get('simulation') is True:
        results = {inst_key: {'status': 'DELETED'}}
        deployments.resource_postback.delay(context['deployment'], results)
        return results

    def on_failure(exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        dep_id = args[0].get('deployment')
        results = {
            "instance:%s" % args[1]: {
                'status': 'ERROR',
                'status-message': ('Unexpected error waiting on loadbalancer'
                                   ' %s delete' % key),
                'error-message': str(exc)
            }
        }
        deployments.resource_postback.delay(dep_id, results)

    wait_on_lb_delete_task.on_failure = on_failure

    if lb_id is None:
        msg = ("Instance ID is not available for Loadbalancer, skipping "
               "wait_on_delete_lb_task for resource %s in deployment %s" %
               (context["resource"], context["deployment"]))
        LOG.info(msg)
        results = {
            inst_key: {
                'status': 'DELETED',
                'status-message': msg
            }
        }
        deployments.resource_postback.delay(context['deployment'], results)
        return

    if api is None:
        api = Provider.connect(context, region)
    dlb = None
    LOG.debug("Checking on loadbalancer %s delete status", lb_id)
    try:
        dlb = api.get(lb_id)
    except pyrax.exceptions.NotFound:
        pass
    if (not dlb) or "DELETED" == dlb.status:
        results = {
            inst_key: {
                'status': 'DELETED',
                'status-message': ''
            }
        }
        deployments.resource_postback.delay(context["deployment"], results)
    else:
        msg = ("Waiting on state DELETED. Load balancer is in state %s"
               % dlb.status)
        wait_on_lb_delete_task.retry(exc=exceptions.CheckmateException(msg))
    return results


@task(default_retry_delay=10, max_retries=10)
@statsd.collect
def add_node(context, lbid, ipaddr, region, resource, api=None):
    """Celery task to add a node to a Cloud Load Balancer."""
    utils.match_celery_logging(LOG)
    instance_key = 'instance:%s' % context['resource']

    if context.get('simulation') is True:
        results = {}
        return results

    if api is None:
        api = Provider.connect(context, region)

    if ipaddr == PLACEHOLDER_IP:
        message = "IP %s is reserved as a placeholder IP by checkmate" % ipaddr
        raise exceptions.CheckmateException(message)

    loadbalancer = api.get(lbid)

    if loadbalancer.status != "ACTIVE":
        exc = exceptions.CheckmateException(
            "Loadbalancer %s cannot be modified while status is %s" %
            (lbid, loadbalancer.status))
        add_node.retry(exc=exc)
    if not (loadbalancer and loadbalancer.port):
        exc = exceptions.CheckmateBadState("Could not retrieve data for load"
                                           " balancer %s" % lbid)
        add_node.retry(exc=exc)
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
                LOG.info("Updated %s:%d from load balancer %d", node.address,
                         node.port, lbid)
                # We return this at the end of the call
            results = {
                instance_key: {
                    'nodes': [node.id]
                }
            }
        elif node.address == PLACEHOLDER_IP:
            # This is the dummy, placeholder node
            placeholder = node

    # Create new node
    if not new_node:
        node = api.Node(address=ipaddr, port=port, condition="ENABLED")
        try:
            _, body = loadbalancer.add_nodes([node])
            node_id = body.get('nodes')[0].get('id')

            # I don't believe you! Check... this has been unreliable. Possible
            # because we need to refresh nodes
            lb_fresh = api.get(lbid)
            if [n for n in lb_fresh.nodes if n.address == ipaddr]:
                #OK!
                LOG.info("Added node %s:%s to load balancer %s", ipaddr, port,
                         lbid)
                results = {
                    instance_key: {
                        'nodes': [node_id]
                    }
                }
                deployments.resource_postback.delay(context['deployment'],
                                                    results)
            else:
                LOG.warning("CloudLB says node %s (ID=%s) was added to LB %s, "
                            "but upon validating, it does not look like that "
                            "is the case!", ipaddr, node_id, lbid)
                # Try again!
                exc = exceptions.CheckmateException("Validation failed - "
                                                    "Node was not added")
                add_node.retry(exc=exc)
        except pyrax.exceptions.ClientException as exc:
            if exc.code == '422':
                LOG.debug("Cannot modify load balancer %d. Will retry "
                          "adding %s (%d %s)", lbid, ipaddr, exc.code,
                          exc.message)
                add_node.retry(exc=exc)
            LOG.debug("Response error from load balancer %d. Will retry "
                      "adding %s (%d %s)", lbid, ipaddr, exc.code,
                      exc.message)
            add_node.retry(exc=exc)
        except StandardError as exc:
            LOG.debug("Error adding %s behind load balancer %d. Error: "
                      "%s. Retrying", ipaddr, lbid, str(exc))
            add_node.retry(exc=exc)

    # Delete placeholder
    if placeholder:
        try:
            placeholder.delete()
            LOG.debug('Removed %s:%s from load balancer %s',
                      placeholder.address, placeholder.port, lbid)
        # The lb client exceptions extend Exception and are missed
        # by the generic handler
        except (pyrax.exceptions.ClientException, StandardError) as exc:
            add_node.retry(exc=exc)

    return results


@task(default_retry_delay=10, max_retries=10)
@statsd.collect
def update_node_status(context, lb_id, ip_address, region, node_status,
                       resource_status, api=None):
    """Celery task to disable a load balancer node
    :param context: request context
    :param lb_id: load balancer id
    :param ip_address: ip address of the node
    :param region: region of the load balancer
    :param node_status: status to be updated on the node
    :param resource_status: status to be updated on the resource
    :param api: api to call
    :return:
    """
    utils.match_celery_logging(LOG)
    source_key = context['source_resource']
    target_key = context['target_resource']
    relation_name = context['relation_name']
    results = {
        'resources': {
            source_key: {
                "relations": {
                    "%s-%s" % (relation_name, target_key): {
                        'state': node_status
                    }
                }
            },
            target_key: {
                "status": resource_status,
                "relations": {
                    "%s-%s" % (relation_name, source_key): {
                        'state': node_status
                    }
                }
            }
        }
    }

    if context.get('simulation') is True:
        deployment_tasks.postback(context['deployment'], results)
        return results

    if api is None:
        api = Provider.connect(context, region)

    loadbalancer = api.get(lb_id)
    node_to_update = None
    for node in loadbalancer.nodes:
        if node.address == ip_address:
            node_to_update = node
    if node_to_update:
        try:
            node_to_update.condition = node_status
            node_to_update.update()
            LOG.info('Update %s to %s for load balancer %s', ip_address,
                     node_status, lb_id)
        except pyrax.exceptions.ClientException as exc:
            if exc.code == '422':
                LOG.debug("Cannot modify load balancer %d. Will retry "
                          "deleting %s (%s %s)", lb_id, ip_address, exc.code,
                          exc.message)
                update_node_status.retry(exc=exc)
            LOG.debug('Response error from load balancer %d. Will retry '
                      'updating node %s (%s %s)', lb_id, ip_address,
                      exc.code,
                      exc.message)
            update_node_status.retry(exc=exc)
        except StandardError as exc:
            LOG.debug("Error updating node %s for load balancer %s. Error: %s"
                      ". Retrying", ip_address, lb_id, str(exc))
            update_node_status.retry(exc=exc)
        deployment_tasks.postback(context['deployment'], results)
        return results
    else:
        LOG.debug('No node matching %s on LB %s', ip_address, lb_id)


@task(default_retry_delay=10, max_retries=10)
@statsd.collect
def delete_node(context, lbid, ipaddr, region, api=None):
    """Celery task to delete a node from a Cloud Load Balancer."""
    utils.match_celery_logging(LOG)

    if context.get('simulation') is True:
        return

    if api is None:
        api = Provider.connect(context, region)

    loadbalancer = api.get(lbid)
    node_to_delete = None
    for node in loadbalancer.nodes:
        if node.address == ipaddr:
            node_to_delete = node
    if node_to_delete:
        try:
            node_to_delete.delete()
            LOG.info('Removed %s from load balancer %s', ipaddr, lbid)
        except pyrax.exceptions.ClientException as exc:
            if exc.code == '422':
                LOG.debug("Cannot modify load balancer %d. Will retry "
                          "deleting %s (%s %s)", lbid, ipaddr, exc.code,
                          exc.message)
                delete_node.retry(exc=exc)
            LOG.debug('Response error from load balancer %d. Will retry '
                      'deleting %s (%s %s)', lbid, ipaddr, exc.code,
                      exc.message)
            delete_node.retry(exc=exc)
        except StandardError as exc:
            LOG.debug("Error deleting %s from load balancer %s. Error: %s. "
                      "Retrying", ipaddr, lbid, str(exc))
            delete_node.retry(exc=exc)
    else:
        LOG.debug('No LB node matching %s on LB %s', ipaddr, lbid)


@task(default_retry_delay=10, max_retries=10)
@statsd.collect
def set_monitor(context, lbid, mon_type, region, path='/', delay=10,
                timeout=10, attempts=3, body='(.*)',
                status='^[234][0-9][0-9]$', api=None):
    '''Create a monitor for a Cloud Load Balancer'''
    utils.match_celery_logging(LOG)

    if context.get('simulation') is True:
        return

    if api is None:
        api = Provider.connect(context, region)

    LOG.debug("Setting monitor on lbid: %s", lbid)
    loadbalancer = api.get(lbid)

    try:
        loadbalancer.add_health_monitor(
            type=mon_type, delay=delay,
            timeout=timeout,
            attemptsBeforeDeactivation=attempts,
            path=path,
            statusRegex=status,
            bodyRegex=body)
    except pyrax.exceptions.ClientException as response_error:
        if response_error.code == '422':
            LOG.debug("Cannot modify load balancer %s. Will retry setting %s "
                      "monitor (%s %s)", lbid, type,
                      response_error.code, response_error.message)
        else:
            LOG.debug("Response error from load balancer %s. Will retry "
                      "setting %s monitor (%s %s)", lbid, type,
                      response_error.code, response_error.message)
        set_monitor.retry(exc=response_error)
    #except cloudlb.errors.ImmutableEntity as im_ent: #TODO(Nate): unique?
    except pyrax.exceptions.PyraxException as exc:
        LOG.debug("Cannot modify loadbalancer %s yet.", lbid, exc_info=True)
        set_monitor.retry(exc=exc)
    except StandardError as exc:
        LOG.debug("Error setting %s monitor on load balancer %s. Error: %s. "
                  "Retrying", type, lbid, str(exc))
        set_monitor.retry(exc=exc)


@task(default_retry_delay=30, max_retries=120, acks_late=True)
@statsd.collect
def wait_on_build(context, lbid, region, api=None):
    """Checks to see if a lb's status is ACTIVE, so we can change resource
    status in deployment
    """

    utils.match_celery_logging(LOG)
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
        deployments.resource_postback.delay(context['deployment'], results)
        return results

    if api is None:
        api = Provider.connect(context, region)

    loadbalancer = api.get(lbid)

    instance_key = 'instance:%s' % context['resource']
    if loadbalancer.status == "ERROR":
        msg = ("Loadbalancer %s build failed" % (lbid))
        results = {
            instance_key: {
                'status': 'ERROR',
                'status-message': msg
            }
        }
        deployments.resource_postback.delay(context['deployment'], results)
        raise exceptions.CheckmateException(msg, friendly_message=msg,
                                            options=exceptions.CAN_RESET)
    elif loadbalancer.status == "ACTIVE":
        results = {
            instance_key: {
                'id': lbid,
                'status': 'ACTIVE',
                'status-message': ''
            }
        }
        deployments.resource_postback.delay(context['deployment'], results)
        return results
    else:
        msg = ("Loadbalancer status is %s, retrying" % loadbalancer.status)
        return wait_on_build.retry(exc=exceptions.CheckmateException(msg))


class CheckmateLoadbalancerBuildFailed(exceptions.CheckmateException):
    """Error building loadbalancer"""
    pass
