#!/usr/bin/env python
import copy
import unittest2 as unittest

from checkmate import utils


class TestUtils(unittest.TestCase):
    """ Test Utils code """

    def setUp(self):
        pass

    def test_extract_sensitive_data_simple(self):
        """Test unary call and simple, one level of depth calls"""
        fxn = utils.extract_sensitive_data
        self.assertEquals(fxn({}), ({}, None))
        combined = {'innocuous': 'Hello!',
            'password': 'secret'}
        innocuous = {'innocuous': 'Hello!'}
        secret = {'password': 'secret'}
        original = copy.copy(combined)
        self.assertEquals(fxn(combined, sensitive_keys=[]), (combined, None))
        self.assertEquals(fxn(combined, ['password']), (innocuous, secret))
        self.assertDictEqual(combined, original)

    def test_extract_sensitive_data_complex(self):
        """Test hierarchy"""
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
                        {'password': 'secret', 'type': 'password'},
                        'scalar',
                        {'name': 'joe'}]
                }
            }
        innocuous = {
            'innocuous': {
                'names': ['Tom', 'Richard', 'Harry']
            },
            'data': {
                'id': 1000,
                'list_with_some_cred_objects': [
                        {'type': 'password'},
                        'scalar',
                        {'name': 'joe'}]
                }
            }
        secret = {
            'data': {
                'credentials': [{'password': 'secret', 'username': 'joe'}],
                'list_with_only_cred_objects': [{'password': 'secret'}],
                'list_with_some_cred_objects': [
                        {'password': 'secret'},
                        None,
                        {}]
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
        data = {'empty_list': [],
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
        c, s = fxn(data, [])
        self.assertDictEqual(data, c)
        merge = utils.merge_dictionary(data, data)
        self.assertDictEqual(data, merge)
        merge = utils.merge_dictionary(data, {})
        self.assertDictEqual(data, merge)
        merge = utils.merge_dictionary({}, data)
        self.assertDictEqual(data, merge)

    def test_merge_dictionary(self):
        dst = dict(a=1, b=2, c=dict(ca=31, cc=33, cd=dict(cca=1)), d=4, f=6,
                g=7)
        src = dict(b='u2', c=dict(cb='u32', cd=dict(cda=dict(cdaa='u3411',
                cdab='u3412'))), e='u5', h=dict(i='u4321'))
        r = utils.merge_dictionary(dst, src)
        assert r is dst
        assert r['a'] == 1 and r['d'] == 4 and r['f'] == 6
        assert r['b'] == 'u2' and r['e'] == 'u5'
        assert dst['c'] is r['c']
        assert dst['c']['cd'] is r['c']['cd']
        assert r['c']['cd']['cda']['cdaa'] == 'u3411'
        assert r['c']['cd']['cda']['cdab'] == 'u3412'
        assert r['g'] == 7
        assert src['h'] is r['h']

    def test_is_ssh_key(self):
        self.assertFalse(utils.is_ssh_key(None))
        self.assertFalse(utils.is_ssh_key(''))
        self.assertFalse(utils.is_ssh_key(1))
        self.assertFalse(utils.is_ssh_key("AAAAB3NzaC1yc2EA"))
        self.assertFalse(utils.is_ssh_key("AAAAB3NzaC1yc2EA-bad"))
        self.assertFalse(utils.is_ssh_key("AAAAB3NzaC1yc2EA onespace"))
        self.assertFalse(utils.is_ssh_key("AAAAB3NzaC1yc2EA two space"))
        self.assertFalse(utils.is_ssh_key("AAAAB3NzaC1yc2EA 3 spaces here"))
        key = """ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDtjYYMFbpCJ/ND3izZ1DqNFQHlooXyNcDGWilAqNqcCfz9L+gpGjY2pQlZz/1Hir3R8fz0MS9VY32RYmP3wWygt85kNccEkOpVGGpGyV/aMFaQHZD0h6d0AT+haP0Iig+OrH1YBnpdgVPWx3SbU4eV/KYGpO9Mintj3P54of22lTK4dOwCNvID9P9w+T1kMfdVxGwhqsSL0RxVXnSSkozXQWCNvaZJMUmidm8YA009c5PoksyWjl3EE+rEzZ8ywvtUJf9DvnLCESfhF3hK5lAiEd8z7gyiQnBexn/dXzldGFiJYJgQ5HolYaNMtTF+AQY6R6Qt0okCPyEDJxHJUM7d"""
        self.assertTrue(utils.is_ssh_key(key))
        self.assertTrue(utils.is_ssh_key("%s /n" % key))
        self.assertTrue(utils.is_ssh_key("%s email@domain.com/n" % key))
        key = """ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEA7TT1qbLElv6tuAaA3Z4tQ752ms0Y7H53yybfFioFHELkp+NRMCKh4AqtqDBFsps1vPzhcXIxn4M4IH0ip7kSx0CSrM/9Vtz8jc+UZwixJdAWwHpum68rGmCQgAsZljI24Q9u8r/hXqjwY6ukTKbC0iy82LHqhcDjh3828+9GyyxbYGm5ND/5G/ZcnHD6HM9YKmc3voz5d/nez3Adlu4I1z4Y1T3lOwOxrP2OqvIeDPvVOZJ9GDmYYRDfqK8OIHDoLAzQx8xu0cvPRDL7gYRXN8nJZ5nOh+51zdPQEl99ACZDSSwTl2biOPNtXtuaGyjB5j8r7dz93JlsN8axeD+ECQ== ziad@sawalha.com"""
        self.assertTrue(utils.is_ssh_key(key))

    def test_get_source_body(self):
        source = utils.get_source_body(self.test_get_source_body)
        self.assertTrue(source.startswith("source = utils"))


if __name__ == '__main__':
    unittest.main(verbosity=2)
