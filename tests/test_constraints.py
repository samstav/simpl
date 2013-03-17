#!/usr/bin/env python
import logging
import unittest2 as unittest

# Init logging before we load the database, 3rd party, and 'noisy' modules
from checkmate.utils import init_console_logging
init_console_logging()
LOG = logging.getLogger(__name__)

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
        self.assertTrue(self.klass.is_syntax_valid({'regex': '', 'message': ''}))

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


if __name__ == '__main__':
    # Run tests. Handle our paramaters separately
    import sys
    args = sys.argv[:]
    # Our --debug means --verbose for unitest
    if '--debug' in args:
        args.pop(args.index('--debug'))
        if '--verbose' not in args:
            args.insert(1, '--verbose')
    unittest.main(argv=args)
