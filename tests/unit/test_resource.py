# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method
'''
import unittest2 as unittest
import mock
import json
import yaml

from checkmate import utils
from checkmate.exceptions import CheckmateValidationException
from checkmate.resource import Resource, LOG


class TestResource(unittest.TestCase):
    error_string = (
        "'%s' not a valid value. Only index, name, provider, relations, "
        "hosted_on, hosts, type, component, dns-name, instance, service, "
        "status, desired-state allowed"
    )

    def setUp(self):
        LOG.warn = mock.Mock()

    def test_empty_dict_is_valid(self):
        Resource.validate({})

    def test_invalid_key_at_root(self):
        with self.assertRaises(CheckmateValidationException):
            Resource.validate({'blerg': 'blerf'})

    def test_id_key_at_root_logs_warning(self):
        Resource.validate({'id': 'i-really-am-21'})
        LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'id'])

    def test_flavor_key_at_root_logs_warning(self):
        Resource.validate({'flavor': 'cookies-n-cream'})
        LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'flavor'])

    def test_image_key_at_root_logs_warning(self):
        Resource.validate({'image': 'iconic'})
        LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'image'])

    def test_disk_key_at_root_logs_warning(self):
        Resource.validate({'disk': 'vinyl'})
        LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'disk'])

    def test_region_key_at_root_logs_warning(self):
        Resource.validate({'region': 'Mendoza Province'})
        LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'region'])

    def test_protocol_key_at_root_logs_warning(self):
        Resource.validate({'protocol': 'Kyoto'})
        LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'protocol'])

    def test_port_key_at_root_logs_warning(self):
        Resource.validate({'port': 'Sydney Harbor'})
        LOG.warn.assert_called_with(
            'DEPRECATED KEY: %s', [self.error_string % 'port'])

    def test_all_valid_root_keys(self):
        Resource.validate({
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
        with self.assertRaises(CheckmateValidationException):
            Resource.validate({'desired-state': {'index': 'S&P 500'}})

    def test_all_valid_desired_state_keys(self):
        Resource.validate({
            'desired-state': {
                'region': 'Mendoza Province',
                'flavor': 'rocky-road',
                'image': 'iconic',
                'disk': 'vinyl',
                'protocol': 'Kyoto',
                'port': 'Sydney Harbor',
                'status': 'INSTANCE STATUS',
                'databases': {}
            }
        })

    def test_set_invalid_root_resource_key(self):
        resource = Resource('0', {})
        with self.assertRaises(CheckmateValidationException):
            resource['blerg'] = 'blerf'

    def test_set_invalid_desired_state_key(self):
        resource = Resource('0', {'desired-state': {}})
        with self.assertRaises(CheckmateValidationException):
            resource['desired-state']['service'] = 'self'

    def test_set_desired_state_with_valid_dict(self):
        resource = Resource('0', {'desired-state': {}})
        resource['desired-state'] = {'port': '80'}
        self.assertEquals({'port': '80'}, resource['desired-state'])

    def test_set_desired_state_with_invalid_dict(self):
        resource = Resource('0', {'desired-state': {}})
        with self.assertRaises(CheckmateValidationException):
            resource['desired-state'] = {'service': 'self'}


    #
    # Test the dict'ness of Resource
    #

    def test_resource_len(self):
        resource = Resource(
            '0',
            {'index': '0', 'desired-state': {'port': '80'}}
        )
        self.assertEquals(2, len(resource))

    def test_resource_get_item(self):
        resource = Resource(
            '0',
            {'index': '0', 'desired-state': {'port': '80'}}
        )
        self.assertEquals({'port': '80'}, resource['desired-state'])

    def test_json_dumps(self):
        resource = Resource(
            '0',
            {'index': '0', 'desired-state': {'port': '80'}}
        )
        self.assertDictEqual(
            {'index': '0', 'desired-state': {'port': '80'}},
            json.loads(json.dumps(resource))
        )

    def test_yaml_dumps(self):
        resource = Resource(
            '0',
            {'index': '0', 'desired-state': {'port': '80'}}
        )
        self.assertDictEqual(
            {'index': '0', 'desired-state': {'port': '80'}},
            yaml.safe_load(utils.to_yaml(resource))
        )


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
