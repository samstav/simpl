# pylint: disable=E1103,R0913,R0912
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

"""
Rackspace Loadbalancer provider manager.
"""
import logging
import pyrax

from checkmate import exceptions
from checkmate import utils

LOG = logging.getLogger(__name__)

#This is the IP address we use for the dummy node.
PLACEHOLDER_IP = '1.2.3.4'


class Manager(object):
    """Contains loadbalancer provider model and logic for interaction."""

    @staticmethod
    def enable_content_caching(lbid, api, simulate=False):
        """Enables content caching on specified loadbalancer."""
        if simulate:
            clb = utils.Simulation(status='ACTIVE')
            clb.content_caching = True
        else:
            try:
                clb = api.get(lbid)
                clb.content_caching = True
            except pyrax.exceptions.ClientException as exc:
                raise exceptions.CheckmateException('ClientException occurred '
                                                    'enabling content caching '
                                                    'on lb %s: %s' % (lbid,
                                                                      exc))
        results = {
            'id': lbid,
            'status': clb.status,
            'caching': clb.content_caching
        }
        return results

    @staticmethod
    def create_loadbalancer(context, name, vip_type, protocol, api, callback,
                            port=None, algorithm='ROUND_ROBIN', tags=None,
                            parent_lb=None, simulate=False):
        """Celery task to create Cloud Load Balancer."""
        if not port:
            port = 443 if "https" == protocol.lower() else 80

        if simulate:
            vip = "4.4.4.20"
            loadbalancer = utils.Simulation(status="BUILD", id="LB1",
                                            public_ip=vip, port=port,
                                            protocol=protocol,
                                            virtual_ips=[utils.Simulation(
                                                ip_version="IPV4",
                                                type="PUBLIC",
                                                address=vip)])
        else:
            fake_node = api.Node(address=PLACEHOLDER_IP, condition="ENABLED",
                                 port=port)

            # determine new or shared vip
            vip = None
            if not parent_lb:
                vip = api.VirtualIP(type=vip_type)
            else:
                # share vip with another lb in the deployment
                other_lb = api.get(parent_lb)
                if not other_lb:
                    raise exceptions.CheckmateException(
                        "Could not locate load balancer %s for shared vip" %
                        parent_lb, options=exceptions.CAN_RESUME)
                for _vip in other_lb.virtual_ips:
                    if vip_type.upper() == _vip.type:
                        vip = api.VirtualIP(id=_vip.id)
                        break
                if not vip:
                    raise exceptions.CheckmateException(
                        "Cannot get %s vip for load balancer %s" % (
                            vip_type, parent_lb),
                        options=exceptions.CAN_RESUME)
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
                        nodes=[fake_node], virtual_ips=[vip],
                        algorithm=algorithm, metadata=new_meta)
                else:
                    loadbalancer = api.create(
                        name=name, port=port, protocol=protocol.upper(),
                        nodes=[fake_node], virtual_ips=[vip],
                        algorithm=algorithm)
                LOG.info("Created load balancer %s ", loadbalancer.id)
            except pyrax.exceptions.OverLimit as exc:
                LOG.info("API Limit reached creating a load balancer")
                raise exceptions.CheckmateException(
                    exc.message, friendly_message=exc.message,
                    options=exceptions.CAN_RETRY)

        # Put the instance_id in the db as soon as it's available
        callback({'id': loadbalancer.id})

        # update our assigned vip
        for vips in loadbalancer.virtual_ips:
            if vips.ip_version == 'IPV4' and vips.type == "PUBLIC":
                address = vips.address

        LOG.debug('Load balancer %s building. VIP = %s', loadbalancer.id, vip)

        results = {
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
        return results

    @staticmethod
    def wait_on_build(lb_id, api, callback, simulate=False):
        """Checks to see if a lb's status is ACTIVE, so we can change resource
        status in deployment
        """
        assert lb_id, "ID must be provided"
        LOG.debug("Getting loadbalancer %s", lb_id)

        if simulate:
            loadbalancer = utils.Simulation(id=lb_id, status="ACTIVE")
        else:
            loadbalancer = api.get(lb_id)

        if loadbalancer.status == "ERROR":
            msg = "Loadbalancer %s build failed" % lb_id
            callback({'status': 'ERROR', 'status-message': msg})
            raise exceptions.CheckmateException(msg, friendly_message=msg,
                                                options=exceptions.CAN_RESET)
        elif loadbalancer.status == "ACTIVE":
            results = {
                'id': lb_id,
                'status': 'ACTIVE',
                'status-message': ''
            }
            return results
        else:
            msg = ("Loadbalancer status is %s, retrying" % loadbalancer.status)
            raise exceptions.CheckmateException(msg,
                                                options=exceptions.CAN_RESUME)

    @staticmethod
    def set_monitor(lb_id, mon_type, api, path='/', delay=10,
                    timeout=10, attempts=3, body='(.*)',
                    status='^[234][0-9][0-9]$', simulate=False):
        """Create a monitor for a Cloud Load Balancer."""
        LOG.debug("Setting monitor on lbid: %s", lb_id)

        if simulate:
            return

        loadbalancer = api.get(lb_id)

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
                msg = ("Cannot modify load balancer %s. Will retry setting "
                       "%s monitor (%s %s)" %
                       (lb_id, mon_type, response_error.code,
                        response_error.message))
                LOG.debug(msg)
            else:
                msg = ("Response error from load balancer %s. Will retry "
                       "setting %s monitor (%s %s)" %
                       (lb_id, mon_type, response_error.code,
                        response_error.message))
                LOG.debug(msg)
            raise exceptions.CheckmateException(
                msg, options=exceptions.CAN_RESUME)
        except pyrax.exceptions.PyraxException as exc:
            LOG.debug("Cannot modify loadbalancer %s yet.", lb_id,
                      exc_info=True)
            raise exceptions.CheckmateException(
                str(exc), options=exceptions.CAN_RESUME)
        except StandardError as exc:
            msg = ("Error setting %s monitor on load balancer %s. Error: %s. "
                   "Retrying" % (mon_type, lb_id, str(exc)))
            LOG.debug(msg)
            raise exceptions.CheckmateException(
                msg, options=exceptions.CAN_RESUME)

    @staticmethod
    def delete_node(lb_id, ip_addr, api, simulate=False):
        """Celery task to delete a node from a Cloud Load Balancer."""
        if simulate:
            return

        loadbalancer = api.get(lb_id)
        node_to_delete = None

        for node in loadbalancer.nodes:
            if node.address == ip_addr:
                node_to_delete = node
        if node_to_delete:
            try:
                node_to_delete.delete()
                LOG.info('Removed %s from load balancer %s', ip_addr, lb_id)
            except pyrax.exceptions.ClientException as exc:
                msg = ("Response error from load balancer %s. Will retry "
                       "deleting %s (%s %s)" % (lb_id, ip_addr, exc.code,
                                                exc.message))
                LOG.debug(msg)
                raise exceptions.CheckmateException(
                    msg, options=exceptions.CAN_RESUME)
            except StandardError as exc:
                msg = ("Error deleting %s from load balancer %s. Error: %s. "
                       "Retrying" % (ip_addr, lb_id, str(exc)))
                LOG.debug(msg)
                raise exceptions.CheckmateException(
                    msg, options=exceptions.CAN_RESUME)
        else:
            LOG.debug('No LB node matching %s on LB %s', ip_addr, lb_id)

    @staticmethod
    def add_node(lb_id, ip_addr, api, simulate=False):
        """Celery task to add a node to a Cloud Load Balancer."""
        if simulate:
            return

        if ip_addr == PLACEHOLDER_IP:
            message = ("IP %s is reserved as a placeholder IP by checkmate"
                       % ip_addr)
            raise exceptions.CheckmateException(message)

        loadbalancer = api.get(lb_id)

        if loadbalancer.status != "ACTIVE":
            raise exceptions.CheckmateException(
                "Loadbalancer %s cannot be modified while status is %s" %
                (lb_id, loadbalancer.status), exceptions.CAN_RESUME)
        if not (loadbalancer and loadbalancer.port):
            raise exceptions.CheckmateBadState("Could not retrieve data for "
                                               "load balancer %s" % lb_id,
                                               exceptions.CAN_RESUME)
        results = None
        port = loadbalancer.port

        # Check existing nodes and asses what we need to do
        new_node = None  # We store our new node here
        placeholder = None  # We store our placeholder node here
        for node in loadbalancer.nodes:
            if node.address == ip_addr:
                if node.port == port and node.condition == "ENABLED":
                    new_node = node
                else:
                    # Node exists. Let's just update it
                    node.port = port
                    node.condition = "ENABLED"
                    node.update()
                    new_node = node
                    LOG.info("Updated %s:%s from load balancer %s",
                             node.address, node.port, lb_id)
                    # We return this at the end of the call
                results = {'nodes': [node.id]}
            elif node.address == PLACEHOLDER_IP:
                # This is the dummy, placeholder node
                placeholder = node

        # Create new node
        if not new_node:
            node = api.Node(address=ip_addr, port=port, condition="ENABLED")
            try:
                _, body = loadbalancer.add_nodes([node])
                node_id = body.get('nodes')[0].get('id')
                # I don't believe you! Check... this has been unreliable.
                # Possible because we need to refresh nodes
                lb_fresh = api.get(lb_id)
                if [n for n in lb_fresh.nodes if n.address == ip_addr]:
                    #OK!
                    LOG.info("Added node %s:%s to load balancer %s", ip_addr,
                             port, lb_id)
                    results = {
                        'nodes': [node_id]
                    }
                else:
                    LOG.warning("CloudLB says node %s (ID=%s) was added to LB "
                                "%s, but upon validating, it does not look "
                                "like that is the case!", ip_addr,
                                node_id, lb_id)
                    # Try again!
                    raise exceptions.CheckmateException("Validation failed - "
                                                        "Node was not added")
            except pyrax.exceptions.ClientException as exc:
                msg = ("Response error from load balancer %s. Will retry "
                       "adding %s (%s %s)" % (lb_id, ip_addr, exc.code,
                                              exc.message))
                LOG.debug(msg)
                raise exceptions.CheckmateException(msg,
                                                    exceptions.CAN_RESUME)
            except StandardError as exc:
                msg = ("Error adding %s behind load balancer %s. Error: %s. "
                       "Retrying" % (ip_addr, lb_id, str(exc)))
                LOG.debug(msg)
                raise exceptions.CheckmateException(msg,
                                                    exceptions.CAN_RESUME)

        # Delete placeholder
        if placeholder:
            try:
                placeholder.delete()
                LOG.debug('Removed %s:%s from load balancer %s',
                          placeholder.address, placeholder.port, lb_id)
            # The lb client exceptions extend Exception and are missed
            # by the generic handler
            except (pyrax.exceptions.ClientException, StandardError) as exc:
                raise exceptions.CheckmateException(
                    str(exc), options=exceptions.CAN_RESUME)
        return results

    @staticmethod
    def wait_on_lb_delete_task(lb_id, api, simulate=False):
        """DELETED status check."""
        dlb = None

        if simulate:
            dlb = utils.Simulation(id=lb_id, status="DELETED")
        else:
            LOG.debug("Checking on loadbalancer %s delete status", lb_id)
            try:
                dlb = api.get(lb_id)
            except pyrax.exceptions.NotFound:
                pass

        if dlb and dlb.status != "DELETED":
            msg = ("Waiting on state DELETED. Load balancer is in state %s"
                   % dlb.status)
            raise exceptions.CheckmateException(msg,
                                                options=exceptions.CAN_RESUME)
        results = {
            'status': 'DELETED',
            'status-message': ''
        }

        return results

    @staticmethod
    def delete_lb_task(lb_id, api, simulate=False):
        """Celery task to delete a Cloud Load Balancer"""
        if simulate:
            results = {
                'status': 'DELETING',
                "status-message": "Waiting on resource deletion"
            }
            return results

        dlb = None
        try:
            dlb = api.get(lb_id)
        except pyrax.exceptions.NotFound:
            LOG.debug('Load balancer %s was already deleted.', lb_id)
            results = {
                'status': 'DELETED',
                'status-message': ''
            }

        if dlb:
            LOG.debug("Found load balancer %s [%s] to delete", dlb, dlb.status)
            if dlb.status in ("ACTIVE", "ERROR", "SUSPENDED"):
                LOG.debug('Deleting Load balancer %s.', lb_id)
                dlb.delete()
                status_message = 'Waiting on resource deletion'
            else:
                status_message = ("Cannot delete LoadBalancer %s, as it "
                                  "currently is in %s state. Waiting for "
                                  "load-balancer status to move to ACTIVE, "
                                  "ERROR or SUSPENDED" % (lb_id, dlb.status))
                LOG.debug(status_message)
                raise exceptions.CheckmateException(
                    status_message, options=exceptions.CAN_RESUME)
            results = {
                'status': 'DELETING',
                'status-message': status_message
            }
        return results

    @staticmethod
    def collect_record_data(record):
        """Validates DNS record passed in."""
        assert record, "No record specified"

        if "id" not in record:
            message = "Missing record id in %s" % record
            raise exceptions.CheckmateException(message)
        if "domain" not in record:
            message = "No domain specified for record %s" % record.get("id")
            raise exceptions.CheckmateException(message)
        contents = {
            "domain_id": record.get("domain"),
            "record_id": record.get("id")
        }
        return contents

    @staticmethod
    def update_node_status(context, lb_id, ip_address, node_status,
                           resource_status, relation, callback, api,
                           simulate=False):
        """Updates status of a loadbalancer node
        :param context: request context
        :param lb_id: load balancer id
        :param ip_address: ip address of the node
        :param node_status: status to be updated on the node
        :param resource_status: status to be updated on the resource
        :param api: api to call
        :param simulate: whether to simulate the call or not
        :return:
        """
        source_key = context['resource_key']
        relation_name = relation['name']
        source_results = {
            "relations": {
                "%s-%s" % (relation_name, relation['target']): {
                    'state': node_status
                }
            }
        }
        target_results = {
            "status": resource_status,
            "relations": {
                "%s-%s" % (relation_name, source_key): {
                    'state': node_status
                }
            }
        }

        if simulate:
            callback(target_results, resource_key=relation['target'])
            return source_results

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
                msg = ("Response error from load balancer %s. Will retry "
                       "updating node %s (%s %s)" % (lb_id, ip_address,
                                                     exc.code,
                                                     exc.message))
                LOG.debug(msg)
                raise exceptions.CheckmateException(
                    msg, options=exceptions.CAN_RESUME)
            except StandardError as exc:
                msg = ("Error updating node %s for load balancer %s. Error: "
                       "%s. Retrying" % (ip_address, lb_id, str(exc)))
                LOG.debug(msg)
                raise exceptions.CheckmateException(
                    msg, options=exceptions.CAN_RESUME)
            callback(target_results, resource_key=relation['target'])
            return source_results
        else:
            LOG.debug('No node matching %s on LB %s', ip_address, lb_id)
