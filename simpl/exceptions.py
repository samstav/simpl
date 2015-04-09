# Copyright (c) 2011-2015 Rackspace US, Inc.
#
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
#


class SimplException(Exception):

    """Base exception for all exceptions raised by the simpl package."""


# TODO(sam): add SimpleConfigException and NoGroupForOption


class SimplGitError(SimplException):

    """Base class for errors from the git module."""


class SimplGitCommandError(SimplGitError):

    def __init__(self, returncode, cmd, output=None, oserror=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
        self.oserror = oserror

    def __str__(self):
        return ("git command '%s' returned non-zero exit status %d and "
                "produced the following output: '%s'"
                % (self.cmd, self.returncode, self.output))


class SimplGitNotRepo(SimplGitError):

    """The directory supplied is not a git repo."""


class SimplCalledProcessError(SimplException):
    """Raised when a process run by execute() returns non-zero.

    The exit status will be stored in the returncode attribute;
    check_output() will also store the output in the output attribute.
    """
    def __init__(self, returncode, cmd, output=None):
        self.returncode = returncode
        self.cmd = cmd
        self.output = output
    def __str__(self):
        return ("Command '%s' returned non-zero exit status %d"
                % (self.cmd, self.returncode))


