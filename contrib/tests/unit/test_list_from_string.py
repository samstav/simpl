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

import unittest

from contrib import bootstrap


class TestListFromString(unittest.TestCase):

    def test_single_value(self):
        val = 'test_value'
        self.assertEqual(val, bootstrap.list_from_string(val))

    def test_newlines(self):
        val = '1\n2\n3'
        wanted = ['1', '2', '3']
        self.assertNotEqual(val, bootstrap.list_from_string(val))
        self.assertEqual(wanted, bootstrap.list_from_string(val))

    def test_spaces(self):
        val = '1 2 3'
        wanted = ['1', '2', '3']
        self.assertNotEqual(val, bootstrap.list_from_string(val))
        self.assertEqual(wanted, bootstrap.list_from_string(val))

    def test_tabs(self):
        val = '1\t2\t3'
        wanted = ['1', '2', '3']
        self.assertNotEqual(val, bootstrap.list_from_string(val))
        self.assertEqual(wanted, bootstrap.list_from_string(val))
