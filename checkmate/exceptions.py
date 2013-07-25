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


class CheckmateUserException(CheckmateException):
    '''
    Exception with user friendly messages
    '''
    def __init__(self, error_message, error_type, friendly_message,
                 error_help):
        self.friendly_message = friendly_message
        self.error_help = error_help
        self.error_message = error_message
        self.error_type = error_type
        super(CheckmateUserException, self).__init__(self.error_message,
                                                     self.error_type,
                                                     self.friendly_message,
                                                     self.error_help)


class CheckmateRetriableException(CheckmateUserException):
    '''Retriable Exception.'''
    def __init__(self, error_message, error_type, friendly_message,
                 error_help):
        super(CheckmateRetriableException, self).__init__(error_message,
                                                          error_type,
                                                          friendly_message,
                                                          error_help)


class CheckmateResumableException(CheckmateUserException):
    '''Retriable Exception.'''
    def __init__(self, error_message, error_type, friendly_message,
                 error_help):
        super(CheckmateResumableException, self).__init__(error_message,
                                                          error_type,
                                                          friendly_message,
                                                          error_help)


class CheckmateValidationException(CheckmateException):
    '''Validation Error.'''
    pass


class CheckmateDataIntegrityError(CheckmateException):
    '''Data has failed integrity checks.'''
    pass
