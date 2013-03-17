"""

Constraint Validation Classes

To add a new constraint type, add:

1. Create a class that inherits from Constraint
2. Override the allowed_keys and required_keys
3. override at a minimum the 'test' method

"""
import inspect
import logging
import re
import sys

from checkmate import utils
from checkmate.exceptions import CheckmateValidationException


LOG = logging.getLogger(__name__)


class Constraint(object):
    """

    Base Class for all Constraints

    """

    required_keys = []
    allowed_keys = []
    message = "not explained"

    @classmethod
    def is_syntax_valid(cls, constraint):
        if not isinstance(constraint, dict):
            return False
        if not all(k in cls.allowed_keys for k in constraint.keys()):
            return False
        if not all(k in constraint.keys() for k in cls.required_keys):
            return False
        return True

    @classmethod
    def from_constraint(cls, constraint):
        """Instantiate correct constraint class based on constraint"""
        for klass in CONSTRAINT_CLASSES:
            if klass.is_syntax_valid(constraint):
                return klass(constraint)
        raise CheckmateValidationException("Constraint '%s' is not a "
                                           "valid constraint" % constraint)

    def __init__(self, constraint):
        if not self.is_syntax_valid(constraint):
            raise CheckmateValidationException("Constraint '%s' is not a "
                                               "valid constraint" % constraint)
        self.constraint = constraint

    def test(self, value):
        return False


CONSTRAINT_CLASSES = [k for n, k in inspect.getmembers(sys.modules[__name__],
                                                       inspect.isclass)
                      if issubclass(k, Constraint)]
