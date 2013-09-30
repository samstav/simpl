# pylint: disable=W0212
#
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
import inspect

from celery.exceptions import MaxRetriesExceededError

from checkmate import exceptions

EVAL_LOCALS = dict(inspect.getmembers(exceptions, inspect.isclass))
EVAL_LOCALS['CAN_RETRY'] = exceptions.CAN_RETRY
EVAL_LOCALS['CAN_RESUME'] = exceptions.CAN_RESUME
EVAL_LOCALS['CAN_RESET'] = exceptions.CAN_RESET
EVAL_LOCALS['MaxRetriesExceededError'] = MaxRetriesExceededError
EVAL_LOCALS['Exception'] = Exception
EVAL_GLOBALS = {'nothing': None}


def set_exception(exception, task):
    """Sets an exception info in a task. Used to report errors that occurred
    during workflow run
    @param exception: Exception to set
    @param task: Task
    @return:
    """
    task_state = task._get_internal_attribute("task_state")
    task_state["info"] = repr(exception)
    task._set_internal_attribute(task_state=task_state)


def get_exception(task):
    """Gets the exception info from a task, evals it and returns the result
    @param task: Task
    @return:
    """
    task_state = task._get_internal_attribute("task_state")
    info = task_state.get("info")
    if info:
        return eval(info, EVAL_GLOBALS, EVAL_LOCALS)


def is_failed(task):
    """Checks whether a task has failed by checking the task_state dict in
    internal attribs. The format of task_state is
    task_state: {
        'state': 'FAILURE',
        'traceback': 'Has the stacktrace of the exception',
        'info': 'info about the exception',
    }
    :param task:
    :return:
    """
    task_state = task._get_internal_attribute("task_state")
    return task_state and task_state.get("state") == "FAILURE"
