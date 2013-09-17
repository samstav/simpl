# pylint: disable=W0212
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

"""Task Class and Helper Functions"""

# pylint: disable=W0611

from checkmate.exceptions import CheckmateException


def set_exception(exception, task):
    """Sets an exception info in a task. Used to report errors that occurred
    during workflow run
    @param exception: Exception to set
    @param task: Task
    @return:
    """
    task_state = task._get_internal_attribute("task_state")
    task_state["info"] = exception.__repr__()
    task._set_internal_attribute(task_state=task_state)


def get_exception(task):
    """Gets the exception info from a task, evals it and returns the result
    @param task: Task
    @return:
    """
    task_state = task._get_internal_attribute("task_state")
    info = task_state["info"]
    return eval(info)


def is_failed(task):
    '''Checks whether a task has failed by checking the task_state dict in
    internal attribs. The format of task_state is
    task_state: {
        'state': 'FAILURE',
        'traceback': 'Has the stacktrace of the exception',
        'info': 'info about the exception',
    }
    :param task:
    :return:
    '''
    task_state = task._get_internal_attribute("task_state")
    return task_state and task_state.get("state") == "FAILURE"
