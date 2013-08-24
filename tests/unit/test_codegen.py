# pylint: disable=C0103

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

"""Tests for Codegen."""
import unittest

from checkmate.common import codegen


class TestCodegen(unittest.TestCase):
    def test_build_kwargs_from_empty_string(self):
        func_name, kwargs = codegen.kwargs_from_string('')
        self.assertIsNone(func_name)
        self.assertEqual({}, kwargs)

    def test_attempt_kwargs_build_with_too_many_function_definitions(self):
        self.assertRaises(SyntaxError, codegen.kwargs_from_string,
                          'my_func(blah=2)\nmy_other_func()')

    def test_attempt_kwargs_build_with_nested_functions(self):
        self.assertRaises(ValueError, codegen.kwargs_from_string,
                          'my_func(my_other_func())')

    def test_build_kwargs_from_string_with_one_integer_value(self):
        func_name, kwargs = codegen.kwargs_from_string('my_func(blah=2)')
        self.assertEqual('my_func', func_name)
        self.assertEqual({'blah': 2}, kwargs)

    def test_build_kwargs_from_string_with_one_string_value(self):
        func_name, kwargs = codegen.kwargs_from_string("my_func(blah='blarg')")
        self.assertEqual('my_func', func_name)
        self.assertEqual({'blah': 'blarg'}, kwargs)

    def test_build_kwargs_from_string_with_one_array(self):
        func_name, kwargs = codegen.kwargs_from_string(
            "my_func(blah=[1, '2', None])")
        self.assertEqual('my_func', func_name)
        self.assertEqual({'blah': [1, '2', None]}, kwargs)

    def test_build_kwargs_from_string_with_multiple_params(self):
        func_name, kwargs = codegen.kwargs_from_string(
            "my_func(blerg=8, blah=[1, '2', None], bleep='')")
        self.assertEqual('my_func', func_name)
        self.assertEqual(
            {'blerg': 8, 'blah': [1, '2', None], 'bleep': ''}, kwargs)


if __name__ == '__main__':
    import sys

    from checkmate import test as cmtest

    cmtest.run_with_params(sys.argv[:])
