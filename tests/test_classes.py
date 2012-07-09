#!/usr/bin/env python
import unittest2 as unittest

from checkmate.classes import ExtensibleDict


class TestExtensibleDict(unittest.TestCase):
    def test_init(self):
        """Check that init works like dict does"""
        data = {
                'key': 'value',
                1: 2,
            }
        ed = ExtensibleDict(data)
        self.assertDictEqual(ed._data, data)

    def test_json_serialization(self):
        data = {'key': 1}
        ed = ExtensibleDict(data)
        jsonized = ed.dumps()
        self.assertEqual(jsonized, '{"key": 1}')

    def test_basic_operations(self):
        ed = ExtensibleDict(key='value')
        self.assertIn('key', ed)
        self.assertEqual(ed['key'], 'value')

        ed['new'] = 2
        self.assertIn('new', ed)
        self.assertEqual(ed['new'], 2)
        self.assertEqual(len(ed), 2)

        del ed['new']
        self.assertNotIn('new', ed)

if __name__ == '__main__':
    unittest.main()
