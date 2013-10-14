# pylint: disable=R0904,C0103
#
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

"""Tests for Blueprint Functions."""
import unittest

from checkmate import functions


class TestScalarFunctions(unittest.TestCase):
    """Test core blueprint function."""

    def test_scalar_None(self):
        self.assertIsNone(functions.evaluate(None))

    def test_scalar_integer(self):
        self.assertEqual(functions.evaluate(1), 1)

    def test_scalar_string(self):
        self.assertEqual(functions.evaluate("A"), "A")

    def test_scalar_boolean(self):
        self.assertIs(functions.evaluate(True), True)
        self.assertIs(functions.evaluate(False), False)

    def test_empty_list(self):
        self.assertEqual(functions.evaluate([]), [])

    def test_scalar_list(self):
        self.assertEqual(functions.evaluate(['1', 2]), ['1', 2])

    def test_if_true(self):
        data = {
            'if': True
        }
        self.assertTrue(functions.evaluate(data))

    def test_if_false(self):
        data = {
            'if': True
        }
        self.assertTrue(functions.evaluate(data))

    def test_if_not_false(self):
        data = {
            'if-not': True
        }
        self.assertFalse(functions.evaluate(data))

    def test_if_not_true(self):
        data = {
            'if-not': True
        }
        self.assertFalse(functions.evaluate(data))

    def test_or(self):
        data = {
            'or': [True, False]
        }
        self.assertTrue(functions.evaluate(data))

    def test_or_false(self):
        data = {
            'or': [False, False]
        }
        self.assertFalse(functions.evaluate(data))

    def test_and(self):
        data = {
            'and': [True, True]
        }
        self.assertTrue(functions.evaluate(data))

    def test_and_false(self):
        data = {
            'and': [False, True]
        }
        self.assertFalse(functions.evaluate(data))

    def test_complex(self):
        data = {
            'if': {
                'and': [
                    True,
                    {'or': [False, True]},
                ]
            }
        }
        self.assertTrue(functions.evaluate(data))


class TestObjectFunctions(unittest.TestCase):
    """Test core blueprint functions for complex datatypes."""

    def setUp(self):
        self.data = {
            'name': 'Sample Data',
            'blueprint': {
                'options': {
                    'opt1int': {
                        'type': 'integer'
                    },
                    'opt2string': {
                        'type': 'string'
                    },
                },
                'services': {
                    'S1': {
                        'component': {'id': 'S1comp'}
                    },
                    'S2': {
                        'component': {'id': 'S2comp'}
                    },
                }},
            'resources': {
                '0': {
                    'service': 'S1',
                    'instance': {'id': 'S1id'},
                },
                '1': {
                    'service': 'S2',
                    'instance': {'id': 'S2id'},
                },
            },
            'inputs': {
                'region': 'North',
                'blueprint': {
                    'size': 'big'
                }
            },
        }

    def test_value_none(self):
        self.assertIsNone(functions.evaluate({'value': None}))

    def test_value_integer(self):
        self.assertEqual(functions.evaluate({'value': 1}), 1)

    def test_value_name(self):
        self.assertEqual(functions.evaluate({'value': 'name://'}, **self.data),
                         'Sample Data')

    def test_value_deep(self):
        function = {'value': 'resources://0/instance/id'}
        self.assertEqual(functions.evaluate(function, **self.data),
                         'S1id')

    def test_resources(self):
        function = {'value': 'resources://1'}
        self.assertEqual(functions.evaluate(function, **self.data),
                         {'service': 'S2', 'instance': {'id': 'S2id'}})

    def test_inputs_scalar(self):
        function = {'value': 'inputs://region'}
        self.assertEqual(functions.evaluate(function, **self.data), "North")

    def test_inputs_scalar_negative(self):
        """Blueprint input does not pick up global input."""
        function = {'value': 'inputs://size'}
        self.assertIsNone(functions.evaluate(function, **self.data))

    def test_inputs_blueprint(self):
        function = {'value': 'inputs://region'}
        self.assertEqual(functions.evaluate(function, **self.data), "North")

    def test_inputs_blueprint_negative(self):
        """Global input does not pick up blueprint input."""
        function = {'value': 'inputs://size'}
        self.assertIsNone(functions.evaluate(function, **self.data))

    def test_exists(self):
        function = {'exists': 'inputs://region'}
        self.assertTrue(functions.evaluate(function, **self.data))

    def test_exists_negative(self):
        function = {'exists': 'inputs://nope'}
        self.assertFalse(functions.evaluate(function, **self.data))

    def test_not_exists(self):
        function = {'not-exists': 'inputs://region'}
        self.assertFalse(functions.evaluate(function, **self.data))

    def test_not_exists_negative(self):
        function = {'not-exists': 'inputs://nope'}
        self.assertTrue(functions.evaluate(function, **self.data))


class TestSafety(unittest.TestCase):
    """Test core blueprint functions for safety."""

    def test_self_referencing(self):
        data = {
            'object': 1
        }
        data['object'] = data
        function = {'value': 'object://object'}
        self.assertEqual(functions.evaluate(function, **data), data)


class TestPathing(unittest.TestCase):
    """Test URL evaluation."""

    def setUp(self):
        self.data = {
            'name': 'Sample Data',
            'root': {'base': 'item'},
            'deep': {'A': {'B': {'C': 'top'}}},
        }

    def test_path_None(self):
        self.assertIsNone(functions.get_from_path(None))

    def test_path_blank(self):
        self.assertEqual(functions.get_from_path(''), '')

    def test_path_scheme_only_scalar(self):
        result = functions.get_from_path('name://', **self.data)
        expected = 'Sample Data'
        self.assertEqual(result, expected)

    def test_path_root(self):
        result = functions.get_from_path('root://', **self.data)
        expected = {'base': 'item'}
        self.assertEqual(result, expected)

    def test_path_scalar(self):
        result = functions.get_from_path('root://base', **self.data)
        expected = 'item'
        self.assertEqual(result, expected)

    def test_path_deep(self):
        result = functions.get_from_path('deep://A/B/C', **self.data)
        expected = 'top'
        self.assertEqual(result, expected)


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
