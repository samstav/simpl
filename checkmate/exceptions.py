# Copyright (c) 2011-2013 Rackspace Hosting
# All Rights Reserved.
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""Custom Exceptions for Checkmate

To be serialization-friendly, call the Exception __init__ with any extra
attributes:

class CheckmateCustomException(Exception):
    def __init__(self, something_custom):
        super(CheckmateCustomException, self).__init__(something_custom)
        self.something_custom = something_custom

This is important to allow exceptions to flow back from the message queue
tasks.
"""

#Error message constants
BLUEPRINT_ERROR = ("There is a possible problem in the Blueprint provided - "
                   "Please contact support")
UNEXPECTED_ERROR = ("Unable to automtically recover from error - Please "
                    "contact support")

# options
CAN_RESUME = 1
CAN_RETRY = 2
CAN_RESET = 4


class CheckmateException(Exception):
    """Checkmate Error."""

    def __init__(self, message=None, friendly_message=None, options=0):
        """Create Checkmate Exception

        :param friendly_message: a message to bubble up to clients (UI, CLI,
                etc...)
        :param options: ...
        """
        args = ()
        self.message = message
        self.friendly_message = friendly_message
        self.options = options
        if message:
            args = args + (message,)
        if friendly_message:
            args = args + (friendly_message,)
        if options and options != 0:
            args = args + (options,)
        super(CheckmateException, self).__init__(*args)

    @property
    def resumable(self):
        """Detect if exception is resumable."""
        return self.options & CAN_RESUME

    @property
    def retriable(self):
        """Detect if exception is retriable."""
        return self.options & CAN_RETRY

    @property
    def resetable(self):
        """Detect if exception can be retried with a task tree reset."""
        return self.options & CAN_RESET


class CheckmateDatabaseConnectionError(CheckmateException):
    """Error connecting to backend database."""
    pass


class CheckmateNoTokenError(CheckmateException):
    """No cloud auth token.

    Auth token was not available in this session.
    Try logging on using an auth token
    """
    pass


class CheckmateNoMapping(CheckmateException):
    """No mapping found between parameter types."""
    pass


class CheckmateInvalidParameterError(CheckmateException):
    """Parameters provided are not valid, not permitted or incongruous."""
    pass


class CheckmateNoData(CheckmateException):
    """No data found."""
    pass


class CheckmateDoesNotExist(CheckmateException):
    """Object does not exist."""
    pass


class CheckmateBadState(CheckmateException):
    """Object is not in correct state for the requested operation."""
    pass


class CheckmateIndexError(CheckmateException):
    """Checkmate Index Error"""
    pass


class CheckmateCalledProcessError(CheckmateException):
    """Wraps CalledProcessError but supports passing in specific error_info."""
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
    """Error Building Server."""
    pass


class CheckmateValidationException(CheckmateException):
    """Validation Error."""
    pass


class CheckmateDataIntegrityError(CheckmateException):
    """Data has failed integrity checks."""
    pass


class CheckmateHOTTemplateException(CheckmateException):
    """Raise when a HOT template is encountered where a Checkmate blueprint is
    expected.
    """
    pass
