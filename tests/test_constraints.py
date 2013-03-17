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
