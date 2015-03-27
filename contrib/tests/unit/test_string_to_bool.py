# Copyright (c) 2011-2015 Rackspace US, Inc.
# All Rights Reserved.
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import unittest

from contrib import bootstrap


class TestStringToBool(unittest.TestCase):

    def test_lower_true_string(self):
        val = 'true'
        out = bootstrap.string_to_bool(val)
        self.assertIsInstance(out, bool)
        self.assertEqual(True, out)

    def test_mixed_true_string(self):
        val = 'True'
        out = bootstrap.string_to_bool(val)
        self.assertIsInstance(out, bool)
        self.assertEqual(True, out)

    def test_lower_false_string(self):
        val = 'false'
        out = bootstrap.string_to_bool(val)
        self.assertIsInstance(out, bool)
        self.assertEqual(False, out)

    def test_mixed_false_string(self):
        val = 'False'
        out = bootstrap.string_to_bool(val)
        self.assertIsInstance(out, bool)
        self.assertEqual(False, out)

    def test_return_non_string(self):
        val = 1
        out = bootstrap.string_to_bool(val)
        self.assertNotIsInstance(out, bool)
        self.assertEqual(val, out)

    def test_raise_value_error(self):
        val = ''
        self.assertRaises(ValueError, bootstrap.string_to_bool, val)