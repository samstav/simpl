# pylint: disable=C0103,R0201

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

"""Tests for Resource class."""
import json
import mock
import unittest
import yaml

from checkmate import exceptions as cmexc
from checkmate import resource as cmres
from checkmate import utils


class TestResource(unittest.TestCase):
    error_string = "extra keys not allowed @ data['%s']"

    def setUp(self):
        self.resource = cmres.Resource('0', {})
        cmres.LOG.warn = mock.Mock()

    def test_empty_dict_is_valid(self):
        cmres.Resource.validate({})

    def test_invalid_key_at_root(self):
        with self.assertRaises(cmexc.CheckmateValidationException):
            cmres.Resource.validate({'blerg': 'blerf'})

    def test_id_key_at_root_logs_warning(self):
        cmres.Resource.validate({'id': 'i-really-am-21'})
        cmres.LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'id'])

    def test_flavor_key_at_root_logs_warning(self):
        cmres.Resource.validate({'flavor': 'cookies-n-cream'})
        cmres.LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'flavor'])

    def test_image_key_at_root_logs_warning(self):
        cmres.Resource.validate({'image': 'iconic'})
        cmres.LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'image'])

    def test_disk_key_at_root_logs_warning(self):
        cmres.Resource.validate({'disk': 'vinyl'})
        cmres.LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'disk'])

    def test_region_key_at_root_logs_warning(self):
        cmres.Resource.validate({'region': 'Mendoza Province'})
        cmres.LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'region'])

    def test_protocol_key_at_root_logs_warning(self):
        cmres.Resource.validate({'protocol': 'Kyoto'})
        cmres.LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'protocol'])

    def test_port_key_at_root_logs_warning(self):
        cmres.Resource.validate({'port': 'Sydney Harbor'})
        cmres.LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'port'])

    def test_all_valid_root_keys(self):
        cmres.Resource.validate({
            'index': 'S&P 500',
            'name': 'Trouble',
            'provider': 'Rackspace',
            'relations': 'foreign',
            'hosted_on': 'NBC',
            'hosts': {'Alex Trebek'},
            'type': 'Lucida Grande',
            'component': 'widget',
            'dns-name': 'www.rackspace.com',
            'instance': {},
            'service': 'self',
            'status': 'ACTIVE',
            'desired-state': {}
        })

    def test_index_key_in_desired_state_is_invalid(self):
        with self.assertRaises(cmexc.CheckmateValidationException):
            cmres.Resource.validate({'desired-state': {'index': 'S&P 500'}})

    def test_all_valid_desired_state_keys(self):
        cmres.Resource.validate({
            'desired-state': {
                'region': 'Mendoza Province',
                'flavor': 'rocky-road',
                'image': 'iconic',
                'disk': 'vinyl',
                'protocol': 'Kyoto',
                'port': 'Sydney Harbor',
                'status': 'INSTANCE STATUS',
                'databases': {},
                'os-type': 'typos',
                'os': 'MS-DOS'
            }
        })

    def test_set_invalid_root_resource_key(self):
        with self.assertRaises(cmexc.CheckmateValidationException):
            self.resource['blerg'] = 'blerf'

    def test_set_invalid_desired_state_key(self):
        self.resource['desired-state'] = {}
        with self.assertRaises(cmexc.CheckmateValidationException):
            self.resource['desired-state']['service'] = 'self'

    def test_set_desired_state_with_valid_dict(self):
        self.resource['desired-state'] = {'port': '80'}
        self.assertEqual({'port': '80'}, self.resource['desired-state'])

    def test_set_desired_state_with_invalid_dict(self):
        self.resource['desired-state'] = {}
        with self.assertRaises(cmexc.CheckmateValidationException):
            self.resource['desired-state'] = {'service': 'self'}

    #
    # Test the dict'ness of Resource
    #

    def test_resource_len(self):
        self.resource['index'] = '0'
        self.resource['desired-state'] = {'port': '80'}
        self.resource['status'] = 'PLANNED'
        self.assertEquals(3, len(self.resource))

    def test_resource_get_item(self):
        self.resource['index'] = '0'
        self.resource['desired-state'] = {'port': '80'}
        self.assertEqual({'port': '80'}, self.resource['desired-state'])

    def test_json_dumps(self):
        self.resource['index'] = '0'
        self.resource['desired-state'] = {'port': '80'}
        self.assertEqual(
            {
                'index': '0',
                'status': 'PLANNED',
                'desired-state': {'port': '80'}
            },
            json.loads(json.dumps(self.resource))
        )

    def test_yaml_dumps(self):
        self.resource['index'] = '0'
        self.resource['desired-state'] = {'port': '80'}
        self.assertEqual(
            {
                'index': '0',
                'status': 'PLANNED',
                'desired-state': {'port': '80'}
            },
            yaml.safe_load(utils.to_yaml(self.resource))
        )

    #
    # State Transition Tests
    #

    def test_initial_state_is_PLANNED(self):
        self.assertEqual('PLANNED', self.resource['status'])

    def test_instantiation_with_specified_status_is_valid(self):
        preexisting_resource = cmres.Resource('0', {'status': 'ACTIVE'})
        self.assertEqual('ACTIVE', preexisting_resource.fsm.current)

    def test_from_PLANNED_straight_to_ACTIVE(self):
        self.assertTrue(self.resource.fsm.permitted('ACTIVE'))

    def test_from_PLANNED_straight_to_DELETING(self):
        self.assertTrue(self.resource.fsm.permitted('DELETING'))

    def test_from_NEW_straight_to_ACTIVE(self):
        self.resource['status'] = 'NEW'
        self.assertTrue(self.resource.fsm.permitted('ACTIVE'))

    def test_from_BUILD_straight_to_ACTIVE(self):
        self.resource['status'] = 'NEW'
        self.resource['status'] = 'BUILD'
        self.assertTrue(self.resource.fsm.permitted('ACTIVE'))

    def test_valid_new_to_deleted_with_no_errors(self):
        self.resource['status'] = 'PLANNED'
        self.assertTrue(self.resource.fsm.permitted('NEW'))
        self.assertTrue(self.resource.fsm.permitted('ACTIVE'))
        self.assertTrue(self.resource.fsm.permitted('DELETING'))
        self.resource['status'] = 'NEW'
        self.assertTrue(self.resource.fsm.permitted('BUILD'))
        self.assertTrue(self.resource.fsm.permitted('ACTIVE'))
        self.assertTrue(self.resource.fsm.permitted('DELETING'))
        self.assertTrue(self.resource.fsm.permitted('ERROR'))
        self.resource['status'] = 'BUILD'
        self.assertTrue(self.resource.fsm.permitted('CONFIGURE'))
        self.assertTrue(self.resource.fsm.permitted('ACTIVE'))
        self.assertTrue(self.resource.fsm.permitted('DELETING'))
        self.assertTrue(self.resource.fsm.permitted('ERROR'))
        self.resource['status'] = 'CONFIGURE'
        self.assertTrue(self.resource.fsm.permitted('ACTIVE'))
        self.assertTrue(self.resource.fsm.permitted('DELETING'))
        self.assertTrue(self.resource.fsm.permitted('ERROR'))
        self.resource['status'] = 'ACTIVE'
        self.assertTrue(self.resource.fsm.permitted('DELETING'))
        self.assertTrue(self.resource.fsm.permitted('ERROR'))
        self.resource['status'] = 'DELETING'
        self.assertTrue(self.resource.fsm.permitted('DELETED'))
        self.assertTrue(self.resource.fsm.permitted('ERROR'))
        self.resource['status'] = 'DELETED'
        self.assertEqual('DELETED', self.resource.fsm.current)

    def test_invalid_transitions_from_PLANNED(self):
        self.assertFalse(self.resource.fsm.permitted('PLANNED'))
        self.assertFalse(self.resource.fsm.permitted('BUILD'))
        self.assertFalse(self.resource.fsm.permitted('CONFIGURE'))
        self.assertFalse(self.resource.fsm.permitted('DELETED'))
        self.assertFalse(self.resource.fsm.permitted('ERROR'))

    def test_invalid_transitions_from_NEW(self):
        self.resource['status'] = 'NEW'
        self.assertFalse(self.resource.fsm.permitted('PLANNED'))
        self.assertFalse(self.resource.fsm.permitted('NEW'))
        self.assertFalse(self.resource.fsm.permitted('CONFIGURE'))
        self.assertFalse(self.resource.fsm.permitted('DELETED'))

    def test_invalid_transitions_from_BUILD(self):
        self.resource['status'] = 'NEW'
        self.resource['status'] = 'BUILD'
        self.assertFalse(self.resource.fsm.permitted('PLANNED'))
        self.assertFalse(self.resource.fsm.permitted('NEW'))
        self.assertFalse(self.resource.fsm.permitted('BUILD'))
        self.assertFalse(self.resource.fsm.permitted('DELETED'))

    def test_invalid_transitions_from_CONFIGURE(self):
        self.resource['status'] = 'NEW'
        self.resource['status'] = 'BUILD'
        self.resource['status'] = 'CONFIGURE'
        self.assertFalse(self.resource.fsm.permitted('PLANNED'))
        self.assertFalse(self.resource.fsm.permitted('NEW'))
        self.assertFalse(self.resource.fsm.permitted('BUILD'))
        self.assertFalse(self.resource.fsm.permitted('CONFIGURE'))
        self.assertFalse(self.resource.fsm.permitted('DELETED'))

    def test_invalid_transitions_from_ACTIVE(self):
        self.resource['status'] = 'NEW'
        self.resource['status'] = 'BUILD'
        self.resource['status'] = 'CONFIGURE'
        self.resource['status'] = 'ACTIVE'
        self.assertFalse(self.resource.fsm.permitted('PLANNED'))
        self.assertFalse(self.resource.fsm.permitted('NEW'))
        self.assertFalse(self.resource.fsm.permitted('BUILD'))
        self.assertFalse(self.resource.fsm.permitted('CONFIGURE'))
        self.assertFalse(self.resource.fsm.permitted('ACTIVE'))
        self.assertFalse(self.resource.fsm.permitted('DELETED'))

    def test_invalid_transitions_from_DELETING(self):
        self.resource['status'] = 'NEW'
        self.resource['status'] = 'BUILD'
        self.resource['status'] = 'CONFIGURE'
        self.resource['status'] = 'ACTIVE'
        self.resource['status'] = 'DELETING'
        self.assertFalse(self.resource.fsm.permitted('PLANNED'))
        self.assertFalse(self.resource.fsm.permitted('NEW'))
        self.assertFalse(self.resource.fsm.permitted('BUILD'))
        self.assertFalse(self.resource.fsm.permitted('CONFIGURE'))
        self.assertFalse(self.resource.fsm.permitted('ACTIVE'))
        self.assertFalse(self.resource.fsm.permitted('DELETING'))

    def test_invalid_transitions_from_DELETED(self):
        self.resource['status'] = 'NEW'
        self.resource['status'] = 'BUILD'
        self.resource['status'] = 'CONFIGURE'
        self.resource['status'] = 'ACTIVE'
        self.resource['status'] = 'DELETING'
        self.resource['status'] = 'DELETED'
        self.assertFalse(self.resource.fsm.permitted('PLANNED'))
        self.assertFalse(self.resource.fsm.permitted('NEW'))
        self.assertFalse(self.resource.fsm.permitted('BUILD'))
        self.assertFalse(self.resource.fsm.permitted('CONFIGURE'))
        self.assertFalse(self.resource.fsm.permitted('ACTIVE'))
        self.assertFalse(self.resource.fsm.permitted('DELETING'))
        self.assertFalse(self.resource.fsm.permitted('DELETED'))
        self.assertFalse(self.resource.fsm.permitted('ERROR'))

    def test_invalid_transitions_from_ERROR(self):
        self.resource['status'] = 'NEW'
        self.resource['status'] = 'ERROR'
        self.assertFalse(self.resource.fsm.permitted('PLANNED'))
        self.assertFalse(self.resource.fsm.permitted('DELETED'))
        self.assertFalse(self.resource.fsm.permitted('ERROR'))

    def test_invalid_transition_results_in_warning(self):
        self.resource['status'] = 'BUILD'
        cmres.LOG.warn.assert_called_with(
            'State change from %s to %s is invalid', 'PLANNED', 'BUILD')


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
