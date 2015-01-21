# Copyright (c) 2011-2015 Rackspace US, Inc.
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

"""Custom Exceptions for Checkmate.

To be serialization-friendly, call the Exception __init__ with any extra
attributes:

class CheckmateCustomException(Exception):
    def __init__(self, something_custom):
        super(CheckmateCustomException, self).__init__(something_custom)
        self.something_custom = something_custom

This is important to allow exceptions to flow back from the message queue
tasks.
"""

import logging

#Error message constants
BLUEPRINT_ERROR = "There is a possible problem in the Blueprint provided."
UNEXPECTED_ERROR = "Unable to automatically recover from error."

# options
CAN_RESUME = 1  # just run the workflow again (ex. to get new token)
CAN_RETRY = 2   # try the task again (ex. external API was down)
CAN_RESET = 4   # clean up and try again (ex. delete ERROR'ed server and retry)

LOG = logging.getLogger(__name__)


class CheckmateException(Exception):

    """Checkmate Error.

    Base for all Checkmate server errors
    """

    def __init__(self, message=None, friendly_message=None, options=0,
                 http_status=None):
        """Create Checkmate Exception.

        :param friendly_message: a message to bubble up to clients (UI, CLI,
                etc...). This defaults to UNEXPECTED_ERROR
        :param options: receives flags from the code raising the error about
                how the error can be handled. ALlowed flags are:
                exceptions.CAN_RESUME
                exceptions.CAN_RETRY
                exceptions.CAN_RESET
        :param http_status: supplied if a specific HTTP status should be used
                for this exception. The format is code + title.

                    Ex.  '404 Not Found'
        """
        args = ()
        self._message = message
        self._friendly_message = friendly_message
        self.options = options
        self.http_status = http_status
        args = (message, friendly_message, options, http_status)
        super(CheckmateException, self).__init__(*args)

    @property
    def message(self):
        """Read only property for _message."""
        if self._message is None:
            return self.__doc__.split('\n')[0]
        else:
            return str(self._message)

    @property
    def friendly_message(self):
        """Return a friendly message always."""
        return self._friendly_message or UNEXPECTED_ERROR

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

    def __str__(self):
        return self.message


class CheckmateDatabaseConnectionError(CheckmateException):

    """Error connecting to backend database."""


class CheckmateNoTokenError(CheckmateException):

    """No cloud auth token.

    Auth token was not available in this session.
    Try logging on using an auth token
    """

    @property
    def friendly_message(self):
        """Return a friendly message always."""
        return self._friendly_message or self._message or UNEXPECTED_ERROR


class CheckmateNoMapping(CheckmateException):

    """No mapping found between parameter types."""

    @property
    def friendly_message(self):
        """Return a friendly message always."""
        return self._friendly_message or self._message or UNEXPECTED_ERROR


class CheckmateInvalidParameterError(CheckmateException):

    """Parameters provided are not valid, not permitted or incongruous."""

    @property
    def friendly_message(self):
        """Return a friendly message always."""
        return self._friendly_message or self._message or UNEXPECTED_ERROR


class CheckmateNoData(CheckmateException):

    """No data found."""


class CheckmateDoesNotExist(CheckmateException):

    """Object does not exist."""

    @property
    def friendly_message(self):
        """Return a friendly message always."""
        return self._friendly_message or self._message or UNEXPECTED_ERROR


class CheckmateBadState(CheckmateException):

    """Object is not in correct state for the requested operation."""

    @property
    def friendly_message(self):
        """Return a friendly message always."""
        return self._friendly_message or self._message or UNEXPECTED_ERROR


class CheckmateIndexError(CheckmateException):

    """Checkmate Index Error."""


class CheckmateCalledProcessError(CheckmateException):

    """Wrap CalledProcessError but support passing in specific error_info."""

    def __init__(self, returncode, cmd, output=None, error_info=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
        self._message = ("Call %s failed with return code %s: %s" %
                        (self.cmd,
                         self.returncode,
                         self.output or '(No output)'))
        self.error_info = error_info
        super(CheckmateCalledProcessError, self).__init__(
            message=self._message,
            friendly_message=UNEXPECTED_ERROR)

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


class CheckmateValidationException(CheckmateException):

    """Validation Error."""

    @property
    def friendly_message(self):
        """Return a friendly message always."""
        return self._friendly_message or self._message or UNEXPECTED_ERROR


class CheckmateDataIntegrityError(CheckmateException):

    """Data has failed integrity checks."""


class CheckmateHOTTemplateException(CheckmateException):

    """A HOT template was encountered where a Checkmate blueprint was expected.
    """
