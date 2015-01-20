# pylint: disable=C0103,R0904

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

"""Tests for constraints."""
import unittest

from checkmate import constraints as cmcon
from checkmate import exceptions as cmexc
from checkmate import utils


class TestConstraint(unittest.TestCase):
    def test_init_method(self):
        self.assertIsInstance(cmcon.Constraint({}), cmcon.Constraint)

    def test_init_wrong_type(self):
        self.assertRaises(
            cmexc.CheckmateValidationException, cmcon.Constraint, 1)

    def test_is_syntax_valid(self):
        self.assertTrue(cmcon.Constraint.is_syntax_valid({}))

    def test_is_syntax_valid_negative(self):
        self.assertFalse(cmcon.Constraint.is_syntax_valid({'A': 1}))

    def test_is_syntax_valid_wrong_type(self):
        self.assertFalse(cmcon.Constraint.is_syntax_valid(1))


class TestRegexConstraint(unittest.TestCase):

    klass = cmcon.RegExConstraint
    test_data = utils.yaml_to_dict("""
        - regex: ^(?=.*).{2,5}$
          message: between 2 and 5 characters
        """)

    def test_constraint_syntax_check(self):
        self.assertTrue(self.klass.is_syntax_valid({'regex': ''}))
        self.assertTrue(self.klass.is_syntax_valid({'regex': '',
                                                    'message': ''}))

    def test_constraint_syntax_check_negative(self):
        self.assertRaises(cmexc.CheckmateValidationException, self.klass,
                          {'regex': '['})

    def test_constraint_detection(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertIsInstance(constraint, self.klass)

    def test_constraint_tests(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertFalse(constraint.test("1"))
        self.assertTrue(constraint.test("12"))
        self.assertFalse(constraint.test("123456"))

    def test_constraint_message(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertEqual(constraint.message, "between 2 and 5 characters")


class TestProtocolConstraint(unittest.TestCase):

    klass = cmcon.ProtocolsConstraint
    test_data = utils.yaml_to_dict("""
        - protocols: [http, https]
          message: Nope. Only http(s)
        """)

    def test_constraint_syntax_check(self):
        self.assertTrue(self.klass.is_syntax_valid({'protocols': ''}))
        self.assertTrue(self.klass.is_syntax_valid({'protocols': '',
                                                    'message': ''}))

    def test_constraint_syntax_check_negative(self):
        self.assertRaises(cmexc.CheckmateValidationException, self.klass,
                          {'protocols': 'http'})

    def test_constraint_detection(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertIsInstance(constraint, self.klass)

    def test_constraint_tests(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertFalse(constraint.test("git://github.com"))
        self.assertTrue(constraint.test("http://me.com"))

    def test_constraint_message(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertEqual(constraint.message, "Nope. Only http(s)")


class TestSimpleComparisonConstraint(unittest.TestCase):

    klass = cmcon.SimpleComparisonConstraint
    test_data = utils.yaml_to_dict("""
            - less-than: 8
            - greater-than: 2
            - less-than-or-equal-to: 9
            - greater-than-or-equal-to: 1
            - less-than: 18
              message: Nope! Less than 18
            - less-than: 100
              greater-than: 98
        """)

    def test_constraint_syntax_check(self):
        self.assertTrue(self.klass.is_syntax_valid({'less-than': ''}))
        self.assertTrue(self.klass.is_syntax_valid({'greater-than': ''}))
        self.assertTrue(self.klass.is_syntax_valid({'less-than-or-equal-to':
                                                    ''}))
        self.assertTrue(self.klass.is_syntax_valid({'greater-than-or-equal-to':
                                                    ''}))

    def test_constraint_with_message(self):
        self.assertTrue(self.klass.is_syntax_valid({'greater-than': '',
                                                    'message': ''}))

    def test_constraint_with_multiples(self):
        self.assertTrue(self.klass.is_syntax_valid({'less-than': '',
                                                    'greater-than': ''}))

    def test_constraint_detection(self):
        for entry in self.test_data:
            constraint = cmcon.Constraint.from_constraint(entry)
            self.assertIsInstance(constraint, self.klass, msg=entry)

    def test_constraint_tests_less_than(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertFalse(constraint.test(9))
        self.assertFalse(constraint.test(8))
        self.assertTrue(constraint.test(7))
        self.assertEqual(constraint.message, "must be less than 8")

    def test_constraint_tests_greater_than(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[1])
        self.assertFalse(constraint.test(1))
        self.assertFalse(constraint.test(2))
        self.assertTrue(constraint.test(3))
        self.assertEqual(constraint.message, "must be greater than 2")

    def test_constraint_tests_less_than_or_equal_to(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[2])
        self.assertFalse(constraint.test(10))
        self.assertTrue(constraint.test(9))
        self.assertTrue(constraint.test(8))
        self.assertEqual(constraint.message, "must be less than or equal to "
                                              "9")

    def test_constraint_tests_greater_than_or_equal_to(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[3])
        self.assertFalse(constraint.test(0))
        self.assertTrue(constraint.test(1))
        self.assertTrue(constraint.test(2))
        self.assertEqual(constraint.message, "must be greater than or equal "
                                              "to 1")

    def test_constraint_message(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[4])
        self.assertEqual(constraint.message, "Nope! Less than 18")

    def test_constraint_combined_keys(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[5])
        self.assertFalse(constraint.test(98))
        self.assertFalse(constraint.test(101))
        self.assertTrue(constraint.test(99))
        self.assertEqual(constraint.message, "must be less than 100, must be "
                                              "greater than 98")


class TestInConstraint(unittest.TestCase):

    klass = cmcon.InConstraint
    test_data = utils.yaml_to_dict("""
        - in: [http, https]
          message: Nope. Only http(s)
        """)

    def test_constraint_syntax_check(self):
        self.assertTrue(self.klass.is_syntax_valid({'in': []}))
        self.assertTrue(self.klass.is_syntax_valid({'in': [],
                                                    'message': ''}))

    def test_constraint_syntax_check_negative(self):
        self.assertRaises(cmexc.CheckmateValidationException, self.klass,
                          {'in': 'http'})

    def test_constraint_detection(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertIsInstance(constraint, self.klass)

    def test_constraint_tests(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertFalse(constraint.test("git"))
        self.assertTrue(constraint.test("http"))

    def test_constraint_message(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertEqual(constraint.message, "Nope. Only http(s)")


class TestStaticConstraint(unittest.TestCase):

    klass = cmcon.StaticConstraint
    test_data = utils.yaml_to_dict("""
        - check: false
          message: 'No'
        """)

    def test_constraint_syntax_check(self):
        self.assertTrue(self.klass.is_syntax_valid({'check': False}))
        self.assertTrue(self.klass.is_syntax_valid({'check': True,
                                                    'message': ''}))

    def test_constraint_detection(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertIsInstance(constraint, self.klass)

    def test_constraint_tests(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertFalse(constraint.test(False))
        self.assertFalse(constraint.test(True))  # value is ignored

    def test_constraint_message(self):
        constraint = cmcon.Constraint.from_constraint(self.test_data[0])
        self.assertEqual(constraint.message, "No")


if __name__ == '__main__':
    from checkmate import test
    test.run_with_params()
