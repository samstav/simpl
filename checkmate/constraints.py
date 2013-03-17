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


class RegExConstraint(Constraint):
    """

    RegEx Constraint

    Syntax:

    - regex: {regular expression}
    - message: optional validation message

    Notes:

    - forward and backward lookups in the regexes are not supported on browsers
    - use a clear message for users but also for other who read your blueprint

    Example:

     constraints:
     - regex: ^(?=.*).{8,15}$
       message: must be between 8 and 15 characters long
     - regex: ^(?=.*\d)
       message: must contain a digit
     - regex: ^(?=.*[a-z])
       message: must contain a lower case letter
     - regex: ^(?=.*[A-Z])
       message: must contain an upper case letter

    """
    required_keys = ['regex']
    allowed_keys = ['regex', 'message']

    @classmethod
    def is_syntax_valid(cls, constraint):
        if not super(RegExConstraint, cls).is_syntax_valid(constraint):
            return False
        return True

    def __init__(self, constraint):
        Constraint.__init__(self, constraint)
        try:
            self.expression = re.compile(constraint['regex'])
        except re.error:
            raise CheckmateValidationException("Constraint has an invalid "
                    "regular expression: %s" % constraint['regex'])
        if 'message' in constraint:
            self.message = constraint['message']

    def test(self, value):
        return self.expression.match(value)


CONSTRAINT_CLASSES = [k for n, k in inspect.getmembers(sys.modules[__name__],
                                                       inspect.isclass)
                      if issubclass(k, Constraint)]
