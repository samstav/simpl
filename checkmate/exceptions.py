'''Custom Exceptions for Checkmate

To be serialization-friendly, call the Exception __init__ with any extra
attributes:

class CheckmateCustomException(Exception):
    def __init__(self, something_custom):
        super(CheckmateCustomException, self).__init__(something_custom)
        self.something_custom = something_custom

This is important to allow exceptions to flow back from the message queue
tasks.
'''


class CheckmateException(Exception):
    '''Checkmate Error.'''
    pass


class CheckmateDatabaseConnectionError(CheckmateException):
    '''Error connecting to backend database.'''
    pass


class CheckmateNoTokenError(CheckmateException):
    '''No cloud auth token.

    Auth token was not available in this session.
    Try logging on using an auth token
    '''
    pass


class CheckmateNoMapping(CheckmateException):
    '''No mapping found between parameter types.'''
    pass


class CheckmateInvalidParameterError(CheckmateException):
    '''Parameters provided are not valid, not permitted or incongruous.'''
    pass


class CheckmateNoData(CheckmateException):
    '''No data found.'''
    pass


class CheckmateDoesNotExist(CheckmateException):
    '''Object does not exist.'''
    pass


class CheckmateBadState(CheckmateException):
    '''Object is not in correct state for the requested operation.'''
    pass


class CheckmateIndexError(CheckmateException):
    '''Checkmate Index Error'''
    pass


class CheckmateCalledProcessError(CheckmateException):
    '''Wraps CalledProcessError but supports passing in specific error_info.'''
    def __init__(self, returncode, cmd, output=None, error_info=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
        self.message = ("Call %s failed with return code %s: %s" %
                        (self.cmd,
                         self.returncode,
                         self.output or '(No output)'))
        self.error_info = error_info
        super(CheckmateCalledProcessError, self).__init__(
            returncode, cmd, output)

    def __repr__(self):
        if self.error_info:
            return self.error_info
        else:
            return super(CheckmateCalledProcessError, self).__repr__()

    def __str__(self):
        if self.error_info:
            return self.error_info
        else:
            return super(CheckmateCalledProcessError, self).__str__()


class CheckmateServerBuildFailed(CheckmateException):
    '''Error Building Server.'''
    pass


class CheckmateRetriableException(CheckmateException):
    '''Retriable Exception.'''

    def __init__(self, message, error_help, error_type, action_required=False):
        self.error_help = error_help
        self.message = message
        self.error_type = error_type
        self.action_required = action_required
        super(CheckmateRetriableException, self).__init__(
            message, error_help, error_type, action_required)


class CheckmateResumableException(CheckmateException):
    '''Retriable Exception.'''

    def __init__(self, message, error_help, error_type, action_required=False):
        self.error_help = error_help
        self.message = message
        self.error_type = error_type
        self.action_required = action_required
        super(CheckmateResumableException, self).__init__(
            message, error_help, error_type, action_required)


class CheckmateValidationException(CheckmateException):
    '''Validation Error.'''
    pass


class CheckmateDataIntegrityError(CheckmateException):
    '''Data has failed integrity checks.'''
    pass
