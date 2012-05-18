#!/usr/bin/env python
import copy
import json
import os
import unittest2 as unittest
from checkmate import utils


class TestUtils(unittest.TestCase):
    """ Test Utils code """

    def setUp(self):
        pass

    def test_get_template_name_from_path(self):
        fxn = utils.get_template_name_from_path
        self.assertEqual(fxn(None), 'default')
        self.assertEqual(fxn(''), 'default')
        self.assertEqual(fxn('/'), 'default')

        expected = {'/workflows': 'workflows',
                    '/deployments': 'deployments',
                    '/blueprints': 'blueprints',
                    '/components': 'components',
                    '/environments': 'environments',
                    '/workflows/1': 'workflow',
                    '/workflows/1/tasks': 'workflow.tasks',
                    '/workflows/1/tasks/1': 'workflow.task',
                    '/workflows/1/status': 'workflow.status'
                }
        for path, template in expected.iteritems():
            self.assertEqual(fxn(path), template, '%s should have returned %s'
                    % (path, template))
        # Check with tenant_id
        for path, template in expected.iteritems():
            self.assertEqual(fxn('/T1000%s' % path), template, '%s should have returned %s'
                    % (path, template))

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

if __name__ == '__main__':
    unittest.main(verbosity=2)
