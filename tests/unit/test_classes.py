# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
import unittest2 as unittest

from checkmate.classes import ExtensibleDict


class TestExtensibleDict(unittest.TestCase):
    def test_init(self):
        """Check that init works like dict does"""
        data = {'key': 'value', 1: 2}
        ed = ExtensibleDict(data)
        self.assertDictEqual(ed._data, data)

    def test_json_serialization(self):
        data = {'key': 1}
        ed = ExtensibleDict(data)
        jsonized = ed.dumps()
        self.assertEqual(jsonized, '{"key": 1}')

    def test_basic_operations(self):
        """Test basic dictionary-type operations"""
        ed = ExtensibleDict(key='value')
        self.assertIn('key', ed)
        self.assertEqual(ed['key'], 'value')

        ed['new'] = 2
        self.assertIn('new', ed)
        self.assertEqual(ed['new'], 2)
        self.assertEqual(len(ed), 2)

        del ed['new']
        self.assertNotIn('new', ed)

    def test_empty_args(self):
        ed = ExtensibleDict(key='value')
        self.assertDictEqual(ed.__dict__(), dict(key='value'))

    def test_empty_kwargs(self):
        template = dict(key='value')
        ed = ExtensibleDict(template)
        self.assertDictEqual(ed.__dict__(), template)

    def test_empty_args_and_kwargs(self):
        ed = ExtensibleDict()
        self.assertDictEqual(ed.__dict__(), {})


if __name__ == '__main__':
    # Any change here should be made in all test files
    import os
    import sys
    sys.path.insert(1, os.path.join(sys.path[0], '../..'))
    from tests.utils import run_with_params
    run_with_params(sys.argv[:])
