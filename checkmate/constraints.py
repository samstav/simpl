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



class ProtocolsConstraint(Constraint):
    """

    URL Protocols Constraint

    Syntax:

    - protocols: [list]
    - message: optional validation message

    Example:

     constraints:
     - protocols: ['http', 'https']
       message: only http and https URLs are supported

    """
    required_keys = ['protocols']
    allowed_keys = ['protocols', 'message']

    def __init__(self, constraint):
        Constraint.__init__(self, constraint)
        protocols = constraint['protocols']
        if not isinstance(protocols, list):
            raise CheckmateValidationException("Protocols constraint does not "
                    "have a list of protocols supplied: %s" % protocols)
        self.protocols = protocols
        if 'message' in constraint:
            self.message = constraint['message']

    def test(self, value):
        if isinstance(value, dict):
            value = value.get('url')
        if not isinstance(value, basestring):
            return False
        if '://' not in value:
            return False
        protocol = value[0:value.index('://')]
        return protocol in self.protocols


class InConstraint(Constraint):
    """

    Constraint to limit to a list

    Syntax:

    - in: [list]
    - message: optional validation message

    Notes:

    - clients (browsers) can use this to display a drop-down if 'choice' is not
      provided

    Example:

     constraints:
     - in: ['Ubuntu 12.04']
       message: only http and https URLs are supported

    """
    required_keys = ['in']
    allowed_keys = ['in', 'message']

    def __init__(self, constraint):
        Constraint.__init__(self, constraint)
        allowed = constraint['in']
        if not isinstance(allowed, list):
            raise CheckmateValidationException("In constraint does not "
                    "have a list of values supplied: %s" % allowed)
        self.allowed = allowed
        if 'message' in constraint:
            self.message = constraint['message']

    def test(self, value):
        return value in self.allowed


class SimpleComparisonConstraint(Constraint):
    """

    Constraint to for simple comparisons: >, <, >=, <=

    Syntax (one or more of the following):

    - less-than: {value}
    - greater-than: {value}
    - less-than-or-equal-to: {value}
    - less-than-or-equal-to: {value}

    - message: optional validation message

    Note:
    - a default message will be generated automatically but can be overridden
    - you can combine more than one rule in one constraint (split them up for
      clarity or to supply different validation messages)

    Example:

     constraints:
     - less-than: 8
       greater-than: 1
       message: must be between 3 and 7

    """
    required_keys = [
                     'less-than',
                     'greater-than',
                     'less-than-or-equal-to',
                     'greater-than-or-equal-to',
                    ]
    allowed_keys = [
                     'less-than',
                     'greater-than',
                     'less-than-or-equal-to',
                     'greater-than-or-equal-to',
                     'message',
                    ]

    @classmethod
    def is_syntax_valid(cls, constraint):
        if not isinstance(constraint, dict):
            return False
        if not all(k in cls.allowed_keys for k in constraint.keys()):
            return False

        # We use 'any' here instead of 'all'. We don't call the superclass

        if not any(k in constraint.keys() for k in cls.required_keys):
            return False
        return True

    def __init__(self, constraint):
        Constraint.__init__(self, constraint)

        comparisons = {
                'less-than': lambda x, y: x < y,
                'greater-than': lambda x, y: x > y,
                'less-than-or-equal-to': lambda x, y: x <= y,
                'greater-than-or-equal-to': lambda x, y: x >= y,
            }

        rules = []
        message = None
        for k, v in constraint.items():
            if k == 'less-than':
                rules.append(lambda x: x < v)
                message = "must be less than %s" % v
            elif k == 'less-than-or-equal-to':
                rules.append(lambda x: x <= v)
                message = "must be less than or equal to %s" % v
            elif k == 'greater-than':
                rules.append(lambda x: x > v)
                message = "must be greater than %s" % v
            elif k == 'greater-than-or-equal-to':
                rules.append(lambda x: x >= v)
                message = "must be greater than or equal to %s" % v
        self.rules = rules

        if 'message' in constraint:
            self.message = constraint['message']
        elif message:
            self.message = message

    def test(self, value):
        return all(rule(value) for rule in self.rules)


CONSTRAINT_CLASSES = [k for n, k in inspect.getmembers(sys.modules[__name__],
                                                       inspect.isclass)
                      if issubclass(k, Constraint)]
