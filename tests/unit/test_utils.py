# pylint: disable=C0103,R0904,W0212

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

"""Tests for utils module."""
import copy
import re
import time
import unittest
import uuid

import bottle
import mock

from checkmate import utils


class TestUtils(unittest.TestCase):
    def tearDown(self):
        # reset the request object's headers and set the body to {}
        bottle.response.bind({})

    def test_extract_sensitive_data_simple(self):
        fxn = utils.extract_sensitive_data
        self.assertEquals(fxn({}), ({}, None))
        combined = {
            'innocuous': 'Hello!',
            'password': 'secret',
        }
        innocuous = {'innocuous': 'Hello!'}
        secret = {'password': 'secret'}
        original = copy.copy(combined)
        self.assertEquals(fxn(combined, sensitive_keys=[]), (combined, None))
        self.assertEquals(fxn(combined, ['password']), (innocuous, secret))
        self.assertDictEqual(combined, original)

    def test_extract_sensitive_data_works_with_None_keys(self):
        sensitive_keys = [re.compile('quux')]
        data = {None: 'foobar'}
        expected = (data, None)
        self.assertEqual(expected,
                         utils.extract_sensitive_data(data, sensitive_keys))

    def test_flatten(self):
        list_of_dict = [{'foo': 'bar'}, {'a': 'b'}, {'foo': 'bar1'}]
        self.assertDictEqual(utils.flatten(list_of_dict),
                             {'foo': 'bar1', 'a': 'b'})

    def test_get_id_for_simulate(self):
        self.assertTrue(utils.get_id(True).startswith("simulate"))
        self.assertFalse(utils.get_id(False).startswith("simulate"))

    def test_extract_data_expression_as_sensitive(self):
        data = {
            "employee": {
                "name": "Bob",
                "title": "Mr.",
                "public_key": "rsa public key",
                "private_key": "a private key",
                "password": "password",
                "position": "left"
            },
            "server": {
                "access": {
                    "rootpassword": "password",
                    "server_privatekey": "private_key",
                    "server_public_key": "public_key"
                },
                "private_ip": "123.45.67.89",
                "public_ip": "127.0.0.1",
                "host_name": "server1"
            },
            "safe_val": "hithere",
            "secret_value": "Immasecret"
        }

        safe = {
            "employee": {
                "name": "Bob",
                "title": "Mr.",
                "public_key": "rsa public key",
                "position": "left"
            },
            "server": {
                "access": {
                    "server_public_key": "public_key"
                },
                "private_ip": "123.45.67.89",
                "public_ip": "127.0.0.1",
                "host_name": "server1"
            },
            "safe_val": "hithere",
        }

        secret = {
            "employee": {
                "private_key": "a private key",
                "password": "password",
            },
            "server": {
                "access": {
                    "rootpassword": "password",
                    "server_privatekey": "private_key",
                }
            },
            "secret_value": "Immasecret"
        }

        original_dict = copy.deepcopy(data)
        secret_keys = ["secret_value", re.compile("password"),
                       re.compile("priv(?:ate)?[-_ ]?key$")]
        body, hidden = utils.extract_sensitive_data(data, secret_keys)
        self.assertDictEqual(body, safe)
        self.assertDictEqual(secret, hidden)
        utils.merge_dictionary(body, hidden)
        self.assertDictEqual(original_dict, body)

    def test_extract_sensitive_data_complex(self):
        fxn = utils.extract_sensitive_data
        self.assertEquals(fxn({}), ({}, None))
        combined = {
            'innocuous': {
                'names': ['Tom', 'Richard', 'Harry']
            },
            'data': {
                'credentials': [{'password': 'secret', 'username': 'joe'}],
                'id': 1000,
                'list_with_only_cred_objects': [{'password': 'secret'}],
                'list_with_some_cred_objects': [
                    {
                        'password': 'secret',
                        'type': 'password',
                    },
                    'scalar',
                    {'name': 'joe'}
                ]
            }
        }
        innocuous = {
            'innocuous': {
                'names': ['Tom', 'Richard', 'Harry']
            },
            'data': {
                'id': 1000,
                'list_with_some_cred_objects': [
                    {
                        'type': 'password'
                    },
                    'scalar',
                    {'name': 'joe'}
                ]
            }
        }
        secret = {
            'data': {
                'credentials': [{'password': 'secret', 'username': 'joe'}],
                'list_with_only_cred_objects': [{'password': 'secret'}],
                'list_with_some_cred_objects': [
                    {
                        'password': 'secret'
                    },
                    None,
                    {}
                ]
            }
        }
        original = copy.copy(combined)
        not_secret, is_secret = fxn(combined, [])
        self.assertDictEqual(not_secret, combined)
        self.assertIsNone(is_secret)

        not_secret, is_secret = fxn(combined, ['credentials', 'password'])
        self.assertDictEqual(not_secret, innocuous)
        self.assertDictEqual(is_secret, secret)
        self.assertDictEqual(combined, original)

        merged = utils.merge_dictionary(innocuous, secret)
        self.assertDictEqual(original, merged)

    def test_default_secrets_detected(self):
        data = {
            'apikey': 'secret',
            'error-string': 'secret',
            'error-traceback': 'secret',
            'password': 'secret',
        }
        body, hidden = utils.extract_sensitive_data(data)
        self.assertIsNone(body)
        self.assertEquals(hidden, data)

    def test_extract_and_merge(self):
        fxn = utils.extract_sensitive_data
        data = {
            'empty_list': [],
            'empty_object': {},
            'null': None,
            'list_with_empty_stuff': [{}, None, []],
            'object_with_empty_stuff': {"o": {}, "n": None, 'l': []},
            "tree": {
                "array": [
                    {
                        "blank": {},
                        "scalar": 1
                    }
                ]
            }
        }
        result, _ = fxn(data, [])
        self.assertDictEqual(data, result)
        merge = utils.merge_dictionary(data, data)
        self.assertDictEqual(data, merge)
        merge = utils.merge_dictionary(data, {})
        self.assertDictEqual(data, merge)
        merge = utils.merge_dictionary({}, data)
        self.assertDictEqual(data, merge)

    def test_merge_dictionary(self):
        dst = dict(a=1, b=2, c=dict(ca=31, cc=33, cd=dict(cca=1)), d=4, f=6,
                   g=7, i=[], k=[3, 4], l=[[], [{'s': 1}]])
        src = dict(b='u2', c=dict(cb='u32', cd=dict(cda=dict(cdaa='u3411',
                   cdab='u3412'))), e='u5', h=dict(i='u4321'), i=[1], j=[1, 2],
                   l=[None, [{'t': 8}]])
        result = utils.merge_dictionary(dst, src)
        self.assertIsInstance(result, dict)
        self.assertEquals(result['a'], 1)
        self.assertEquals(result['d'], 4)
        self.assertEquals(result['f'], 6)
        self.assertEquals(result['b'], 'u2')
        self.assertEquals(result['e'], 'u5')
        self.assertIs(result['c'], dst['c'])
        self.assertIs(result['c']['cd'], dst['c']['cd'])
        self.assertEquals(result['c']['cd']['cda']['cdaa'], 'u3411')
        self.assertEquals(result['c']['cd']['cda']['cdab'], 'u3412')
        self.assertEquals(result['g'], 7)
        self.assertIs(src['h'], result['h'])
        self.assertEquals(result['i'], [1])
        self.assertEquals(result['j'], [1, 2])
        self.assertEquals(result['k'], [3, 4])
        self.assertEquals(result['l'], [[], [{'s': 1, 't': 8}]])

    def test_merge_lists(self):
        dst = [[], [2], [None, 4]]
        src = [[1], [], [3, None]]
        result = utils.merge_lists(dst, src)
        self.assertIsInstance(result, list)
        self.assertEquals(result[0], [1])
        self.assertEquals(result[1], [2])
        self.assertEquals(result[2], [3, 4], "Found: %s" % result[2])

    def test_is_ssh_key(self):
        self.assertFalse(utils.is_ssh_key(None))
        self.assertFalse(utils.is_ssh_key(''))
        self.assertFalse(utils.is_ssh_key(1))
        self.assertFalse(utils.is_ssh_key("AAAAB3NzaC1yc2EA"))
        self.assertFalse(utils.is_ssh_key("AAAAB3NzaC1yc2EA-bad"))
        self.assertFalse(utils.is_ssh_key("AAAAB3NzaC1yc2EA onespace"))
        self.assertFalse(utils.is_ssh_key("AAAAB3NzaC1yc2EA two space"))
        self.assertFalse(utils.is_ssh_key("AAAAB3NzaC1yc2EA 3 spaces here"))
        key = ("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtjYYMFbpCJ/ND3izZ1DqNFQ"
               "HlooXyNcDGWilAqNqcCfz9L+gpGjY2pQlZz/1Hir3R8fz0MS9VY32RYmP3wWyg"
               "t85kNccEkOpVGGpGyV/aMFaQHZD0h6d0AT+haP0Iig+OrH1YBnpdgVPWx3SbU4"
               "eV/KYGpO9Mintj3P54of22lTK4dOwCNvID9P9w+T1kMfdVxGwhqsSL0RxVXnSS"
               "kozXQWCNvaZJMUmidm8YA009c5PoksyWjl3EE+rEzZ8ywvtUJf9DvnLCESfhF3"
               "hK5lAiEd8z7gyiQnBexn/dXzldGFiJYJgQ5HolYaNMtTF+AQY6R6Qt0okCPyED"
               "JxHJUM7d")
        self.assertTrue(utils.is_ssh_key(key))
        self.assertTrue(utils.is_ssh_key("%s /n" % key))
        self.assertTrue(utils.is_ssh_key("%s email@domain.com/n" % key))
        key = ("ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA7TT1qbLElv6tuAaA3Z4tQ752ms"
               "0Y7H53yybfFioFHELkp+NRMCKh4AqtqDBFsps1vPzhcXIxn4M4IH0ip7kSx0CS"
               "rM/9Vtz8jc+UZwixJdAWwHpum68rGmCQgAsZljI24Q9u8r/hXqjwY6ukTKbC0i"
               "y82LHqhcDjh3828+9GyyxbYGm5ND/5G/ZcnHD6HM9YKmc3voz5d/nez3Adlu4I"
               "1z4Y1T3lOwOxrP2OqvIeDPvVOZJ9GDmYYRDfqK8OIHDoLAzQx8xu0cvPRDL7gY"
               "RXN8nJZ5nOh+51zdPQEl99ACZDSSwTl2biOPNtXtuaGyjB5j8r7dz93JlsN8ax"
               "eD+ECQ== ziad@sawalha.com")
        self.assertTrue(utils.is_ssh_key(key))

    def test_get_source_body(self):
        source = utils.get_source_body(self.test_get_source_body)
        self.assertTrue(source.startswith("source = utils"))

        source = utils.get_source_body(self.dummy_static)
        self.assertTrue(source.startswith('"""Used for get_source_body'))

    @staticmethod
    def dummy_static():
        """Used for get_source_body test."""
        pass

    def test_is_uuid_blanks(self):
        self.assertFalse(utils.is_uuid(None), "None is not a UUID")
        self.assertFalse(utils.is_uuid(""), "Empty string is not a UUID")
        self.assertFalse(utils.is_uuid(" "), "Space is not a UUID")

    def test_is_uuid_negatives(self):
        self.assertFalse(utils.is_uuid("12345"), "12345 is not a UUID")
        self.assertFalse(utils.is_uuid(utils), "module is not a UUID")

    def test_is_uuid_positives(self):
        self.assertTrue(utils.is_uuid(uuid.uuid4()), "uuid() is a UUID")
        self.assertTrue(utils.is_uuid(uuid.uuid4().hex),
                        "uuid string is a UUID")

    def test_write_path(self):
        cases = [
            {
                'name': 'scalar at root',
                'start': {},
                'path': 'root',
                'value': 'scalar',
                'expected': {'root': 'scalar'}
            }, {
                'name': 'int at root',
                'start': {},
                'path': 'root',
                'value': 10,
                'expected': {'root': 10}
            }, {
                'name': 'bool at root',
                'start': {},
                'path': 'root',
                'value': True,
                'expected': {'root': True}
            }, {
                'name': 'value at two piece path',
                'start': {},
                'path': 'root/subfolder',
                'value': True,
                'expected': {'root': {'subfolder': True}}
            }, {
                'name': 'value at multi piece path',
                'start': {},
                'path': 'one/two/three',
                'value': {},
                'expected': {'one': {'two': {'three': {}}}}
            }, {
                'name': 'add to existing',
                'start': {'root': {'exists': True}},
                'path': 'root/new',
                'value': False,
                'expected': {'root': {'exists': True, 'new': False}}
            }, {
                'name': 'overwrite existing',
                'start': {'root': {'exists': True}},
                'path': 'root/exists',
                'value': False,
                'expected': {'root': {'exists': False}}
            }
        ]
        for case in cases:
            result = case['start']
            utils.write_path(result, case['path'], case['value'])
            self.assertDictEqual(result, case['expected'], msg=case['name'])

    def test_read_path(self):
        cases = [
            {
                'name': 'simple value',
                'start': {'root': 1},
                'path': 'root',
                'expected': 1
            }, {
                'name': 'simple path',
                'start': {'root': {'folder': 2}},
                'path': 'root/folder',
                'expected': 2
            }, {
                'name': 'blank path',
                'start': {'root': 1},
                'path': '',
                'expected': None
            }, {
                'name': '/ only',
                'start': {'root': 1},
                'path': '/',
                'expected': None
            }, {
                'name': 'extra /',
                'start': {'root': 1},
                'path': '/root/',
                'expected': 1
            }, {
                'name': 'nonexistent root',
                'start': {'root': 1},
                'path': 'not-there',
                'expected': None
            }, {
                'name': 'nonexistent path',
                'start': {'root': 1},
                'path': 'root/not-there',
                'expected': None
            }, {
                'name': 'empty source',
                'start': {},
                'path': 'root',
                'expected': None
            },
        ]
        for case in cases:
            result = utils.read_path(case['start'], case['path'])
            self.assertEqual(result, case['expected'], msg=case['name'])

    def test_path_exists(self):
        cases = [
            {
                'name': 'simple value',
                'start': {'root': 1},
                'path': 'root',
                'expected': True
            }, {
                'name': 'simple path',
                'start': {'root': {'folder': 2}},
                'path': 'root/folder',
                'expected': True
            }, {
                'name': 'blank path',
                'start': {'root': 1},
                'path': '',
                'expected': False
            }, {
                'name': '/ only',
                'start': {'root': 1},
                'path': '/',
                'expected': True
            }, {
                'name': 'extra /',
                'start': {'root': 1},
                'path': '/root/',
                'expected': True
            }, {
                'name': 'nonexistent root',
                'start': {'root': 1},
                'path': 'not-there',
                'expected': False
            }, {
                'name': 'nonexistent path',
                'start': {'root': 1},
                'path': 'root/not-there',
                'expected': False
            }, {
                'name': 'empty source',
                'start': {},
                'path': 'root',
                'expected': False
            },
        ]
        for case in cases:
            result = utils.path_exists(case['start'], case['path'])
            self.assertEqual(result, case['expected'], msg=case['name'])

    def test_is_evaluable(self):
        self.assertTrue(utils.is_evaluable('=generate_password()'))
        self.assertTrue(utils.is_evaluable('=generate_uuid()'))
        self.assertFalse(utils.is_evaluable('=generate_something_else()'))
        self.assertFalse(utils.is_evaluable({'not-a-string': 'boom!'}))

    def test_get_formatted_time_string(self):
        some_time = time.gmtime(0)
        with mock.patch.object(utils.time, 'gmtime') as mock_gmt:
            mock_gmt.return_value = some_time
            result = utils.get_time_string()
            self.assertEquals(result, "1970-01-01 00:00:00 +0000")

    def test_get_formatted_time_string_with_input(self):
        result = utils.get_time_string(time_gmt=time.gmtime(0))
        self.assertEquals(result, "1970-01-01 00:00:00 +0000")

    #
    # _validate_range_values tests
    #

    def test_negative_is_invalid(self):
        bottle.request.environ = {'QUERY_STRING': 'offset=-2'}
        kwargs = {}
        with self.assertRaises(ValueError):
            utils._validate_range_values(bottle.request, 'offset', kwargs)

    def test_non_numeric_is_invalid(self):
        bottle.request.environ = {'QUERY_STRING': 'limit=blah'}
        kwargs = {}
        with self.assertRaises(ValueError):
            utils._validate_range_values(bottle.request, 'limit', kwargs)

    def test_nothing_provided_is_valid_but_none(self):
        bottle.request.environ = {'QUERY_STRING': ''}
        kwargs = {}
        utils._validate_range_values(bottle.request, 'offset', kwargs)
        self.assertEquals(None, kwargs.get('offset'))
        self.assertEquals(200, bottle.response.status_code)

    def test_valid_number_passed_in_param(self):
        bottle.request.environ = {'QUERY_STRING': ''}
        kwargs = {'limit': '4236'}
        utils._validate_range_values(bottle.request, 'limit', kwargs)
        self.assertEquals(4236, kwargs['limit'])
        self.assertEquals(200, bottle.response.status_code)

    def test_valid_number_passed_in_request(self):
        bottle.request.environ = {'QUERY_STRING': 'offset=2'}
        kwargs = {}
        utils._validate_range_values(bottle.request, 'offset', kwargs)
        self.assertEquals(2, kwargs['offset'])
        self.assertEquals(200, bottle.response.status_code)

    def test_pagination_headers_no_ranges_no_results(self):
        utils._write_pagination_headers({'results': {}}, 0, None,
                                        bottle.response, 'deployments', '')
        self.assertEquals(200, bottle.response.status_code)
        self.assertEquals(
            [
                ('Content-Range', 'deployments 0-0/0'),
                ('Content-Type', 'text/html; charset=UTF-8')
            ],
            bottle.response.headerlist
        )

    def test_pagination_headers_no_ranges_but_with_results(self):
        utils._write_pagination_headers(
            {
                'collection-count': 4,
                'results': {'1': {}, '2': {}, '3': {}, '4': {}}
            },
            0, None, bottle.response, 'deployments', ''
        )
        self.assertEquals(200, bottle.response.status_code)
        self.assertEquals(
            [
                ('Content-Range', 'deployments 0-3/4'),
                ('Content-Type', 'text/html; charset=UTF-8')
            ],
            bottle.response.headerlist
        )

    def test_pagination_headers_with_ranges_and_within_results(self):
        utils._write_pagination_headers(
            {
                'collection-count': 4,
                'results': {'2': {}, '3': {}}
            },
            1, 2, bottle.response, 'deployments', 'T3'
        )
        self.assertEquals(206, bottle.response.status_code)
        self.assertItemsEqual(
            [
                ('Link', '</T3/deployments?limit=2>; rel="first"; '
                         'title="First page"'),
                ('Link', '</T3/deployments?offset=2>; rel="last"; '
                         'title="Last page"'),
                ('Content-Range', 'deployments 1-2/4'),
                ('Content-Type', 'text/html; charset=UTF-8')
            ],
            bottle.response.headerlist
        )

    def test_generate_password(self):
        password = utils.evaluate('generate_password()')
        self.assertEqual(8, len(password))

    def test_generate_12_character_password(self):
        password = utils.evaluate('generate_password(min_length=12)')
        self.assertEqual(12, len(password))

    def test_escape_yaml_simple_string_simple(self):
        self.assertEqual(utils.escape_yaml_simple_string('simple'), "simple")

    def test_escape_yaml_simple_string_null(self):
        self.assertEqual(utils.escape_yaml_simple_string(None), 'null')

    def test_escape_yaml_simple_string_blank(self):
        self.assertEqual(utils.escape_yaml_simple_string(''), "''")

    def test_escape_yaml_simple_string_at(self):
        self.assertEqual(utils.escape_yaml_simple_string("@starts_with_at"),
                         "'@starts_with_at'")

    def test_escape_yaml_simple_string_multi_line(self):
        self.assertEqual(utils.escape_yaml_simple_string('A\nB'), 'A\nB')

    def test_escape_yaml_simple_string_object(self):
        self.assertEqual(utils.escape_yaml_simple_string({'A': 1}), {'A': 1})

    def test_get_ips_from_server_public_address_of_version_4(self):
        server = mock.Mock()
        server.addresses = {'public': [{'version': 4, 'addr': '1.1.2.2'}]}
        expected = {'ip': '1.1.2.2', 'public_ip': '1.1.2.2'}
        self.assertEqual(utils.get_ips_from_server(server, False), expected)

    def test_get_ips_from_server_with_different_address_type(self):
        server = mock.Mock()
        server.addresses = {'foobar': [{'version': 4, 'addr': '1.1.2.2'}]}
        server.accessIPv4 = None
        expected = {'ip': '1.1.2.2'}
        self.assertEqual(
            utils.get_ips_from_server(server,
                                      False,
                                      primary_address_type='foobar'),
            expected)

    def test_get_ips_from_server_public_ip_is_ipv4(self):
        server = mock.Mock()
        server.addresses = {'public': [{'version': 4, 'addr': '1.1.1.1'}]}
        server.accessIPv4 = None
        expected = {'ip': '1.1.1.1', 'public_ip': '1.1.1.1'}
        self.assertEqual(utils.get_ips_from_server(server, False), expected)

    def test_get_ips_from_server_private_ip_is_ipv4(self):
        server = mock.Mock()
        server.addresses = {'private': [{'version': 4, 'addr': '1.1.1.1'}]}
        server.accessIPv4 = None
        expected = {'ip': None, 'private_ip': '1.1.1.1'}
        self.assertEqual(utils.get_ips_from_server(server, False), expected)

    def test_get_ips_from_server_private_ip_is_not_ipv4(self):
        server = mock.Mock()
        server.addresses = {'private': [{'version': 6, 'addr': '1.1.1.1'}]}
        server.accessIPv4 = None
        expected = {'ip': None}
        self.assertEqual(utils.get_ips_from_server(server, False), expected)

    def test_hide_url_password(self):
        hidden = utils.hide_url_password('http://user:pass@localhost')
        self.assertEqual(hidden, 'http://user:*****@localhost')

    def test_hide_url_password_mongo(self):
        hidden = utils.hide_url_password('mongodb://user:pass@localhost/db')
        self.assertEqual(hidden, 'mongodb://user:*****@localhost/db')


class TestQueryParams(unittest.TestCase):

    def setUp(self):
        self.parser = utils.QueryParams.parse

    def test_whitelist_is_optional(self):
        query = self.parser({'foo': 'bar'})
        self.assertIn('foo', query)
        self.assertEqual(query['foo'], 'bar')

    def test_add_keys_as_whitelist_if_no_whitelist(self):
        query = self.parser({'foo': 'bar', 'asdf': 'qwer'})
        self.assertIn('whitelist', query)
        self.assertIn('foo',  query['whitelist'])
        self.assertIn('asdf', query['whitelist'])

    def test_add_whitelist_to_query(self):
        query = self.parser({}, 'fake whitelist')
        self.assertEqual(query['whitelist'], 'fake whitelist')

    def test_add_value_instead_of_array_with_one_element(self):
        query = self.parser({'foo': ['bar']})
        self.assertEqual(query['foo'], 'bar')

    def test_add_array_if_array_has_more_than_one_element(self):
        query = self.parser({'foo': ['bar', 'zoo']})
        self.assertEqual(query['foo'], ['bar', 'zoo'])

    def test_should_not_add_non_whitelisted_values(self):
        whitelist = ['bar']
        query = self.parser({'foo': 'zoo'}, whitelist)
        self.assertNotIn('foo', query)

    def test_should_not_add_empty_values_to_query(self):
        query = self.parser({'foo': '', 'bar': None})
        self.assertNotIn('foo', query)
        self.assertNotIn('bar', query)

    def test_should_indicate_if_rackconnect_account(self):
        self.assertTrue(utils.is_rackconnect_account({
            "roles": ['rack_connect', 'rax_managed']}
        ))
        self.assertFalse(utils.is_rackconnect_account({
            "roles": ['rax_managed']}
        ))

    def test_cap_limit(self):
        self.assertEquals(90, utils.cap_limit(90, None))
        self.assertEquals(100, utils.cap_limit(120, None))
        self.assertEquals(100, utils.cap_limit(-10, None))

    def test_filter_resources(self):
        resources = {"1": {"provider": "compute"}, "2": {}}
        filtered = utils.filter_resources(resources, "compute")
        self.assertEquals(1, len(filtered))
        self.assertDictEqual({"provider": "compute"}, filtered[0])


class TestFormatCheck(unittest.TestCase):
    def test_no_data(self):
        self.assertEqual({'resources': {}}, utils.format_check(None))

    def test_empty_data(self):
        self.assertEqual({'resources': {}}, utils.format_check({}))

    def test_desired_but_no_instance(self):
        expected = {'resources': {
            '0': [{
                'type': 'WARNING',
                'message': 'Resource 0 has desired-state but no instance.'
            }]
        }}
        data = {'0': {'desired-state': {'flavor': '3'}}}
        self.assertEqual(expected, utils.format_check(data))

    def test_all_output(self):
        expected = {'resources': {
            '0': [{
                'type': 'WARNING',
                'message': 'not-there does not exist in instance.'}
            ],
            '1': [
                {
                    'type': 'INFORMATION',
                    'message': 'region is valid.'
                },
                {
                    'type': 'WARNING',
                    'message': "flavor invalid: currently '3'. Should be '5'."
                }
            ]
        }}
        data = {
            '0': {
                'desired-state': {'not-there': '42'},
                'instance': {}
            },
            '1': {
                'desired-state': {'region': 'DFW', 'flavor': '5'},
                'region': 'DFW',
                'instance': {'flavor': '3'}
            }
        }
        self.assertEqual(expected, utils.format_check(data))


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
