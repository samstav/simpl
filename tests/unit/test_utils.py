# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''

import copy
import re
import time
import unittest2 as unittest
import uuid
import mox

from checkmate import utils


class TestUtils(unittest.TestCase):

    def setUp(self):
        pass

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

    def test_flatten(self):
        list_of_dict = [{'foo': 'bar'}, {'a': 'b'}, {'foo': 'bar1'}]
        self.assertDictEqual(utils.flatten(list_of_dict),
                             {'foo': 'bar1', 'a': 'b'})

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
        c, s = fxn(combined, [])
        self.assertDictEqual(c, combined)
        self.assertIsNone(s)

        c, s = fxn(combined, ['credentials', 'password'])
        self.assertDictEqual(c, innocuous)
        self.assertDictEqual(s, secret)
        self.assertDictEqual(combined, original)

        merged = utils.merge_dictionary(innocuous, secret)
        self.assertDictEqual(original, merged)

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
        c, _ = fxn(data, [])
        self.assertDictEqual(data, c)
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
        r = utils.merge_dictionary(dst, src)
        self.assertIsInstance(r, dict)
        self.assertEquals(r['a'], 1)
        self.assertEquals(r['d'], 4)
        self.assertEquals(r['f'], 6)
        self.assertEquals(r['b'], 'u2')
        self.assertEquals(r['e'], 'u5')
        self.assertIs(r['c'], dst['c'])
        self.assertIs(r['c']['cd'], dst['c']['cd'])
        self.assertEquals(r['c']['cd']['cda']['cdaa'], 'u3411')
        self.assertEquals(r['c']['cd']['cda']['cdab'], 'u3412')
        self.assertEquals(r['g'], 7)
        self.assertIs(src['h'], r['h'])
        self.assertEquals(r['i'], [1])
        self.assertEquals(r['j'], [1, 2])
        self.assertEquals(r['k'], [3, 4])
        self.assertEquals(r['l'], [[], [{'s': 1, 't': 8}]])

    def test_merge_lists(self):
        dst = [[], [2], [None, 4]]
        src = [[1], [], [3, None]]
        r = utils.merge_lists(dst, src)
        self.assertIsInstance(r, list)
        self.assertEquals(r[0], [1])
        self.assertEquals(r[1], [2])
        self.assertEquals(r[2], [3, 4], "Found: %s" % r[2])

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
        self.assertTrue(source.startswith("'''used for get_source_body"))

    @staticmethod
    def dummy_static():
        '''used for get_source_body test'''
        pass

    def test_isUUID_blanks(self):
        self.assertFalse(utils.isUUID(None), "None is not a UUID")
        self.assertFalse(utils.isUUID(""), "Empty string is not a UUID")
        self.assertFalse(utils.isUUID(" "), "Space is not a UUID")

    def test_isUUID_negatives(self):
        self.assertFalse(utils.isUUID("12345"), "12345 is not a UUID")
        self.assertFalse(utils.isUUID(utils), "module is not a UUID")

    def test_isUUID_positives(self):
        self.assertTrue(utils.isUUID(uuid.uuid4()), "uuid() is a UUID")
        self.assertTrue(utils.isUUID(uuid.uuid4().hex),
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

    def test_is_evaluable(self):
        self.assertTrue(utils.is_evaluable('=generate_password()'))
        self.assertTrue(utils.is_evaluable('=generate_uuid()'))
        self.assertFalse(utils.is_evaluable('=generate_something_else()'))
        self.assertFalse(utils.is_evaluable({'not-a-string': 'boom!'}))

    def test_get_formatted_time_string(self):
        mock = mox.Mox()
        mock_time = time.gmtime(0)
        mock.StubOutWithMock(utils, 'gmtime')
        utils.gmtime().AndReturn(mock_time)
        mock.ReplayAll()
        result = utils.get_time_string()
        mock.VerifyAll()
        mock.UnsetStubs()
        self.assertEquals(result, "1970-01-01 00:00:00 +0000")

    def test_get_formatted_time_string_with_input(self):
        result = utils.get_time_string(time.gmtime(0))
        self.assertEquals(result, "1970-01-01 00:00:00 +0000")


if __name__ == '__main__':
    # Any change here should be made in all test files
    import sys
    from checkmate.test import run_with_params
    run_with_params(sys.argv[:])
