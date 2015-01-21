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

"""Tests for ExtensibleDict class."""
import unittest

from checkmate import classes


class TestExtensibleDict(unittest.TestCase):
    def test_init(self):
        """Check that init works like dict does."""
        data = {'key': 'value', 1: 2}
        edict = classes.ExtensibleDict(data)
        self.assertDictEqual(edict._data, data)

    def test_json_serialization(self):
        data = {'key': 1}
        edict = classes.ExtensibleDict(data)
        jsonized = edict.dumps()
        self.assertEqual(jsonized, '{"key": 1}')

    def test_basic_operations(self):
        """Test basic dictionary-type operations."""
        edict = classes.ExtensibleDict(key='value')
        self.assertIn('key', edict)
        self.assertEqual(edict['key'], 'value')

        edict['new'] = 2
        self.assertIn('new', edict)
        self.assertEqual(edict['new'], 2)
        self.assertEqual(len(edict), 2)

        del edict['new']
        self.assertNotIn('new', edict)

    def test_empty_args(self):
        edict = classes.ExtensibleDict(key='value')
        self.assertDictEqual(edict.__dict__(), dict(key='value'))

    def test_empty_kwargs(self):
        template = dict(key='value')
        edict = classes.ExtensibleDict(template)
        self.assertDictEqual(edict.__dict__(), template)

    def test_empty_args_and_kwargs(self):
        edict = classes.ExtensibleDict()
        self.assertDictEqual(edict.__dict__(), {})


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
