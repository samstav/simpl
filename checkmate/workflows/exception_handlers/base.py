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
# pylint: disable=R0903

"""ExceptionHandler Base Class"""

import logging

LOG = logging.getLogger(__name__)


class ExceptionHandlerBase(object):
    """Base Class for Exception Handlers."""

    def __init__(self, workflow, task, context, driver):
        """Initialize a handler for a specific task.

        :param workflow: this is a SpiffWorkflow
        """
        self.workflow = workflow
        self.task = task
        self.context = context
        self.driver = driver

    @staticmethod
    def can_handle(failed_task, exception):
        """Determine if this handler can handle a failed task.

        :param failed_task: the SpiffWorkflow task
        :param exception: the exception causing the task to failed_task
        :returns: True/False
        """
        return False

    def friendly_message(self, exception):
        """Client-viewable message to display while handling failed task."""
        LOG.debug("%s.friendly_message called, but was not implemented",
                  self.__class__.__name__)

    def handle(self):
        """Do the required actions with the failed task.

        :returns: id of a new workflow if one was created.
        """
        LOG.debug("%s.handle called, but was not implemented",
                  self.__class__.__name__)
