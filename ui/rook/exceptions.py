"""Custome Exceptions for Checkmate

To be serialization-friendly, call the Exception __init__ with any extra
attributes:

class RookCustomException(Exception):
    def __init__(self, something_custom):
        super(RookCustomException, self).__init__(something_custom)
        self.something_custom = something_custom

This is important to allow exceptioons to flow back from the message queue
tasks.
"""


class RookException(Exception):
    """Rook Error"""
    pass


class RookDatabaseMigrationError(RookException):
    pass


class RookDatabaseConnectionError(RookException):
    """Error connecting to backend database"""
    pass
