#!/usr/bin/env python
# pylint: disable=C0302,R0904,C0103,R0903
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

"""Decorator to quickly add statsd (graphite) instrumentation to Celery
task functions.

With some slight modification, this could be used to instrument just
about any (non-celery) function and be made abstract enough to customize
metric names, etc.

Stats reported include number of times the task was accepted by a worker
(`started`), the number of successes, and the number of times the task
raised an exception. In addition, it also reports how long the task took
to complete. Usage:

>>> @task
>>> @instrument_task
>>> def mytask():
>>>     # do stuff
>>>     pass

Please note that the order of decorators is important to Celery. See
http://ask.github.com/celery/userguide/tasks.html#decorating-tasks
for more information.

Uses `simple_decorator` from
http://wiki.python.org/moin/PythonDecoratorLibrary#Property_Definition

Limitation: Does not readily work on subclasses of celery.tasks.Task
because it always reports `task_name` as 'run'
"""
from __future__ import absolute_import
import logging
import time

import statsd

from checkmate.common import config

CONFIG = config.current()
LOG = logging.getLogger(__name__)


def simple_decorator(decorator):
    """Borrowed from:
    http://wiki.python.org/moin/PythonDecoratorLibrary#Property_Definition

    Original docstring:
    This decorator can be used to turn simple functions
    into well-behaved decorators, so long as the decorators
    are fairly simple. If a decorator expects a function and
    returns a function (no descriptors), and if it doesn't
    modify function attributes or docstring, then it is
    eligible to use this. Simply apply @simple_decorator to
    your decorator and it will automatically preserve the
    docstring and function attributes of functions to which
    it is applied.
    """
    def new_decorator(func):
        """Inherit attributes from original method."""
        decorated = decorator(func)
        decorated.__name__ = func.__name__
        decorated.__module__ = func.__module__  # or celery throws a fit
        decorated.__doc__ = func.__doc__
        decorated.__dict__.update(func.__dict__)
        return decorated
    # Now a few lines needed to make simple_decorator itself
    # be a well-behaved decorator.
    new_decorator.__name__ = decorator.__name__
    new_decorator.__doc__ = decorator.__doc__
    new_decorator.__dict__.update(decorator.__dict__)
    return new_decorator


@simple_decorator
def collect(func):
    """Wraps a celery task with statsd collect code."""
    task_name = func.__name__
    stats_ns = func.__module__

    def collect_wrapper(*args, **kwargs):
        """Replacement for decorated function."""
        if not CONFIG.statsd_host:
            start = time.time()
            try:
                return func(*args, **kwargs)
            except Exception:
                raise
            finally:
                end = time.time()
                LOG.debug("%s took %s to run", func.__name__, end - start)

        stats_conn = statsd.connection.Connection(
            host=CONFIG.statsd_host,
            port=CONFIG.statsd_port,
            sample_rate=1
        )

        if kwargs.get('statsd_counter') is None:
            counter = statsd.counter.Counter('%s.status' % stats_ns,
                                             stats_conn)
        else:
            counter = kwargs['statsd_counter']

        counter.increment('%s.started' % task_name)

        if kwargs.get('statsd_timer') is None:
            timer = statsd.timer.Timer('%s.duration' % stats_ns, stats_conn)
        else:
            timer = kwargs['statsd_timer']

        timer.start()

        try:
            ret = func(*args, **kwargs)
        except StandardError:
            counter.increment('%s.exceptions' % task_name)
            raise
        else:
            counter.increment('%s.success' % task_name)
            timer.stop('%s.success' % task_name)
            return ret
        finally:
            try:
                del timer
                del counter
                del stats_conn
            except StandardError:
                pass

    return collect_wrapper
