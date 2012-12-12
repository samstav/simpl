"""Custome Exceptions for Checkmate

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
    """Error switching databases"""
    pass


class CheckmateDatabaseConnectionError(CheckmateException):
    """Error connecting to backend database"""
    pass


class CheckmateNoTokenError(CheckmateException):
    """No cloud auth token was available in this session. Try logging on using
    an auth token"""
    pass


class CheckmateNoMapping(CheckmateException):
    """No mapping found between parameter types"""
    pass


class CheckmateNoData(CheckmateException):
    """No data found"""
    pass


class CheckmateDoesNotExist(CheckmateException):
    """Object does not exist"""
    pass


class CheckmateBadState(CheckmateException):
    """Object is not in correct state for the requested operation"""
    pass


class CheckmateIndexError(CheckmateException):
    """Checkmate Index Error"""
    pass


class CheckmateCalledProcessError(CheckmateException):
    """Wraps CalledProcessError but supports passing in specific error_info"""
    def __init__(self, returncode, cmd, output=None, error_info=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
        self.error_info = error_info
        super(CheckmateException, self).__init__(returncode, cmd, output)

    def __repr__(self):
        if self.error_info:
            return self.error_info
        else:
            return super(CheckmateException, self).__repr__()

    def __str__(self):
        if self.error_info:
            return self.error_info
        else:
            return super(CheckmateException, self).__str__()


class CheckmateServerBuildFailed(CheckmateException):
    """Error Building Server"""
    pass


class CheckmateValidationException(CheckmateException):
    """Validation Error"""
    pass
