"""Custome Exceptions for CheckMate

To be serialization-friendly, call the Exception __init__ with any extra
attributes:

class CheckmateCustomException(Exception):
    def __init__(self, something_custom):
        super(CheckmateCustomException, self).__init__(something_custom)
        self.something_custom = something_custom

This is important to allow exceptioons to flow back from the message queue
tasks.
"""


class CheckmateException(Exception):
    """Checkmate Error"""
    pass


class CheckmateDatabaseMigrationError(CheckmateException):
    pass


class CheckmateNoTokenError(CheckmateException):
    """No cloud auth token was available in this session. Try logging on using
    an auth token"""
    pass


class CheckmateNoMapping(CheckmateException):
    """No mapping found between parameter types"""
    pass


class CheckmateCalledProcessError(CheckmateException):
    def __init__(self, returncode, cmd, output=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
        super(CheckmateException, self).__init__(returncode, cmd, output)


class CheckmateServerBuildFailed(CheckmateException):
    pass


class CheckmateValidationException(CheckmateException):
    pass
