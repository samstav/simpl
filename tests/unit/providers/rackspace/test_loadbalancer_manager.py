# pylint: disable=R0904,C0103,W0212,E1103
# Copyright (c) 2011-2015 Rackspace US, Inc.
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
Module for testing loadbalancer manager
"""
import mock
import unittest

import pyrax
from pyrax import cloudloadbalancers as clb

from checkmate import exceptions
from checkmate.providers.rackspace.loadbalancer import manager
from checkmate import utils


class TestEnableContentCaching(unittest.TestCase):
    """Class for testing enable_content_caching task."""

    def setUp(self):
        """Setup vars for re-use."""
        self.lbid = '12345'
        self.api = mock.MagicMock()

    def test_sim_success(self):
        """Verifies results on simulation."""
        expected = {
            'id': '12345',
            'status': 'ACTIVE',
            'caching': True
        }
        results = manager.Manager.enable_content_caching(self.lbid, 'api',
                                                         simulate=True)
        self.assertEqual(expected, results)

    def test_success(self):
        """Verifies method calls and results."""
        lb = mock.Mock()
        lb.status = 'ACTIVE'
        self.api.get.return_value = lb
        expected = {
            'id': '12345',
            'status': 'ACTIVE',
            'caching': True
        }
        results = manager.Manager.enable_content_caching(self.lbid, self.api)
        self.assertEqual(results, expected)
        self.api.get.assert_called_with(self.lbid)

    def test_api_get_exception(self):
        """Verifies CheckmateException raised when caught ClientException."""
        self.api.get.side_effect = pyrax.exceptions.ClientException('testing')
        expected = 'ClientException occurred enabling content caching on lb '
        self.assertRaisesRegexp(exceptions.CheckmateException, expected,
                                manager.Manager.enable_content_caching,
                                self.lbid, self.api)


class TestCreateLoadBalancer(unittest.TestCase):
    def test_sim(self):
        expected = {
            'id': 'LB1',
            'status': 'BUILD',
            'protocol': 'http',
            'region': mock.ANY,
            'interfaces': {
                'vip': {
                    'public_ip': '4.4.4.20',
                    'ip': '4.4.4.20'
                }
            },
            'port': 80,
            'public_ip': '4.4.4.20',
        }

        mock_api = mock.Mock()
        mock_callback = mock.Mock()
        actual = manager.Manager.create_loadbalancer(
            {}, "name", "public", "http", mock_api, mock_callback,
            simulate=True)
        self.assertEqual(expected, actual)
        mock_callback.assert_called_once_with({'id': 'LB1'})

    def test_success(self):
        vip = "0.0.0.0"
        expected = {
            'id': 'LB_ID',
            'status': 'BUILD',
            'protocol': 'http',
            'region': mock.ANY,
            'interfaces': {
                'vip': {
                    'public_ip': vip,
                    'ip': vip
                }
            },
            'port': 80,
            'public_ip': vip,
        }
        mock_api = mock.Mock()
        mock_callback = mock.Mock()
        mock_api.create.return_value = utils.Simulation(
            id="LB_ID", port=80, public_ip=vip, protocol="http",
            virtual_ips=[utils.Simulation(ip_version="IPV4", type="PUBLIC",
                                          address="0.0.0.0")])
        actual = manager.Manager.create_loadbalancer(
            {}, "name", "public", "http", mock_api, mock_callback)
        self.assertEqual(expected, actual)
        mock_callback.assert_called_once_with({'id': 'LB_ID'})
        self.assertTrue(mock_api.create.called)

    def test_overlimit_error_handling(self):
        mock_api = mock.Mock()
        mock_callback = mock.Mock()
        mock_api.create.side_effect = pyrax.exceptions.OverLimit("400")
        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.create_loadbalancer,
                          {}, "name", "public", "http", mock_api,
                          mock_callback)
        self.assertTrue(mock_api.create.called)


class TestWaitOnBuild(unittest.TestCase):
    def test_sim(self):
        expected = {
            'id': 'LB_ID',
            'status': 'ACTIVE',
            'status-message': '',
        }
        actual = manager.Manager.wait_on_build("LB_ID", None, None,
                                               simulate=True)
        self.assertEqual(expected, actual)

    def test_success(self):
        expected = {
            'id': 'LB_ID',
            'status': 'ACTIVE',
            'status-message': '',
        }
        mock_api = mock.Mock()
        mock_get = mock_api.get.return_value
        mock_get.status = "ACTIVE"

        actual = manager.Manager.wait_on_build("LB_ID", mock_api, None)
        self.assertEqual(expected, actual)
        mock_api.get.assert_called_once_with("LB_ID")

    def test_for_errored_lb(self):
        mock_callback = mock.Mock()
        mock_api = mock.Mock()
        mock_get = mock_api.get.return_value
        mock_get.status = "ERROR"

        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.wait_on_build,
                          "LB_ID", mock_api, mock_callback)
        mock_api.get.assert_called_once_with("LB_ID")
        mock_callback.assert_called_once_with(
            {'status': 'ERROR', 'status-message': 'Loadbalancer LB_ID build '
                                                  'failed'})

    def test_for_building_lb(self):
        mock_callback = mock.Mock()
        mock_api = mock.Mock()
        mock_get = mock_api.get.return_value
        mock_get.status = "BUILD"

        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.wait_on_build,
                          "LB_ID", mock_api, mock_callback)
        mock_api.get.assert_called_once_with("LB_ID")


class TestSetMonitor(unittest.TestCase):
    def test_success(self):
        mock_api = mock.Mock()
        mock_get = mock_api.get.return_value

        manager.Manager.set_monitor("LB_ID", "type", mock_api, path="path",
                                    delay=1, timeout=1, attempts=1,
                                    body="body", status="status")
        mock_api.get.assert_called_once_with("LB_ID")
        mock_get.add_health_monitor.assert_called_once_with(
            type="type", delay=1, timeout=1, path="path",
            statusRegex="status", attemptsBeforeDeactivation=1,
            bodyRegex="body")

    def test_sim(self):
        mock_api = mock.Mock()

        manager.Manager.set_monitor("LB_ID", "type", mock_api, path="path",
                                    delay=1, timeout=1, attempts=1,
                                    body="body", status="status",
                                    simulate=True)
        self.assertFalse(mock_api.get.called)

    def test_pyrax_exc_handling(self):
        mock_api = mock.Mock()
        mock_get = mock_api.get.return_value
        mock_get.add_health_monitor.side_effect = pyrax.exceptions\
            .PyraxException

        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.set_monitor, "LB_ID", "type",
                          mock_api, path="path", delay=1, timeout=1,
                          attempts=1, body="body", status="status")
        mock_api.get.assert_called_once_with("LB_ID")

    def test_standard_error_handling(self):
        mock_api = mock.Mock()
        mock_get = mock_api.get.return_value
        mock_get.add_health_monitor.side_effect = StandardError

        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.set_monitor, "LB_ID", "type",
                          mock_api, path="path", delay=1, timeout=1,
                          attempts=1, body="body", status="status")
        mock_api.get.assert_called_once_with("LB_ID")

    def test_422_client_exc_handling(self):
        mock_api = mock.Mock()
        mock_get = mock_api.get.return_value
        mock_get.add_health_monitor.side_effect = pyrax.exceptions\
            .ClientException('422')

        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.set_monitor, "LB_ID", "type",
                          mock_api, path="path", delay=1, timeout=1,
                          attempts=1, body="body", status="status")
        mock_api.get.assert_called_once_with("LB_ID")

    def test_other_client_exc_handling(self):
        mock_api = mock.Mock()
        mock_get = mock_api.get.return_value
        mock_get.add_health_monitor.side_effect = pyrax.exceptions\
            .ClientException('400')

        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.set_monitor, "LB_ID", "type",
                          mock_api, path="path", delay=1, timeout=1,
                          attempts=1, body="body", status="status")
        mock_api.get.assert_called_once_with("LB_ID")


class TestDeleteNode(unittest.TestCase):
    def test_success(self):
        mock_api = mock.Mock()
        mock_lb = mock_api.get.return_value
        mock_node = mock.Mock(address="0.0.0.0")
        mock_lb.nodes = [mock_node]
        manager.Manager.delete_node("LB_ID", "0.0.0.0", mock_api)
        self.assertTrue(mock_node.delete.called)
        mock_api.get.assert_called_once_with("LB_ID")

    def test_client_exc_handling(self):
        mock_api = mock.Mock()
        mock_lb = mock_api.get.return_value
        mock_node = mock.Mock(address="0.0.0.0")
        mock_lb.nodes = [mock_node]
        mock_node.delete.side_effect = pyrax.exceptions.ClientException
        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.delete_node, "LB_ID", "0.0.0.0",
                          mock_api)
        self.assertTrue(mock_node.delete.called)
        mock_api.get.assert_called_once_with("LB_ID")

    def test_standard_error_handling(self):
        mock_api = mock.Mock()
        mock_lb = mock_api.get.return_value
        mock_node = mock.Mock(address="0.0.0.0")
        mock_lb.nodes = [mock_node]
        mock_node.delete.side_effect = StandardError
        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.delete_node, "LB_ID", "0.0.0.0",
                          mock_api)
        self.assertTrue(mock_node.delete.called)
        mock_api.get.assert_called_once_with("LB_ID")

    def test_sim(self):
        mock_api = mock.Mock()
        manager.Manager.delete_node("LB_ID", "0.0.0.0", mock_api,
                                    simulate=True)
        self.assertFalse(mock_api.get.called)


class TestAddNode(unittest.TestCase):
    def test_sim(self):
        mock_api = mock.Mock()
        manager.Manager.add_node("LB_ID", "0.0.0.0", None, mock_api,
                                 simulate=True)
        self.assertFalse(mock_api.get.called)

    def test_success(self):
        mock_api = mock.Mock()
        node = clb.Node(address="0.0.0.0", port="80", condition="ENABLED")
        old_lb = mock.Mock(status="ACTIVE", port="80", nodes=[])
        fresh_lb = mock.Mock(nodes=[node])
        mock_api.get.side_effect = [old_lb, fresh_lb]
        mock_api.Node.return_value = node
        old_lb.add_nodes.return_value = (None, {'nodes': [{'id': 3456}]})

        actual = manager.Manager.add_node(1234, "0.0.0.0", None, mock_api)
        self.assertDictEqual({'nodes': [3456]}, actual)
        old_lb.add_nodes.assert_called_once_with([node])
        calls = [mock.call(1234), mock.call(1234)]
        mock_api.get.assert_has_calls(calls)

    def test_for_existing_node(self):
        mock_api = mock.Mock()
        node = clb.Node(id="NODE_ID", address="0.0.0.0", port=80,
                        condition="ENABLED")
        old_lb = mock.Mock(status="ACTIVE", port=80, nodes=[node])
        mock_api.get.return_value = old_lb

        actual = manager.Manager.add_node("LB_ID", "0.0.0.0", None, mock_api)
        self.assertDictEqual({'nodes': ["NODE_ID"]}, actual)
        mock_api.get.assert_called_once_with("LB_ID")

    def test_for_existing_disabled_node(self):
        mock_api = mock.Mock()
        node = clb.Node(id="NODE_ID", address="0.0.0.0", port=800,
                        condition="DISABLED")
        node.update = mock.Mock()
        old_lb = mock.Mock(status="ACTIVE", port=80, nodes=[node])
        mock_api.get.return_value = old_lb

        actual = manager.Manager.add_node(1234, "0.0.0.0", None, mock_api)
        self.assertDictEqual({'nodes': ["NODE_ID"]}, actual)
        self.assertTrue(node.update.called)
        self.assertEqual(node.port, 80)
        self.assertEqual(node.condition, "ENABLED")
        mock_api.get.assert_called_once_with(1234)

    def test_client_exc_handling(self):
        mock_api = mock.Mock()
        node = clb.Node(address="0.0.0.0", port=80, condition="ENABLED")
        lb = mock.Mock(status="ACTIVE", port=80, nodes=[])
        mock_api.get.return_value = lb
        mock_api.Node.return_value = node
        lb.add_nodes.side_effect = pyrax.exceptions.ClientException

        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.add_node, 1234, "0.0.0.0", None,
                          mock_api)
        lb.add_nodes.assert_called_once_with([node])
        mock_api.get.assert_called_once_with(1234)

    def test_standard_exc_handling(self):
        mock_api = mock.Mock()
        node = clb.Node(address="0.0.0.0", port=80, condition="ENABLED")
        lb = mock.Mock(status="ACTIVE", port=80, nodes=[])
        mock_api.get.return_value = lb
        mock_api.Node.return_value = node
        lb.add_nodes.side_effect = StandardError

        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.add_node, 1234, "0.0.0.0", None,
                          mock_api)
        lb.add_nodes.assert_called_once_with([node])
        mock_api.get.assert_called_once_with(1234)

    def test_for_placeholder_ip(self):
        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.add_node, 1234,
                          manager.PLACEHOLDER_IP, None, None)

    def test_for_non_active_lb(self):
        mock_api = mock.Mock()
        lb = mock.Mock(status="BUILD")
        mock_api.get.return_value = lb
        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.add_node, 1234, "0.0.0.0", None,
                          mock_api)

    def test_for_invalid_lb(self):
        mock_api = mock.Mock()
        lb = mock.Mock(status="ACTIVE", port=None)
        mock_api.get.return_value = lb
        self.assertRaises(exceptions.CheckmateBadState,
                          manager.Manager.add_node, 1234, "0.0.0.0", None,
                          mock_api)

    def test_placeholder_delete(self):
        mock_api = mock.Mock()
        placeholder_node = clb.Node(address=manager.PLACEHOLDER_IP, port=80,
                                    condition="ENABLED")
        node = clb.Node(address="0.0.0.0", port=80,
                        condition="ENABLED")
        lb = mock.Mock(status="ACTIVE", port=80,
                       nodes=[node, placeholder_node])
        mock_api.get.return_value = lb
        placeholder_node.delete = mock.Mock()

        manager.Manager.add_node(1234, "0.0.0.0", None, mock_api)
        self.assertTrue(placeholder_node.delete.called)
        mock_api.get.assert_called_once_with(1234)

    def test_placeholder_delete_exc_handling(self):
        mock_api = mock.Mock()
        placeholder_node = clb.Node(address=manager.PLACEHOLDER_IP, port=80,
                                    condition="ENABLED")
        node = clb.Node(address="0.0.0.0", port=80,
                        condition="ENABLED")
        lb = mock.Mock(status="ACTIVE", port=80,
                       nodes=[node, placeholder_node])
        mock_api.get.return_value = lb
        placeholder_node.delete = mock.Mock(
            side_effect=pyrax.exceptions.ClientException)

        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.add_node, 1234, "0.0.0.0", None,
                          mock_api)
        self.assertTrue(placeholder_node.delete.called)
        mock_api.get.assert_called_once_with(1234)


class TestWaitOnLbDelete(unittest.TestCase):
    def test_sim(self):
        expected = {'status': 'DELETED', 'status-message': ''}
        actual = manager.Manager.wait_on_lb_delete_task(1234, None,
                                                        simulate=True)
        self.assertDictEqual(actual, expected)

    def test_success(self):
        mock_api = mock.Mock()
        mock_api.get.return_value = mock.Mock(status='DELETED')
        expected = {'status': 'DELETED', 'status-message': ''}
        actual = manager.Manager.wait_on_lb_delete_task(1234, mock_api)
        self.assertDictEqual(actual, expected)
        mock_api.get.assert_called_once_with(1234)

    def test_for_invalid_lb(self):
        mock_api = mock.Mock()
        mock_api.get.side_effect = pyrax.exceptions.NotFound(404)
        expected = {'status': 'DELETED', 'status-message': ''}
        actual = manager.Manager.wait_on_lb_delete_task(1234, mock_api)
        self.assertDictEqual(actual, expected)
        mock_api.get.assert_called_once_with(1234)

    def test_for_deleting_lb(self):
        mock_api = mock.Mock()
        mock_api.get.return_value = mock.Mock(status='DELETING')
        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.wait_on_lb_delete_task, 1234,
                          mock_api)
        mock_api.get.assert_called_once_with(1234)


class TestDeleteLbTask(unittest.TestCase):
    def test_sim(self):
        expected = {
            'status': 'DELETING',
            'status-message': 'Waiting on resource deletion'
        }
        actual = manager.Manager.delete_lb_task(1234, None, simulate=True)
        self.assertDictEqual(actual, expected)

    def test_success(self):
        mock_api = mock.Mock()
        mock_lb = mock.Mock(status="ACTIVE")
        mock_api.get.return_value = mock_lb
        expected = {
            'status': 'DELETING',
            'status-message': 'Waiting on resource deletion'
        }
        actual = manager.Manager.delete_lb_task(1234, mock_api)
        self.assertDictEqual(actual, expected)
        mock_api.get.assert_called_once_with(1234)
        self.assertTrue(mock_lb.delete.called)

    def test_for_building_lb(self):
        mock_api = mock.Mock()
        mock_lb = mock.Mock(status="BUILD")
        mock_api.get.return_value = mock_lb
        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.delete_lb_task, 1234, mock_api)
        mock_api.get.assert_called_once_with(1234)

    def test_for_invalid_lb(self):
        mock_api = mock.Mock()
        mock_api.get.side_effect = pyrax.exceptions.NotFound(404)
        expected = {
            'status': 'DELETED',
            'status-message': ''
        }
        actual = manager.Manager.delete_lb_task(1234, mock_api)
        self.assertDictEqual(actual, expected)
        mock_api.get.assert_called_once_with(1234)

    def test_for_deleted_lb(self):
        mock_api = mock.Mock()
        mock_lb = mock.Mock(status="DELETED")
        mock_api.get.return_value = mock_lb
        expected = {
            'status': 'DELETED',
            'status-message': ''
        }
        actual = manager.Manager.delete_lb_task(1234, mock_api)
        self.assertDictEqual(actual, expected)
        mock_api.get.assert_called_once_with(1234)


class TestCollectRecordData(unittest.TestCase):
    def test_success(self):
        record = {"domain": "foo.com", "id": "ID"}
        expected = {
            "domain_id": "foo.com",
            "record_id": "ID",
        }
        actual = manager.Manager.collect_record_data(record)
        self.assertDictEqual(actual, expected)

    def test_without_id(self):
        record = {"domain": "foo.com"}
        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.collect_record_data, record)

    def test_without_domain(self):
        record = {"id": "ID"}
        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.collect_record_data, record)


class TestUpdateNodeStatus(unittest.TestCase):
    def test_sim(self):
        mock_callback = mock.Mock()
        expected = {
            "relations": {
                "lb-web-2": {
                    "state": "ENABLED"
                }
            }
        }
        target_results = {
            "status": "ACTIVE",
            "relations": {
                "lb-web-1": {
                    "state": "ENABLED"
                }
            }
        }
        relation = {"name": "lb-web", "target": "2"}
        actual = manager.Manager.update_node_status(
            {'resource_key': '1'}, 1234, "0.0.0.0", "ENABLED", "ACTIVE",
            relation, mock_callback, None, simulate=True)
        self.assertDictEqual(actual, expected)
        mock_callback.assert_called_once_with(target_results,
                                              resource_key="2")

    def test_success(self):
        mock_callback = mock.Mock()
        mock_api = mock.Mock()
        mock_node = mock.Mock(address="0.0.0.0")
        mock_api.get.return_value = mock.Mock(nodes=[mock_node])

        expected = {
            "relations": {
                "lb-web-2": {
                    "state": "ENABLED"
                }
            }
        }
        target_results = {
            "status": "ACTIVE",
            "relations": {
                "lb-web-1": {
                    "state": "ENABLED"
                }
            }
        }
        relation = {"name": "lb-web", "target": "2"}
        actual = manager.Manager.update_node_status(
            {'resource_key': '1'}, 1234, "0.0.0.0", "ENABLED", "ACTIVE",
            relation, mock_callback, mock_api)
        self.assertDictEqual(actual, expected)
        self.assertTrue(mock_node.update.called)
        self.assertEqual(mock_node.condition, "ENABLED")
        mock_callback.assert_called_once_with(target_results,
                                              resource_key="2")
        mock_api.get.assert_called_once_with(1234)

    def test_pyrax_exc_handling(self):
        mock_callback = mock.Mock()
        mock_api = mock.Mock()
        mock_node = mock.Mock(address="0.0.0.0")
        mock_api.get.return_value = mock.Mock(nodes=[mock_node])
        mock_node.update.side_effect = pyrax.exceptions.ClientException(422)

        relation = {"name": "lb-web", "target": "2"}
        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.update_node_status,
                          {'resource_key': '1'}, 1234, "0.0.0.0", "ENABLED",
                          "ACTIVE", relation, mock_callback, mock_api)
        self.assertTrue(mock_node.update.called)
        self.assertFalse(mock_callback.update.called)
        self.assertEqual(mock_node.condition, "ENABLED")
        mock_api.get.assert_called_once_with(1234)

    def test_standard_error_handling(self):
        mock_callback = mock.Mock()
        mock_api = mock.Mock()
        mock_node = mock.Mock(address="0.0.0.0")
        mock_api.get.return_value = mock.Mock(nodes=[mock_node])
        mock_node.update.side_effect = StandardError

        relation = {"name": "lb-web", "target": "2"}
        self.assertRaises(exceptions.CheckmateException,
                          manager.Manager.update_node_status,
                          {'resource_key': '1'}, 1234, "0.0.0.0", "ENABLED",
                          "ACTIVE", relation, mock_callback, mock_api)
        self.assertTrue(mock_node.update.called)
        self.assertFalse(mock_callback.update.called)
        self.assertEqual(mock_node.condition, "ENABLED")
        mock_api.get.assert_called_once_with(1234)


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
