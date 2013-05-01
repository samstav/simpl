# pylint: disable=C0103,C0111,R0903,R0904,W0212,W0232
'''
For tests, we don't care about:
    C0103 - Invalid name (method names too long)
    C0111 - Missing docstring
    R0903 - Too few public methods
    R0904 - Too many public methods
    W0212 - Access to protected member of a client class
    W0232 - Class has no __init__ method '''

import unittest2 as unittest

from checkmate import constraints
from checkmate.constraints import Constraint
from checkmate.exceptions import CheckmateValidationException
from checkmate import utils


class TestConstraint(unittest.TestCase):
    def test_init_method(self):
        self.assertIsInstance(Constraint({}), Constraint)

    def test_init_wrong_type(self):
        self.assertRaises(CheckmateValidationException, Constraint, 1)

    def test_is_syntax_valid(self):
        self.assertTrue(Constraint.is_syntax_valid({}))

    def test_is_syntax_valid_negative(self):
        self.assertFalse(Constraint.is_syntax_valid({'A': 1}))

    def test_is_syntax_valid_wrong_type(self):
        self.assertFalse(Constraint.is_syntax_valid(1))


class TestRegexConstraint(unittest.TestCase):

    klass = constraints.RegExConstraint
    test_data = utils.yaml_to_dict("""
        - regex: ^(?=.*).{2,5}$
          message: between 2 and 5 characters
        """)

    def test_constraint_syntax_check(self):
        self.assertTrue(self.klass.is_syntax_valid({'regex': ''}))
        self.assertTrue(self.klass.is_syntax_valid({'regex': '',
                                                    'message': ''}))

    def test_constraint_syntax_check_negative(self):
        self.assertRaises(CheckmateValidationException, self.klass,
                          {'regex': '['})

    def test_constraint_detection(self):
        constraint = Constraint.from_constraint(self.test_data[0])
        self.assertIsInstance(constraint, self.klass)

    def test_constraint_tests(self):
        constraint = Constraint.from_constraint(self.test_data[0])
        self.assertFalse(constraint.test("1"))
        self.assertTrue(constraint.test("12"))
        self.assertFalse(constraint.test("123456"))

    def test_constraint_message(self):
        constraint = Constraint.from_constraint(self.test_data[0])
        self.assertEquals(constraint.message, "between 2 and 5 characters")


class TestProtocolConstraint(unittest.TestCase):

    klass = constraints.ProtocolsConstraint
    test_data = utils.yaml_to_dict("""
        - protocols: [http, https]
          message: Nope. Only http(s)
        """)

    def test_constraint_syntax_check(self):
        self.assertTrue(self.klass.is_syntax_valid({'protocols': ''}))
        self.assertTrue(self.klass.is_syntax_valid({'protocols': '',
                                                    'message': ''}))

    def test_constraint_syntax_check_negative(self):
        self.assertRaises(CheckmateValidationException, self.klass,
                          {'protocols': 'http'})

    def test_constraint_detection(self):
        constraint = Constraint.from_constraint(self.test_data[0])
        self.assertIsInstance(constraint, self.klass)

    def test_constraint_tests(self):
        constraint = Constraint.from_constraint(self.test_data[0])
        self.assertFalse(constraint.test("git://github.com"))
        self.assertTrue(constraint.test("http://me.com"))

    def test_constraint_message(self):
        constraint = Constraint.from_constraint(self.test_data[0])
        self.assertEquals(constraint.message, "Nope. Only http(s)")


class TestSimpleComparisonConstraint(unittest.TestCase):

    klass = constraints.SimpleComparisonConstraint
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
        for test in self.test_data:
            constraint = Constraint.from_constraint(test)
            self.assertIsInstance(constraint, self.klass, msg=test)

    def test_constraint_tests_less_than(self):
        constraint = Constraint.from_constraint(self.test_data[0])
        self.assertFalse(constraint.test(9))
        self.assertFalse(constraint.test(8))
        self.assertTrue(constraint.test(7))
        self.assertEquals(constraint.message, "must be less than 8")

    def test_constraint_tests_greater_than(self):
        constraint = Constraint.from_constraint(self.test_data[1])
        self.assertFalse(constraint.test(1))
        self.assertFalse(constraint.test(2))
        self.assertTrue(constraint.test(3))
        self.assertEquals(constraint.message, "must be greater than 2")

    def test_constraint_tests_less_than_or_equal_to(self):
        constraint = Constraint.from_constraint(self.test_data[2])
        self.assertFalse(constraint.test(10))
        self.assertTrue(constraint.test(9))
        self.assertTrue(constraint.test(8))
        self.assertEquals(constraint.message, "must be less than or equal to "
                                              "9")

    def test_constraint_tests_greater_than_or_equal_to(self):
        constraint = Constraint.from_constraint(self.test_data[3])
        self.assertFalse(constraint.test(0))
        self.assertTrue(constraint.test(1))
        self.assertTrue(constraint.test(2))
        self.assertEquals(constraint.message, "must be greater than or equal "
                                              "to 1")

    def test_constraint_message(self):
        constraint = Constraint.from_constraint(self.test_data[4])
        self.assertEquals(constraint.message, "Nope! Less than 18")

    def test_constraint_combined_keys(self):
        constraint = Constraint.from_constraint(self.test_data[5])
        self.assertFalse(constraint.test(98))
        self.assertFalse(constraint.test(101))
        self.assertTrue(constraint.test(99))
        self.assertEquals(constraint.message, "must be less than 100, must be "
                                              "greater than 98")


class TestInConstraint(unittest.TestCase):

    klass = constraints.InConstraint
    test_data = utils.yaml_to_dict("""
        - in: [http, https]
          message: Nope. Only http(s)
        """)

    def test_constraint_syntax_check(self):
        self.assertTrue(self.klass.is_syntax_valid({'in': []}))
        self.assertTrue(self.klass.is_syntax_valid({'in': [],
                                                    'message': ''}))

    def test_constraint_syntax_check_negative(self):
        self.assertRaises(CheckmateValidationException, self.klass,
                          {'in': 'http'})

    def test_constraint_detection(self):
        constraint = Constraint.from_constraint(self.test_data[0])
        self.assertIsInstance(constraint, self.klass)

    def test_constraint_tests(self):
        constraint = Constraint.from_constraint(self.test_data[0])
        self.assertFalse(constraint.test("git"))
        self.assertTrue(constraint.test("http"))

    def test_constraint_message(self):
        constraint = Constraint.from_constraint(self.test_data[0])
        self.assertEquals(constraint.message, "Nope. Only http(s)")


if __name__ == '__main__':
    # Any change here should be made in all test files
    import os, sys
    sys.path.insert(1, os.path.join(sys.path[0], '../..'))
    from tests.utils import run_with_params
    run_with_params(sys.argv[:])
